import arcade
import asyncio
import threading
import zmq
import zmq.asyncio
from queue import Queue
import sys
import time
from classView import ClassSelectView
from login import MenuView
from playerView import CreatePlayerView
from sprites import (
    PlayerSprite, EnemySprite, ProjectileSprite,
    load_player_animations, load_enemy_animations,
    load_projectile_animations, get_enemy_type_defs,
    PROJECTILE_ANIMATION_CONFIGS, CLASS_SCALES, ENEMY_SCALES, IDLE, WALK, ATTACK, DEATH, WALK_ATTACK, DOWN, UP, LEFT, RIGHT,
)

# Windows fix για να λειτουργεί το asyncio με τον κατάλληλο event loop σε Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

REGION_MAPS = {
    "firstRegion": "assets/maps/firstRegion.tmx",
    "secondRegion": "assets/maps/secondRegion.tmx",
    "thirdRegion": "assets/maps/thirdRegion.tmx",
    "fourthRegion": "assets/maps/fourthRegion.tmx",
}

CLIENT_PLAYER_ID = None     # Player id
CLIENT_NICKNAME = None      # Player nickname

# Queue για μεταφορά game state από networking thread προς το main (Arcade) thread
state_queue = Queue()

# Global references
NETWORK_LOOP = None           # asyncio loop στο networking thread
SERVER_ACCEPTED = None        # True / False αφού απαντήσει ο server στο CONNECT
CONTROL_ACTIVE = True         # γίνeται False όταν κλείσει το παράθυρο
DISCONNECT_SENT = False       # γίνεται True όταν σταλεί DISCONNECT στον server

# ZeroMQ context για τη σύνδεση με τα sockets
ctx = zmq.asyncio.Context()

# PUSH socket, στέλνει inputs
push_socket = ctx.socket(zmq.PUSH)
push_socket.connect("tcp://127.0.0.1:5555")

# SUB socket, παίρνει το game state από το server
sub_socket = ctx.socket(zmq.SUB)
sub_socket.connect("tcp://127.0.0.1:5556")
sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

# CONTROL SOCKET, για σύνδεση/αποσύνδεση
control_socket = ctx.socket(zmq.REQ)
control_socket.connect("tcp://127.0.0.1:5557")

### Ασύγχρονες μέθοδοι για το δίκτυο ###

# Στέλνει input κίνησης στον server
async def send_move(direction: str):
    await push_socket.send_json({
        "id": CLIENT_PLAYER_ID,
        "move": direction
    })

# Στέλνει input επίθεσης στον server
async def send_attack(direction: str):
    await push_socket.send_json({
        "id": CLIENT_PLAYER_ID,
        "attack": True,
        "dir": direction
    })

# Λαμβάνει συνεχώς game state από τον server και το βάζει στην thread-safe queue
async def receive_state():
    while True:
        state = await sub_socket.recv_json()
        state_queue.put(state)

# Χειρίζεται CONNECT / DISCONNECT
async def control_loop():
    global SERVER_ACCEPTED, CONTROL_ACTIVE, DISCONNECT_SENT

    # Σύνδεση
    await control_socket.send_json({
        "type": "connect",
        "id": CLIENT_PLAYER_ID,
        "nickname": CLIENT_NICKNAME,
        "class_name": getattr(arcade.get_window(), "class_name", None)
    })
    reply = await control_socket.recv_json()
    print("[Control reply]:", reply)

    # Επιτυχής σύνδεση (πάντα)
    SERVER_ACCEPTED = True

    # Μένουμε ζωντανοί μέχρι να κλείσει το παράθυρο
    while CONTROL_ACTIVE:
        await asyncio.sleep(0.1)

    # Αποσύνδεση
    try:
        await control_socket.send_json({
            "type": "disconnect",
            "id": CLIENT_PLAYER_ID,
            "nickname": CLIENT_NICKNAME
        })
        await control_socket.recv_json()
    except Exception as e:
        print("Error sending DISCONNECT:", e)

    DISCONNECT_SENT = True
    print("[Client] Disconnect sent.")

# Κεντρικό async entry point του networking thread
async def io_main():
    asyncio.create_task(receive_state())
    asyncio.create_task(control_loop())

    # Περιμένουμε να μάθουμε αν ο server μας δέχτηκε ή όχι
    global SERVER_ACCEPTED
    while SERVER_ACCEPTED is None:
        await asyncio.sleep(0.05)

    # Κρατάμε το loop ζωντανό
    while True:
        await asyncio.sleep(1)

# Δημιουργεί νέο asyncio loop σε ξεχωριστό thread, το Arcade δεν μπορεί να είναι στο ίδιο thread με το asyncio
def thread_worker():
    global NETWORK_LOOP
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    NETWORK_LOOP = loop
    loop.create_task(io_main())
    loop.run_forever()

# Main Window
class GameWindow(arcade.Window):
    def on_close(self):
        global CONTROL_ACTIVE       # Χρησιμοποιούμε global flag ώστε το networking thread να καταλάβει ότι το παράθυρο έκλεισε
        CONTROL_ACTIVE = False      # Ο client δεν είναι πλέον ενεργός και θα σταλεί DISCONNECT στον server
        print("Window closed, will send DISCONNECT...")
        super().on_close()          # Κλείσιμο παραθύρου

# Connecting View
class ConnectingView(arcade.View):
    def __init__(self):
        super().__init__()

        # Text αντικείμενο που εμφανίζει μήνυμα σύνδεσης
        self.msg = arcade.Text("Connecting to server...", 0, 0, arcade.color.WHITE, 20, anchor_x="center")

    def on_show_view(self):
        arcade.set_background_color(arcade.color.BLACK)

        # Κεντράρουμε το μήνυμα στο παράθυρο
        self.msg.x = self.window.width // 2
        self.msg.y = self.window.height // 2

    def on_draw(self):
        self.clear()
        self.msg.draw() # Σχεδιάζουμε το μήνυμα σύνδεσης

    def on_update(self, delta_time: float):
        global SERVER_ACCEPTED      # Χρησιμοποιούμε global μεταβλητή που ενημερώνεται από το networking thread (control_loop)

        # Αν ο server απάντησε θετικά
        if SERVER_ACCEPTED is True:
            game_view = MyGame()                # Δημιουργούμε το βασικό Game View
            self.window.show_view(game_view)    # Αλλάζουμε view από Connecting → Game

        # Αν ο server απέρριψε τη σύνδεση
        elif SERVER_ACCEPTED is False:
            # Κλείνουμε το παράθυρο
            self.window.close()

