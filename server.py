import asyncio
import zmq
import zmq.asyncio
import sys
import time
from sprites import get_enemy_type_defs, get_player_type_defs
from stats import (XP_REQUIREMENTS, is_dragon_type, is_dragon_damageable_state, get_dragon_runtime_defaults)
from dragon_enemy import (update_dragon, find_nearest_player_in_region, player_is_behind_dragon, direction_from_dragon_to_player)
import math
from region import Region

# Windows fix για να λειτουργεί το asyncio με τον κατάλληλο event loop σε Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TILE_SCALING = 1.0                      # Scale Πλακιδίων

regions = {
    "firstRegion": Region("firstRegion", "assets/maps/firstRegion.tmx", TILE_SCALING),
    "secondRegion": Region("secondRegion", "assets/maps/secondRegion.tmx", TILE_SCALING),
    "thirdRegion": Region("thirdRegion", "assets/maps/thirdRegion.tmx", TILE_SCALING),
    "fourthRegion": Region("fourthRegion", "assets/maps/fourthRegion.tmx", TILE_SCALING),
}

START_REGION = "firstRegion"

# Διαστάσεις παίκτη
PLAYER_WIDTH  = 32
PLAYER_HEIGHT = 48

SPEED = 5             # Ταχύτητα κίνησης του παίκτη

# Ρυθμίσεις για ανίχνευση "κολλήματος" εχθρού:
# αν δεν έχει ουσιαστική μετακίνηση για κάποιο χρόνο, θεωρείται stuck
STUCK_THRESHOLD = 1.0     # δευτερόλεπτα χωρίς ουσιαστική πρόοδο
UNSTUCK_DURATION = 0.8    # διάρκεια κίνησης για ξεκόλλημα
MIN_PROGRESS_PX = 0.6     # ελάχιστη μετακίνηση σε pixels ώστε να θεωρηθεί πρόοδος

PLAYER_ANIM_FRAME_TIME = 0.12

PLAYER_ATTACK_ANIM_FRAMES = {
    "Warrior": {
        "attack": 6,
        "walk_attack": 6,
    },
    "Mage": {
        "attack": 5,
        "walk_attack": 5,
    },
    "Marksman": {
        "attack": 8,
        "walk_attack": 8,
    },
}

server_start_time = time.time() # Χρόνος εκκίνησης server

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

next_spawn_index = 0  # Δείκτης για κυκλική επιλογή επόμενου spawn point παίκτη

# Φόρτωση εχθρών από το spawn του tiled
for region_name, region in regions.items():
    for (enemy_id, enemy_type, x, y) in region.enemy_spawns:

        defs = get_enemy_type_defs(enemy_type)

        enemy_data = {
            # Περιοχή εχθρού
            "region": region_name,

            # Είδος εχθρού
            "type": enemy_type,

            # Τρέχουσα θέση και αρχική θέση spawn
            "x": x,
            "y": y,
            "spawn_x": x,
            "spawn_y": y,

            # Κατάσταση animation / συμπεριφοράς
            "state": "idle",
            "dir": "right" if is_dragon_type(enemy_type) else "down",
            "dead": False,
            "hurt_seq": 0,

            # Στατιστικά μάχης
            "hp": defs["hp_max"],
            "hp_max": defs["hp_max"],
            "damage": defs["damage"],
            "resist": defs["resist"],
            "attack_speed": defs["attack_speed"],
            "move_speed": defs["move_speed"],
            "attack_type": defs.get("attack_type", "melee"),
            "special": defs.get("special"),

            "tier": defs.get("tier", 1),
            "xp_reward": defs.get("xp_reward", 40 * defs.get("tier", 1)),

            # Διαστάσεις hitbox
            "hitbox_w": defs["hitbox_w"],
            "hitbox_h": defs["hitbox_h"],

            # Αποστάσεις συμπεριφοράς εχθρού
            "aggro_radius": defs["aggro_radius"],   # απόσταση εντοπισμού παίκτη
            "lose_radius": defs["lose_radius"],     # απόσταση εγκατάλειψης στόχου
            "attack_range": defs["attack_range"],   # απόσταση επίθεσης

            # Χρονισμός επιθέσεων
            "windup": defs["windup"],
            "attack_cooldown": 1.0 / defs["attack_speed"],
            "next_attack_time": 0.0,
            "pending_hit_time": 0.0,
            "attack_seq": 0,

            # Τρέχων στόχος και μεταβλητές για stuck handling
            "target": None,

            "last_x": x,
            "last_y": y,
            "stuck_time": 0.0,
            "unstuck_until": 0.0,
            "unstuck_side": 1,
        }

        if is_dragon_type(enemy_type):
            enemy_data.update(get_dragon_runtime_defaults(defs, x, y, time.time()))

        enemies[enemy_id] = enemy_data

TICK_DT = 0.02      # Η διάρκεια κάθε "tick" σε δευτερόλεπτα (ρυθμίζει το frame rate ~50 updates/sec)
tick = 0            # Μετρητής "tick" για το παιχνίδι

def get_region(region_name: str) -> Region:
    return regions[region_name]

def rect_contains_point(rect, x, y):
    return (
        rect["x"] <= x <= rect["x"] + rect["width"] and
        rect["y"] <= y <= rect["y"] + rect["height"]
    )

def try_player_transition(player):
    current_region = get_region(player["region"])

    for tr in current_region.transitions:
        if rect_contains_point(tr, player["x"], player["y"]):
            target_region_name = tr["target_map"]
            target_spawn_name = tr["target_spawn"]

            if target_region_name not in regions:
                print(f"Unknown target region: {target_region_name}")
                return

            target_region = get_region(target_region_name)
            spawn_pos = target_region.get_named_spawn(target_spawn_name)

            if spawn_pos is None:
                print(f"Spawn '{target_spawn_name}' not found in region '{target_region_name}'")
                return

            player["region"] = target_region_name
            player["x"], player["y"] = spawn_pos

            print(f"Player {player['nickname']} transitioned to {target_region_name} at spawn {target_spawn_name}")
            return
        
def get_player_attack_anim_duration(class_name, attack_state):
    frames_by_state = PLAYER_ATTACK_ANIM_FRAMES.get(class_name)

    if frames_by_state is None:
        return 0.60

    frames = frames_by_state.get(attack_state, frames_by_state.get("attack", 5))

    return frames * PLAYER_ANIM_FRAME_TIME

