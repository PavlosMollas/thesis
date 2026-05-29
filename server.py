import asyncio
import zmq
import zmq.asyncio
import sys
import time
from sprites import get_enemy_type_defs, get_player_type_defs
from stats import (XP_REQUIREMENTS, is_dragon_type, is_dragon_damageable_state, get_dragon_runtime_defaults, PerformanceStats)
from dragon_enemy import (update_dragon, find_nearest_player_in_region, player_is_behind_dragon, direction_from_dragon_to_player)
import math
from region import Region
from db_game import get_player_inventory, get_player_by_id, update_player_progress, update_last_login, buy_item_for_player, consume_item_for_player, reset_player_progress
from game_session import GameSessionManager

# Windows fix για να λειτουργεί το asyncio με τον κατάλληλο event loop σε Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TILE_SCALING = 1.0                      # Κλίμακα φόρτωσης των tilemaps

regions = { # Φόρτωση όλων των περιοχών του παιχνιδιού από τα αντίστοιχα TMX αρχεία
    "firstRegion": Region("firstRegion", "assets/maps/firstRegion.tmx", TILE_SCALING),
    "secondRegion": Region("secondRegion", "assets/maps/secondRegion.tmx", TILE_SCALING),
    "thirdRegion": Region("thirdRegion", "assets/maps/thirdRegion.tmx", TILE_SCALING),
    "fourthRegion": Region("fourthRegion", "assets/maps/fourthRegion.tmx", TILE_SCALING),
}

START_REGION = "firstRegion"    # Αρχική περιοχή στην οποία εμφανίζονται οι παίκτες όταν συνδέονται

game_status = "playing"         # Γενική κατάσταση του παιχνιδιού, όπως playing, win ή loss
game_finished_handled = False   # Flag για να μη γίνει παραπάνω από μία φορά η διαδικασία τερματισμού παιχνιδιού

# Διαχειριστής του session, δηλαδή lobby, loading, playing και finished phase
session = GameSessionManager(lobby_duration=15.0, loading_duration=3.0, finish_duration=3.0)

# Διαστάσεις hitbox/σώματος παίκτη που χρησιμοποιούνται σε collision checks
PLAYER_WIDTH  = 32
PLAYER_HEIGHT = 48

# Ρυθμός αναπλήρωσης energy και HP ανά δευτερόλεπτο
ENERGY_REGEN_PER_SECOND = 0.01
HP_REGEN_PER_SECOND = 0.2

SPEED = 5               # Βασική ταχύτητα κίνησης του παίκτη

# Ρυθμίσεις για ανίχνευση εχθρού που έχει κολλήσει, αν ένας εχθρός δεν μετακινηθεί αρκετά για συγκεκριμένο χρόνο, ενεργοποιείται προσωρινή κίνηση ξεκολλήματος
STUCK_THRESHOLD = 1.0     # δευτερόλεπτα χωρίς ουσιαστική πρόοδο
UNSTUCK_DURATION = 0.8    # διάρκεια κίνησης για ξεκόλλημα
MIN_PROGRESS_PX = 0.6     # ελάχιστη μετακίνηση σε pixels ώστε να θεωρηθεί πρόοδος

PLAYER_ANIM_FRAME_TIME = 0.12   # Χρόνος ανά frame animation παίκτη, για να εκτιμά ο server τη διάρκεια επίθεσης και το timing των hits
PLAYER_ATTACK_ANIM_FRAMES = {   # Πλήθος frames για κάθε attack animation ανά κλάση
    "Warrior": {
        "attack": 6,
        "attack02": 6,
        "attack03": 5,
        "walk_attack": 6,
    },
    "Mage": {
        "attack": 5,
        "attack02": 7,
        "attack03": 7,
        "walk_attack": 5,
    },
    "Marksman": {
        "attack": 8,
        "attack02": 8,
        "walk_attack": 8,
    },
}

server_start_time = time.time()     # Χρονική στιγμή εκκίνησης του server, χρησιμοποιείται για elapsed time
PLAYER_TIMEOUT_SECONDS = 3.0        # Αν δεν λαμβάνεται heartbeat/input από έναν παίκτη για αυτό το διάστημα, θεωρείται inactive
disconnected_active_players = {}    # Προσωρινή αποθήκευση active παικτών που αποσυνδέθηκαν/έγιναν timeout

ctx = zmq.asyncio.Context()         # Δημιουργία του zmq context για τη σύνδεση με τα sockets

# PULL socket: δέχεται inputs από τους clients, όπως movement, attacks και item actions
pull_socket = ctx.socket(zmq.PULL)
pull_socket.bind("tcp://*:5555")    # Ακούμε στις εισερχόμενες συνδέσεις στην θύρα 5555

# PUB socket: δημοσιεύει το game state προς όλους τους clients
pub_socket = ctx.socket(zmq.PUB)
pub_socket.bind("tcp://*:5556")     # Ακούμε για να στείλουμε κατάσταση στους πελάτες στη θύρα 5556

# REP socket: δέχεται control requests από clients, όπως connect και disconnec
control_socket = ctx.socket(zmq.REP)
control_socket.bind("tcp://*:5557") # Ακούμε για αιτήματα σύνδεσης και αποσύνδεσης στη θύρα 5557

players = {}          # Λεξικό με όλα τα δεδομένα των συνδεδεμένων παικτών
enemies = {}          # Λεξικό με όλα τα δεδομένα των εχθρών του παιχνιδιού

connected = set()     # Σύνολο με τους συνδεδεμένους παίκτες

next_spawn_index = 0  # Δείκτης για κυκλική επιλογή spawn point όταν συνδέονται νέοι παίκτες

# Δημιουργία των εχθρών από τα enemy spawn objects που υπάρχουν στα TMX maps
for region_name, region in regions.items():
    for (enemy_id, enemy_type, x, y) in region.enemy_spawns:
        defs = get_enemy_type_defs(enemy_type)  # Παίρνουμε τα στατιστικά και τις ρυθμίσεις του συγκεκριμένου τύπου εχθρού

        # Runtime state του εχθρού
        enemy_data = {
            "region": region_name,  # Περιοχή εχθρού
            "type": enemy_type,     # Είδος εχθρού

            # Τρέχουσα θέση και αρχική θέση spawn
            "x": x,
            "y": y,
            "spawn_x": x,
            "spawn_y": y,

            # Κατάσταση animation / συμπεριφοράς
            "state": "idle",
            "dir": "right" if is_dragon_type(enemy_type) else "down",
            "dead": False,
            "hurt_seq": 0,  # Μετρητής hurt animation που αυξάνεται κάθε φορά που ο εχθρός δέχεται hit, ώστε οι clients να ξέρουν πότε να παίξουν νέο hurt animation

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
            "pending_hit_time": 0.0,   # Χρονική στιγμή στην οποία θα εφαρμοστεί το damage μετά το windup της επίθεσης
            "attack_seq": 0,           # Μετρητής attack animation που αυξάνεται κάθε φορά που ξεκινά νέα επίθεση, ώστε οι clients να κάνουν reset το attack animation

            # Τρέχων στόχος και μεταβλητές για stuck handling
            "target": None,

            "last_x": x,
            "last_y": y,
            "stuck_time": 0.0,
            "unstuck_until": 0.0,
            "unstuck_side": 1,
        }

        if is_dragon_type(enemy_type):  # Αν ο εχθρός είναι dragon, προστίθενται επιπλέον runtime πεδία για τη δική του ειδική συμπεριφορά
            enemy_data.update(get_dragon_runtime_defaults(defs, x, y, time.time()))

        enemies[enemy_id] = enemy_data

TICK_DT = 0.02      # Η διάρκεια κάθε "tick" σε δευτερόλεπτα (ρυθμίζει το frame rate ~50 updates/sec)
tick = 0            # Μετρητής "tick" για το παιχνίδι

ENEMY_AI_INTERVAL = 0.04    # Δεν ενημερώνουμε τους εχθρούς σε κάθε server tick, αλλά κάθε 0.04 sec για να μειώνεται το φόρτο του server
enemy_ai_timer = 0.0        # Μετρητής που μετράει πόσος χρόνος έχει περάσει από την τελευταία ενημέρωση των εχθρών

server_stats = PerformanceStats(    # Αντικείμενο για την καταγραφή μετρικών απόδοσης του server σε αρχείο CSV
    "server_metrics.csv",
    [
        "time_seconds",     # Χρόνος από την έναρξη της μέτρησης
        "avg_tick_ms",      # Μέσος χρόνος επεξεργασίας tick στο χρονικό διάστημα μέτρησης
        "max_tick_ms",      # Μέγιστος χρόνος επεξεργασίας tick στο χρονικό διάστημα μέτρησης
        "players",          # Πλήθος συνδεδεμένων παικτών
        "active_enemies"    # Πλήθος ενεργών εχθρών, δηλαδή εχθρών σε περιοχές με παίκτη
    ]
)

server_metrics_interval = 20.0  # Κάθε πόσα δευτερόλεπτα θα γράφονται συγκεντρωτικά metrics στο CSV
server_metrics_timer = 0.0      # Μετρητής που μετράει πόσος χρόνος έχει περάσει από την τελευταία καταγραφή metrics
server_tick_ms_samples = []     # Λίστα που αποθηκεύει προσωρινά τα tick_ms κάθε tick

# Επιστρέφει το αντικείμενο Region με βάση το όνομα της περιοχής
def get_region(region_name: str) -> Region:
    return regions[region_name]

# Ελέγχει αν ένα σημείο x, y βρίσκεται μέσα σε ένα ορθογώνιο object, χρησιμοποιείται για τα transition
def rect_contains_point(rect, x, y):
    return (
        rect["x"] <= x <= rect["x"] + rect["width"] and
        rect["y"] <= y <= rect["y"] + rect["height"]
    )

# Επιστρέφει True αν ο στόχος της συγκεκριμένης περιοχής έχει ολοκληρωθεί
def is_region_objective_complete(region_name):
    return get_region_objective_info(region_name).get("complete", True)

