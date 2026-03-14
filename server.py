import asyncio
import zmq
import zmq.asyncio
import sys
import time
import arcade
from sprites import ENEMY_TYPES
import math

# Windows fix για να λειτουργεί το asyncio με τον κατάλληλο event loop σε Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TILE_SCALING = 1.0                      # Scale Πλακιδίων

tile_map = arcade.load_tilemap(
    "assets/maps/firstRegion.tmx",      # Φόρτωση χάρτη από το tiled
    scaling=TILE_SCALING,
    use_spatial_hash=True               # Το collision γίνεται μόνο με κοντινά αντικείμενα (βελτίωση απόδοσης)
)

wall_list = tile_map.sprite_lists["Walls"]  # Παίρνουμε το walls layer του tiled για να βάλουμε collision μόνο σε αυτά

# Διαστάσεις χάρτη σε pixels
MAP_WIDTH  = tile_map.width * tile_map.tile_width
MAP_HEIGHT = tile_map.height * tile_map.tile_height

# Διαστάσεις παίκτη
PLAYER_WIDTH  = 32
PLAYER_HEIGHT = 48

SPEED = 5             # Ταχύτητα κίνησης του παίκτη

STUCK_THRESHOLD = 1.0     # seconds χωρίς ουσιαστική κίνηση -> θεωρείται stuck
UNSTUCK_DURATION = 0.8    # seconds που θα κάνει πλάγια κίνηση για να ξεκολλήσει
MIN_PROGRESS_PX = 0.6     # κάτω από αυτό θεωρείται "δεν κουνήθηκε"

server_start_time = time.time() # Χρόνος παιχνιδιού

ctx = zmq.asyncio.Context()     # Δημιουργία του zmq context για τη σύνδεση με τα sockets

# Movement input (PULL): Δημιουργία socket για να λαμβάνει τα inputs από τους παίκτες
pull_socket = ctx.socket(zmq.PULL)
pull_socket.bind("tcp://*:5555")    # Ακούμε στις εισερχόμενες συνδέσεις στην θύρα 5555

# Broadcast state (PUB): Δημιουργία socket για να στέλνει την κατάσταση του παιχνιδιού στους πελάτες
pub_socket = ctx.socket(zmq.PUB)
pub_socket.bind("tcp://*:5556")     # Ακούμε για να στείλουμε κατάσταση στους πελάτες στη θύρα 5556

# Control socket (REQ/REP): Δημιουργία socket για σύνδεση/αποσύνδεση με τους πελάτες (request-response)
control_socket = ctx.socket(zmq.REP)
control_socket.bind("tcp://*:5557") # Ακούμε για αιτήματα σύνδεσης και αποσύνδεσης στη θύρα 5557

# Player data: Λεξικό που περιέχει τα δεδομένα των παικτών
players = {}          # pid → {x, y} (πληροφορίες για την θέση κάθε παίκτη)
enemies = {}

connected = set()     # Σύνολο παικτών σε σειρά σύνδεσης

spawn_points = []     # Λίστα για το spawn παικτών
enemy_spawns = []     # Λίστα για το spawn εχθρών
next_spawn_index = 0

object_layer = tile_map.object_lists.get("Object")  # Παίρνουμε το object layer για το spawn 

if not object_layer:
    raise RuntimeError("No Object layer found in TMX map")

for obj in object_layer:
    if obj.name == "player_spawn":  # Για κάθε object με το όνομα player_spawn (έτσι έχει ονομαστεί στο tiled), προσθέτουμε το σημείο στη λίστα
        x, y = obj.shape
        spawn_points.append((x, y))
    
    elif obj.name and obj.name.startswith("orc"):
        x, y = obj.shape
        enemy_spawns.append((obj.name, x, y))

if not spawn_points:
    raise RuntimeError("No player_spawn objects found in Object layer")

print("Spawn points loaded from TMX:", spawn_points)
print("Enemy spawns:", enemy_spawns)