# Μέθοδος που ελέγχει αν ο παίκτης ή ο εχθρός βρίσκεται πάνω σε γέφυρα
def on_bridge(region_name, x, y, w, h):
    region = get_region(region_name)
    bridge_list = region.bridge_list

    if not bridge_list:
        return False

    # Υπολογισμός ορίων του hitbox με βάση το κέντρο (x, y)
    left   = x - w / 2
    right  = x + w / 2
    bottom = y - h / 2
    top    = y + h / 2

    # Έλεγχος overlap με κάθε bridge sprite
    for bridge in bridge_list:
        if right > bridge.left and left < bridge.right and top > bridge.bottom and bottom < bridge.top:
            return True
        
    return False

# Μέθοδος για το collision
# Ελέγχει collision με τοίχους χρησιμοποιώντας ορθογώνιο hitbox (AABB)
def collides_with_walls_aabb(region_name, x, y, w, h):
    region = get_region(region_name)
    wall_list = region.wall_list
    river_list = region.river_list
    lava_list = region.lava_list
    bridge_wall_list = region.bridge_wall_list

    # Αν ο παίκτης ή ο εχθρός είναι πάνω στη γέφυρα, αγνοούμε το collision από walls
    if on_bridge(region_name, x, y, w, h):
        return False

    # Υπολογισμός ορίων AABB (Axis-Aligned Bounding Box)
    left   = x - w / 2
    right  = x + w / 2
    bottom = y - h / 2
    top    = y + h / 2

    # Έλεγχος overlap με κάθε wall sprite
    for wall in wall_list:
        if right > wall.left and left < wall.right and top > wall.bottom and bottom < wall.top:
            return True
        
    # Collision με water
    for river in river_list:
        if right > river.left and left < river.right and top > river.bottom and bottom < river.top:
            return True
        
    if lava_list:
        for lava in lava_list:
            if right > lava.left and left < lava.right and top > lava.bottom and bottom < lava.top:
                return True
        
    for bridge_wall in bridge_wall_list:
        if right > bridge_wall.left and left < bridge_wall.right and top > bridge_wall.bottom and bottom < bridge_wall.top:
            return True
    return False

# Μέθοδος για τον έλεγχο collision του παίκτη με τις σταθερές διαστάσεις του
def player_hits_walls(player, x, y):
    return collides_with_walls_aabb(player["region"], x, y, PLAYER_WIDTH, PLAYER_HEIGHT)

# Μέθοδος για τον έλεγχο collision του εχθρού με βάση το δικό του hitbox
def enemy_hits_walls(e, x, y):
    return collides_with_walls_aabb(e["region"], x, y, e["hitbox_w"], e["hitbox_h"])

# Μέθοδος κίνησης εχθρού ξεχωριστά στους άξονες X, Y για καλύτερο έλεγχο collision και πιο ομαλή κίνηση
def move_enemy(e, delta_x, delta_y):
    moved = False
    current_x, current_y = e["x"], e["y"]

    region = get_region(e["region"])
    map_width = region.map_width
    map_height = region.map_height

    # Κίνηση στον άξονα X
    new_x = current_x + delta_x

    # Περιορισμός στον άξονα Χ ώστε να μείνει μέσα στα όρια του χάρτη
    w = e["hitbox_w"]
    h = e["hitbox_h"]
    new_x = max(w/2, min(new_x, map_width - w/2))

    # Αν δεν υπάρχει collision, εφαρμόζουμε τη νέα θέση στον άξονα Χ
    if not enemy_hits_walls(e, new_x, current_y):
        e["x"] = new_x
        moved = moved or (abs(delta_x) > 1e-6)

    # Κίνηση στον άξονα Y
    new_y = current_y + delta_y

    # Περιορισμός στον άξονα Y ώστε να μείνει μέσα στα όρια του χάρτη
    new_y = max(h/2, min(new_y, map_height - h/2))

    # Αν δεν υπάρχει collision, εφαρμόζουμε τη νέα θέση στον άξονα Y
    if not enemy_hits_walls(e, e["x"], new_y):
        e["y"] = new_y
        moved = moved or (abs(delta_y) > 1e-6)

    return moved

# Μέθοδος που ελέγχει αν δύο ορθογώνια επικαλύπτονται, ώστε να ανιχνευθεί σύγκρουση
def aabb_overlap(ax, ay, aw, ah, bx, by, bw, bh):
    # Ελέγχει αν τα κέντρα των δύο ορθογωνίων είναι αρκετά κοντά ώστε τα hitbox τους να επικαλύπτονται σε X και Y
    return (abs(ax - bx) * 2 < (aw + bw)) and (abs(ay - by) * 2 < (ah + bh))