# Υπολογίζει την πρόοδο του objective για μια περιοχή και επιστρέφει το κείμενο, το πόσοι στόχοι απομένουν και αν έχει ολοκληρωθεί
def get_region_objective_info(region_name):
    remaining = 0

    if region_name in ("firstRegion", "secondRegion"):  # Στις δύο πρώτες περιοχές ο στόχος είναι να νικηθούν όλοι οι enemies της περιοχής
        for e in enemies.values():
            if e.get("region") != region_name:          # Μετράμε μόνο enemies που ανήκουν στη συγκεκριμένη περιοχή
                continue

            if not e.get("dead", False):                # Αν ο enemy δεν είναι νεκρός, προσμετράται στους στόχους που απομένουν
                remaining += 1

        return {    # Επιστρέφουμε πληροφορίες objective για να σταλούν στον client
            "text": "Defeat all enemies",
            "remaining": remaining,
            "complete": remaining == 0,
        }

    if region_name in ("thirdRegion", "fourthRegion"):  # Στις δύο τελευταίες περιοχές ο στόχος αφορά μόνο τους dragons
        for e in enemies.values():
            if e.get("region") != region_name:          # Αγνοούμε enemies από άλλες περιοχές
                continue

            if not is_dragon_type(e.get("type", "")):   # Μετράμε μόνο dragon enemies
                continue

            if not e.get("dead", False):                # Αν ο dragon δεν είναι νεκρός, παραμένει ως στόχος
                remaining += 1

        return {        
            "text": "Defeat all dragons",
            "remaining": remaining,
            "complete": remaining == 0,
        }

    return {        # Για περιοχές χωρίς objective, θεωρούμε ότι ο στόχος είναι ήδη ολοκληρωμένος
        "text": "",
        "remaining": 0,
        "complete": True,
    }

# Ελέγχει αν ο παίκτης βρίσκεται μέσα σε κάποιο transition object και τον μεταφέρει στο αντίστοιχο region
def player_transition(player):
    global game_status

    if game_status != "playing":    # Transitions επιτρέπονται μόνο όσο το παιχνίδι είναι ενεργό
        return

    if player.get("dead", False):   # Νεκροί παίκτες δεν μπορούν να αλλάξουν περιοχή
        return

    current_region_name = player["region"]
    current_region = get_region(current_region_name)    # Παίρνουμε το region στο οποίο βρίσκεται αυτή τη στιγμή ο παίκτης

    # Ελέγχουμε όλα τα transition rectangles που έχουν οριστεί στο τρέχον region
    for tr in current_region.transitions:
        if rect_contains_point(tr, player["x"], player["y"]):

            # Ο παίκτης μπορεί να περάσει στο επόμενο region μόνο αν έχει ολοκληρωθεί το objective
            if not is_region_objective_complete(current_region_name):
                return

            # Αν το transition έχει action win, σημαίνει ότι είναι το τελικό σημείο νίκης
            action = tr.get("action")
            if action == "win":
                game_status = "win"
                session.finish_game("win")
                print(f"VICTORY: Player {player['nickname']} reached the final transition")
                return

            # Για κανονικό transition, διαβάζουμε το target region και το spawn point
            target_region_name = tr["target_map"]
            target_spawn_name = tr["target_spawn"]

            if target_region_name not in regions:       # Έλεγχος ότι το target region υπάρχει στο dictionary regions
                print(f"Unknown target region: {target_region_name}")
                return

            # Παίρνουμε τη θέση spawn στο target region
            target_region = get_region(target_region_name)
            spawn_pos = target_region.get_named_spawn(target_spawn_name)

            if spawn_pos is None:       # Αν δεν βρεθεί το spawn point, δεν γίνεται transition
                print(f"Spawn '{target_spawn_name}' not found in region '{target_region_name}'")
                return

            # Ενημερώνουμε region και θέση παίκτη, από το επόμενο game state ο client θα φορτώσει το αντίστοιχο map
            player["region"] = target_region_name
            player["x"], player["y"] = spawn_pos

            print(f"Player {player['nickname']} transitioned to {target_region_name} at spawn {target_spawn_name}")
            return

# Υπολογίζει τη διάρκεια του attack animation ενός παίκτη με βάση την κλάση του και το είδος του attack state    
def get_player_attack_anim_duration(class_name, attack_state):
    frames_by_state = PLAYER_ATTACK_ANIM_FRAMES.get(class_name) # Παίρνουμε το dictionary με τα animation frames της συγκεκριμένης κλάσης

    if frames_by_state is None: # Αν δεν υπάρχει καταχώρηση για την κλάση, επιστρέφουμε μια default διάρκεια 0.60 δευτερολέπτων
        return 0.60

    # Παίρνουμε τον αριθμό frames για το συγκεκριμένο attack state, χρησιμοποιούμε fallback το "attack" ή default τιμή 5 frames αν δεν υπάρχει state
    frames = frames_by_state.get(attack_state, frames_by_state.get("attack", 5))

    return frames * PLAYER_ANIM_FRAME_TIME  # Η συνολική διάρκεια του animation είναι αριθμός frames * διάρκεια κάθε frame

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

    new_x = current_x + delta_x     # Κίνηση στον άξονα X

    # Περιορισμός στον άξονα Χ ώστε να μείνει μέσα στα όρια του χάρτη
    w = e["hitbox_w"]
    h = e["hitbox_h"]
    new_x = max(w/2, min(new_x, map_width - w/2))

    # Αν δεν υπάρχει collision, εφαρμόζουμε τη νέα θέση στον άξονα Χ
    if not enemy_hits_walls(e, new_x, current_y):
        e["x"] = new_x
        moved = moved or (abs(delta_x) > 1e-6)

    new_y = current_y + delta_y                     # Κίνηση στον άξονα Y
    new_y = max(h/2, min(new_y, map_height - h/2))  # Περιορισμός στον άξονα Y ώστε να μείνει μέσα στα όρια του χάρτη

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
        if p.get("dead"):           # Αγνοούμε παίκτες που έχουν πεθάνει
                continue

        # Παίρνουμε την προηγούμενη θέση του παίκτη πριν εφαρμοστεί η κίνηση αυτού του tick, αν δεν υπάρχει προηγούμενη θέση χρησιμοποιούμε την τρέχουσα
        prev_player_x, prev_player_y = prev_players.get(pid, (p["x"], p["y"]))

        for eid, e in enemies.items():  # Για κάθε παίκτη ελέγχουμε όλους τους εχθρούς
            if p["region"] != e["region"]:  # Αγνοούμε συγκρούσεις όταν παίκτης και εχθρός βρίσκονται σε διαφορετική περιοχή
                continue

            if e.get("dead"):           # Αγνοούμε εχθρούς που έχουν πεθάνει
                continue

            # Όταν ο dragon είναι στον αέρα, δεν κάνει collision με τον παίκτη
            if e.get("special") == "dragon" and e.get("dragon_mode") == "air":
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

            # Για τον dragon δεν τον γυρίζουμε πάντα πίσω, γιατί μπορεί να φαίνεται ότι περπατάει αλλά να μένει ακίνητος όταν ακουμπάει τον παίκτη
            if e.get("special") == "dragon":
                old_dx = abs(prev_enemy_x - p["x"])
                new_dx = abs(e["x"] - p["x"])

                # Αν η νέα θέση τον απομακρύνει από τον παίκτη, την κρατάμε και έτσι μπορεί να ξεκολλήσει όταν ο παίκτης τον ακουμπάει από πίσω ή από το πλάι
                if new_dx >= old_dx:
                    continue

                # Αν όμως η νέα θέση τον φέρνει πιο κοντά στον παίκτη, τότε τον γυρίζουμε πίσω και αλλάζουμε κατεύθυνση patrol ώστε να μη συνεχίσει να περπατάει πάνω του
                e["x"], e["y"] = prev_enemy_x, prev_enemy_y

                if p["x"] >= e["x"]:
                    e["patrol_dir"] = "left"
                    e["dir"] = "left"
                else:
                    e["patrol_dir"] = "right"
                    e["dir"] = "right"

            else:
                e["x"], e["y"] = prev_enemy_x, prev_enemy_y     # Οι απλοί enemies επιστρέφουν στην προηγούμενη θέση τους, ώστε να μη σπρώχνουν τον παίκτη

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
def move_enemy_towards_target(e, target_x, target_y, dt=TICK_DT):
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
    speed = e["move_speed"] * (dt / TICK_DT)

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

    moved = False       # Κίνηση: δοκιμάζει 3 επιλογές (ευθεία, μόνο άξονα X, μόνο άξονα Y)

    moved = move_enemy(e, dir_x * speed, dir_y * speed) # Προσπάθεια πλήρους διαγώνιας / ευθείας κίνησης

    if not moved:       # Αν απέτυχε, δοκιμή μόνο στον άξονα X
        moved = move_enemy(e, dir_x * speed, 0)         

    if not moved:       # Αν απέτυχε και πάλι, δοκιμή μόνο στον άξονα Y
        moved = move_enemy(e, 0, dir_y * speed)

    e["dir"] = dir_from_delta(dx, dy)   # Ενημέρωση direction για animation

