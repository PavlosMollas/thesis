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
    load_enemy_animations, load_player_animations, EnemySprite, PlayerSprite,
    IDLE, WALK, ATTACK, HURT, DEATH, WALK_ATTACK,
    DOWN, UP, LEFT, RIGHT, CLASS_SCALES
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

# Στέλνει input κίνησης στον server.
async def send_move(direction: str):
    await push_socket.send_json({
        "id": CLIENT_PLAYER_ID,
        "move": direction
    })

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
        # Movement μόνο (WASD): last pressed wins
        self.held_move = set()     # πατημένα WASD
        self.move_order = []       # σειρά πατημάτων WASD (τελευταίο στο τέλος)
        self.last_sent_move = None # για να μη στέλνουμε συνέχεια το ίδιο

        self.actor_list = arcade.SpriteList()   # Λίστα με όλα τα sprites που σχεδιάζονται

        self.enemy_list = arcade.SpriteList()   # Λίστα με τα sprites των εχθρών
        self.enemy_animation_dict = {}          # Λεξικό για animation ανά είδος εχθρού

        self.attack_buffered = False
        self.attack_buffer_threshold = 0.70  # τελευταίο 30% του attack επιτρέπει buffer
        
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
    
    def load_region(self, region_name: str):
        if region_name not in REGION_MAPS:
            raise RuntimeError(f"Unknown region '{region_name}'")

        self.current_region_name = region_name

        self.tile_map = arcade.load_tilemap(
            REGION_MAPS[region_name],
            scaling=1.0,
            use_spatial_hash=True
        )

        # Visual layers
        self.terrain_list = self.tile_map.sprite_lists.get("Terrain")
        self.road_list = self.tile_map.sprite_lists.get("Road")
        self.lava_list = self.tile_map.sprite_lists.get("Lava")
        self.river_list = self.tile_map.sprite_lists.get("River")
        self.wall_list = self.tile_map.sprite_lists.get("Walls", arcade.SpriteList())
        self.bridge_list = self.tile_map.sprite_lists.get("Bridge")

        self.map_width = self.tile_map.width * self.tile_map.tile_width
        self.map_height = self.tile_map.height * self.tile_map.tile_height

        # ξαναχτίζουμε actor_list για σωστό draw order
        self.actor_list = arcade.SpriteList()

        for w in self.wall_list:
            self.actor_list.append(w)

        if self.player_sprite is not None:
            self.actor_list.append(self.player_sprite)

        for spr in self.other_sprites.values():
            self.actor_list.append(spr)

        for spr in self.enemy_sprites.values():
            self.actor_list.append(spr)

        if self.player_sprite is not None:
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

    def draw_enemy_status_bars(self, spr: EnemySprite):
        x = spr.center_x
        y = spr.top + 18

        w = 54
        hp_h = 7

        hp_ratio = 0.0
        if getattr(spr, "hp_max", 0) > 0:
            hp_ratio = spr.hp / spr.hp_max
        hp_ratio = max(0.0, min(1.0, hp_ratio))

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

    # Καθαρίζουμε τα πατημένα πλήκτρα όταν φεύγουμε από το view
    def on_hide_view(self):
        self.attack_buffered = False
        self.held_keys.clear()
        self.held_move.clear()
        self.move_order.clear()
        self.last_sent_move = None

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

        # Παίρνουμε το πιο πρόσφατο state και αδειάζουμε την ουρά
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

        # Αλλαγή περιοχής
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

                # καθάρισε interpolation buffers για να μη γίνει οπτικό glitch
                self.position_buffers.clear()
                self.snapshots.clear()
                self.interp_t.clear()

                # reset camera κοντά στον player
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
            if self.current_region_name is not None and player_region != self.current_region_name:
                continue

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
                    #spr.class_name = class_name
                    self.other_sprites[pid] = spr
                    self.actor_list.append(spr)
                sprite = self.other_sprites[pid]

            # ενημέρωση UI fields
            sprite.nickname = nickname
            sprite.level = level
            sprite.hp = hp
            sprite.energy = energy

            # server-driven visual sync
            if pid != CLIENT_PLAYER_ID or sprite.state not in (ATTACK, WALK_ATTACK):
                sprite.set_base_state(pstate, pdir)

            if pdead:
                sprite.trigger_death(pdir)
            elif phurt_seq > getattr(sprite, "last_hurt_seq", 0):
                sprite.last_hurt_seq = phurt_seq
                sprite.trigger_hurt(pdir)

            # Buffer θέσεων: κρατάμε τις 2 πιο πρόσφατες θέσεις από τον server
            buf = self.position_buffers.setdefault(pid, [])
            buf.append((x, y, tick))
            if len(buf) > 2:
                buf.pop(0)

            # Snapshot: αποθηκεύουμε τη θέση του sprite όταν ήρθε το update ώστε να κάνουμε interpolation από εκεί
            self.snapshots[pid] = (sprite.center_x, sprite.center_y)
            
            # Reset του τοπικού χρονικού παραμέτρου interpolation
            self.interp_t[pid] = 0.0

        # Καθαρισμός παικτών που δεν υπάρχουν πια στο server state
        existing_pids = {
            pid for pid, pos in players_state.items()
            if pos.get("region", "firstRegion") == self.current_region_name and pid != CLIENT_PLAYER_ID
        }

        for pid in list(self.other_sprites.keys()):
            if pid not in existing_pids:
                spr = self.other_sprites[pid]
                self.actor_list.remove(spr)
                del self.other_sprites[pid]
                self.position_buffers.pop(pid, None)
                self.snapshots.pop(pid, None)
                self.interp_t.pop(pid, None)

        for eid, epos in enemies_state.items():
            enemy_region = epos.get("region", "firstRegion")
            if self.current_region_name is not None and enemy_region != self.current_region_name:
                continue

            ex = epos["x"]
            ey = epos["y"]
            etype = epos.get("type", "orc")
            estate = epos.get("state", IDLE)
            edir = epos.get("dir", DOWN)
            hp = epos.get("hp", 1.0)
            hp_max = epos.get("hp_max", 1.0)
            dead = epos.get("dead", False)
            hurt_seq = epos.get("hurt_seq", 0)

            # create if missing
            if eid not in self.enemy_sprites:
                if etype not in self.enemy_animation_dict:
                    self.enemy_animation_dict[etype] = load_enemy_animations(etype)

                espr = EnemySprite(etype, self.enemy_animation_dict[etype])
                self.enemy_sprites[eid] = espr
                self.enemy_list.append(espr)
                self.actor_list.append(espr)   # για depth sort μαζί με όλους

            espr = self.enemy_sprites[eid]

            # update fields
            espr.center_x = ex
            espr.center_y = ey
            espr.hp = hp
            espr.hp_max = hp_max
            espr.nickname = etype

            # state/dir
            espr.set_base_state(estate, edir)

            # remove if dead 
            if dead:
                espr.trigger_death(edir)
            elif hurt_seq > getattr(espr, "last_hurt_seq", 0):
                espr.last_hurt_seq = hurt_seq
                espr.trigger_hurt(edir)
        
        existing_eids = {
            eid for eid, epos in enemies_state.items()
            if epos.get("region", "firstRegion") == self.current_region_name
        }

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

            # Έλεγχος αν ο παίκτης κινείται
            move_dx = x1 - x0
            move_dy = y1 - y0
            moving = abs(move_dx) > 0.01 or abs(move_dy) > 0.01

            # --- IMPORTANT: Μην overwrit-άρεις combat states του local player ---
            if sprite.state in (ATTACK, HURT, DEATH, WALK_ATTACK):
                # προαιρετικά: μπορείς να ενημερώνεις last_direction από την κίνηση, αλλά όχι state
                locked = getattr(sprite, "attack_dir", None)
                if locked is not None:
                    sprite.direction = locked
                    sprite.last_direction = locked
                continue  # ή continue (αν είσαι μέσα σε loop)

            # Ορισμός animation και κατεύθυνσης
            if moving:
                if abs(move_dx) > abs(move_dy):
                    direction = RIGHT if move_dx > 0 else LEFT
                else:
                    direction = UP if move_dy > 0 else DOWN

                sprite.last_direction = direction
                sprite.set_state(WALK, direction)
            else:
                sprite.set_state(IDLE, sprite.last_direction)

    # Μέθοδος που καλείται κάθε frame συντονίζει networking, κίνηση, animation και κάμερα
    def on_update(self, delta_time):
        # Ενημέρωση κατάστασης από τον server
        self.process_server_state()

        # Εφαρμογή smoothing στην κίνηση
        self.apply_smoothing(delta_time)

        # Αποστολή movement input στον server (μόνο 1 κατεύθυνση: last pressed wins)
        if NETWORK_LOOP is not None and self.player_sprite:
            s = self.player_sprite.state

            if s in (ATTACK, HURT, DEATH):
                # attack στάσιμο -> STOP
                move_dir = None

            elif s == WALK_ATTACK:
                # walk_attack -> κίνηση ΜΟΝΟ μπροστά (locked)
                move_dir = self.dir_to_move_str(self.player_sprite.attack_dir)

            else:
                move_dir = None

                # διάλεξε το τελευταίο πατημένο WASD που είναι ακόμα πατημένο
                for k in reversed(self.move_order):
                    if k in self.held_move:
                        if k == arcade.key.W:
                            move_dir = "UP"
                        elif k == arcade.key.S:
                            move_dir = "DOWN"
                        elif k == arcade.key.A:
                            move_dir = "LEFT"
                        elif k == arcade.key.D:
                            move_dir = "RIGHT"
                        break

            # στείλε μόνο αν άλλαξε (για να μη spamάρεις)
            # αν δεν υπάρχει κίνηση -> στείλε STOP (1 φορά)
            if move_dir is None:
                if self.last_sent_move is not None:
                    self.last_sent_move = None
                    asyncio.run_coroutine_threadsafe(send_move("STOP"), NETWORK_LOOP)
            else:
                if move_dir != self.last_sent_move:
                    self.last_sent_move = move_dir
                    asyncio.run_coroutine_threadsafe(send_move(move_dir), NETWORK_LOOP)

        # Ενημέρωση animation τοπικού παίκτη
        if self.player_sprite:
            self.player_sprite.update_animation(delta_time)

            if getattr(self.player_sprite, "despawn", False):
                self.player_sprite.remove_from_sprite_lists()

            # --- Consume attack buffer (Case C) ---
            if self.player_sprite.attack_finished:
                self.player_sprite.attack_finished = False

                if self.attack_buffered:
                    self.attack_buffered = False
                    next_state = getattr(self, "buffer_attack_state", None) or ATTACK
                    self.buffer_attack_state = None

                    self.player_sprite.attack_dir = self.player_sprite.last_direction
                    self.player_sprite.base_state = next_state
                    self.player_sprite.base_direction = self.player_sprite.attack_dir
                    self.player_sprite.force_state(next_state, self.player_sprite.attack_dir, reset=True)

                else:
                    self.player_sprite.attack_dir = None

                    if self.held_move:
                        self.player_sprite.set_base_state(WALK, self.player_sprite.last_direction)
                    else:
                        self.player_sprite.set_base_state(IDLE, self.player_sprite.last_direction)

        # Ενημέρωση animation άλλων παικτών
        for spr in self.other_sprites.values():
            spr.update_animation(delta_time)

        for e in list(self.enemy_list):
            e.update_animation(delta_time)
            if getattr(e, "despawn", False):
                e.remove_from_sprite_lists()
            
        # Ενημέρωση κάμερας
        self.update_camera()

        if self.region_message_timer > 0:
            self.region_message_timer -= delta_time
            if self.region_message_timer <= 0:
                self.region_message_timer = 0
                self.region_message = ""

    def is_moving_input(self):
        return len(self.held_move) > 0   # ή self.last_sent_move is not None

    def on_key_press(self, key, modifiers):
        # (Optional) Ignore direction changes while attacking
        if self.player_sprite and self.player_sprite.state in (ATTACK, WALK_ATTACK):
            if key in (arcade.key.W, arcade.key.A, arcade.key.S, arcade.key.D):
                return
        # --- ATTACK (SPACE): Case C (lock + 1 buffer) ---
        if key == arcade.key.SPACE and self.player_sprite:
            spr = self.player_sprite

            if spr.state == DEATH or getattr(spr, "death_started", False):
                return

            attack_state = WALK_ATTACK if self.is_moving_input() else ATTACK

            # Αν ήδη κάνει attack -> buffer μόνο κοντά στο τέλος
            if spr.state in (ATTACK, WALK_ATTACK):
                frames = spr.animations[spr.state][spr.direction]
                progress = spr.cur_frame / (len(frames) - 1) if len(frames) > 1 else 1.0

                if progress >= self.attack_buffer_threshold:
                    self.attack_buffered = True
                    self.buffer_attack_state = attack_state
                return

            # Ξεκίνα νέο attack τώρα
            self.attack_buffered = False
            self.buffer_attack_state = None

            # LOCK direction για ΟΛΟ το attack
            spr.attack_dir = spr.last_direction
            spr.base_state = attack_state
            spr.base_direction = spr.attack_dir
            spr.force_state(attack_state, spr.attack_dir, reset=True)
        
            if NETWORK_LOOP is not None:
                dir_str = self.dir_to_move_str(spr.attack_dir)
                if dir_str is not None:
                    asyncio.run_coroutine_threadsafe(send_attack(dir_str), NETWORK_LOOP)

            return

    # Movement keys (μόνο WASD) - last pressed wins
        if key in (arcade.key.W, arcade.key.A, arcade.key.S, arcade.key.D):
            self.held_move.add(key)

            # κάνε το key "τελευταίο" στη σειρά
            if key in self.move_order:
                self.move_order.remove(key)
            self.move_order.append(key)
            return

        # Όλα τα άλλα keys (spells κλπ) επιτρέπονται ταυτόχρονα
        self.held_keys.add(key)

    def on_key_release(self, key, modifiers):
        # Movement keys (μόνο WASD)
        if key in (arcade.key.W, arcade.key.A, arcade.key.S, arcade.key.D):
            self.held_move.discard(key)
            if key in self.move_order:
                self.move_order.remove(key)
            return

        # Άλλα keys (spells κλπ)
        self.held_keys.discard(key)

    def dir_to_move_str(self, d):
        if d == UP: return "UP"
        if d == DOWN: return "DOWN"
        if d == LEFT: return "LEFT"
        if d == RIGHT: return "RIGHT"
        return None

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