# Μέθοδος για την αποφυγή του "σπρωξίματος" μεταξύ παίκτη και εχθρού (δεν κινεί ο ένας τον άλλο)
# Αν παίκτης και εχθρός επικαλυφθούν τότε και οι δύο επιστρέφουν στις προηγούμενες θέσεις τους
def player_enemy_blocking(prev_players, prev_enemies):
    # Διατρέχουμε όλους τους παίκτες
    for pid, p in players.items():
        # Παίρνουμε την προηγούμενη θέση του παίκτη πριν εφαρμοστεί η κίνηση αυτού του tick, αν δεν υπάρχει προηγούμενη θέση χρησιμοποιούμε την τρέχουσα
        prev_player_x, prev_player_y = prev_players.get(pid, (p["x"], p["y"]))

        for eid, e in enemies.items():  # Για κάθε παίκτη ελέγχουμε όλους τους εχθρούς
            if e.get("dead"):           # Αγνοούμε εχθρούς που έχουν πεθάνει
                continue

            if p["region"] != e["region"]:  # Αγνοούμε συγκρούσεις όταν παίκτης και εχθρός βρίσκονται σε διαφορετική περιοχή
                continue

            # Παίρνουμε την προηγούμενη θέση του εχθρού, ώστε αν υπάρξει overlap να επιστρέψει πίσω και να μη σπρώξει τον παίκτη
            prev_enemy_x, prev_enemy_y = prev_enemies.get(eid, (e["x"], e["y"]))

            # Δεν χρησιμοποιούμε ολόκληρο το hitbox του enemy για blocking, αλλά ένα μικρότερο blocking hitbox
            # Για τον dragon χρησιμοποιούμε μεγαλύτερο ποσοστό, γιατί είναι boss με μεγάλο σώμα και θέλουμε να μπλοκάρει πιο σταθερά τον παίκτη
            if e.get("special") == "dragon":
                enemy_block_w = e["hitbox_w"] * 0.90
                enemy_block_h = e["hitbox_h"] * 0.80
            else:
                enemy_block_w = e["hitbox_w"] * 0.65
                enemy_block_h = e["hitbox_h"] * 0.65

            # Χρησιμοποιούμε μικρότερο blocking hitbox και για τον player, ώστε να μην μπλοκάρει υπερβολικά από μικρές επαφές στα άκρα του sprite
            player_block_w = PLAYER_WIDTH * 0.75
            player_block_h = PLAYER_HEIGHT * 0.75

            # Αν δεν υπάρχει overlap, δεν κάνουμε τίποτα
            if not aabb_overlap(
                p["x"], p["y"], player_block_w, player_block_h,
                e["x"], e["y"], enemy_block_w, enemy_block_h
            ):
                continue

            # Υπάρχει overlap, οπότε διορθώνουμε πρώτα ανά άξονα, ώστε ο παίκτης να μη γυρίζει πάντα πλήρως στην προηγούμενη θέση

            # Δοκιμάζουμε αν με το παλιό Y συνεχίζει το overlap, άρα φταίει το νέο X
            overlap_with_old_y = aabb_overlap(
                p["x"], prev_player_y, player_block_w, player_block_h,
                e["x"], e["y"], enemy_block_w, enemy_block_h
            )

            # Δοκιμάζουμε αν με το παλιό X συνεχίζει το overlap, άρα φταίει το νέο Y
            overlap_with_old_x = aabb_overlap(
                prev_player_x, p["y"], player_block_w, player_block_h,
                e["x"], e["y"], enemy_block_w, enemy_block_h
            )

            if overlap_with_old_y:      # Αν με το παλιό Y συνεχίζει να υπάρχει overlap, τότε διορθώνουμε τον X άξονα γυρίζοντας το X του παίκτη πίσω
                p["x"] = prev_player_x

            if overlap_with_old_x:      # Αν με το παλιό X συνεχίζει να υπάρχει overlap, τότε διορθώνουμε τον Y άξονα γυρίζοντας το Y του παίκτη πίσω
                p["y"] = prev_player_y

            # Αν και τα δύο ακόμα κάνουν overlap, τότε γυρνάμε και τα δύο
            if aabb_overlap(
                p["x"], p["y"], player_block_w, player_block_h,
                e["x"], e["y"], enemy_block_w, enemy_block_h
            ):
                p["x"], p["y"] = prev_player_x, prev_player_y

            # Enemy πίσω στην προηγούμενη θέση του, για να μη σπρώχνει τον παίκτη
            e["x"], e["y"] = prev_enemy_x, prev_enemy_y

# Μέθοδος που υπολογίζει την ευκλείδεια απόσταση μεταξύ δύο σημείων
def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)

# Μέθοδος που μετατρέπει ένα διάνυσμα (dx, dy) σε κατεύθυνση για animation / state
def dir_from_delta(dx, dy):
    if abs(dx) > abs(dy):
        return "right" if dx > 0 else "left"
    else:
        return "up" if dy > 0 else "down"
    
def target_in_directional_range(e, p):
    # Υπολογίζουμε τη θέση του παίκτη ως προς τον εχθρό
    dx = p["x"] - e["x"]
    dy = p["y"] - e["y"]

    direction = e.get("dir", "down")            # Η κατεύθυνση στην οποία κοιτάει ο εχθρός
    attack_range = e.get("attack_range", 64)    # Η μέγιστη απόσταση που μπορεί να φτάσει η επίθεση

    lane_half_width = 28    # Το projectile χτυπάει σε μία γραμμή μπροστά από τον εχθρό

    # Υπολογισμός κατεύθυνσης για το projectile
    if direction == "right":
        return dx > 0 and dx <= attack_range and abs(dy) <= lane_half_width

    if direction == "left":
        return dx < 0 and abs(dx) <= attack_range and abs(dy) <= lane_half_width

    if direction == "up":
        return dy > 0 and dy <= attack_range and abs(dx) <= lane_half_width

    if direction == "down":
        return dy < 0 and abs(dy) <= attack_range and abs(dx) <= lane_half_width

    return False

# Μέθοδος που υπολογίζει την κατεύθυνση του εχθρού προς τον στόχο και καλεί τη μέθοδο κίνησης
def move_enemy_towards_target(e, target_x, target_y):
    current_x, current_y = e["x"], e["y"]
    dx = target_x - current_x
    dy = target_y - current_y

    # Ευκλείδεια απόσταση
    d = dist(current_x, current_y, target_x, target_y)

    # Αν η απόσταση είναι σχεδόν μηδενική, σταματάει η κίνηση
    if d < 0.001:
        return

    # Κανονικοποιημένο διάνυσμα κατεύθυνσης προς τον στόχο
    dir_x = dx / d
    dir_y = dy / d

    # Ταχύτητα enemy σε pixels ανά tick
    speed = e["move_speed"] 

    now = time.time()

    # Αν ο εχθρός είναι σε unstuck mode, κινείται πλάγια αντί για ευθεία προς τον στόχο
    if now < e.get("unstuck_until", 0.0):
        side = e.get("unstuck_side", 1)

        # Κάθετο διάνυσμα στην κατεύθυνση προς τον στόχο
        px = -dir_y * side
        py =  dir_x * side

        move_enemy(e, px * speed, py * speed)
        e["dir"] = dir_from_delta(px, py)
        return

    # Κίνηση: δοκιμάζει 3 επιλογές (ευθεία, μόνο άξονα X, μόνο άξονα Y)
    moved = False

    # Προσπάθεια πλήρους διαγώνιας / ευθείας κίνησης
    moved = move_enemy(e, dir_x * speed, dir_y * speed)

    # Αν απέτυχε, δοκιμή μόνο στον άξονα X
    if not moved:
        moved = move_enemy(e, dir_x * speed, 0)

    # Αν απέτυχε και πάλι, δοκιμή μόνο στον άξονα Y
    if not moved:
        moved = move_enemy(e, 0, dir_y * speed)

    # Ενημέρωση direction για animation
    e["dir"] = dir_from_delta(dx, dy)