# Επιλέγει ποια πλάγια κατεύθυνση unstuck (1 ή -1) φέρνει τον εχθρό πιο κοντά στον στόχο
def choose_unstuck_side_towards_target(e, target_x, target_y):
    current_x, current_y = e["x"], e["y"]
    dx = target_x - current_x
    dy = target_y - current_y

    d = dist(current_x, current_y, target_x, target_y)  # Ευκλείδεια απόσταση

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

    move_enemy(tmp1, (-dir_y) * speed, (dir_x) * speed)     # Δοκιμαστική μετακίνηση στην πρώτη πλάγια κατεύθυνση

    x1, y1 = tmp1["x"], tmp1["y"]           # Παίρνουμε τη νέα δοκιμαστική θέση

    d1 = dist(target_x, target_y, x1, y1)   # Υπολογίζουμε την απόσταση από τον στόχο μετά από αυτή τη δοκιμή

    # Δοκιμή πλάγιας κίνησης με πλευρά -1
    # Δημιουργούμε δεύτερο προσωρινό αντίγραφο του εχθρού, ώστε να ελέγξουμε την αντίθετη κάθετη κατεύθυνση
    tmp2 = {"x": current_x, "y": current_y, "hitbox_w": e["hitbox_w"], "hitbox_h": e["hitbox_h"]}
    tmp2.update(e)

    move_enemy(tmp2, (dir_y) * speed, (-dir_x) * speed) # Δοκιμαστική μετακίνηση στη δεύτερη πλάγια κατεύθυνση

    x2, y2 = tmp2["x"], tmp2["y"]                       # Παίρνουμε τη νέα δοκιμαστική θέση

    d2 = dist(target_x, target_y, x2, y2)               # Υπολογίζουμε την απόσταση από τον στόχο μετά από αυτή τη δοκιμή

    return 1 if d1 <= d2 else -1                        # Επιλέγουμε την πλευρά που μικραίνει περισσότερο την απόσταση από τον στόχο

# Επιστρέφει τις περιοχές στις οποίες υπάρχουν ζωντανοί παίκτες
def get_active_regions():
    active_regions = set()

    for p in players.values():          # Διατρέχουμε όλους τους παίκτες που υπάρχουν στον server
        if not p.get("dead", False):    # Μετράμε μόνο τους παίκτες που δεν είναι νεκροί
            active_regions.add(p.get("region", START_REGION))   # Προσθέτουμε την περιοχή του παίκτη στο set, αν δεν υπάρχει χρησιμοποιείται fallback

    return active_regions

# Μέθοδος που ενημερώνει τη συμπεριφορά και την κίνηση όλων των εχθρών
def update_enemy_chase_and_movement(dt=TICK_DT):
    active_regions = get_active_regions()

    for e in enemies.values():
        # Αν η περιοχή δεν έχει ενεργό παίκτη, δεν κυνηγάμε κανέναν
        # Όμως αν ο enemy έχει φύγει από το spawn, πρέπει να συνεχίσει να ενημερώνεται ώστε να επιστρέψει πίσω
        if e.get("region") not in active_regions:
            sx, sy = e["spawn_x"], e["spawn_y"]
            d_spawn = dist(e["x"], e["y"], sx, sy)

            e["target"] = None
            e["pending_hit_time"] = 0.0
            e["next_attack_time"] = 0.0
            e["unstuck_until"] = 0.0

            if d_spawn <= 2.0:
                e["state"] = "idle"
            else:
                e["state"] = "walk"
                move_enemy_towards_target(e, sx, sy, dt)

            continue

        if e.get("dead"):   # Παραλείπουμε νεκρούς εχθρούς
            continue

        # Αν ο εχθρός είναι dragon, δεν ακολουθεί το απλό chase/attack σύστημα των υπόλοιπων εχθρών
        if e.get("special") == "dragon":
            update_dragon(e, players, dist, move_enemy, collides_with_walls_aabb)
            continue

        # Εύρεση κοντινότερου ζωντανού παίκτη
        nearest_pid, nearest_player, nearest_d = find_nearest_player_in_region(e, players, dist)

        # Αν δεν υπάρχει κανένας ζωντανός παίκτης στην ίδια περιοχή, ο enemy χάνει τον στόχο του και επιστρέφει στο spawn
        if nearest_pid is None:
            e["target"] = None
            e["pending_hit_time"] = 0.0
            e["next_attack_time"] = 0.0
            e["unstuck_until"] = 0.0

            sx, sy = e["spawn_x"], e["spawn_y"]
            d_spawn = dist(e["x"], e["y"], sx, sy)

            if d_spawn <= 2.0:
                e["state"] = "idle"
            else:
                e["state"] = "walk"
                move_enemy_towards_target(e, sx, sy)

            continue

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
                    move_enemy_towards_target(e, tp["x"], tp["y"], dt)

            else:
                if d <= e["attack_range"]:
                    e["state"] = "attack"
                    e["dir"] = dir_from_delta(tp["x"] - e["x"], tp["y"] - e["y"])
                    e["unstuck_until"] = 0.0    # Επαναφορά unstuck mode
                
                # Αλλιώς κινείται προς τον στόχο
                else:
                    e["state"] = "walk"
                    move_enemy_towards_target(e, tp["x"], tp["y"], dt)
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
            e["stuck_time"] = e.get("stuck_time", 0.0) + dt
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
    active_regions = get_active_regions()   # Παίρνουμε μόνο τις περιοχές όπου υπάρχουν ζωντανοί παίκτες

    for e in enemies.values():                      # Διατρέχουμε όλους τους εχθρούς
        if e.get("region") not in active_regions:   # Αγνοούμε εχθρούς που βρίσκονται σε περιοχές χωρίς ζωντανούς παίκτες
            continue

        if e.get("special") == "dragon":         # Οι dragons έχουν ξεχωριστή λογική επίθεσης και δεν υπολογίζονται σε αυτή τη γενική μέθοδο
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

# Μέθοδος που ελέγχει αν ένας enemy βρίσκεται μέσα στην κατεύθυνση επίθεσης του παίκτη
def enemy_in_player_directional_range(p, e, attack_defs):
    dx = e["x"] - p["x"]
    dy = e["y"] - p["y"]

    # Παίρνουμε την κατεύθυνση της επίθεσης του παίκτη, αν δεν υπάρχει attack_dir χρησιμοποιούμε την τρέχουσα κατεύθυνση του παίκτη
    direction = p.get("attack_dir", p.get("dir", "down"))

    attack_range = attack_defs.get("range", 70)                 # Απόσταση που φτάνει η επίθεση

    # Πλάτος της επίθεσης που χρησιμοποιείται ώστε η επίθεση να χτυπά μόνο enemies που είναι περίπου στην ίδια ευθεία
    lane_half_width = attack_defs.get("lane_half_width", 36)

    # Αν ο παίκτης χτυπάει δεξιά, ο enemy πρέπει να είναι δεξιά του και μέσα στο επιτρεπτό range και πλάτος
    if direction == "right":
        return dx > 0 and dx <= attack_range and abs(dy) <= lane_half_width

    # Αν ο παίκτης χτυπάει αριστερά, ο enemy πρέπει να είναι αριστερά του
    if direction == "left":
        return dx < 0 and abs(dx) <= attack_range and abs(dy) <= lane_half_width

    # Αν ο παίκτης χτυπάει πάνω, ο enemy πρέπει να είναι πάνω του
    if direction == "up":
        return dy > 0 and dy <= attack_range and abs(dx) <= lane_half_width

    # Αν ο παίκτης χτυπάει κάτω, ο enemy πρέπει να είναι κάτω του
    if direction == "down":
        return dy < 0 and abs(dy) <= attack_range and abs(dx) <= lane_half_width

    return False    # Αν η κατεύθυνση δεν είναι έγκυρη, δεν υπάρχει hit

# Μέθοδος που επιστρέφει πόσο XP χρειάζεται ο παίκτης για το επόμενο level
def get_xp_next_for_level(level):
    return XP_REQUIREMENTS.get(level, 0)

# Μέθοδος που προσθέτει XP στον παίκτη και ελέγχει αν πρέπει να ανέβει level
def gain_player_xp(p, amount):
    # Αν ο παίκτης είναι ήδη στο μέγιστο level, δεν κρατάμε άλλο XP
    if p.get("level", 1) >= p.get("max_level", 10):
        p["level"] = p.get("max_level", 10)
        p["xp"] = 0
        p["xp_next"] = 0
        return

    p["xp"] = p.get("xp", 0) + amount   # Προσθέτουμε το XP που κέρδισε ο παίκτης

    # Όσο το XP είναι αρκετό για level up, ανεβάζουμε level
    # Το while επιτρέπει να ανέβει περισσότερα από ένα level αν κερδίσει πολύ XP μαζί
    while p["level"] < p["max_level"] and p["xp"] >= p["xp_next"]:
        # Αφαιρούμε το XP που χρειάστηκε για το τρέχον level up
        p["xp"] -= p["xp_next"]

        # Αύξηση level
        p["level"] += 1

        # Αύξηση βασικών στατιστικών όταν ο παίκτης ανεβαίνει level
        p["hp_max"] += 15              # Αυξάνεται η μέγιστη ζωή
        p["damage"] += 4               # Αυξάνεται η βασική ζημιά
        p["resist"] += 1               # Αυξάνεται η άμυνα

        # Στο level up ο παίκτης παίρνει 10% του μέγιστου HP
        hp_max = p.get("hp_max", 100)
        hp_cur = p.get("hp_cur", p.get("hp", 1.0) * hp_max)

        hp_cur = min(
            hp_max,
            hp_cur + hp_max * 0.10
        )

        p["hp_cur"] = hp_cur
        p["hp"] = hp_cur / hp_max

        # Παίρνει επίσης 10% energy στο level up, χωρίς να ξεπεράσει το 100%
        p["energy"] = min(
            1.0,
            p.get("energy", 1.0) + 0.10
        )

        p["xp_next"] = get_xp_next_for_level(p["level"])    # Υπολογίζουμε το XP που χρειάζεται για το επόμενο level

    # Αν έφτασε στο μέγιστο level, μηδενίζουμε το XP και το xp_next
    if p["level"] >= p["max_level"]:
        p["level"] = p["max_level"]
        p["xp"] = 0
        p["xp_next"] = 0