# init enemies from tiled spawns
for (name, x, y) in enemy_spawns:

    etype = name   # Όνομα εχθρού
    defs = ENEMY_TYPES[etype]

    enemies[name] = {

        # identity
        "type": etype,

        # position
        "x": x,
        "y": y,
        "spawn_x": x,
        "spawn_y": y,

        # state
        "state": "idle",
        "dir": "down",
        "dead": False,
        "hurt_seq": 0,

        # combat stats
        "hp": defs["hp_max"],
        "hp_max": defs["hp_max"],
        "damage": defs["damage"],
        "resist": defs["resist"],
        "attack_speed": defs["attack_speed"],
        "move_speed": defs["move_speed"],

        # hitbox
        "hitbox_w": defs["hitbox_w"],
        "hitbox_h": defs["hitbox_h"],

        # AI ranges
        "aggro_radius": defs["aggro_radius"],
        "lose_radius": defs["lose_radius"],
        "attack_range": defs["attack_range"],

        # attack timing
        "windup": defs["windup"],
        "attack_cooldown": 1.0 / defs["attack_speed"],
        "next_attack_time": 0.0,
        "pending_hit_time": 0.0,

        # targeting
        "target": None,

        "last_x": x,
        "last_y": y,
        "stuck_time": 0.0,
        "unstuck_until": 0.0,
        "unstuck_side": 1,
    }

TICK_DT = 0.02      # Η διάρκεια κάθε "tick" σε δευτερόλεπτα (ρυθμίζει το frame rate)
tick = 0            # Μετρητής "tick" για το παιχνίδι

# Μέθοδος για το state των παικτών
async def handle_control():
    global next_spawn_index
    while True:
        msg = await control_socket.recv_json()  # Περιμένει και λαμβάνει τα μηνύματα ελέγχου
        pid = msg["id"]     # Το id του παίκτη
        typ = msg["type"]   # Τύπος αιτήματος (σύνδεση ή αποσύνδεση)

        if typ == "connect":
            nickname = msg.get("nickname") or pid

            if pid in connected:
                await control_socket.send_json({"status": "ok"})
                continue

            # Προσθήκη του παίκτη στo σύνολο των συνδεδεμένων
            connected.add(pid)

            # Spawn place
            spawn_index = next_spawn_index
            next_spawn_index += 1

            x, y = spawn_points[spawn_index % len(spawn_points)]

            # Πληροφορίες παίκτη
            players[pid] = {
                "x": x,         # Θέση
                "y": y, 
                "nickname": nickname,   # Ψευδώνυμο
                "level": 1,     

                # Combat 
                "hp": 1.0,      
                "hp_cur": 100,
                "hp_max": 100, 
                "energy": 1.0,   
                "resist": 0,

                # State
                "state": "idle",
                "dir": "down",
                "dead": False,
                "hurt_seq": 0,

                # Attack
                "attack_requested": False,
                "attack_dir": "down",
                "attack_cooldown": 0.45,
                "next_attack_time": 0.0,
                "damage": 35,

                "move_dir": "STOP",
                }   

            print(f"Player {nickname} CONNECTED at spawn {spawn_index}")

            await control_socket.send_json({
                "status": "ok",
            })

        # Αποσύνδεση παίκτη
        elif typ == "disconnect":
            name = players.get(pid, {}).get("nickname", pid)
            print(f"Player {name} DISCONNECTED")

            connected.discard(pid)
            players.pop(pid, None)

            await control_socket.send_json({"status": "ok"})

# Μέθοδος για το collision
def collides_with_walls_aabb(x, y, w, h):
    left   = x - w / 2
    right  = x + w / 2
    bottom = y - h / 2
    top    = y + h / 2

    for wall in wall_list:
        if right > wall.left and left < wall.right and top > wall.bottom and bottom < wall.top:
            return True
    return False

def player_hits_walls(x, y):
    return collides_with_walls_aabb(x, y, PLAYER_WIDTH, PLAYER_HEIGHT)

def enemy_hits_walls(e, x, y):
    return collides_with_walls_aabb(x, y, e["hitbox_w"], e["hitbox_h"])