# Game View
class MyGame(arcade.View):
    def __init__(self):
        super().__init__()

        self.player_animation_dict = {}     # Dictionary που κρατάει τα animation της κάθε κλάσης για χρήση (αντί να φορτώνεται από το δίσκο κάθε φορά)

        self.held_keys = set()    # Set που κρατάει ποια πλήκτρα είναι πατημένα (για hold keys)
        self.held_move = set()     # πατημένα WASD
        self.move_order = []       # σειρά πατημάτων WASD (τελευταίο στο τέλος)
        self.last_sent_move = None # για να μη στέλνουμε συνέχεια το ίδιο

        self.actor_list = arcade.SpriteList()   # Λίστα με όλα τα sprites που σχεδιάζονται

        self.enemy_list = arcade.SpriteList()   # Λίστα με τα sprites των εχθρών
        self.enemy_animation_dict = {}          # Λεξικό για animation ανά είδος εχθρού

        self.enemy_projectiles = arcade.SpriteList()    # Λίστα για τις μακρινές επιθέσεις των magic goblins
        self.projectile_animation_dict = {}             # Λεξικό για το animation των επιθέσεων των magic goblins

        self.attack_buffered = False
        self.attack_buffer_threshold = 0.70     # τελευταίο 30% του attack επιτρέπει buffer

        self.local_next_attack_time = 0.0       # Χρονική στιγμή που θα επιτρέπεται ξανά τοπικά νέο attack
        self.local_attack_cooldown = 0.45       # Τοπικό cooldown επίθεσης, ώστε να μην στέλνονται συνεχόμενα attack requests στον server
        self.buffer_attack_state = None         # Αποθηκεύει προσωρινά attack input που πατήθηκε λίγο πριν τελειώσει το τρέχον attack animation
        
        # Tilemap layers
        self.terrain_list = None
        self.road_list = None
        self.river_list = None
        self.wall_list = None
        self.bridge_list = None
        self.lava_list = None

        # Περιοχές
        self.current_region_name = None
        self.tile_map = None

        self.world_camera = arcade.Camera2D()   # Κάμερα για τον κόσμο

        self.elapsed_time = 0.0     # Χρόνος που έχει περάσει στο match (από server)

        self.player_animations = None   # Animations του local player
        self.player_sprite = None       # Sprite του τοπικού παίκτη

        self.other_sprites = {}         # Dict για τους άλλους παίκτες
        self.enemy_sprites = {}         # Dict για εχθρούς
        
        # Μεταβλητές για smoothing στην κίνηση
        self.position_buffers = {}      # Λεξικό που κρατά για κάθε παίκτη τις δύο πιο πρόσφατες θέσεις του με server tick για εξομάλυνση κίνησης
        self.snapshots = {}             # Θέση sprite τη στιγμή που ήρθε το τελευταίο update
        self.interp_t = {}              # Xρόνος που πέρασε από το τελευταίο server update

        # text για τον χρόνο παιχνιδιού (timer)
        self.timer_text = arcade.Text(
            "00:00",
            10, 10,
            arcade.color.WHITE,
            font_size=20
        )

        # text για μήνυμα αλλαγής περιοχής
        self.region_message = ""
        self.region_message_timer = 0.0

        self.region_message_text = arcade.Text(
            "",
            0, 0,
            arcade.color.WHITE,
            font_size=20,
            anchor_x="center",
            anchor_y="center"
        )

    # Μέθοδος για την κίνηση του παίκτη πίσω από τα walls (έξω από το collision point)
    def sort_key(self, sprite):
        offset = 0
        if hasattr(sprite, "properties"):
            offset = sprite.properties.get("sort_offset", 0)

        # Αν είναι player sprite, κάνουμε sort με βάση τα "πόδια" (bottom)
        if isinstance(sprite, (PlayerSprite, EnemySprite)):
            return sprite.bottom

        return sprite.center_y + offset     # Για όλα τα άλλα sprites, sort με βάση το center_y + offset
    
    # Μέθοδος που φορτώνει την περιοχή που αντιστοιχεί στο region_name
    def load_region(self, region_name: str):
        if region_name not in REGION_MAPS:      # Αν το region δεν υπάρχει στο dictionary REGION_MAPS, σταματάμε με error
            raise RuntimeError(f"Unknown region '{region_name}'")

        self.current_region_name = region_name  # Αποθηκεύουμε το όνομα της τρέχουσας περιοχής

        self.tile_map = arcade.load_tilemap(    # Φορτώνουμε το αντίστοιχο TMX map από το Tiled
            REGION_MAPS[region_name],
            scaling=1.0,
            use_spatial_hash=True
        )

        # Visual/collision layers του χάρτη
        self.terrain_list = self.tile_map.sprite_lists.get("Terrain", arcade.SpriteList())
        self.road_list = self.tile_map.sprite_lists.get("Road", arcade.SpriteList())
        self.lava_list = self.tile_map.sprite_lists.get("Lava", arcade.SpriteList())
        self.river_list = self.tile_map.sprite_lists.get("River", arcade.SpriteList())
        self.wall_list = self.tile_map.sprite_lists.get("Walls", arcade.SpriteList())
        self.bridge_list = self.tile_map.sprite_lists.get("Bridge", arcade.SpriteList())

        # Υπολογισμός διαστάσεων του map σε pixels
        self.map_width = self.tile_map.width * self.tile_map.tile_width
        self.map_height = self.tile_map.height * self.tile_map.tile_height

        # Ξαναδημιουργούμε τις λίστες sprites μετά τη φόρτωση νέας περιοχής, ώστε να περιέχουν τα σωστά sprites και να διατηρείται σωστό draw order
        self.actor_list = arcade.SpriteList()
        self.enemy_projectiles = arcade.SpriteList()

        for w in self.wall_list:                # Προσθέτουμε τα walls στο actor_list, ώστε να σχεδιάζονται μαζί με τα υπόλοιπα αντικείμενα
            self.actor_list.append(w)

        if self.player_sprite is not None:      # Προσθέτουμε τον τοπικό παίκτη στη νέα actor_list
            self.actor_list.append(self.player_sprite)

        for spr in self.other_sprites.values(): # Προσθέτουμε τους υπόλοιπους παίκτες
            self.actor_list.append(spr)

        for spr in self.enemy_sprites.values(): # Προσθέτουμε τους εχθρούς
            self.actor_list.append(spr)

        if self.player_sprite is not None:      # Αν υπάρχει player sprite, τοποθετούμε την κάμερα πάνω στον παίκτη μετά τη φόρτωση της περιοχής
            self.world_camera.position = (
                self.player_sprite.center_x,
                self.player_sprite.center_y
            )
    
    # Μέθοδος για την κάμερα
    def update_camera(self):
        # Αν δεν υπάρχει ακόμα player, δεν κάνουμε τίποτα
        if not self.player_sprite:
            return

        # Θέση παίκτη
        px = self.player_sprite.center_x
        py = self.player_sprite.center_y

        # Τρέχουσα θέση κάμερας
        cam_x, cam_y = self.world_camera.position

        # Περιοχή όπου ο παίκτης μπορεί να κινείται χωρίς να κινείται η κάμερα
        dead_w = 120
        dead_h = 80

        left = cam_x - dead_w
        right = cam_x + dead_w
        bottom = cam_y - dead_h
        top = cam_y + dead_h

        # Τρέχουσα θέση κάμερας
        target_x = cam_x
        target_y = cam_y

        # Αν ο παίκτης βγει από την περιοχή που ορίσαμε, μετακινούμε την κάμερα
        if px < left:
            target_x = px + dead_w
        elif px > right:
            target_x = px - dead_w

        if py < bottom:
            target_y = py + dead_h
        elif py > top:
            target_y = py - dead_h

        # Όρια του map για να μην φεύγει εκτός η κάμερα
        half_w = self.world_camera.viewport_width / 2
        half_h = self.world_camera.viewport_height / 2

        target_x = max(half_w, min(target_x, self.map_width - half_w))
        target_y = max(half_h, min(target_y, self.map_height - half_h))

        # Smoothing κάμερας
        lerp = 0.15
        self.world_camera.position = (
            cam_x + (target_x - cam_x) * lerp,
            cam_y + (target_y - cam_y) * lerp
        )

    # Μέθοδος εμφάνισης UI για HP, energy για παίκτες
    def draw_player_status_bars(self, spr: PlayerSprite):
        # θέση πάνω από το κεφάλι
        x = spr.center_x
        y = spr.top + 18

        # διαστάσεις
        w = 54
        hp_h = 7
        energy_h = 3
        gap = 2

        # values 
        hp = max(0.0, min(1.0, getattr(spr, "hp", 1.0)))
        en = max(0.0, min(1.0, getattr(spr, "energy", 1.0)))

        left = x - w / 2

        # nickname
        spr.nickname_text.text = getattr(spr, "nickname", "")
        spr.nickname_text.x = x
        spr.nickname_text.y = y + hp_h
        spr.nickname_text.draw()

        # level
        spr.level_text.text = str(getattr(spr, "level", 1))
        spr.level_text.x = left - gap
        spr.level_text.y = y + hp_h / 2
        spr.level_text.draw()

        # backgrounds
        arcade.draw_lbwh_rectangle_filled(left - 1, y - 1, w + 2, hp_h + 2, arcade.color.BLACK)
        arcade.draw_lbwh_rectangle_filled(left - 1, y - (energy_h + gap) - 1, w + 2, energy_h + 2, arcade.color.BLACK)

        # HP
        arcade.draw_lbwh_rectangle_filled(left, y, w, hp_h, arcade.color.DARK_GREEN)
        arcade.draw_lbwh_rectangle_filled(left, y, w * hp, hp_h, arcade.color.GREEN)

        # ENERGY
        y2 = y - (energy_h + gap)
        arcade.draw_lbwh_rectangle_filled(left, y2, w, energy_h, arcade.color.DARK_YELLOW)
        arcade.draw_lbwh_rectangle_filled(left, y2, w * en, energy_h, arcade.color.YELLOW)

    # Μέθοδος εμφάνισης UI για HP, energy για εχθρούς
    def draw_enemy_status_bars(self, spr: EnemySprite):
        # θέση πάνω από το κεφάλι
        x = spr.center_x
        y = spr.top + 18

        # διαστάσεις
        w = 54
        hp_h = 7

        hp_ratio = 0.0                          # Υπολογίζουμε το ποσοστό ζωής του sprite για τη μπάρα HP
        if getattr(spr, "hp_max", 0) > 0:       # Αν υπάρχει έγκυρο μέγιστο HP, υπολογίζουμε τρέχον HP / μέγιστο HP
            hp_ratio = spr.hp / spr.hp_max
        hp_ratio = max(0.0, min(1.0, hp_ratio)) # Περιορίζουμε το ποσοστό ζωής στο διάστημα 0.0 - 1.0

        left = x - w / 2

        # nickname
        spr.nickname_text.text = getattr(spr, "nickname", "")
        spr.nickname_text.x = x
        spr.nickname_text.y = y + hp_h + 3
        spr.nickname_text.draw()

        # HP background
        arcade.draw_lbwh_rectangle_filled(left - 1, y - 1, w + 2, hp_h + 2, arcade.color.BLACK)

        # HP bar
        arcade.draw_lbwh_rectangle_filled(left, y, w, hp_h, arcade.color.BLACK)
        arcade.draw_lbwh_rectangle_filled(left, y, w * hp_ratio, hp_h, arcade.color.RED)

    # Μέθοδος που καθαρίζει όλα τα τοπικά inputs του παίκτη
    def stop_local_input(self):
        self.held_keys.clear()      # Καθαρίζουμε τα πλήκτρα που θεωρούνται πατημένα
        self.held_move.clear()      # Καθαρίζουμε τις ενεργές κατευθύνσεις κίνησης
        self.move_order.clear()     # Καθαρίζουμε τη σειρά με την οποία πατήθηκαν τα πλήκτρα κίνησης

        # Ακυρώνουμε τυχόν buffered attack
        self.attack_buffered = False
        self.buffer_attack_state = None

        if self.player_sprite:      # Αν υπάρχει τοπικό player sprite, καθαρίζουμε την κατεύθυνση επίθεσης
            self.player_sprite.attack_dir = None

            # Αν ο παίκτης δεν είναι σε death animation, τον επιστρέφουμε οπτικά σε idle state
            if not getattr(self.player_sprite, "death_started", False):
                self.player_sprite.base_state = IDLE
                self.player_sprite.base_direction = self.player_sprite.last_direction
                self.player_sprite.force_state(IDLE, self.player_sprite.last_direction, reset=False)

        if self.last_sent_move is not None: # Καθαρίζουμε την τελευταία κίνηση που στάλθηκε στον server, ώστε να μπορεί να σταλεί ξανά STOP αν χρειαστεί
            self.last_sent_move = None

        if NETWORK_LOOP is not None:        # Αν υπάρχει ενεργό network loop, στέλνουμε STOP στον server για να σταματήσει η server-side κίνηση του παίκτη
            asyncio.run_coroutine_threadsafe(send_move("STOP"), NETWORK_LOOP)

    # Μέθοδος για την αρχικοποίηση του View όταν γίνεται ενεργό
    def on_show_view(self):
        # Reset κάμερας
        self.world_camera.position = (0, 0)
        self.world_camera.zoom = 1.0

        arcade.set_background_color(arcade.color.BLACK)

        self.current_region_name = None

        # Φόρτωση animations με βάση την κλάση που διάλεξε ο παίκτης
        if not hasattr(self.window, "class_name") or not self.window.class_name:
            raise RuntimeError("No class selected! window.class_name is missing.")

        chosen_class = self.window.class_name
        print("Loading animations for:", chosen_class)
        self.player_animations = load_player_animations(chosen_class)
        self.player_animation_dict[chosen_class] = self.player_animations

        # Δημιουργία player sprite
        if self.player_sprite is None:
            player_scale = CLASS_SCALES.get(chosen_class, 2.0)
            self.player_sprite = PlayerSprite(self.player_animations, scale=player_scale)

            # Βάζει το nickname από το login
            self.player_sprite.nickname = getattr(self.window, "nickname", "Player")

            # Προσωρινά stats
            self.player_sprite.hp = 1.0
            self.player_sprite.energy = 1.0
            self.player_sprite.level = getattr(self.window, "level", 1)
        
        self.load_region("firstRegion")

        # Τοποθέτηση timer στο UI
        self.timer_text.x = 10
        self.timer_text.y = self.window.height - 30

        self.attack_buffered = False

        self.held_keys.clear()  # Καθαρισμός input
        self.held_move.clear()
        self.move_order.clear()
        self.last_sent_move = None

    # Μέθοδος που καλείται όταν το συγκεκριμένο view παύει να εμφανίζεται
    def on_hide_view(self):
        self.stop_local_input()

    # Μέθοδος που καλείται όταν το παράθυρο χάνει focus
    def on_deactivate(self):
        self.stop_local_input()

    # Ζωγραφίζουμε τα αντικείμενα
    def on_draw(self):
        self.clear()

        # Ενεργοποίηση world camera
        with self.world_camera.activate():
            if self.terrain_list:
                self.terrain_list.draw()        # Ζωγραφίζουμε terrain

            if self.road_list:
                self.road_list.draw()           # Ζωγραφίζουμε δρόμο

            if self.lava_list:
                self.lava_list.draw()           # Ζωγραφίζουμε λάβα

            if self.river_list:
                self.river_list.draw()          # Ζωγραφίζουμε ποτάμι

            # Layer γέφυρας
            if self.bridge_list:
                self.bridge_list.draw()

            # Ταξινόμηση αντικειμένων με βάση το Y (για σωστό βάθος)
            self.actor_list.sort(key=self.sort_key)  # Ζωγραφίζουμε όλα τα sprites
            self.actor_list.draw()

            # Projectiles εχθρών
            self.enemy_projectiles.draw()

            # Μπάρες για local player
            if self.player_sprite:
                self.draw_player_status_bars(self.player_sprite)

            # Μπάρες για άλλους παίκτες
            for spr in self.other_sprites.values():
                if isinstance(spr, PlayerSprite):
                    self.draw_player_status_bars(spr)

            # Μπάρες για enemies
            for spr in self.enemy_sprites.values():
                if isinstance(spr, EnemySprite) and not getattr(spr, "dead", False):
                    self.draw_enemy_status_bars(spr)

        self.timer_text.draw()      # Ζωγραφίζουμε το timer

        # Εμφάνιση μηνύματος στο κέντρο της οθόνης όταν αλλάξουμε περιοχή
        if self.region_message:
            box_width = 420
            box_height = 80

            left = self.window.width / 2 - box_width / 2
            right = self.window.width / 2 + box_width / 2
            bottom = self.window.height / 2 - box_height / 2
            top = self.window.height / 2 + box_height / 2

            arcade.draw_lrbt_rectangle_filled(
                left,
                right,
                bottom,
                top,
                (0, 0, 0, 180)
            )

            self.region_message_text.draw()

    # Μέθοδος που διαβάζει το πιο πρόσφατο state που έστειλε ο server και ενημερώνει τις τοπικές δομές (buffers, snapshots, sprites)
    def process_server_state(self):
        # Αν δεν υπάρχει κανένα state στην ουρά, δεν κάνουμε τίποτα
        if state_queue.empty():
            return None

        # Παίρνουμε μόνο το πιο πρόσφατο state και αγνοούμε τα παλαιότερα, ώστε ο client να μη μένει πίσω αν έχουν μαζευτεί πολλά updates
        latest_state = None
        while not state_queue.empty():
            latest_state = state_queue.get()

        # Αν για κάποιο λόγο δεν πήραμε state, σταματάμε
        if latest_state is None:
            return None
        
        # Παίρνουμε το tick του server (αύξων μετρητής)
        tick = latest_state.get("tick")
        if tick is None:
            return None
        
        # Διάρκεια ενός tick στον server
        tick_dt = latest_state.get("tick_dt", 0.02)
        self.tick_dt = tick_dt

        # Χρόνος αγώνα (elapsed time) από τον server
        self.elapsed_time = latest_state.get("elapsed_time", self.elapsed_time)

        # Κατάσταση όλων των παικτών από τον server
        players_state = latest_state.get("players", {})
        enemies_state = latest_state.get("enemies", {})

        # Ελέγχουμε αν ο τοπικός παίκτης άλλαξε περιοχή σύμφωνα με τον server
        local_player_state = players_state.get(CLIENT_PLAYER_ID)
        if local_player_state is not None:
            new_region = local_player_state.get("region", "firstRegion")
            if new_region != self.current_region_name:
                self.load_region(new_region)

                # Μήνυμα αλλαγής περιοχής
                self.region_message = "Proceeding to the next region..."
                self.region_message_timer = 1.5
                self.region_message_text.text = self.region_message
                self.region_message_text.x = self.window.width / 2
                self.region_message_text.y = self.window.height / 2

                # Καθαρίζουμε τα interpolation buffers ώστε να μη γίνει οπτικό glitch από παλιές θέσεις της προηγούμενης περιοχής
                self.position_buffers.clear()
                self.snapshots.clear()
                self.interp_t.clear()

                # Επανατοποθετούμε την κάμερα κοντά στον παίκτη μετά την αλλαγή περιοχής
                if self.player_sprite is not None:
                    self.world_camera.position = (
                        self.player_sprite.center_x,
                        self.player_sprite.center_y
                    )

        # Ενημέρωση του timer σε μορφή mm:ss
        minutes = int(self.elapsed_time) // 60
        seconds = int(self.elapsed_time) % 60
        self.timer_text.text = f"{minutes:02d}:{seconds:02d}"

        # Για κάθε παίκτη που υπάρχει στο server state
        for pid, pos in players_state.items():
            player_region = pos.get("region", "firstRegion")

            # Αγνοούμε παίκτες που βρίσκονται σε άλλη περιοχή από αυτή που βλέπει ο client
            if self.current_region_name is not None and player_region != self.current_region_name:
                continue

            # Διαβάζουμε τα βασικά δεδομένα του παίκτη που έστειλε ο server
            x = pos["x"]
            y = pos["y"]
            nickname = pos.get("nickname", pid)
            class_name = pos.get("class_name", "Warrior")   # Default τιμή για fallback
            level = pos.get("level", 1)
            hp = pos.get("hp", 1.0)
            energy = pos.get("energy", 1.0)
            pstate = pos.get("state", IDLE)
            pdir = pos.get("dir", DOWN)
            phurt_seq = pos.get("hurt_seq", 0)
            pdead = pos.get("dead", False)

            # Αν είναι ο τοπικός παίκτης, χρησιμοποιούμε το main sprite
            if pid == CLIENT_PLAYER_ID:
                sprite = self.player_sprite
            else:
                # Αν είναι άλλος παίκτης και δεν έχουμε sprite, το δημιουργούμε
                if pid not in self.other_sprites:
                    if class_name not in self.player_animation_dict:
                        self.player_animation_dict[class_name] = load_player_animations(class_name)

                    player_scale = CLASS_SCALES.get(class_name, 2.0)
                    spr = PlayerSprite(self.player_animation_dict[class_name], scale=player_scale)
                    self.other_sprites[pid] = spr
                    self.actor_list.append(spr)
                sprite = self.other_sprites[pid]

            # Ενημέρωση UI fields
            sprite.nickname = nickname
            sprite.level = level
            sprite.hp = hp
            sprite.energy = energy

            # Για τους remote players το animation state συγχρονίζεται απευθείας από τον server
            # Για τον local player αποφεύγουμε να το κάνουμε εδώ, ώστε να μη χαλάει το τοπικό attack animation
            if pid != CLIENT_PLAYER_ID:
                sprite.set_base_state(pstate, pdir)

            # Αν ο server δηλώσει ότι ο παίκτης πέθανε, ξεκινάμε death animation
            # Αν αυξήθηκε το hurt_seq, σημαίνει ότι δέχτηκε νέο hit και ενεργοποιούμε hurt feedback
            if pdead:
                sprite.trigger_death(pdir)
            elif phurt_seq > getattr(sprite, "last_hurt_seq", 0):
                sprite.last_hurt_seq = phurt_seq
                sprite.trigger_hurt(pdir)

            # Buffer θέσεων: κρατάμε τις δύο πιο πρόσφατες θέσεις που έστειλε ο server, ώστε να γίνει ομαλή κίνηση/interpolation
            buf = self.position_buffers.setdefault(pid, [])
            buf.append((x, y, tick))
            if len(buf) > 2:
                buf.pop(0)

            # Snapshot: αποθηκεύουμε την τρέχουσα θέση του sprite τη στιγμή που ήρθε το update, ώστε το interpolation να ξεκινήσει από αυτή τη θέση
            self.snapshots[pid] = (sprite.center_x, sprite.center_y)
            
            self.interp_t[pid] = 0.0    # Μηδενίζουμε τον τοπικό interpolation timer για το νέο update

        # Καθαρισμός remote players που δεν υπάρχουν πλέον στο server state, ή δεν βρίσκονται στην τρέχουσα περιοχή
        existing_pids = {
            pid for pid, pos in players_state.items()
            if pos.get("region", "firstRegion") == self.current_region_name and pid != CLIENT_PLAYER_ID
        }

        # Αφαιρούμε το sprite και καθαρίζουμε τα αντίστοιχα interpolation δεδομένα
        for pid in list(self.other_sprites.keys()):
            if pid not in existing_pids:
                spr = self.other_sprites[pid]
                self.actor_list.remove(spr)
                del self.other_sprites[pid]
                self.position_buffers.pop(pid, None)
                self.snapshots.pop(pid, None)
                self.interp_t.pop(pid, None)

        # Ενημέρωση εχθρών με βάση το server state
        for eid, epos in enemies_state.items():
            enemy_region = epos.get("region", "firstRegion")

            # Αγνοούμε εχθρούς που βρίσκονται σε άλλη περιοχή
            if self.current_region_name is not None and enemy_region != self.current_region_name:
                continue

            # Διαβάζουμε τα βασικά δεδομένα του εχθρού που έστειλε ο server
            ex = epos["x"]
            ey = epos["y"]
            etype = epos.get("type", "orc")
            estate = epos.get("state", IDLE)
            edir = epos.get("dir", DOWN)
            hp = epos.get("hp", 1.0)
            hp_max = epos.get("hp_max", 1.0)
            dead = epos.get("dead", False)
            hurt_seq = epos.get("hurt_seq", 0)
            attack_seq = epos.get("attack_seq", 0)

            # Αν δεν υπάρχει ακόμα sprite για τον συγκεκριμένο εχθρό, το δημιουργούμε
            if eid not in self.enemy_sprites:
                if etype not in self.enemy_animation_dict:
                    self.enemy_animation_dict[etype] = load_enemy_animations(etype)

                enemy_scale = ENEMY_SCALES.get(etype, 1.9)
                espr = EnemySprite(etype, self.enemy_animation_dict[etype], scale=enemy_scale)
                
                self.enemy_sprites[eid] = espr
                self.enemy_list.append(espr)
                self.actor_list.append(espr)   # για depth sort μαζί με όλους

            espr = self.enemy_sprites[eid]

            # Ενημερώνουμε θέση, ζωή και όνομα του enemy sprite
            espr.center_x = ex
            espr.center_y = ey
            espr.hp = hp
            espr.hp_max = hp_max
            espr.nickname = etype

            # Αν ο enemy είναι νεκρός, ενεργοποιούμε death animation
            if dead:
                espr.trigger_death(edir)

            # Αν έχει δεχτεί νέο hit, ενεργοποιούμε hurt animation
            elif hurt_seq > getattr(espr, "last_hurt_seq", 0):
                espr.last_hurt_seq = hurt_seq
                espr.trigger_hurt(edir)

            # Αν ξεκίνησε νέο attack σύμφωνα με τον server,
            # κάνουμε reset το attack animation ώστε να παίξει από την αρχή.
            elif estate in (ATTACK, WALK_ATTACK) and attack_seq > getattr(espr, "last_attack_seq", 0):
                espr.last_attack_seq = attack_seq
                espr.force_state(estate, edir, reset=True)

            # Αν δεν υπάρχει νέο attack/hurt/death, απλά συγχρονίζουμε το base state
            else:
                espr.set_base_state(estate, edir)
        
        # Κρατάμε μόνο τους enemies που υπάρχουν ακόμα στο server state και βρίσκονται στην τρέχουσα περιοχή
        existing_eids = {
            eid for eid, epos in enemies_state.items()
            if epos.get("region", "firstRegion") == self.current_region_name
        }

        # Αφαιρούμε enemy sprites που δεν υπάρχουν πλέον ή ανήκουν σε άλλη περιοχή
        for eid in list(self.enemy_sprites.keys()):
            if eid not in existing_eids:
                spr = self.enemy_sprites.pop(eid)
                spr.remove_from_sprite_lists()

    # Μέθοδος που κάνει interpolation και extrapolation ώστε η κίνηση των παικτών να φαίνεται ομαλή
    def apply_smoothing(self, delta_time):
        # Αν δεν υπάρχει player ή client id, δεν κάνουμε τίποτα
        if CLIENT_PLAYER_ID is None or self.player_sprite is None:
            return

        # Δημιουργούμε ενιαίο dict με όλα τα sprites
        all_sprites = {CLIENT_PLAYER_ID: self.player_sprite}
        all_sprites.update(self.other_sprites)

        for pid, sprite in all_sprites.items():
            buf = self.position_buffers.get(pid)
            if not buf:
                continue

            # Αν έχουμε μόνο μία θέση, πάμε κατευθείαν εκεί
            if len(buf) == 1:
                x, y, _ = buf[0]
                sprite.center_x = x
                sprite.center_y = y
                continue

            # Παίρνουμε τις δύο πιο πρόσφατες θέσεις από τον server
            (x0, y0, tick0), (x1, y1, tick1) = buf[0], buf[1]
            dt_ticks = tick1 - tick0
            dt_server = dt_ticks * getattr(self, "tick_dt", 0.02)

            # Αν κάτι πάει στραβά με τα ticks
            if dt_ticks <= 0 or dt_server <= 0:
                # Πάμε απευθείας στην τελευταία θέση
                target_x, target_y = x1, y1
            else:
                # Υπολογισμός ταχύτητας
                vx = (x1 - x0) / dt_server
                vy = (y1 - y0) / dt_server

                # Extrapolation: πρόβλεψη θέσης λίγο μπροστά
                prediction_dt = getattr(self, "tick_dt", 0.02)
                target_x = x1 + vx * prediction_dt
                target_y = y1 + vy * prediction_dt

            # Τοπικός χρόνος interpolation
            t_local = self.interp_t.get(pid, 0.0) + delta_time
            self.interp_t[pid] = t_local

            # Παράμετρος interpolation 0 ή 1
            if dt_server > 0:
                x_param = t_local / dt_server
            else:
                x_param = 1.0

            if x_param > 1.0:
                x_param = 1.0
            elif x_param < 0.0:
                x_param = 0.0

            # Θέση snapshot (αφετηρία interpolation)
            snap_x, snap_y = self.snapshots.get(pid, (sprite.center_x, sprite.center_y))

            # Linear interpolation (LERP)
            sprite.center_x = snap_x + (target_x - snap_x) * x_param
            sprite.center_y = snap_y + (target_y - snap_y) * x_param

    # Μέθοδος που καλείται κάθε frame συντονίζει networking, κίνηση, animation και κάμερα
    def on_update(self, delta_time):
        # Ενημέρωση κατάστασης από τον server
        self.process_server_state()

        # Εφαρμογή smoothing στην κίνηση
        self.apply_smoothing(delta_time)

        # Αποστολή movement input στον server
        # Ο client στέλνει μόνο μία κατεύθυνση κάθε φορά, με λογική last pressed wins
        if NETWORK_LOOP is not None and self.player_sprite:
            s = self.player_sprite.state

            if s == DEATH or getattr(self.player_sprite, "death_started", False):   # Αν ο παίκτης είναι νεκρός, δεν στέλνουμε κίνηση
                move_dir = None

            # Αν ο παίκτης βρίσκεται σε στάσιμο attack animation, σταματάμε την κίνηση μέχρι να ολοκληρωθεί το attack
            elif s == ATTACK and self.player_sprite.attack_dir is not None: 
                move_dir = None

            else:
                # Παίρνουμε την τελευταία ενεργή WASD κατεύθυνση και τη μετατρέπουμε σε string για αποστολή στον server
                current_move_dir = self.get_current_move_dir()
                move_dir = self.dir_to_move_str(current_move_dir)

            # Στέλνουμε νέο movement command μόνο όταν αλλάξει η κατεύθυνση
            # Αν δεν υπάρχει πλέον κίνηση, στέλνουμε STOP μία φορά
            if move_dir is None:
                if self.last_sent_move is not None:
                    self.last_sent_move = None
                    asyncio.run_coroutine_threadsafe(send_move("STOP"), NETWORK_LOOP)
            else:
                if move_dir != self.last_sent_move:
                    self.last_sent_move = move_dir
                    asyncio.run_coroutine_threadsafe(send_move(move_dir), NETWORK_LOOP)

        # Ενημέρωση του local animation state με βάση το input, μόνο όταν δεν παίζει attack ή death animation
        if self.player_sprite:
            active_attack = (
                self.player_sprite.state in (ATTACK, WALK_ATTACK)
                and self.player_sprite.attack_dir is not None
            )

            if (
                not active_attack
                and not getattr(self.player_sprite, "death_started", False)
            ):
                current_move_dir = self.get_current_move_dir()

                # Αν κρατιέται πλήκτρο κίνησης, ο local player δείχνει walk προς αυτή την κατεύθυνση
                if current_move_dir is not None:
                    self.player_sprite.last_direction = current_move_dir
                    self.player_sprite.set_base_state(WALK, current_move_dir)

                # Αν δεν υπάρχει κίνηση, επιστρέφει σε idle κοιτώντας την τελευταία κατεύθυνση
                else:
                    self.player_sprite.set_base_state(IDLE, self.player_sprite.last_direction)

        # Ενημέρωση animation του τοπικού παίκτη
        if self.player_sprite:
            self.player_sprite.update_animation(delta_time)

            # Αν έχει ολοκληρωθεί death animation και πρέπει να αφαιρεθεί, αφαιρείται από τα sprite lists
            if getattr(self.player_sprite, "despawn", False):
                self.player_sprite.remove_from_sprite_lists()

            # Αν τελείωσε το attack animation, ελέγχουμε αν υπάρχει buffered attack
            # Αν υπάρχει, προσπαθούμε να το εκτελέσουμε άμεσα, αλλιώς επιστρέφουμε σε walk/idle
            if self.player_sprite.attack_finished:
                self.player_sprite.attack_finished = False

                # Αν ο παίκτης πάτησε ξανά attack όσο το προηγούμενο attack animation ήταν ακόμα ενεργό,
                # τότε έχουμε αποθηκεύσει αυτό το input στο attack_buffered
                if self.attack_buffered:
                    now = time.time()

                    # Αν το cooldown δεν έχει τελειώσει, ακυρώνουμε το buffered attack και επιστρέφουμε τον παίκτη σε walk ή idle
                    if now < self.local_next_attack_time:
                        self.attack_buffered = False
                        self.buffer_attack_state = None
                        self.player_sprite.attack_dir = None

                        move_dir = self.get_current_move_dir()

                        if move_dir is not None:
                            self.player_sprite.last_direction = move_dir
                            self.player_sprite.base_state = WALK
                            self.player_sprite.base_direction = move_dir
                            self.player_sprite.force_state(WALK, move_dir, reset=True)
                        else:
                            self.player_sprite.base_state = IDLE
                            self.player_sprite.base_direction = self.player_sprite.last_direction
                            self.player_sprite.force_state(IDLE, self.player_sprite.last_direction, reset=True)

                    # Αν το cooldown έχει τελειώσει, εκτελούμε το buffered attack
                    else:
                        self.attack_buffered = False
                        next_state = getattr(self, "buffer_attack_state", None) or ATTACK   # Παίρνουμε το επόμενο attack state που είχε αποθηκευτεί
                        self.buffer_attack_state = None     # Καθαρίζουμε το αποθηκευμένο state αφού το χρησιμοποιήσαμε

                        self.local_next_attack_time = now + self.local_attack_cooldown

                        current_move_dir = self.get_current_move_dir()
                        self.player_sprite.attack_dir = current_move_dir or self.player_sprite.last_direction   # Κλειδώνουμε την κατεύθυνση του νέου attack στην τελευταία κατεύθυνση του παίκτη
                        self.player_sprite.last_direction = self.player_sprite.attack_dir
                        
                        self.player_sprite.base_state = next_state  # Ενημερώνουμε το base state ώστε, όσο το attack είναι ενεργό, το sprite να θεωρεί ως κύρια κατάσταση το νέο attack
                        self.player_sprite.base_direction = self.player_sprite.attack_dir
                        self.player_sprite.force_state(next_state, self.player_sprite.attack_dir, reset=True)   # Αναγκάζουμε το sprite να ξεκινήσει αμέσως το νέο attack animation από το frame 0

                        # Στέλνουμε το buffered attack στον server
                        if NETWORK_LOOP is not None:
                            dir_str = self.dir_to_move_str(self.player_sprite.attack_dir)
                            if dir_str is not None:
                                asyncio.run_coroutine_threadsafe(send_attack(dir_str), NETWORK_LOOP)

                else:
                    # Δεν υπάρχει buffered attack, άρα ξεκλειδώνουμε την κατεύθυνση επίθεσης και επιστρέφουμε τον παίκτη σε walk ή idle ανάλογα με το input
                    self.player_sprite.attack_dir = None    
                    self.player_sprite.attack_finished = False
                    move_dir = self.get_current_move_dir()

                    if move_dir is not None:
                        self.player_sprite.last_direction = move_dir
                        self.player_sprite.base_state = WALK
                        self.player_sprite.base_direction = move_dir
                        self.player_sprite.force_state(WALK, move_dir, reset=True)
                    else:
                        self.player_sprite.base_state = IDLE
                        self.player_sprite.base_direction = self.player_sprite.last_direction
                        self.player_sprite.force_state(IDLE, self.player_sprite.last_direction, reset=True)

        # Ενημέρωση animation των remote players
        for spr in self.other_sprites.values():
            spr.update_animation(delta_time)

        # Ενημέρωση animation εχθρών
        for e in list(self.enemy_list):
            e.update_animation(delta_time)

            self.spawn_enemy_projectile_if_needed(e)    # Αν ο enemy είναι ranged, ελέγχουμε αν βρίσκεται στο σωστό attack frame ώστε να δημιουργηθεί projectile

            if getattr(e, "despawn", False):    # Αν έχει τελειώσει το death animation και έχει περάσει το hold time, το EnemySprite κάνει despawn
                e.remove_from_sprite_lists()

        # Ενημέρωση enemy projectiles
        self.enemy_projectiles.update() 

        # Διατρέχουμε όλα τα ενεργά enemy projectiles
        for projectile in list(self.enemy_projectiles):
            projectile.update_animation(delta_time)

            # Σύγκρουση projectile με παίκτη
            if self.player_sprite and arcade.check_for_collision(projectile, self.player_sprite):
                projectile.remove_from_sprite_lists()
                continue

            if getattr(projectile, "remove_me", False): # Αν το projectile έχει φτάσει το max_range του, το αφαιρούμε
                projectile.remove_from_sprite_lists()
            
        # Ενημέρωση κάμερας
        self.update_camera()

        if self.region_message_timer > 0:
            self.region_message_timer -= delta_time
            if self.region_message_timer <= 0:
                self.region_message_timer = 0
                self.region_message = ""

    # Μέθοδος που επιστρέφει την τελευταία κατεύθυνση από WASD που πατήθηκε και εξακολουθεί να κρατιέται πατημένη
    def get_current_move_dir(self):
        for k in reversed(self.move_order):     # Λογική last pressed wins
            if k in self.held_move:
                if k == arcade.key.W:
                    return UP
                elif k == arcade.key.S:
                    return DOWN
                elif k == arcade.key.A:
                    return LEFT
                elif k == arcade.key.D:
                    return RIGHT

        return None     # Αν δεν κρατιέται κανένα πλήκτρο κίνησης, δεν υπάρχει ενεργή κατεύθυνση
    
    # Μέθοδος για τα projectile των ranged εχθρών
    def spawn_enemy_projectile_if_needed(self, enemy: EnemySprite):
        enemy_def = get_enemy_type_defs(enemy.enemy_type)

        if enemy_def.get("attack_type") != "ranged":    # Θέλουμε μόνο ranged χαρακτήρες
            return

        if enemy.state not in (ATTACK, WALK_ATTACK):    # Το projectile πρέπει να δημιουργείται μόνο όταν ο enemy βρίσκεται σε attack animation
            return

        if enemy.projectile_spawned:    # Κάθε attack animation έχει μόνο ένα projectile
            return

        spawn_frame = enemy_def.get("projectile_spawn_frame", 7)    # Frame του attack animation στο οποίο θα εμφανιστεί το projectile

        if enemy.cur_frame < spawn_frame:   # Αν το animation δεν έχει φτάσει ακόμα στο κατάλληλο frame, περιμένουμε
            return

        projectile_type = enemy_def.get("projectile_type")
        if projectile_type is None:         # Αν δεν έχει οριστεί projectile type, δεν δημιουργείται projectile
            return

        if projectile_type not in self.projectile_animation_dict:   # Αν δεν έχουν φορτωθεί ακόμα τα animations του projectile, τα φορτώνουμε
            self.projectile_animation_dict[projectile_type] = load_projectile_animations(projectile_type)

        projectile_cfg = PROJECTILE_ANIMATION_CONFIGS[projectile_type]  # Παίρνουμε τις ρυθμίσεις του projectile

        # Δημιουργία του projectile sprite με βάση την κατεύθυνση του εχθρού
        projectile = ProjectileSprite(
            animations=self.projectile_animation_dict[projectile_type],
            direction=enemy.direction,
            speed=enemy_def.get("projectile_speed", 7.0),
            damage=enemy_def.get("damage", 1),
            max_range=enemy_def.get("projectile_range", 260),
            scale=projectile_cfg.get("scale", 2.0),
        )

        # Η επίθεση του goblin έρχεται λίγο πάνω από το κέντρο του σώματός του
        projectile.center_x = enemy.center_x
        projectile.center_y = enemy.center_y + 15

        self.enemy_projectiles.append(projectile)   # Προσθέτουμε το projectile στη λίστα των enemy projectiles

        enemy.projectile_spawned = True             # Σημειώνουμε ότι το projectile δημιουργήθηκε, ώστε να μη δημιουργηθεί ξανά στο ίδιο attack animation

    # Μέθοδος που επιστρέφει True αν ο παίκτης κρατάει κάποιο πλήκτρο κίνησης
    def is_moving_input(self):
        return len(self.held_move) > 0   

    # Μέθοδος για τις λειτουργίες με το πάτημα κουμπιών
    def on_key_press(self, key, modifiers):
        # Πλήκτρα κίνησης WASD
        # Τα αποθηκεύουμε πάντα, ακόμα και αν ο παίκτης βρίσκεται σε attack animation, ώστε να ξέρουμε ποια κατεύθυνση κρατάει ο χρήστης
        if key in (arcade.key.W, arcade.key.A, arcade.key.S, arcade.key.D):
            self.held_move.add(key)

            # Το πλήκτρο που πατήθηκε τελευταίο μπαίνει στο τέλος της λίστας, έτσι εφαρμόζεται λογική last pressed wins
            if key in self.move_order:
                self.move_order.remove(key)
            self.move_order.append(key)

            # Άμεση αλλαγή facing direction για τον local player
            if self.player_sprite:
                if key == arcade.key.W:
                    direction = UP
                elif key == arcade.key.S:
                    direction = DOWN
                elif key == arcade.key.A:
                    direction = LEFT
                elif key == arcade.key.D:
                    direction = RIGHT

                # Ελέγχουμε αν ο παίκτης βρίσκεται ήδη σε attack animation, αν επιτίθεται δεν αλλάζουμε την κατεύθυνση του animation
                active_attack = (
                    self.player_sprite.state in (ATTACK, WALK_ATTACK)
                    and self.player_sprite.attack_dir is not None
                )

                # Αν δεν υπάρχει ενεργό attack και ο παίκτης δεν πεθαίνει, ενημερώνουμε άμεσα το local animation σε walk
                if (
                    not active_attack
                    and not getattr(self.player_sprite, "death_started", False)
                ):
                    self.player_sprite.last_direction = direction
                    self.player_sprite.base_state = WALK
                    self.player_sprite.base_direction = direction
                    self.player_sprite.force_state(WALK, direction, reset=False)

            return
    
        # Πλήκτρο επίθεσης
        # Χρησιμοποιείται local cooldown και attack buffering, ώστε να μη στέλνονται συνεχόμενες επιθέσεις στον server
        if key == arcade.key.SPACE and self.player_sprite:
            now = time.time()
            spr = self.player_sprite

            # Αν ο παίκτης είναι νεκρός, δεν μπορεί να επιτεθεί
            if spr.state == DEATH or getattr(spr, "death_started", False):
                return

            attack_state = ATTACK

            # Ελέγχουμε αν υπάρχει ήδη ενεργό attack animation
            active_attack = spr.state in (ATTACK, WALK_ATTACK) and spr.attack_dir is not None

            if active_attack:
                # Υπολογίζουμε την πρόοδο του attack animation
                frames = spr.animations[spr.state][spr.direction]
                progress = spr.cur_frame / (len(frames) - 1) if len(frames) > 1 else 1.0

                # Αν το attack πλησιάζει στο τέλος, επιτρέπουμε να αποθηκευτεί ένα buffered attack
                if progress >= self.attack_buffer_threshold and not self.attack_buffered:
                    self.attack_buffered = True
                    self.buffer_attack_state = attack_state

                return
            
            if now < self.local_next_attack_time:   # Αν δεν έχει τελειώσει το local cooldown, δεν ξεκινάμε νέο attack
                return
            
            # Αν ο παίκτης κινείται δεν ξεκινάμε άμεσα attack, το αποθηκεύουμε ως buffered ώστε να εκτελεστεί όταν σταματήσει η κίνηση
            if self.is_moving_input():
                self.attack_buffered = True
                self.buffer_attack_state = ATTACK
                return

            # Ξεκινάμε νέο attack τώρα
            self.local_next_attack_time = now + self.local_attack_cooldown

            # Καθαρίζουμε τυχόν προηγούμενο buffered attack
            self.attack_buffered = False
            self.buffer_attack_state = None

            # Κλειδώνουμε την κατεύθυνση του attack για όλη τη διάρκειά του
            current_move_dir = self.get_current_move_dir()
            spr.attack_dir = current_move_dir or spr.last_direction
            spr.last_direction = spr.attack_dir

            # Ενημερώνουμε άμεσα το local animation του παίκτη
            spr.base_state = attack_state
            spr.base_direction = spr.attack_dir
            spr.force_state(attack_state, spr.attack_dir, reset=True)
        
            # Στέλνουμε το attack request στον server
            if NETWORK_LOOP is not None:
                dir_str = self.dir_to_move_str(spr.attack_dir)
                if dir_str is not None:
                    asyncio.run_coroutine_threadsafe(send_attack(dir_str), NETWORK_LOOP)

            return

        # Όλα τα υπόλοιπα πλήκτρα αποθηκεύονται ξεχωριστά, ώστε να μπορούν να χρησιμοποιηθούν αργότερα για spells ή άλλες ενέργειες
        self.held_keys.add(key)

    # Μέθοδος για τις λειτουργίες με το που αφήσουμε κάποιο κουμπί
    def on_key_release(self, key, modifiers):
        # Απελευθέρωση πλήκτρων κίνησης WASD
        if key in (arcade.key.W, arcade.key.A, arcade.key.S, arcade.key.D):
            self.held_move.discard(key)     # Αφαιρούμε το πλήκτρο από τις ενεργές κατευθύνσεις

            if key in self.move_order:      # Αφαιρούμε το πλήκτρο και από τη σειρά πατημένων κινήσεων
                self.move_order.remove(key)

            if self.player_sprite:
                active_attack = (           # Αν παίζει attack animation, δεν αλλάζουμε το animation state από την κίνηση
                    self.player_sprite.state in (ATTACK, WALK_ATTACK)
                    and self.player_sprite.attack_dir is not None
                )

                if (
                    not active_attack
                    and not getattr(self.player_sprite, "death_started", False)
                ):
                    move_dir = self.get_current_move_dir()  # Ελέγχουμε αν υπάρχει άλλο πλήκτρο κίνησης που συνεχίζει να κρατιέται

                    if move_dir is not None:
                        # Αν υπάρχει άλλη ενεργή κατεύθυνση, συνεχίζουμε με walk προς αυτήν
                        self.player_sprite.last_direction = move_dir
                        self.player_sprite.base_state = WALK
                        self.player_sprite.base_direction = move_dir
                        self.player_sprite.force_state(WALK, move_dir, reset=False)
                    else:
                        # Αν δεν υπάρχει πλέον κίνηση, ελέγχουμε αν υπάρχει buffered attack
                        if self.attack_buffered:
                            now = time.time()

                            # Αν έχει περάσει το cooldown, εκτελούμε το buffered attack
                            if now >= self.local_next_attack_time:
                                self.attack_buffered = False
                                self.buffer_attack_state = None

                                self.local_next_attack_time = now + self.local_attack_cooldown

                                # Το attack γίνεται προς την τελευταία κατεύθυνση που κοιτούσε ο παίκτης
                                self.player_sprite.attack_dir = self.player_sprite.last_direction
                                self.player_sprite.base_state = ATTACK
                                self.player_sprite.base_direction = self.player_sprite.attack_dir
                                self.player_sprite.force_state(ATTACK, self.player_sprite.attack_dir, reset=True)

                                # Στέλνουμε το buffered attack στον server
                                if NETWORK_LOOP is not None:
                                    dir_str = self.dir_to_move_str(self.player_sprite.attack_dir)
                                    if dir_str is not None:
                                        asyncio.run_coroutine_threadsafe(send_attack(dir_str), NETWORK_LOOP)

                                return

                        # Αν δεν υπάρχει κίνηση ούτε buffered attack, ο παίκτης επιστρέφει σε idle animation
                        self.player_sprite.base_state = IDLE
                        self.player_sprite.base_direction = self.player_sprite.last_direction
                        self.player_sprite.force_state(IDLE, self.player_sprite.last_direction, reset=False)

            return

        # Απελευθέρωση άλλων πλήκτρων
        self.held_keys.discard(key)
    
    # Μέθοδος για μετατροπή κατεύθυνσης από client constants σε strings για τον server
    def dir_to_move_str(self, d):
        if d == UP: return "UP"
        if d == DOWN: return "DOWN"
        if d == LEFT: return "LEFT"
        if d == RIGHT: return "RIGHT"

        return None # Αν δεν υπάρχει έγκυρη κατεύθυνση, δεν επιστρέφεται τίποτα