# Επιλέγει ποια πλάγια κατεύθυνση unstuck (1 ή -1) φέρνει τον εχθρό πιο κοντά στον στόχο
def choose_unstuck_side_towards_target(e, target_x, target_y):
    current_x, current_y = e["x"], e["y"]
    dx = target_x - current_x
    dy = target_y - current_y

    # Ευκλείδεια απόσταση
    d = dist(current_x, current_y, target_x, target_y)

    # Αν εχθρός και στόχος είναι σχεδόν στο ίδιο σημείο, κρατάμε την προεπιλεγμένη τιμή
    if d < 1e-6:
        return 1

    # Κανονικοποιημένο διάνυσμα προς τον στόχο
    dir_x = dx / d
    dir_y = dy / d
    speed = e["move_speed"]

    # Δοκιμή πλάγιας κίνησης με πλευρά 1
    # Δημιουργούμε ένα προσωρινό αντίγραφο του εχθρού, ώστε να ελέγξουμε πού θα κατέληγε αν κινούνταν προς τη μία κάθετη κατεύθυνση
    tmp1 = {"x": current_x, "y": current_y, "hitbox_w": e["hitbox_w"], "hitbox_h": e["hitbox_h"]}
    tmp1.update(e)  # Αντιγράφουμε και τα υπόλοιπα στοιχεία που χρειάζονται για collision / movement

    # Δοκιμαστική μετακίνηση στην πρώτη πλάγια κατεύθυνση
    move_enemy(tmp1, (-dir_y) * speed, (dir_x) * speed)

    # Παίρνουμε τη νέα δοκιμαστική θέση
    x1, y1 = tmp1["x"], tmp1["y"]

    # Υπολογίζουμε την απόσταση από τον στόχο μετά από αυτή τη δοκιμή
    d1 = dist(target_x, target_y, x1, y1)

    # Δοκιμή πλάγιας κίνησης με πλευρά -1
    # Δημιουργούμε δεύτερο προσωρινό αντίγραφο του εχθρού, ώστε να ελέγξουμε την αντίθετη κάθετη κατεύθυνση
    tmp2 = {"x": current_x, "y": current_y, "hitbox_w": e["hitbox_w"], "hitbox_h": e["hitbox_h"]}
    tmp2.update(e)

    # Δοκιμαστική μετακίνηση στη δεύτερη πλάγια κατεύθυνση
    move_enemy(tmp2, (dir_y) * speed, (-dir_x) * speed)

    # Παίρνουμε τη νέα δοκιμαστική θέση
    x2, y2 = tmp2["x"], tmp2["y"]

    # Υπολογίζουμε την απόσταση από τον στόχο μετά από αυτή τη δοκιμή
    d2 = dist(target_x, target_y, x2, y2)

    # Επιλέγουμε την πλευρά που μικραίνει περισσότερο την απόσταση από τον στόχο
    return 1 if d1 <= d2 else -1