def try_move_enemy(e, vx, vy):
    """
    Προσπαθεί να μετακινήσει enemy κατά (vx, vy) με axis-separated collision.
    Επιστρέφει True αν κινήθηκε έστω λίγο.
    """
    moved = False
    ex, ey = e["x"], e["y"]

    # X axis
    nx = ex + vx

    # clamp X
    w = e["hitbox_w"]; h = e["hitbox_h"]
    nx = max(w/2, min(nx, MAP_WIDTH - w/2))

    if not enemy_hits_walls(e, nx, ey):
        e["x"] = nx
        moved = moved or (abs(vx) > 1e-6)

    # Y axis
    ny = ey + vy

    # clamp Y
    ny = max(h/2, min(ny, MAP_HEIGHT - h/2))

    if not enemy_hits_walls(e, e["x"], ny):
        e["y"] = ny
        moved = moved or (abs(vy) > 1e-6)

    return moved

def aabb_overlap(ax, ay, aw, ah, bx, by, bw, bh):
    return (abs(ax - bx) * 2 < (aw + bw)) and (abs(ay - by) * 2 < (ah + bh))

def resolve_player_enemy_blocking(prev_players, prev_enemies):
    """
    Blocking collision:
    Αν player και enemy overlap -> revert ΚΑΙ οι δύο στις προηγούμενες θέσεις τους.
    Κανείς δεν σπρώχνει κανέναν.
    """
    for pid, p in players.items():
        px0, py0 = prev_players.get(pid, (p["x"], p["y"]))

        for eid, e in enemies.items():
            if e.get("dead"):
                continue

            ex0, ey0 = prev_enemies.get(eid, (e["x"], e["y"]))

            if aabb_overlap(
                p["x"], p["y"], PLAYER_WIDTH, PLAYER_HEIGHT,
                e["x"], e["y"], e["hitbox_w"], e["hitbox_h"]
            ):
                # revert BOTH
                p["x"], p["y"] = px0, py0
                e["x"], e["y"] = ex0, ey0

def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)

def dir_from_delta(dx, dy):
    if abs(dx) > abs(dy):
        return "right" if dx > 0 else "left"
    else:
        return "up" if dy > 0 else "down"

def move_towards_enemy(e, tx, ty):
    ex, ey = e["x"], e["y"]
    dx = tx - ex
    dy = ty - ey
    d = math.hypot(dx, dy)
    if d < 0.001:
        return

    nx = dx / d
    ny = dy / d

    speed = e["move_speed"]  # px per tick

    now = time.time()

    # Αν είμαστε σε unstuck mode, κινήσου ΠΛΑΓΙΑ (perpendicular) αντί για ευθεία
    if now < e.get("unstuck_until", 0.0):
        side = e.get("unstuck_side", 1)  # 1 ή -1
        # perpendicular vector: ( -ny, nx ) ή ( ny, -nx )
        px = -ny * side
        py =  nx * side

        try_move_enemy(e, px * speed, py * speed)
        e["dir"] = dir_from_delta(px, py)
        return

    # Κανονική κίνηση: δοκιμάζει 3 επιλογές (ευθεία -> μόνο X -> μόνο Y)
    moved = False

    # 1) full vector
    moved = try_move_enemy(e, nx * speed, ny * speed)

    # 2) αν δεν μπόρεσε, προσπάθησε μόνο X
    if not moved:
        moved = try_move_enemy(e, nx * speed, 0)

    # 3) αν δεν μπόρεσε, προσπάθησε μόνο Y
    if not moved:
        moved = try_move_enemy(e, 0, ny * speed)

    # direction για animation
    e["dir"] = dir_from_delta(dx, dy)