# Ελέγχει αν ένας εχθρός βρίσκεται μέσα στην περιοχή χτυπήματος ενός player attack
def enemy_hit_by_player_attack(p, e, attack_defs):
    # Παίρνουμε το σχήμα και τον τύπο της επίθεσης από τα attack definitions
    attack_shape = attack_defs.get("attack_shape", "directional")
    attack_type = attack_defs.get("attack_type", "melee")

    # Τα ranged directional attacks, όπως το basic του Marksman, χρησιμοποιούν ξεχωριστό έλεγχο ευθείας/lane προς την κατεύθυνση του παίκτη
    if attack_type == "ranged" and attack_shape == "directional":
        return enemy_in_player_directional_range(p, e, attack_defs)

    attack_dir = p.get("attack_dir", p.get("dir", "down"))  # Κατεύθυνση επίθεσης. Αν δεν υπάρχει attack_dir, χρησιμοποιείται η τρέχουσα κατεύθυνση του παίκτη

    # Θέσεις παίκτη και εχθρού
    px = p["x"]
    py = p["y"]
    ex = e["x"]
    ey = e["y"]

    # Διαφορά θέσης εχθρού σε σχέση με τον παίκτη
    dx = ex - px
    dy = ey - py

    attack_range = attack_defs.get("range", 70)     # Μέγιστη εμβέλεια επίθεσης

    # Directional attack: χτυπά έναν εχθρό μόνο αν είναι μέσα στην εμβέλεια και βρίσκεται μπροστά από τον παίκτη με βάση την κατεύθυνση επίθεσης
    if attack_shape == "directional":
        d = dist(px, py, ex, ey)

        if d > attack_range:    # Αν ο εχθρός είναι εκτός εμβέλειας, δεν δέχεται ζημιά
            return False

        # Έλεγχος ότι ο εχθρός βρίσκεται στη σωστή πλευρά του παίκτη
        if attack_dir == "up" and dy <= 0:
            return False
        if attack_dir == "down" and dy >= 0:
            return False
        if attack_dir == "left" and dx >= 0:
            return False
        if attack_dir == "right" and dx <= 0:
            return False

        return True

    # Front AOE: χτυπά περιοχή μπροστά από τον παίκτη, με συγκεκριμένη εμβέλεια και πλάτος
    if attack_shape == "front_aoe":
        half_width = attack_defs.get("aoe_width", 90) / 2

        if attack_dir == "right":
            return dx > 0 and dx <= attack_range and abs(dy) <= half_width

        if attack_dir == "left":
            return dx < 0 and abs(dx) <= attack_range and abs(dy) <= half_width

        if attack_dir == "up":
            return dy > 0 and dy <= attack_range and abs(dx) <= half_width

        if attack_dir == "down":
            return dy < 0 and abs(dy) <= attack_range and abs(dx) <= half_width

        return False

    # Side AOE: χτυπά οριζόντια περιοχή δεξιά και αριστερά από τον παίκτη
    if attack_shape == "side_aoe":
        half_height = attack_defs.get("aoe_width", 100) / 2

        # Χτυπάει και αριστερά και δεξιά, ανεξάρτητα από το πού κοιτάει ο παίκτης
        return abs(dx) <= attack_range and abs(dy) <= half_height and abs(dx) > 0

    return False

# Μέθοδος που μετακινεί τον παίκτη γρήγορα προς την κατεύθυνση που κοιτάει
def apply_player_dash(p, dash_distance):
    direction = p.get("attack_dir", p.get("dir", "down"))   # Παίρνουμε την κατεύθυνση του dash από το attack_dir ή fallback στο dir

    # Μετατροπή κατεύθυνσης σε διανυσματική κίνηση
    dx = 0
    dy = 0

    if direction == "up":
        dy = 1
    elif direction == "down":
        dy = -1
    elif direction == "left":
        dx = -1
    elif direction == "right":
        dx = 1
    else:   # Αν δεν υπάρχει έγκυρη κατεύθυνση, το dash ακυρώνεται
        return

    # Παίρνουμε την περιοχή του παίκτη για όρια χάρτη και collisions
    region = get_region(p["region"])
    map_width = region.map_width
    map_height = region.map_height

    # Το dash γίνεται σε μικρά βήματα, ώστε να σταματάει αν βρει wall
    step_size = 8
    steps = int(dash_distance / step_size)

    for _ in range(steps):
        # Υπολογισμός νέας πιθανής θέσης
        new_x = p["x"] + dx * step_size
        new_y = p["y"] + dy * step_size

        # Κρατάμε τον παίκτη μέσα στα όρια του χάρτη
        new_x = max(PLAYER_WIDTH / 2, min(new_x, map_width - PLAYER_WIDTH / 2))
        new_y = max(PLAYER_HEIGHT / 2, min(new_y, map_height - PLAYER_HEIGHT / 2))

        # Αν βρίσκει τοίχο, σταματάει το dash
        if player_hits_walls(p, new_x, new_y):
            break

        # Εφαρμογή του dash
        p["x"] = new_x
        p["y"] = new_y

# Επαναφέρει το runtime state του παιχνιδιού για νέο session
def reset_runtime_game_state():
    global game_status, game_finished_handled, next_spawn_index, server_start_time, tick

    # Επαναφορά βασικών μεταβλητών παιχνιδιού
    game_status = "playing"
    game_finished_handled = False
    next_spawn_index = 0
    server_start_time = time.time()
    tick = 0

    reset_enemies()     # Επαναφορά όλων των εχθρών στις αρχικές τους θέσεις και τιμές

    print("Runtime game state reset. New session started.")

# Επαναδημιουργεί όλους τους εχθρούς από τα spawn points των περιοχών
def reset_enemies():
    enemies.clear() # Καθαρίζουμε τους τρέχοντες εχθρούς

    for region_name, region in regions.items(): # Ξαναφορτώνουμε enemies από τα enemy spawns των TMX maps
        for (enemy_id, enemy_type, x, y) in region.enemy_spawns:
            defs = get_enemy_type_defs(enemy_type)  # Παίρνουμε τα στατιστικά του συγκεκριμένου τύπου εχθρού

            enemy_data = {  # Δημιουργούμε νέο runtime state για τον εχθρό
                "region": region_name,
                "type": enemy_type,

                "x": x,
                "y": y,
                "spawn_x": x,
                "spawn_y": y,

                "state": "idle",
                "dir": "right" if is_dragon_type(enemy_type) else "down",
                "dead": False,
                "hurt_seq": 0,

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

                "hitbox_w": defs["hitbox_w"],
                "hitbox_h": defs["hitbox_h"],

                "aggro_radius": defs["aggro_radius"],
                "lose_radius": defs["lose_radius"],
                "attack_range": defs["attack_range"],

                "windup": defs["windup"],
                "attack_cooldown": 1.0 / defs["attack_speed"],
                "next_attack_time": 0.0,
                "pending_hit_time": 0.0,
                "attack_seq": 0,

                "target": None,

                "last_x": x,
                "last_y": y,
                "stuck_time": 0.0,
                "unstuck_until": 0.0,
                "unstuck_side": 1,
            }

            if is_dragon_type(enemy_type):  # Αν ο εχθρός είναι dragon, προστίθενται και τα ειδικά runtime πεδία του dragon
                enemy_data.update(get_dragon_runtime_defaults(defs, x, y, time.time()))

            enemies[enemy_id] = enemy_data

    print("Enemies reset to initial state.")

# Μέθοδος που εφαρμόζει στατιστικά level σε παίκτη που φορτώνεται από τη βάση
def apply_level_stats_from_saved_level(p):
    level = p.get("level", 1)

    bonus_levels = max(0, level - 1)    # Κάθε level πάνω από το 1 δίνει επιπλέον stats

    # Προσθήκη bonus HP, damage και resist με βάση το level
    p["hp_max"] += 15 * bonus_levels
    p["damage"] += 4 * bonus_levels
    p["resist"] += 1 * bonus_levels

    # Ο παίκτης ξεκινά με πλήρες HP μετά τη φόρτωση
    p["hp_cur"] = p["hp_max"]
    p["hp"] = 1.0

# Μέθοδος που φορτώνει το inventory του παίκτη από τη βάση σε μορφή list dictionaries
def load_player_inventory_payload(player_id):
    player_inventory_rows = get_player_inventory(player_id)

    player_inventory = []
    for row in player_inventory_rows:   # Μετατροπή κάθε γραμμής της βάσης σε dictionary για να μπορεί να σταλεί εύκολα στον client
        item_name, quantity, price, category, stackable, max_stack = row

        player_inventory.append({
            "item_name": item_name,
            "quantity": quantity,
            "price": price,
            "category": category,
            "stackable": stackable,
            "max_stack": max_stack,
        })

    return player_inventory

# Αφαιρεί ενεργό buff από item όταν λήξει 
def remove_item_buff(p, item_name):
    buffs = p.setdefault("item_buffs", {})  # Παίρνουμε ή δημιουργούμε το dictionary των ενεργών item buffs

    if item_name not in buffs:      # Αν το συγκεκριμένο buff δεν είναι ενεργό, δεν κάνουμε τίποτα
        return

    buff = buffs.pop(item_name)     # Αφαιρούμε το buff και αντιστρέφουμε τα bonus που είχε δώσει

    p["damage"] -= buff.get("damage_bonus", 0)
    p["resist"] -= buff.get("resist_bonus", 0)

    recompute_item_attack_speed_multiplier(p)   # Μετά την αφαίρεση, ξαναϋπολογίζουμε το συνολικό attack speed multiplier

# Υπολογίζει ξανά το attack speed multiplier από όλα τα ενεργά buffs
def recompute_item_attack_speed_multiplier(p):
    mult = 1.0

    for buff in p.get("item_buffs", {}).values():   # Πολλαπλασιάζουμε τα multipliers όλων των ενεργών buffs
        mult *= buff.get("attack_speed_multiplier", 1.0)

    p["item_attack_speed_multiplier"] = mult

# Ελέγχει αν έχουν λήξει προσωρινά elixir buffs
def update_item_buffs():
    now = time.time()

    for p in players.values():  # Ελέγχουμε buffs για κάθε παίκτη
        buffs = p.setdefault("item_buffs", {})

        expired = [ # Λίστα με buffs των οποίων έχει περάσει ο χρόνος λήξης
            item_name
            for item_name, buff in buffs.items()
            if now >= buff.get("expires_at", 0.0)
        ]

        for item_name in expired:   # Αφαιρούμε τα expired buffs
            remove_item_buff(p, item_name)