def main():
    # Χρησιμοποιούμε global μεταβλητές που ελέγχουν αν ο server δέχτηκε τον client και αν στάλθηκε DISCONNECT
    global SERVER_ACCEPTED, DISCONNECT_SENT

    window = GameWindow(1000, 800, "Celestial Lands")   # Δημιουργία του κεντρικού παραθύρου του παιχνιδιού
    window.game_mode = None                             # Μεταβλητή που δηλώνει τον τύπο παιχνιδιού
    window.network_started = False                      # Flag για να μη ξεκινήσει το networking thread πάνω από μία φορά

    # Μέθοδος που καλείται όταν ο χρήστης ξεκινά το παιχνίδι
    def start_game():
        global SERVER_ACCEPTED, CLIENT_PLAYER_ID, CLIENT_NICKNAME        # Χρησιμοποιούμε global για το player id, το nickname και την απάντηση του server

        # Αν ο χρήστης ξεκινά νέο παιχνίδι
        if window.game_mode == "NEW_GAME":
            # Αν δεν έχει δημιουργηθεί ακόμα player
            if not hasattr(window, "player_id"):
                # Πηγαίνουμε στο view δημιουργίας χαρακτήρα
                window.show_view(CreatePlayerView())
                return
            
            if not hasattr(window, "class_name") or not window.class_name:
                window.show_view(ClassSelectView())
                return

        # Παίρνουμε το player id και το nickname που δημιουργήθηκε στο menu / character creation
        CLIENT_PLAYER_ID = window.player_id
        CLIENT_NICKNAME = window.nickname

        # Έλεγχος ώστε το networking thread να ξεκινήσει μία φορά
        if not window.network_started:
            window.network_started = True

            SERVER_ACCEPTED = None  # Reset της απάντησης του server πριν το connect

            # Δημιουργία ξεχωριστού thread για networking (asyncio + zmq)
            t = threading.Thread(
                target=thread_worker,   # συνάρτηση που τρέχει το event loop
                daemon=True             # daemon ώστε να κλείσει μαζί με το πρόγραμμα
            )
            print("CLIENT_PLAYER_ID =", CLIENT_PLAYER_ID)
            t.start()   # Εκκίνηση του networking thread

        # Αντί να μπλοκάρουμε το main thread, εμφανίζουμε το ConnectingView μέχρι να απαντήσει ο server
        window.show_view(ConnectingView())

    # Συνδέουμε τη συνάρτηση start_game με το window ώστε να μπορεί να καλείται από το MenuView
    window.start_game = start_game

    # Εμφανίζουμε αρχικά το βασικό μενού
    window.show_view(MenuView())

    # Κεντράρουμε το παράθυρο στην οθόνη
    window.center_window()

    # Εκκίνηση του main loop του Arcade
    arcade.run()

    # Εδώ έχει κλείσει το παράθυρο

    # Αν το networking είχε ξεκινήσει
    if window.network_started:
        # Θέτουμε timeout ασφαλείας 5 δευτερολέπτων
        timeout = time.time() + 5  
        # Περιμένουμε να σταλεί το DISCONNECT ή να λήξει το timeout πριν τερματίσει η διαδικασία
        while not DISCONNECT_SENT and time.time() < timeout:
            time.sleep(0.01)

    sys.exit(0) # Τερματισμός της εφαρμογής

if __name__ == "__main__":
    main()