# Μέθοδος που ενημερώνει τη συμπεριφορά και την κίνηση όλων των εχθρών
def update_enemy_chase_and_movement():
    for e in enemies.values():
        # Παραλείπουμε νεκρούς εχθρούς
        if e.get("dead"):
            continue

        # Αν ο εχθρός είναι dragon, δεν ακολουθεί το απλό chase/attack σύστημα των υπόλοιπων εχθρών
        if e.get("special") == "dragon":
            update_dragon(e, players, dist, move_enemy, collides_with_walls_aabb)
            continue

        # Εύρεση κοντινότερου ζωντανού παίκτη
        nearest_pid, nearest_player, nearest_d = find_nearest_player_in_region(e, players, dist)

        # Αν υπάρχει κοντινότερος παίκτης μέσα στο aggro radius, ο εχθρός μπορεί να αλλάξει focus σε αυτόν
        if nearest_pid is not None and nearest_d <= e["aggro_radius"]:
            current_target = e.get("target")

            if current_target is None:      # Αν ο εχθρός δεν έχει στόχο, στοχεύει τον κοντινότερο παίκτη
                e["target"] = nearest_pid

            elif current_target in players:     # Αν ο εχθρός έχει ήδη στόχο, τότε συγκρίνουμε τον τωρινό στόχο με τον νέο κοντινότερο παίκτη
                current_player = players[current_target]

                if (    # Αν ο τωρινός στόχος πέθανε ή άλλαξε περιοχή, ο εχθρός αλλάζει στόχο στον κοντινότερο διαθέσιμο παίκτη
                    current_player.get("dead", False)
                    or current_player.get("region") != e["region"]
                ):
                    e["target"] = nearest_pid
                    e["pending_hit_time"] = 0.0

                else:
                    current_d = dist(e["x"], e["y"], current_player["x"], current_player["y"])   # Υπολογίζουμε την απόσταση του εχθρού από τον τωρινό στόχο

                    # Τιμή όριο για να μην γίνεται αλλαγή στόχων συνεχώς σε πολύ κοντινές αποστάσεις
                    switch_margin = 20

                     # Αν ο κοντινότερος παίκτης δεν είναι ο τωρινός στόχος και ο στόχος είναι πιο μακριά, τότε ο εχθρός αλλάζει focus στον κοντινότερο
                    if nearest_pid != current_target and nearest_d + switch_margin < current_d:
                        e["target"] = nearest_pid
                        e["pending_hit_time"] = 0.0

        # Απώλεια στόχου
        if e["target"] is not None:
            tp = players.get(e["target"])

            # Αν ο στόχος δεν υπάρχει πια ή είναι νεκρός, τον αφήνει
            if tp is None or tp.get("dead", False) or tp.get("region") != e["region"]:
                e["target"] = None
            else:
                d = dist(e["x"], e["y"], tp["x"], tp["y"])

                # Αν ο στόχος απομακρύνθηκε πολύ, σταματά το κυνήγι
                if d > e["lose_radius"]:
                    e["target"] = None

        # Συμπεριφορά εχθρού
        if e["target"] is not None:
            tp = players[e["target"]]
            d = dist(e["x"], e["y"], tp["x"], tp["y"])

            # Αν ο στόχος είναι εντός attack range, ο εχθρός επιτίθεται
            attack_type = e.get("attack_type", "melee")

            if attack_type == "ranged":
                e["dir"] = dir_from_delta(tp["x"] - e["x"], tp["y"] - e["y"])

                # Ο ranged enemy επιτίθεται μόνο αν ο στόχος είναι στη σωστή ευθεία/lane.
                if target_in_directional_range(e, tp):
                    e["state"] = "attack"
                    e["unstuck_until"] = 0.0
                else:
                    e["state"] = "walk"
                    move_enemy_towards_target(e, tp["x"], tp["y"])

            else:
                if d <= e["attack_range"]:
                    e["state"] = "attack"
                    e["dir"] = dir_from_delta(tp["x"] - e["x"], tp["y"] - e["y"])
                    e["unstuck_until"] = 0.0    # Επαναφορά unstuck mode
                
                # Αλλιώς κινείται προς τον στόχο
                else:
                    e["state"] = "walk"
                    move_enemy_towards_target(e, tp["x"], tp["y"])
        else:
             # Αν δεν υπάρχει στόχος, ο εχθρός επιστρέφει στο αρχικό spawn point
            sx, sy = e["spawn_x"], e["spawn_y"]
            d = dist(e["x"], e["y"], sx, sy)

            # Αν έφτασε κοντά στο spawn, μένει σε idle state
            if d <= 2.0:
                e["state"] = "idle"
                e["unstuck_until"] = 0.0    # Επαναφορά unstuck mode
            else:
                e["state"] = "walk"
                move_enemy_towards_target(e, sx, sy)

        # Έλεγχος αν ο εχθρός έχει κολλήσει
        lx = e.get("last_x", e["x"])
        ly = e.get("last_y", e["y"])

        # Υπολογισμός πραγματικής μετακίνησης από το προηγούμενο tick
        moved_dist = dist(e["x"], e["y"], lx, ly)

        # Αν κινείται ("walk state") αλλά δεν προχωρά αρκετά, μετράμε stuck time
        if moved_dist < MIN_PROGRESS_PX and e["state"] == "walk":
            e["stuck_time"] = e.get("stuck_time", 0.0) + TICK_DT
        else:
            e["stuck_time"] = 0.0

        # Αποθήκευση τρέχουσας θέσης για το επόμενο tick
        e["last_x"] = e["x"]
        e["last_y"] = e["y"]

        # Αν μείνει stuck για αρκετό χρόνο, ενεργοποιούμε unstuck mode
        if e["stuck_time"] >= STUCK_THRESHOLD:
            e["stuck_time"] = 0.0
            e["unstuck_until"] = time.time() + UNSTUCK_DURATION

            # Αν έχει target, ξεκολλάει προς εκείνον
            if e.get("target") is not None and e["target"] in players:
                tx = players[e["target"]]["x"]
                ty = players[e["target"]]["y"]
            
            # Αλλιώς ξεκολλάει προς το spawn point του
            else:
                tx = e["spawn_x"]
                ty = e["spawn_y"]

            # Επιλέγουμε την πλάγια κατεύθυνση που τον φέρνει πιο κοντά στον στόχο
            e["unstuck_side"] = choose_unstuck_side_towards_target(e, tx, ty)

# Μέθοδος που εφαρμόζει τις επιθέσεις των εχθρών στους παίκτες
def apply_enemy_attacks():
    now = time.time()

    for e in enemies.values():
        if e.get("special") == "dragon":
            continue

        # Αγνοούμε νεκρούς εχθρούς ή εχθρούς χωρίς στόχο
        if e.get("dead") or e["target"] is None:
            continue

        # Αν ο εχθρός δεν είναι πλέον σε attack state, ακυρώνουμε τυχόν pending hit
        if e["state"] != "attack":
            e["pending_hit_time"] = 0.0
            continue

        tp = players.get(e["target"])

        # Αν ο στόχος δεν υπάρχει ή πέθανε ή είναι σε διαφορετική περιοχή, καθαρίζουμε στόχο και pending attack
        if tp is None or tp.get("dead", False) or tp.get("region") != e["region"]:
            e["target"] = None
            e["pending_hit_time"] = 0.0
            continue

        # Αν ο παίκτης βγήκε εκτός range, ακυρώνεται το attack
        d = dist(e["x"], e["y"], tp["x"], tp["y"])
        if d > e["attack_range"]:
            e["pending_hit_time"] = 0.0
            continue

        # Έλεγχος επαναφόρτισης (cooldown)
        if now < e["next_attack_time"]:
            continue

        # Αν ξεκινά τώρα το attack, ορίζουμε πότε θα γίνει το πραγματικό hit
        if e["pending_hit_time"] <= 0.0:
            e["pending_hit_time"] = now + e["windup"]

            # Κάθε φορά που ξεκινάει νέο attack, αυξάνουμε το attack_seq και ο client καταλαβαίνει ότι πρέπει να ξαναπαίξει το attack animation από την αρχή
            e["attack_seq"] = e.get("attack_seq", 0) + 1

            # Το cooldown ξεκινάει από τώρα για να μην ξεκινά πολλές επιθέσεις μαζί
            e["next_attack_time"] = now + e["attack_cooldown"]
            continue

        # Αν ήρθε η στιγμή του hit
        if now >= e["pending_hit_time"]:
            e["pending_hit_time"] = 0.0

            # Τελικός έλεγχος ότι ο παίκτης είναι ακόμα έγκυρος στόχος
            attack_type = e.get("attack_type", "melee")

            if attack_type == "ranged":
                can_hit = target_in_directional_range(e, tp)
            else:
                d2 = dist(e["x"], e["y"], tp["x"], tp["y"])
                can_hit = d2 <= e["attack_range"]

            if can_hit:
                # Υπολογισμός τελικής ζημιάς μετά το resist του παίκτη
                player_resist = tp.get("resist", 0)
                dmg = max(0, e["damage"] - player_resist)

                # Το hp αποθηκεύεται και ως normalized (0..1) και ως τρέχον hp
                player_hp_max = tp.get("hp_max", 100)
                hp_cur = tp.get("hp_cur", tp["hp"] * player_hp_max)

                # Εφαρμογή damage
                hp_cur -= dmg
                if hp_cur < 0:
                    hp_cur = 0

                # Ενημέρωση τιμών ζωής
                tp["hp_cur"] = hp_cur
                tp["hp_max"] = player_hp_max
                tp["hp"] = hp_cur / player_hp_max

                # Αν ο παίκτης πέθανε, αλλάζουμε state
                if hp_cur <= 0:
                    tp["dead"] = True
                    tp["state"] = "death"
                else:
                    # Διαφορετικά αυξάνουμε hurt sequence για animation
                    # Θέλουμε νέο animation όταν τελειώσει το προηγούμενο και όχι ενδιάμεσα να γίνεται reset
                    tp["hurt_seq"] = tp.get("hurt_seq", 0) + 1