# Εφαρμόζει το effect ενός item στον παίκτη
def apply_item_effect(p, item_name):
    now = time.time()

    # Health potion: +25 HP
    if item_name == "Health_Potion":
        hp_max = p.get("hp_max", 100)
        hp_cur = p.get("hp_cur", p.get("hp", 1.0) * hp_max)

        # Αν είναι ήδη full, δεν καταναλώνουμε item
        if hp_cur >= hp_max:
            return False, "HP already full"

        hp_cur = min(hp_max, hp_cur + 25)

        p["hp_cur"] = hp_cur
        p["hp"] = hp_cur / hp_max
        return True, "Health potion used"

    # Energy potion: +20% energy
    if item_name == "Energy_Potion":
        energy = p.get("energy", 1.0)

        # Αν είναι ήδη full, δεν καταναλώνουμε item
        if energy >= 1.0:
            return False, "Energy already full"

        p["energy"] = min(1.0, energy + 0.20)
        return True, "Energy potion used"

    # Elixir of Toughness: +10 resist, +5 damage για 60 sec
    if item_name == "ElixirOfToughness":
        remove_item_buff(p, item_name)

        p["resist"] += 10
        p["damage"] += 5

        p.setdefault("item_buffs", {})[item_name] = {
            "expires_at": now + 60.0,
            "resist_bonus": 10,
            "damage_bonus": 5,
            "attack_speed_multiplier": 1.0,
        }

        recompute_item_attack_speed_multiplier(p)
        return True, "Toughness elixir used"

    # Elixir of Magic: +15 damage για 60 sec
    if item_name == "ElixirOfMagic":
        remove_item_buff(p, item_name)

        p["damage"] += 15

        p.setdefault("item_buffs", {})[item_name] = {
            "expires_at": now + 60.0,
            "resist_bonus": 0,
            "damage_bonus": 15,
            "attack_speed_multiplier": 1.0,
        }

        recompute_item_attack_speed_multiplier(p)
        return True, "Magic elixir used"

    # Elixir of Power: +5 damage και 10% γρηγορότερο attack speed για 60 sec
    if item_name == "ElixirOfPower":
        remove_item_buff(p, item_name)

        p["damage"] += 5

        p.setdefault("item_buffs", {})[item_name] = {
            "expires_at": now + 60.0,
            "resist_bonus": 0,
            "damage_bonus": 5,
            "attack_speed_multiplier": 0.90,
        }

        recompute_item_attack_speed_multiplier(p)
        return True, "Power elixir used"

    return False, "Unknown item"

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

        # Έλεγχος επαναφόρτισης (cooldown)
        next_attack_times = p.setdefault("next_attack_times", {
            "basic": 0.0,
            "skill1": 0.0,
            "skill2": 0.0,
        })

        if now < next_attack_times.get(attack_id, 0.0):
            continue

        # Έλεγχος αν ο παίκτης έχει ξεκλειδώσει το συγκεκριμένο attack με βάση το level του
        required_level = attack_defs.get("unlock_level", 1)
        if p.get("level", 1) < required_level:
            continue

        # Έλεγχος ενέργειας
        energy_cost = attack_defs.get("energy_cost", 0.0)
        if p.get("energy", 1.0) < energy_cost:
            continue

        # Αφαίρεση ενέργειας
        p["energy"] = max(0.0, p.get("energy", 1.0) - energy_cost)

        # Ορίζουμε το επόμενο χρονικό σημείο στο οποίο ο παίκτης θα μπορεί να ξαναεπιτεθεί
        cooldown = attack_defs.get("cooldown", 0.45)

        # Rapid Fire του Marksman: όσο είναι ενεργό, μειώνει το cooldown του basic attack
        if (
            class_name == "Marksman"
            and attack_id == "basic"
            and now < p.get("rapid_fire_until", 0.0)
        ):
            cooldown *= class_defs["attacks"]["skill1"].get("attack_speed_multiplier", 1.0)

        cooldown *= p.get("item_attack_speed_multiplier", 1.0)
        
        next_attack_times[attack_id] = now + cooldown   # Item buff

        # Αν το skill είναι buff, δεν κάνει damage και δεν ψάχνει στόχο
        if attack_defs.get("type") == "buff":
            duration = attack_defs.get("duration", 5.0)
            p["rapid_fire_until"] = now + duration
            continue

        # Αν το skill είναι dash, μετακινεί τον παίκτη και δεν κάνει damage
        if attack_defs.get("type") == "dash":
            dash_distance = attack_defs.get("dash_distance", 160)
            apply_player_dash(p, dash_distance)
            continue

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

            if not enemy_hit_by_player_attack(p, e, attack_defs):
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

            # Gold reward
            gold_gain = e.get("gold_reward", 10 * e.get("tier", 1))
            p["gold"] = p.get("gold", 0) + gold_gain

            try:
                update_player_progress(     # Αποθηκεύουμε στη βάση την ενημερωμένη πρόοδο του παίκτη μετά το kill, δηλαδή gold, XP και level
                    p.get("player_id", ""),
                    int(p.get("gold", 0)),
                    int(p.get("xp", 0)),
                    int(p.get("level", 1))
                )
            except Exception as ex:
                print("Error saving player progress:", ex)

        else:
            # Διαφορετικά αυξάνουμε hurt sequence για animation
            e["hurt_seq"] = e.get("hurt_seq", 0) + 1

# Μηδενίζει την πρόοδο όλων των παικτών που υπάρχουν σε ένα snapshot λίστας
def reset_progress_for_players_snapshot(player_snapshots):
    for p in player_snapshots:
        player_id = p.get("player_id")  # Παίρνουμε το database player_id του παίκτ

        if not player_id:       # Αν δεν υπάρχει player_id, δεν μπορούμε να κάνουμε reset στη βάση
            continue

        try:    # Επαναφορά progress στη βάση: gold, XP, level και inventory
            reset_player_progress(player_id)
            print(f"Reset progress for player {player_id}")
        except Exception as ex:
            print(f"Error resetting progress for player {player_id}:", ex)

# Για όλους τους παίκτες του τρέχοντος παιχνιδιού, μηδενίζει την πρόοδό τους
def reset_progress_for_current_game():
    # Συνδυάζουμε τους ενεργούς παίκτες που υπάρχουν ακόμα στο players με active παίκτες που αποσυνδέθηκαν πρόσφατα αλλά ανήκαν στο ίδιο game
    snapshots = list(players.values()) + list(disconnected_active_players.values())
    reset_progress_for_players_snapshot(snapshots)

# Ελέγχει αν το παιχνίδι πρέπει να τελειώσει με ήττα
def check_loss_condition():
    global game_status

    if game_status != "playing":    # Αν το game δεν είναι ενεργό, δεν ελέγχουμε loss
        return

    if not players:                 # Αν δεν έχει συνδεθεί κανένας παίκτης, δεν θεωρείται loss
        return

    if session.phase != session.PHASE_PLAYING:  # Loss ελέγχουμε μόνο όταν το session βρίσκεται πραγματικά στη φάση playing
        return

    alive_players = 0

    for pid, p in players.items():  # Μετράμε μόνο τους active players του session
        if not session.is_active_player(pid):
            continue

        if not p.get("dead", False):    # Αν βρεθεί έστω ένας ζωντανός active player, το παιχνίδι συνεχίζεται
            alive_players += 1

    if alive_players == 0:      # Αν κανένας active player δεν είναι ζωντανός, το παιχνίδι τελειώνει με loss
        game_status = "loss"
        session.finish_game("loss")
        print("GAME OVER: All players died")

# Ελέγχει για παίκτες που δεν έχουν στείλει heartbeat, input για αρκετή ώρα και τους αφαιρεί από το παιχνίδι
def cleanup_stale_players():
    now = time.time()
    stale_pids = []

    for pid, p in players.items():  # Εντοπίζουμε ποιοι παίκτες έχουν ξεπεράσει το timeout όριο
        last_seen = p.get("last_seen", 0.0)

        if now - last_seen >= PLAYER_TIMEOUT_SECONDS:
            stale_pids.append(pid)

    for pid in stale_pids:  # Αφαιρούμε τους timed out παίκτες
        name = players.get(pid, {}).get("nickname", pid)
        print(f"Player {name} timed out")

        was_active = session.is_active_player(pid)  # Ελέγχουμε αν ο παίκτης ήταν active στο τρέχον session
        player_snapshot = players.get(pid)

        # Αν ήταν active player, κρατάμε snapshot πριν αφαιρεθεί
        if was_active and player_snapshot:
            disconnected_active_players[pid] = dict(player_snapshot)

        session_event = session.disconnect_player(pid)  # Ενημερώνουμε το session ότι ο παίκτης αποσυνδέθηκε

        connected.discard(pid)  # Αφαιρούμε τον παίκτη από τα runtime structures του server
        players.pop(pid, None)

        # Αν ο timed out παίκτης ήταν ο τελευταίος active player, το παιχνίδι θεωρείται εγκαταλελειμμένο και γίνεται reset
        if session_event == "game_abandoned":
            print("All active players timed out. Game abandoned and reset.")

            reset_progress_for_current_game()       # Μηδενίζουμε την πρόοδο όλων των παικτών που συμμετείχαν στο game

            # Καθαρίζουμε πλήρως τα runtime δεδομένα παικτών και session
            players.clear()
            connected.clear()
            disconnected_active_players.clear()
            reset_runtime_game_state()
            break

# Χειρίζεται την ολοκλήρωση του παιχνιδιού μετά από win ή loss
def handle_game_finished():
    global game_finished_handled

    if game_status == "playing":    # Αν το παιχνίδι συνεχίζεται, δεν γίνεται τίποτα
        return

    if game_finished_handled:       # Αποφεύγουμε να εκτελεστεί η διαδικασία τέλους πάνω από μία φορά
        return

    game_finished_handled = True

    print(f"Game finished with status: {game_status}. Resetting player progress...")

    reset_progress_for_current_game()   # Μετά από win ή loss μηδενίζεται η πρόοδος των παικτών του session