def choose_unstuck_side_towards_target(e, tx, ty):
    """
    Διαλέγει unstuck_side = 1 ή -1 με βάση ποια πλευρική κίνηση (perpendicular)
    φέρνει το enemy πιο κοντά στον στόχο (tx, ty), με σεβασμό σε walls+clamp.
    """
    ex0, ey0 = e["x"], e["y"]
    dx = tx - ex0
    dy = ty - ey0
    d = math.hypot(dx, dy)
    if d < 1e-6:
        return 1

    nx = dx / d
    ny = dy / d
    speed = e["move_speed"]

    # δοκιμάζουμε τα 2 perpendicular:
    # side=1 => (-ny, nx)
    # side=-1 => (ny, -nx)

    # --- simulate side=1 ---
    tmp1 = {"x": ex0, "y": ey0, "hitbox_w": e["hitbox_w"], "hitbox_h": e["hitbox_h"]}
    tmp1.update(e)  # για να έχει ό,τι χρειάζεται enemy_hits_walls
    x1, y1 = ex0, ey0
    try_move_enemy(tmp1, (-ny) * speed, (nx) * speed)
    x1, y1 = tmp1["x"], tmp1["y"]
    d1 = math.hypot(tx - x1, ty - y1)

    # --- simulate side=-1 ---
    tmp2 = {"x": ex0, "y": ey0, "hitbox_w": e["hitbox_w"], "hitbox_h": e["hitbox_h"]}
    tmp2.update(e)
    try_move_enemy(tmp2, (ny) * speed, (-nx) * speed)
    x2, y2 = tmp2["x"], tmp2["y"]
    d2 = math.hypot(tx - x2, ty - y2)

    # διάλεξε την πλευρά που μειώνει περισσότερο την απόσταση
    return 1 if d1 <= d2 else -1

def update_enemy_ai_and_movement():
    for eid, e in enemies.items():
        if e.get("dead"):
            continue

        # find nearest player
        nearest_pid = None
        nearest_d = 1e9
        for pid, p in players.items():
            if p.get("dead", False):
                continue

            d = dist(e["x"], e["y"], p["x"], p["y"])
            if d < nearest_d:
                nearest_d = d
                nearest_pid = pid

        # acquire target
        if e["target"] is None:
            if nearest_pid is not None and nearest_d <= e["aggro_radius"]:
                e["target"] = nearest_pid

        # lose target
        if e["target"] is not None:
            tp = players.get(e["target"])
            if tp is None or tp.get("dead", False):
                e["target"] = None
            else:
                d = dist(e["x"], e["y"], tp["x"], tp["y"])
                if d > e["lose_radius"]:
                    e["target"] = None

        # act
        if e["target"] is not None:
            tp = players[e["target"]]
            d = dist(e["x"], e["y"], tp["x"], tp["y"])

            if d <= e["attack_range"]:
                e["state"] = "attack"
                e["dir"] = dir_from_delta(tp["x"] - e["x"], tp["y"] - e["y"])
                e["unstuck_until"] = 0.0    # reset
            else:
                e["state"] = "walk"
                move_towards_enemy(e, tp["x"], tp["y"])
        else:
            # return to spawn
            sx, sy = e["spawn_x"], e["spawn_y"]
            d = dist(e["x"], e["y"], sx, sy)
            if d <= 2.0:
                e["state"] = "idle"
                e["unstuck_until"] = 0.0    # reset
            else:
                e["state"] = "walk"
                move_towards_enemy(e, sx, sy)

        # --- anti-stuck detector ---
        lx = e.get("last_x", e["x"])
        ly = e.get("last_y", e["y"])

        moved_dist = math.hypot(e["x"] - lx, e["y"] - ly)

        if moved_dist < MIN_PROGRESS_PX and e["state"] == "walk":
            e["stuck_time"] = e.get("stuck_time", 0.0) + TICK_DT
        else:
            e["stuck_time"] = 0.0

        e["last_x"] = e["x"]
        e["last_y"] = e["y"]

        # Αν stuck για 1s -> μπες σε unstuck mode
        if e["stuck_time"] >= STUCK_THRESHOLD:
            e["stuck_time"] = 0.0
            e["unstuck_until"] = time.time() + UNSTUCK_DURATION

            # στόχος: player αν υπάρχει, αλλιώς spawn
            if e.get("target") is not None and e["target"] in players:
                tx = players[e["target"]]["x"]
                ty = players[e["target"]]["y"]
            else:
                tx = e["spawn_x"]
                ty = e["spawn_y"]

            # διάλεξε πλευρά που ΠΛΗΣΙΑΖΕΙ τον στόχο (όχι random/hash)
            e["unstuck_side"] = choose_unstuck_side_towards_target(e, tx, ty)