def enemy_in_player_directional_range(p, e, attack_defs):
    dx = e["x"] - p["x"]
    dy = e["y"] - p["y"]

    direction = p.get("attack_dir", p.get("dir", "down"))
    attack_range = attack_defs.get("range", 70)
    lane_half_width = attack_defs.get("lane_half_width", 36)

    if direction == "right":
        return dx > 0 and dx <= attack_range and abs(dy) <= lane_half_width

    if direction == "left":
        return dx < 0 and abs(dx) <= attack_range and abs(dy) <= lane_half_width

    if direction == "up":
        return dy > 0 and dy <= attack_range and abs(dx) <= lane_half_width

    if direction == "down":
        return dy < 0 and abs(dy) <= attack_range and abs(dx) <= lane_half_width

    return False

def get_xp_next_for_level(level):
    return XP_REQUIREMENTS.get(level, 0)


def gain_player_xp(p, amount):
    if p.get("level", 1) >= p.get("max_level", 10):
        p["level"] = p.get("max_level", 10)
        p["xp"] = 0
        p["xp_next"] = 0
        return

    p["xp"] = p.get("xp", 0) + amount

    while p["level"] < p["max_level"] and p["xp"] >= p["xp_next"]:
        p["xp"] -= p["xp_next"]
        p["level"] += 1

        # Level up stat scaling
        p["hp_max"] += 15
        p["hp_cur"] = p["hp_max"]
        p["hp"] = 1.0
        p["damage"] += 4
        p["resist"] += 1

        p["xp_next"] = get_xp_next_for_level(p["level"])

    if p["level"] >= p["max_level"]:
        p["level"] = p["max_level"]
        p["xp"] = 0
        p["xp_next"] = 0

# Μέθοδος που εφαρμόζει τις επιθέσεις των παικτών πάνω στους εχθρούς
def apply_player_attacks():
    now = time.time()

    for p in players.values():
        # Αγνοούμε νεκρούς παίκτες
        if p.get("dead", False):
            continue

        # Αν ο παίκτης δεν πάτησε πλήκτρο για επίθεση, πάμε στον επόμενο
        if not p.get("attack_requested", False):
            continue

        p["attack_requested"] = False   # Θέτουμε το αίτημα επίθεσης σε false μετά την επίθεση

        # Έλεγχος επαναφόρτισης (cooldown)
        if now < p.get("next_attack_time", 0.0):
            continue

        # Παίρνουμε την κλάση του παίκτη για να βρούμε τα αντίστοιχα attack stats
        class_name = p.get("class_name", "Warrior") 

        try:
            class_defs = get_player_type_defs(class_name)
        except ValueError:
            class_defs = get_player_type_defs("Warrior")

        # Παίρνουμε το attack που ζητήθηκε (basic, skill1, skill2)
        attack_id = p.get("attack_id", "basic")
        attacks = class_defs.get("attacks", {})

        if attack_id not in attacks:    # Αν για κάποιο λόγο το attack δεν υπάρχει, χρησιμοποιούμε το basic
            attack_id = "basic"

        attack_defs = attacks[attack_id]

        # Έλεγχος αν ο παίκτης έχει ξεκλειδώσει το συγκεκριμένο attack με βάση το level του
        required_level = attack_defs.get("unlock_level", 1)
        if p.get("level", 1) < required_level:
            continue

        # Ορίζουμε το επόμενο χρονικό σημείο στο οποίο ο παίκτης θα μπορεί να ξαναεπιτεθεί
        cooldown = attack_defs.get("cooldown", 0.45)
        p["next_attack_time"] = now + cooldown

        # Παίρνουμε τον τύπο και την απόσταση της επίθεσης
        attack_type = attack_defs.get("attack_type", class_defs.get("attack_type", "melee"))
        attack_range = attack_defs.get("range", 70)

        px = p["x"]
        py = p["y"]

        # Θα επιλεγεί ο κοντινότερος enemy που είναι μπροστά από τον παίκτη
        target_eid = None
        best_dist = 999999

        for eid, e in enemies.items():
            # Αγνοούμε νεκρούς εχθρούς
            if e.get("dead", False):
                continue

            if e["region"] != p["region"]:      # Ο παίκτης μπορεί να χτυπήσει μόνο εχθρούς που βρίσκονται στην ίδια περιοχή
                continue

            d = dist(px, py, e["x"], e["y"])    # Υπολογίζουμε την απόσταση παίκτη-εχθρού

            if d > attack_range:                # Αν ο εχθρός είναι πιο μακριά από το range της επίθεσης, δεν μπορεί να χτυπηθεί
                continue

            if attack_type == "ranged":         # Για ranged επιθέσεις ελέγχουμε αν ο εχθρός βρίσκεται στη σωστή ευθεία
                if not enemy_in_player_directional_range(p, e, attack_defs):
                    continue

            else:   # Για melee επιθέσεις ελέγχουμε απλά αν ο εχθρός βρίσκεται μπροστά από τον παίκτη
                attack_dir = p.get("attack_dir", "down")
                dx = e["x"] - px
                dy = e["y"] - py

                if attack_dir == "up" and dy <= 0:      # Αν ο παίκτης χτυπάει προς τα πάνω, ο εχθρός πρέπει να είναι πάνω του
                    continue
                if attack_dir == "down" and dy >= 0:    # Αν ο παίκτης χτυπάει προς τα κάτω, ο εχθρός πρέπει να είναι κάτω του
                    continue
                if attack_dir == "left" and dx >= 0:    # Αν ο παίκτης χτυπάει αριστερά, ο εχθρός πρέπει να είναι αριστερά του
                    continue
                if attack_dir == "right" and dx <= 0:   # Αν ο παίκτης χτυπάει δεξιά, ο εχθρός πρέπει να είναι δεξιά του
                    continue

            # Επιλέγουμε τον κοντινότερο έγκυρο στόχο
            if d < best_dist:
                best_dist = d
                target_eid = eid

        # Αν δεν βρέθηκε στόχος, δεν γίνεται hit
        if target_eid is None:
            continue

        e = enemies[target_eid]     # Παίρνουμε τον εχθρό που επιλέχθηκε ως στόχος

        # Αν είναι dragon και είναι σε state που δεν χτυπιέται, αγνοούμε το hit
        if e.get("special") == "dragon":
            if not is_dragon_damageable_state(e.get("state", "idle")):
                continue

            # Μετράμε hits στο ground phase, για να χρησιμοποιηθούν αργότερα στο rise
            e["hits_taken_ground"] = e.get("hits_taken_ground", 0) + 1

            # Αν ο player τον χτύπησε από πίσω, ο dragon θα γυρίσει και θα κάνει attack
            if player_is_behind_dragon(p, e):
                e["last_back_hit_time"] = now
                e["last_back_hit_by"] = p.get("nickname", "")
                e["last_back_hit_dir"] = direction_from_dragon_to_player(e, p)

        base_damage = p.get("damage", class_defs.get("damage", 25)) # Υπολογισμός βασικής ζημιάς του παίκτη
        multiplier = attack_defs.get("damage_multiplier", 1.0)      # Πολλαπλασιαστής ζημιάς ανάλογα με το attack που χρησιμοποιήθηκε

        # Υπολογισμός damage μετά το resist του εχθρού
        dmg = int(base_damage * multiplier)
        dmg = max(0, dmg - e.get("resist", 0))

        e["hp"] -= dmg  # Εφαρμόζουμε τη ζημιά στον εχθρό

        # Αν ο enemy πεθάνει
        if e["hp"] <= 0:
            e["hp"] = 0
            e["dead"] = True
            e["state"] = "death"

            # Ο παίκτης παίρνει XP όταν σκοτώνει τον εχθρό
            xp_gain = e.get("xp_reward", 40 * e.get("tier", 1))
            gain_player_xp(p, xp_gain)
        else:
            # Διαφορετικά αυξάνουμε hurt sequence για animation
            e["hurt_seq"] = e.get("hurt_seq", 0) + 1