# Μέθοδος για το state των παικτών (connect/disconnect)
async def handle_control():
    global next_spawn_index, game_status, game_finished_handled, server_start_time, tick

    while True:
        msg = await control_socket.recv_json()  # Περιμένει και λαμβάνει τα μηνύματα ελέγχου
        pid = msg["id"]     # Το id του παίκτη
        typ = msg["type"]   # Τύπος αιτήματος (σύνδεση ή αποσύνδεση)

        # Σύνδεση παίκτη
        if typ == "connect":
            # Αν δεν έχει σταλεί nickname ή class_name, ορίζονται default τιμές
            nickname = msg.get("nickname") or pid
            class_name = msg.get("class_name") or "Warrior"

            normalized_nickname = nickname.strip().lower()  # Κανονικοποιούμε το nickname ώστε να μη διαφέρει λόγω κεφαλαίων/κενών

            # Ελέγχουμε αν υπάρχει ήδη συνδεδεμένος παίκτης με το ίδιο nickname
            existing_pid_for_nickname = None    

            for existing_pid, existing_player in players.items():
                if existing_player.get("nickname", "").strip().lower() == normalized_nickname:
                    existing_pid_for_nickname = existing_pid
                    break

            # Ο παίκτης θεωρείται ήδη συνδεδεμένος είτε αν υπάρχει το ίδιο pid, είτε αν υπάρχει άλλος runtime παίκτης με το ίδιο nickname
            player_already_connected = (
                pid in connected
                or existing_pid_for_nickname is not None
            )

            # Αν ο παίκτης είναι ήδη συνδεδεμένος αλλά το session είναι ακόμα στο lobby, επιτρέπουμε reconnect και αφαιρούμε την παλιά runtime εγγραφή
            if player_already_connected and session.phase == session.PHASE_LOBBY:
                old_pid = pid

                # Αν βρέθηκε παλιός παίκτης με ίδιο nickname, χρησιμοποιούμε το παλιό pid ώστε να αφαιρεθεί σωστά από players/connected/session
                if existing_pid_for_nickname is not None:
                    old_pid = existing_pid_for_nickname

                print(f"Reconnecting lobby player '{nickname}'")

                # Καθαρίζουμε την προηγούμενη lobby εγγραφή ώστε να γίνει νέα σύνδεση
                session.disconnect_player(old_pid)
                connected.discard(old_pid)
                players.pop(old_pid, None)

            # Αν ο παίκτης είναι ήδη συνδεδεμένος και το session δεν είναι lobby, απορρίπτουμε τη σύνδεση για να μη δημιουργηθεί διπλός παίκτης στο παιχνίδι
            elif player_already_connected:
                await control_socket.send_json({
                    "status": "error",
                    "reason": "Player already in game"
                })
                print(f"Rejected connection for nickname '{nickname}': already in game")
                continue

            # Αν το session έχει μείνει stuck σε playing/loading/finished αλλά δεν υπάρχουν players, το καθαρίζουμε ώστε να μπορεί να ξεκινήσει νέο lobby
            if session.phase not in (session.PHASE_IDLE, session.PHASE_LOBBY) and not players:
                print("Session was stuck without players. Resetting to idle.")
                session.reset_to_idle()
                reset_runtime_game_state()

            # Ελέγχουμε αν ο παίκτης μπορεί να επανασυνδεθεί σε ενεργό παιχνίδι από snapshot που κρατήθηκε όταν αποσυνδέθηκε
            reconnect_snapshot = disconnected_active_players.get(pid)
            allow_active_reconnect = False

            # Active reconnect επιτρέπεται μόνο όσο το session είναι σε playing
            if session.phase == session.PHASE_PLAYING:
                reconnect_snapshot = disconnected_active_players.get(pid)

                # Για ασφάλεια, επιβεβαιώνουμε ότι το nickname του snapshot ταιριάζει με το nickname του νέου connect request
                if reconnect_snapshot:
                    saved_nickname = reconnect_snapshot.get("nickname", "").strip().lower()

                    if saved_nickname == normalized_nickname:
                        allow_active_reconnect = True

            # Αν το παιχνίδι έχει ήδη ξεκινήσει και δεν πρόκειται για active reconnect, δεν επιτρέπεται νέος παίκτης να μπει στο τρέχον session
            if session.phase not in (session.PHASE_IDLE, session.PHASE_LOBBY) and not allow_active_reconnect:
                await control_socket.send_json({
                    "status": "error",
                    "reason": "Game already in progress. Please try again later."
                })
                print(f"Rejected connection for {pid}: game already in progress")
                continue

            # Επανασύνδεση παίκτη που ήταν active στο παιχνίδι και είχε αποσυνδεθεί προσωρινά
            if allow_active_reconnect:
                print(f"Reconnecting active player '{nickname}'")

                # Ο παίκτης ξαναμπαίνει στους active players του session
                player_session_phase = session.PHASE_PLAYING
                session.active_players.add(pid)

                # Επαναφέρουμε το προηγούμενο runtime state του παίκτη και ενημερώνουμε το last_seen ώστε να μη θεωρηθεί αμέσως timed out
                restored_player = disconnected_active_players.pop(pid)
                restored_player["last_seen"] = time.time()
                restored_player["session_phase"] = player_session_phase

                # Ο restored παίκτης μπαίνει ξανά στα runtime structures του server
                players[pid] = restored_player
                connected.add(pid)

                await control_socket.send_json({
                    "status": "ok",
                    "id": pid
                })

                continue

            # Αν δεν είναι active reconnect, ο παίκτης μπαίνει κανονικά στο lobby μέσω session manager
            else:
                player_session_phase = session.connect_player(pid)

            # Παίρνουμε τα στατιστικά της κλάσης, αν η κλάση δεν είναι έγκυρη γίνεται fallback
            try:    
                class_defs = get_player_type_defs(class_name)
            except ValueError:
                class_name = "Warrior"
                class_defs = get_player_type_defs(class_name)

            connected.add(pid)      # Προσθέτουμε τον παίκτη στο σύνολο των συνδεδεμένων

            # Παίρνουμε τα spawn points της αρχικής περιοχής
            start_region = regions[START_REGION]
            spawn_points = start_region.spawn_points

            # Επιλέγουμε spawn point κυκλικά, ώστε οι παίκτες να μη μπαίνουν όλοι πάντα στο ίδιο σημείο
            spawn_index = next_spawn_index
            next_spawn_index += 1

            x, y = spawn_points[spawn_index % len(spawn_points)]

            hp_max = class_defs.get("hp_max", 100)

            player_row = get_player_by_id(pid)      # Ελέγχουμε αν ο παίκτης υπάρχει ήδη στη βάση

            # Returning player: φορτώνουμε gold, XP, level, nickname και class από τη βάση
            if player_row is not None:
                db_player_id, db_nickname, db_class_name, db_gold, db_xp, db_level = player_row

                player_gold = db_gold
                player_xp = db_xp
                player_level = db_level

                # Αν είναι Returning Player, καλύτερα κρατάμε τα στοιχεία από τη βάση
                nickname = db_nickname
                class_name = db_class_name
                class_defs = get_player_type_defs(class_name)

                update_last_login(pid)  # Ενημερώνουμε την τελευταία σύνδεση του παίκτη

            else:   # Νέος runtime player χωρίς αποθηκευμένη πρόοδο
                player_gold = 0
                player_xp = 0
                player_level = class_defs.get("level", 1)

            player_inventory = load_player_inventory_payload(pid)   # Φορτώνουμε το inventory του παίκτη από τη βάση σε μορφή payload για το game state

            # Δημιουργία εγγραφής παίκτη
            players[pid] = {
                # Θέση στον χάρτη
                "x": x,         
                "y": y, 

                # Βασικά στοιχεία παίκτη και αποθηκευμένη πρόοδος
                "nickname": nickname,  
                "class_name": class_name,
                "player_id": pid,
                "gold": player_gold,
                "inventory": player_inventory,
                "level": player_level,
                "xp": player_xp,
                "xp_next": get_xp_next_for_level(player_level),
                "max_level": class_defs.get("max_level", 10),

                # Στατιστικά μάχης και resources
                "hp": 1.0,
                "hp_cur": hp_max,
                "hp_max": hp_max,
                "energy": 1.0,
                "resist": class_defs.get("resist", 0),
                "damage": class_defs.get("damage", 25),

                # Buffs από items/elixirs
                "item_buffs": {},
                "item_attack_speed_multiplier": 1.0,

                "attack_type": class_defs.get("attack_type", "melee"),
                "move_speed": class_defs.get("move_speed", SPEED),

                # Κατάσταση animation και ζωής
                "state": "idle",
                "dir": "down",
                "dead": False,
                "hurt_seq": 0,

                # Πεδία επίθεσης, cooldowns και pending hit timing
                "attack_requested": False,
                "attack_id": "basic",
                "attack_dir": "down",
                "attack_cooldown": class_defs["attacks"]["basic"].get("cooldown", 0.45),
                "next_attack_times": {
                    "basic": 0.0,
                    "skill1": 0.0,
                    "skill2": 0.0,
                },
                "attack_anim_until": 0.0,
                "attack_state": "attack",
                "pending_hit_time": 0.0,
                "rapid_fire_until": 0.0,

                # Κατεύθυνση κίνησης
                "move_dir": "STOP",

                # Περιοχή, session phase και χρόνος τελευταίας επικοινωνίας
                "region": START_REGION,
                "session_phase": player_session_phase,
                "last_seen": time.time(),
                }   
            
            apply_level_stats_from_saved_level(players[pid])    # Εφαρμόζουμε τα bonus stats που αντιστοιχούν στο αποθηκευμένο level του παίκτη

            print(f"Player {nickname} CONNECTED at spawn {spawn_index}")

            # Στέλνουμε επιβεβαίωση σύνδεσης στον client
            await control_socket.send_json({
                "status": "ok",
            })

        # Αποσύνδεση παίκτη
        elif typ == "disconnect":
            # Παίρνουμε το nickname, αν υπάρχει, αλλιώς χρησιμοποιούμε το player id
            name = players.get(pid, {}).get("nickname", pid)
            print(f"Player {name} DISCONNECTED")

            # Ελέγχουμε αν ο παίκτης συμμετείχε ενεργά στο τρέχον παιχνίδι
            was_active = session.is_active_player(pid)
            player_snapshot = players.get(pid)

            # Αν ήταν active player, κρατάμε snapshot πριν αφαιρεθεί για να μπορεί να γίνει reset progress ή reconnect ακόμα και μετά την αφαίρεση από players
            if was_active and player_snapshot:
                disconnected_active_players[pid] = dict(player_snapshot)

            session_event = session.disconnect_player(pid)  # Ενημερώνουμε το session manager ότι ο παίκτης αποσυνδέθηκε

            # Αφαιρούμε τον παίκτη από τα runtime structures
            connected.discard(pid)
            players.pop(pid, None)

            # Αν δεν έμεινε κανένας active player, το παιχνίδι θεωρείται abandoned και γίνεται reset της προόδου και του runtime state
            if session_event == "game_abandoned":
                print("All active players disconnected. Game abandoned and reset.")

                reset_progress_for_current_game()   # Reset progress για όλους τους παίκτες που συμμετείχαν στο τρέχον game

                # Καθαρίζουμε όλα τα runtime δεδομένα και επαναφέρουμε το game για νέο session
                players.clear()
                connected.clear()
                disconnected_active_players.clear()
                reset_runtime_game_state()

            await control_socket.send_json({"status": "ok"})    # Στέλνουμε επιβεβαίωση αποσύνδεσης στον client