def apply_enemy_attacks():
    now = time.time()

    for eid, e in enemies.items():
        if e.get("dead") or e["target"] is None:
            continue

        if e["state"] != "attack":
            # αν βγήκε από attack state, καθάρισε pending
            e["pending_hit_time"] = 0.0
            continue

        tp = players.get(e["target"])
        if tp is None or tp.get("dead", False):
            e["target"] = None
            e["pending_hit_time"] = 0.0
            continue

        # αν δεν είναι πια σε range, cancel
        d = dist(e["x"], e["y"], tp["x"], tp["y"])
        if d > e["attack_range"]:
            e["pending_hit_time"] = 0.0
            continue

        # cooldown check
        if now < e["next_attack_time"]:
            continue

        # αν δεν έχει ξεκινήσει αυτό το attack, όρισε hit time
        if e["pending_hit_time"] <= 0.0:
            e["pending_hit_time"] = now + e["windup"]
            # κλείδωσε cooldown από τώρα (ώστε να μη spam-άρει starts)
            e["next_attack_time"] = now + e["attack_cooldown"]
            continue

        # αν ήρθε η ώρα για hit
        if now >= e["pending_hit_time"]:
            e["pending_hit_time"] = 0.0

            # τελικό check ότι είναι ακόμα κοντά
            d2 = dist(e["x"], e["y"], tp["x"], tp["y"])
            if d2 <= e["attack_range"]:
                # player resist για τώρα 0 αν δεν έχεις
                player_resist = tp.get("resist", 0)
                dmg = max(0, e["damage"] - player_resist)

                # Εσύ έχεις hp 0..1 τώρα. Για combat καλύτερα να πας σε real hp,
                # αλλά προσωρινά μπορούμε να το μεταφράσουμε:
                # π.χ. αν player έχει max 100:
                player_hp_max = tp.get("hp_max", 100)
                # αν tp["hp"] είναι normalized, φτιάξε current:
                hp_cur = tp.get("hp_cur", tp["hp"] * player_hp_max)

                hp_cur -= dmg
                if hp_cur < 0:
                    hp_cur = 0

                tp["hp_cur"] = hp_cur
                tp["hp_max"] = player_hp_max
                tp["hp"] = hp_cur / player_hp_max

                if hp_cur <= 0:
                    tp["dead"] = True
                    tp["state"] = "death"
                else:
                    tp["hurt_seq"] = tp.get("hurt_seq", 0) + 1

def apply_player_attacks():
    now = time.time()

    for pid, p in players.items():
        if p.get("dead", False):
            continue

        if not p.get("attack_requested", False):
            continue

        p["attack_requested"] = False

        if now < p.get("next_attack_time", 0.0):
            continue

        p["next_attack_time"] = now + p.get("attack_cooldown", 0.45)

        attack_dir = p.get("attack_dir", "down")
        px = p["x"]
        py = p["y"]

        attack_range = 70

        target_eid = None
        best_dist = 999999

        for eid, e in enemies.items():
            if e.get("dead", False):
                continue

            dx = e["x"] - px
            dy = e["y"] - py

            # directional filter
            if attack_dir == "up" and dy <= 0:
                continue
            if attack_dir == "down" and dy >= 0:
                continue
            if attack_dir == "left" and dx >= 0:
                continue
            if attack_dir == "right" and dx <= 0:
                continue

            d = dist(px, py, e["x"], e["y"])
            if d > attack_range:
                continue

            if d < best_dist:
                best_dist = d
                target_eid = eid

        if target_eid is None:
            continue

        e = enemies[target_eid]

        dmg = max(0, p.get("damage", 35) - e.get("resist", 0))
        e["hp"] -= dmg

        if e["hp"] <= 0:
            e["hp"] = 0
            e["dead"] = True
            e["state"] = "death"
        else:
            e["hurt_seq"] = e.get("hurt_seq", 0) + 1