# Μέθοδος για το state των παικτών (connect/disconnect)
async def handle_control():
    global next_spawn_index

    while True:
        msg = await control_socket.recv_json()  # Περιμένει και λαμβάνει τα μηνύματα ελέγχου
        pid = msg["id"]     # Το id του παίκτη
        typ = msg["type"]   # Τύπος αιτήματος (σύνδεση ή αποσύνδεση)

        # Σύνδεση παίκτη
        if typ == "connect":
            # Αν δεν έχει σταλεί nickname ή class_name, ορίζονται default τιμές
            nickname = msg.get("nickname") or pid
            class_name = msg.get("class_name") or "Warrior"

            try:
                class_defs = get_player_type_defs(class_name)
            except ValueError:
                class_name = "Warrior"
                class_defs = get_player_type_defs(class_name)

            # Αν ο παίκτης είναι ήδη συνδεδεμένος, στέλνουμε απάντηση "ok"
            if pid in connected:
                await control_socket.send_json({"status": "ok"})
                continue

            # Προσθήκη του παίκτη στo σύνολο των συνδεδεμένων
            connected.add(pid)

            # Περιοχή και spawn σε αυτή
            start_region = regions[START_REGION]
            spawn_points = start_region.spawn_points

            # Spawn place
            spawn_index = next_spawn_index
            next_spawn_index += 1

            x, y = spawn_points[spawn_index % len(spawn_points)]

            hp_max = class_defs.get("hp_max", 100)

            # Δημιουργία εγγραφής παίκτη
            players[pid] = {
                # Θέση
                "x": x,         
                "y": y, 

                # Βασικά στοιχεία
                "nickname": nickname,  
                "class_name": class_name,
                "level": class_defs.get("level", 1),
                "xp": class_defs.get("xp", 0),
                "xp_next": class_defs.get("xp_next", XP_REQUIREMENTS[1]),
                "max_level": class_defs.get("max_level", 10),

                "hp": 1.0,
                "hp_cur": hp_max,
                "hp_max": hp_max,
                "energy": 1.0,
                "resist": class_defs.get("resist", 0),
                "damage": class_defs.get("damage", 25),

                "attack_type": class_defs.get("attack_type", "melee"),
                "move_speed": class_defs.get("move_speed", SPEED),

                # Κατάσταση παίκτη
                "state": "idle",
                "dir": "down",
                "dead": False,
                "hurt_seq": 0,

                # Στοιχεία επίθεσης
                "attack_requested": False,
                "attack_id": "basic",
                "attack_dir": "down",
                "attack_cooldown": class_defs["attacks"]["basic"].get("cooldown", 0.45),
                "next_attack_time": 0.0,
                "attack_anim_until": 0.0,
                "attack_state": "attack",
                "pending_hit_time": 0.0,

                # Κατεύθυνση κίνησης
                "move_dir": "STOP",

                # Αρχική περιοχή
                "region": START_REGION,
                }   

            print(f"Player {nickname} CONNECTED at spawn {spawn_index}")

            # Επιβεβαίωση σύνδεσης προς client
            await control_socket.send_json({
                "status": "ok",
            })

        # Αποσύνδεση παίκτη
        elif typ == "disconnect":
            # Παίρνουμε το nickname, αν υπάρχει, αλλιώς χρησιμοποιούμε το player id
            name = players.get(pid, {}).get("nickname", pid)
            print(f"Player {name} DISCONNECTED")

            # Αφαίρεση από connected players και από το players dict
            connected.discard(pid)
            players.pop(pid, None)

            # Επιβεβαίωση αποσύνδεσης προς client
            await control_socket.send_json({"status": "ok"})