# Μέθοδος που λαμβάνει και επεξεργάζεται τα inputs των παικτών
async def handle_inputs():
    while True:
        # Περιμένει μήνυμα input από κάποιον client
        msg = await pull_socket.recv_json()
        pid = msg["id"]

        # Αν ο παίκτης δεν υπάρχει πια, αγνοούμε το μήνυμα
        if pid not in players:
            continue

        # Heartbeat μήνυμα: ενημερώνει το last_seen του παίκτη ώστε να μη θεωρηθεί timed out από τον server
        if msg.get("heartbeat"):
            players[pid]["last_seen"] = time.time()
            continue

        if not session.can_player_play(pid):    # Inputs γίνονται δεκτά μόνο από παίκτες που συμμετέχουν ενεργά στο playing phase
            continue

        if game_status != "playing":            # Αν το παιχνίδι δεν είναι σε κατάσταση playing, αγνοούμε input ενεργειών
            continue

        # Input κίνησης από τον client
        if "move" in msg:
            direction = msg.get("move", "STOP")

            # Αν η κατεύθυνση δεν είναι έγκυρη, χρησιμοποιούμε STOP
            if direction not in ("UP", "DOWN", "LEFT", "RIGHT", "STOP"):
                direction = "STOP"

            # Αν ο παίκτης δεν είναι νεκρός, αποθηκεύουμε τη νέα κατεύθυνση κίνησης
            if not players[pid].get("dead", False):
                players[pid]["move_dir"] = direction

        # Αγορά item από τον παίκτη
        if "buy_item" in msg:
            item_name = msg.get("buy_item")

            if item_name not in (   # Επιτρέπουμε μόνο συγκεκριμένα items για λόγους ασφάλειας/ελέγχου
                "Health_Potion",
                "Energy_Potion",
                "ElixirOfToughness",
                "ElixirOfMagic",
                "ElixirOfPower"
            ):
                continue

            success, reason = buy_item_for_player(pid, item_name, 1)    # Η αγορά γίνεται μέσω βάσης, ώστε να ελεγχθεί gold και max stack

            if not success: # Αν η αγορά απέτυχε, δεν ενημερώνουμε το runtime inventory
                print(f"Purchase failed for {pid}: {reason}")
                continue

            # Μετά την αγορά ξαναφορτώνουμε gold από τη βάση
            player_row = get_player_by_id(pid)
            if player_row is not None:
                db_player_id, db_nickname, db_class_name, db_gold, db_xp, db_level = player_row
                players[pid]["gold"] = db_gold

            # Μετά την αγορά ξαναφορτώνουμε inventory από τη βάση
            players[pid]["inventory"] = load_player_inventory_payload(pid)

            print(f"Player {players[pid].get('nickname', pid)} bought {msg.get('buy_item')}")

        # Χρήση item από τον παίκτη
        if "use_item" in msg:
            item_name = msg.get("use_item")

            if item_name not in (   # Επιτρέπονται μόνο τα items που υποστηρίζονται από το παιχνίδι
                "Health_Potion",
                "Energy_Potion",
                "ElixirOfToughness",
                "ElixirOfMagic",
                "ElixirOfPower"
            ):
                continue

            p = players[pid]

            # Εφαρμόζουμε το effect, αν δεν μπορεί να εφαρμοστεί δεν καταναλώνουμε το item
            effect_ok, effect_reason = apply_item_effect(p, item_name)

            if not effect_ok:
                print(f"Use item failed for {pid}: {effect_reason}")
                continue

            consumed, reason = consume_item_for_player(pid, item_name)  # Αν εφαρμόστηκε, τότε το καταναλώνουμε από τη βάση

            if not consumed:
                print(f"Consume failed for {pid}: {reason}")

                # Αν απέτυχε το consume, αφαιρούμε το elixir buff ώστε να μη μείνει δωρεάν effect
                if item_name.startswith("Elixir"):
                    remove_item_buff(p, item_name)

                continue

            # Ξαναφορτώνουμε inventory από τη βάση μετά την κατανάλωση
            players[pid]["inventory"] = load_player_inventory_payload(pid)

            print(f"Player {players[pid].get('nickname', pid)} used {item_name}")

        # Input επίθεσης
        if msg.get("attack"):
            # Αν είναι νεκρός δεν μπορεί να επιτεθεί
            if players[pid].get("dead", False):
                continue

            now = time.time()

            # Αν υπάρχει ήδη attack request που δεν έχει επεξεργαστεί ακόμα, αγνοούμε επιπλέον attack inputs για να μην ανανεώνεται συνέχεια το animation lock
            if players[pid].get("attack_requested", False):
                continue

            # Παίρνουμε το attack id και κάνουμε fallback σε basic αν δεν είναι έγκυρο
            attack_id = msg.get("attack_id", "basic")
            if attack_id not in ("basic", "skill1", "skill2"):
                attack_id = "basic"

            class_name = players[pid].get("class_name", "Warrior")  # Παίρνουμε τα attack definitions της κλάσης του παίκτη

            try:
                class_defs = get_player_type_defs(class_name)
            except ValueError:
                class_defs = get_player_type_defs("Warrior")

            attacks = class_defs.get("attacks", {})

            if attack_id not in attacks:    # Αν το attack δεν υπάρχει για αυτή την κλάση, χρησιμοποιείται το basic
                attack_id = "basic"

            attack_defs = attacks[attack_id]

            # Αν το skill δεν έχει ξεκλειδωθεί από το level του παίκτη, δεν ξεκινά ούτε animation ούτε hit
            required_level = attack_defs.get("unlock_level", 1)
            if players[pid].get("level", 1) < required_level:
                continue

            # Αν δεν υπάρχει αρκετή ενέργεια, το attack απορρίπτεται
            energy_cost = attack_defs.get("energy_cost", 0.0)
            if players[pid].get("energy", 1.0) < energy_cost:
                continue

            next_attack_times = players[pid].setdefault("next_attack_times", {  # Local cooldowns στον server για κάθε attack
                "basic": 0.0,
                "skill1": 0.0,
                "skill2": 0.0,
            })

            # Αν ο παίκτης είναι ακόμα σε cooldown, δεν αλλάζουμε ούτε state ούτε attack_anim_until για να μην κολλάει ο παίκτης σε attack animation χωρίς πραγματικό hit
            if now < next_attack_times.get(attack_id, 0.0):
                players[pid]["attack_requested"] = False
                continue

            # Κατεύθυνση επίθεσης
            adir = msg.get("dir", "DOWN")

            # Αν η κατεύθυνση δεν είναι έγκυρη, χρησιμοποιούμε DOWN
            if adir not in ("UP", "DOWN", "LEFT", "RIGHT"):
                adir = "DOWN"

            # Αν το skill είναι buff, δεν αλλάζουμε animation/state
            # Απλώς στέλνουμε request για να το επεξεργαστεί το apply_player_attacks
            if attack_defs.get("type") == "buff":
                players[pid]["attack_requested"] = True
                players[pid]["attack_id"] = attack_id
                players[pid]["attack_dir"] = adir.lower()
                players[pid]["dir"] = adir.lower()
                continue

            # Για τα υπόλοιπα attacks παίρνουμε animation από τα stats
            attack_state = attack_defs.get("animation", "attack")

            # Αποθηκεύουμε το attack request στο runtime state του παίκτη
            players[pid]["attack_requested"] = True
            players[pid]["attack_id"] = attack_id
            players[pid]["attack_dir"] = adir.lower()
            players[pid]["dir"] = adir.lower()

            # Ενημερώνουμε το state ώστε οι clients να παίξουν το αντίστοιχο attack animation
            players[pid]["state"] = attack_state
            players[pid]["attack_state"] = attack_state

            # Υπολογίζουμε πόσο θα διαρκέσει το attack animation
            class_name = players[pid].get("class_name", "Warrior")
            anim_duration = get_player_attack_anim_duration(class_name, attack_state)

            players[pid]["attack_anim_until"] = now + anim_duration # Μέχρι αυτή τη χρονική στιγμή ο παίκτης θεωρείται ότι βρίσκεται σε attack animation