# Μέθοδος για τα inputs
async def handle_inputs():
    while True:
        msg = await pull_socket.recv_json()
        pid = msg["id"]

        if pid not in players:
            continue

        # movement
        if "move" in msg:
            direction = msg.get("move", "STOP")

            if direction not in ("UP", "DOWN", "LEFT", "RIGHT", "STOP"):
                direction = "STOP"

            if not players[pid].get("dead", False):
                players[pid]["move_dir"] = direction

        # attack
        if msg.get("attack"):
            if players[pid].get("dead", False):
                continue

            adir = msg.get("dir", "DOWN")
            if adir not in ("UP", "DOWN", "LEFT", "RIGHT"):
                adir = "DOWN"

            players[pid]["attack_requested"] = True
            players[pid]["attack_dir"] = adir.lower()    

# Μέθοδος για τη μετάδοση κατάστασης παιχνιδιού
async def broadcast_state():
    while True:
        global tick
        tick += 1       # Αύξηση του tick για κάθε frame

        elapsed_time = time.time() - server_start_time

        prev_players = {pid: (p["x"], p["y"]) for pid, p in players.items()}
        prev_enemies = {eid: (e["x"], e["y"]) for eid, e in enemies.items()}

        for pid, p in players.items():
            if p.get("dead", False):
                p["move_dir"] = "STOP"
                continue

            direction = p.get("move_dir", "STOP")

            # Κίνηση του παίκτη με βάση την εισερχόμενη εντολή
            new_x = p["x"]
            new_y = p["y"]

            # Εφαρμογή κίνησης με βάση την εντολή που έστειλε ο client
            if direction == "UP":
                new_y += SPEED
            elif direction == "DOWN":
                new_y -= SPEED
            elif direction == "LEFT":
                new_x -= SPEED
            elif direction == "RIGHT":
                new_x += SPEED

            # Περιορισμός της νέας θέσης ώστε ο παίκτης να μην βγει εκτός των ορίων του χάρτη
            new_x = max(PLAYER_WIDTH / 2, min(new_x, MAP_WIDTH - PLAYER_WIDTH / 2))
            new_y = max(PLAYER_HEIGHT / 2, min(new_y, MAP_HEIGHT - PLAYER_HEIGHT / 2))

            # Έλεγχος collision
            if not player_hits_walls(new_x, p["y"]):
                p["x"] = new_x

            if not player_hits_walls(p["x"], new_y):
                p["y"] = new_y

            # visual state/direction
            if not p.get("dead", False):
                if direction == "UP":
                    p["dir"] = "up"
                    p["state"] = "walk"
                elif direction == "DOWN":
                    p["dir"] = "down"
                    p["state"] = "walk"
                elif direction == "LEFT":
                    p["dir"] = "left"
                    p["state"] = "walk"
                elif direction == "RIGHT":
                    p["dir"] = "right"
                    p["state"] = "walk"
                else:
                    p["state"] = "idle"

        # 1) enemy AI + movement
        update_enemy_ai_and_movement()

        # 2) collisions between entities (ώστε να μην περνάνε μέσα)
        resolve_player_enemy_blocking(prev_players, prev_enemies)

        # 3) enemy attacks (damage to players)
        apply_enemy_attacks()

        apply_player_attacks()

        # Στέλνει την κατάσταση του παιχνιδιού σε όλους τους πελάτες
        await pub_socket.send_json({
            "tick": tick,
            "tick_dt": TICK_DT,             # Διάρκεια κάθε "tick"
            "players": dict(players),             # Κατάσταση των παικτών
            "enemies": dict(enemies),
            "elapsed_time": elapsed_time    # Χρόνος που έχει περάσει από την έναρξη
        })

        await asyncio.sleep(TICK_DT)  # 50 FPS, ρυθμός ανανέωσης 20ms

async def main():
    await asyncio.gather(
        handle_control(),       # Επεξεργασία αιτημάτων σύνδεσης/αποσύνδεσης
        handle_inputs(),        # Επεξεργασία των κινήσεων των παικτών
        broadcast_state()       # Μετάδοση της κατάστασης του παιχνιδιού
    )

if __name__ == "__main__":
    asyncio.run(main())