# Μέθοδος που λαμβάνει και επεξεργάζεται τα inputs των παικτών
async def handle_inputs():
    while True:
        # Περιμένει μήνυμα input από κάποιον client
        msg = await pull_socket.recv_json()
        pid = msg["id"]

        # Αν ο παίκτης δεν υπάρχει πια, αγνοούμε το μήνυμα
        if pid not in players:
            continue

        # Input κίνησης
        if "move" in msg:
            direction = msg.get("move", "STOP")

            # Αν η κατεύθυνση δεν είναι έγκυρη, χρησιμοποιούμε STOP
            if direction not in ("UP", "DOWN", "LEFT", "RIGHT", "STOP"):
                direction = "STOP"

            # Αν ο παίκτης δεν είναι νεκρός, αποθηκεύουμε τη νέα κατεύθυνση κίνησης
            if not players[pid].get("dead", False):
                players[pid]["move_dir"] = direction

        # Input επίθεσης
        if msg.get("attack"):
            # Αν είναι νεκρός δεν μπορεί να επιτεθεί
            if players[pid].get("dead", False):
                continue

            now = time.time()

            # Αν υπάρχει ήδη attack request που δεν έχει επεξεργαστεί ακόμα, αγνοούμε επιπλέον attack inputs για να μην ανανεώνεται συνέχεια το animation lock
            if players[pid].get("attack_requested", False):
                continue

            # Αν ο παίκτης είναι ακόμα σε cooldown, δεν αλλάζουμε ούτε state ούτε attack_anim_until για να μην κολλάει ο παίκτης σε attack animation χωρίς πραγματικό hit
            if now < players[pid].get("next_attack_time", 0.0):
                players[pid]["attack_requested"] = False
                continue

            # Κατεύθυνση επίθεσης
            adir = msg.get("dir", "DOWN")

            # Αν η κατεύθυνση δεν είναι έγκυρη, χρησιμοποιούμε DOWN
            if adir not in ("UP", "DOWN", "LEFT", "RIGHT"):
                adir = "DOWN"

            # Για την επίθεση χρησιμοποιούμε το attack animation
            attack_state = "attack"

            players[pid]["attack_requested"] = True
            players[pid]["attack_id"] = msg.get("attack_id", "basic")
            players[pid]["attack_dir"] = adir.lower()
            players[pid]["dir"] = adir.lower()

            players[pid]["state"] = attack_state
            players[pid]["attack_state"] = attack_state

            class_name = players[pid].get("class_name", "Warrior")
            anim_duration = get_player_attack_anim_duration(class_name, attack_state)

            players[pid]["attack_anim_until"] = now + anim_duration

# Μέθοδος που ενημερώνει και μεταδίδει συνεχώς την κατάσταση του παιχνιδιού
async def broadcast_state():
    while True:
        global tick
        tick += 1       # Αύξηση του tick για κάθε frame / update

        elapsed_time = time.time() - server_start_time  # Χρόνος που έχει περάσει από την εκκίνηση του server

        # Αποθήκευση προηγούμενων θέσεων παικτών και εχθρών, ώστε να μπορούν να χρησιμοποιηθούν σε collision correction
        prev_players = {pid: (p["x"], p["y"]) for pid, p in players.items()}
        prev_enemies = {eid: (e["x"], e["y"]) for eid, e in enemies.items()}

        # Ενημέρωση κίνησης παικτών
        for p in players.values():
            # Αν ο παίκτης είναι νεκρός, σταματάει να κινείται
            if p.get("dead", False):
                p["move_dir"] = "STOP"
                continue

            direction = p.get("move_dir", "STOP")

            # Αρχικά θεωρούμε ως νέα θέση την τρέχουσα
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

            region = get_region(p["region"])
            map_width = region.map_width
            map_height = region.map_height

            # Περιορισμός της νέας θέσης ώστε ο παίκτης να μην βγει εκτός των ορίων του χάρτη
            new_x = max(PLAYER_WIDTH / 2, min(new_x, map_width - PLAYER_WIDTH / 2))
            new_y = max(PLAYER_HEIGHT / 2, min(new_y, map_height - PLAYER_HEIGHT / 2))

            # Έλεγχος collision ξεχωριστά για X και Y
            if not player_hits_walls(p, new_x, p["y"]):
                p["x"] = new_x

            if not player_hits_walls(p, p["x"], new_y):
                p["y"] = new_y

            # Ενημέρωση visual state / direction
            if not p.get("dead", False):
                now = time.time()

                # Όσο διαρκεί το attack animation, δεν αλλάζουμε state / direction από την κίνηση
                if now < p.get("attack_anim_until", 0.0):
                    p["dir"] = p.get("attack_dir", p.get("dir", "down"))
                    p["state"] = p.get("attack_state", "attack")
                else:
                    # Αν δεν παίζει attack animation, το state εξαρτάται από την κίνηση
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
            
            try_player_transition(p)

        # Κλήση μεθόδων για ενημέρωση συμπεριφοράς, συγκρούσεων και επιθέσεων παικτών και εχθρών

        update_enemy_chase_and_movement()  # Ενημέρωση και κίνησης εχθρών

        apply_enemy_attacks()   # Επιθέσεις εχθρών

        apply_player_attacks()  # Επιθέσεις παικτών

        player_enemy_blocking(prev_players, prev_enemies)   # Συγκρούση παικτών/εχθρών ώστε να μην περνάνε ο ένας μέσα από τον άλλο

        # Στέλνει την κατάσταση του παιχνιδιού σε όλους τους πελάτες
        await pub_socket.send_json({
            "tick": tick,
            "tick_dt": TICK_DT,             # Διάρκεια κάθε "tick"
            "players": dict(players),       # Τρέχουσα κατάσταση παικτών
            "enemies": dict(enemies),       # Τρέχουσα κατάσταση εχθρών
            "elapsed_time": elapsed_time    # Χρόνος που έχει περάσει από την έναρξη
        })

        # Παύση μέχρι το επόμενο tick
        await asyncio.sleep(TICK_DT)  # 50 FPS, ρυθμός ανανέωσης 20ms

# Main ασύγχρονη μέθοδος του server
async def main():
    await asyncio.gather(
        handle_control(),       # Επεξεργασία αιτημάτων σύνδεσης/αποσύνδεσης
        handle_inputs(),        # Επεξεργασία των κινήσεων των παικτών
        broadcast_state()       # Ενημέρωση και μετάδοση της κατάστασης του παιχνιδιού
    )
# Εκκίνηση του asyncio server
if __name__ == "__main__":
    asyncio.run(main())