# Μέθοδος που ενημερώνει και μεταδίδει συνεχώς την κατάσταση του παιχνιδιού
async def broadcast_state():
    global tick, server_metrics_timer, server_tick_ms_samples, enemy_ai_timer

    while True:
        tick += 1       # Αύξηση του tick για κάθε frame / update

        tick_start = time.perf_counter()    # Αρχή μέτρησης χρόνου επεξεργασίας του tick

        elapsed_time = time.time() - server_start_time  # Χρόνος που έχει περάσει από την εκκίνηση του server

        # Αποθήκευση προηγούμενων θέσεων παικτών και εχθρών, ώστε να μπορούν να χρησιμοποιηθούν σε collision correction
        prev_players = {pid: (p["x"], p["y"]) for pid, p in players.items()}
        prev_enemies = {eid: (e["x"], e["y"]) for eid, e in enemies.items()}

        # Ενημέρωση όλων των παικτών
        for p in players.values():
            # Αν ο παίκτης είναι νεκρός, σταματάει να κινείται
            if p.get("dead", False):
                p["move_dir"] = "STOP"
                continue
            
            # Αναπλήρωση energy με βάση τον ρυθμό ανά δευτερόλεπτο και το tick duration
            p["energy"] = min(
                1.0,
                p.get("energy", 1.0) + ENERGY_REGEN_PER_SECOND * TICK_DT
            )

            # Αναπλήρωση HP με βάση την πραγματική τιμή hp_cur και ενημέρωση του ποσοστού hp που στέλνεται στον client
            hp_max = p.get("hp_max", 100)
            hp_cur = p.get("hp_cur", p.get("hp", 1.0) * hp_max)

            hp_cur = min(
                hp_max,
                hp_cur + HP_REGEN_PER_SECOND * TICK_DT
            )

            p["hp_cur"] = hp_cur
            p["hp_max"] = hp_max
            p["hp"] = hp_cur / hp_max

            direction = p.get("move_dir", "STOP")       # Παίρνουμε την τελευταία κατεύθυνση κίνησης που έστειλε ο client

            # Αρχικά η νέα θέση είναι ίδια με την τρέχουσα
            new_x = p["x"]
            new_y = p["y"]

            # Υπολογισμός νέας θέσης με βάση την κατεύθυνση
            if direction == "UP":
                new_y += SPEED
            elif direction == "DOWN":
                new_y -= SPEED
            elif direction == "LEFT":
                new_x -= SPEED
            elif direction == "RIGHT":
                new_x += SPEED

            # Παίρνουμε τα όρια της περιοχής στην οποία βρίσκεται ο παίκτης
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

            # Ενημέρωση visual state και direction του παίκτη
            if not p.get("dead", False):
                now = time.time()

                # Όσο διαρκεί το attack animation, δεν αλλάζουμε state από την κίνηση ώστε να μη διακοπεί οπτικά η επίθεση
                if now < p.get("attack_anim_until", 0.0):
                    p["dir"] = p.get("attack_dir", p.get("dir", "down"))
                    p["state"] = p.get("attack_state", "attack")
                else:
                    # Αν δεν υπάρχει ενεργό attack animation, το state εξαρτάται από την κίνηση
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
            
            player_transition(p)        # Ελέγχουμε αν ο παίκτης πάτησε σε transition area για αλλαγή περιοχής ή τελική νίκη

        cleanup_stale_players()         # Αφαιρεί παίκτες που δεν έχουν στείλει heartbeat/input για αρκετή ώρα

        session_events = session.update()   # Ενημερώνει το session manager και επιστρέφει πιθανά events αλλαγής φάσης

        # Όταν ξεκινά το playing phase, επαναφέρουμε το runtime game state
        for event in session_events:
            if event == "playing_started":
                reset_runtime_game_state()

            # Όταν ολοκληρωθεί η finished φάση, καθαρίζουμε παίκτες και runtime state
            elif event == "finished_cleared":
                reset_progress_for_current_game()

                players.clear()
                connected.clear()
                disconnected_active_players.clear()
                reset_runtime_game_state()

        # Εκτελούμε gameplay ενημερώσεις μόνο όσο το παιχνίδι είναι ενεργό
        if session.phase == session.PHASE_PLAYING and game_status == "playing":
            enemy_ai_timer += TICK_DT

            # Ενημέρωση εχθρών όταν περάσει το προκαθορισμένο interval
            if enemy_ai_timer >= ENEMY_AI_INTERVAL:
                update_enemy_chase_and_movement(enemy_ai_timer)
                enemy_ai_timer = 0.0

            # Εφαρμογή combat και buffs
            apply_enemy_attacks()
            apply_player_attacks()
            update_item_buffs()

            # Διόρθωση επικάλυψης παικτών/εχθρών και έλεγχος ήττας
            player_enemy_blocking(prev_players, prev_enemies)
            check_loss_condition()

        handle_game_finished()  # Αν το παιχνίδι έχει τελειώσει, χειριζόμαστε το reset προόδου μία φορά

        players_payload = {}    # Δημιουργούμε καθαρό payload παικτών για αποστολή στους clients

        for pid, p in players.items():
            # Αν το session παίζεται, δεν στέλνουμε παίκτες που δεν είναι active στο τρέχον game
            if session.phase == session.PHASE_PLAYING and not session.is_active_player(pid):
                continue

            # Δημιουργούμε λίστα με τα ενεργά elixirs και τον χρόνο που απομένει
            active_elixirs = []

            now = time.time()

            for item_name, buff in p.get("item_buffs", {}).items():
                remaining = max(0.0, buff.get("expires_at", 0.0) - now)

                if remaining > 0:
                    active_elixirs.append({
                        "item_name": item_name,
                        "remaining": remaining,
                        "duration": buff.get("duration", 60.0),
                    })

            # Υπολογίζουμε το objective της περιοχής του παίκτη ώστε ο client να εμφανίσει σωστό objective text progress
            objective_info = get_region_objective_info(p.get("region", START_REGION))

            # Δεδομένα του συγκεκριμένου παίκτη που θα σταλεί στους clients
            players_payload[pid] = {
                "x": p["x"],
                "y": p["y"],
                "region": p.get("region", START_REGION),

                "nickname": p.get("nickname", pid),
                "class_name": p.get("class_name", "Warrior"),

                "level": p.get("level", 1),
                "xp": p.get("xp", 0),
                "xp_next": p.get("xp_next", 0),

                "hp": p.get("hp", 1.0),
                "hp_cur": p.get("hp_cur", 100),
                "hp_max": p.get("hp_max", 100),
                "energy": p.get("energy", 1.0),

                "gold": p.get("gold", 0),
                "inventory": p.get("inventory", []),
                "active_elixirs": active_elixirs,

                "state": p.get("state", "idle"),
                "dir": p.get("dir", "down"),
                "dead": p.get("dead", False),
                "hurt_seq": p.get("hurt_seq", 0),

                "objective_text": objective_info["text"],
                "objective_remaining": objective_info["remaining"],
                "objective_complete": objective_info["complete"],
            }

        active_regions = get_active_regions()   # Περιοχές όπου υπάρχουν ζωντανοί παίκτες
        enemies_payload = {}                    # Δεδομένα εχθρών που θα σταλούν στους clients

        for eid, e in enemies.items():
            if e.get("region") not in active_regions:   # Αγνοούμε enemies από ανενεργές περιοχές
                continue

            enemies_payload[eid] = {    # Δεδομένα εχθρών που θα σταλούν στους clients
                "x": e["x"],
                "y": e["y"],
                "region": e.get("region", START_REGION),
                "type": e.get("type", "orc"),
                "state": e.get("state", "idle"),
                "dir": e.get("dir", "down"),
                "hp": e.get("hp", 1.0),
                "hp_max": e.get("hp_max", 1.0),
                "dead": e.get("dead", False),
                "hurt_seq": e.get("hurt_seq", 0),
                "attack_seq": e.get("attack_seq", 0),
            }

        # Έλεγχος loss, finished πριν σταλεί το state στους client
        check_loss_condition()
        handle_game_finished()

        # Στέλνει την κατάσταση του παιχνιδιού σε όλους τους πελάτες
        await pub_socket.send_json({
            "tick": tick,
            "tick_dt": TICK_DT,             # Διάρκεια κάθε "tick"
            "players": players_payload,     # Τρέχουσα κατάσταση παικτών
            "enemies": enemies_payload,     # Τρέχουσα κατάσταση εχθρών
            "elapsed_time": elapsed_time,   # Χρόνος που έχει περάσει από την έναρξη
            "game_status": game_status,     # Κατάσταση παιχνιδιού
            "session": session.get_public_state(),
            "player_session_status": {
                pid: session.get_player_phase(pid)
                for pid in players.keys()
            },
        })

        # Τέλος μέτρησης χρόνου επεξεργασίας του tick
        tick_end = time.perf_counter()
        tick_ms = (tick_end - tick_start) * 1000.0

        # Αποθήκευση του tick_ms στο προσωρινό sample list
        server_tick_ms_samples.append(tick_ms)

        # Αυξάνουμε τον timer με βάση το server tick interval
        server_metrics_timer += TICK_DT

        # Κάθε 20 δευτερόλεπτα γράφουμε συγκεντρωτικά αποτελέσματα στο CSV
        if server_metrics_timer >= server_metrics_interval:
            current_time = server_stats.elapsed_time()

            avg_tick_ms = sum(server_tick_ms_samples) / len(server_tick_ms_samples)
            max_tick_ms = max(server_tick_ms_samples)

            active_regions = get_active_regions()

            active_enemy_count = sum(
                1 for e in enemies.values()
                if e.get("region") in active_regions and not e.get("dead", False)
            )

            server_stats.write_row([
                round(current_time, 3),
                round(avg_tick_ms, 3),
                round(max_tick_ms, 3),
                len(players),
                active_enemy_count
            ])

            # Καθαρίζουμε τα samples για το επόμενο διάστημα 20 δευτερολέπτων
            server_tick_ms_samples.clear()
            server_metrics_timer = 0.0

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