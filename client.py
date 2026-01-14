import arcade
import asyncio
import threading
import zmq
import zmq.asyncio
from queue import Queue
import sys
import time
from login import MenuView
from playerView import CreatePlayerView
from classView import ClassSelectView

# Windows fix για να λειτουργεί το asyncio με τον κατάλληλο event loop σε Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

CLIENT_PLAYER_ID = None     # Player id

# Ρυθμίσεις Sprite sheet 
FRAME_W = 64    # Πλάτος frame στο sprite sheet
FRAME_H = 64    # Ύψος frame στο sprite sheet
SCALE = 2       # Κλίμακα sprite στο παιχνίδι

# Κατευθύνσεις για τα animation
DOWN  = "down"
LEFT  = "left"
RIGHT = "right"
UP    = "up"

# Κατάσταση Animation
IDLE = "idle"
WALK = "walk"

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

# Ασύγχρονες μέθοδοι για το δίκτυο

# Στέλνει input κίνησης στον server.
async def send_move(direction: str):
    await push_socket.send_json({
        "id": CLIENT_PLAYER_ID,
        "move": direction
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
        "id": CLIENT_PLAYER_ID
    })
    reply = await control_socket.recv_json()
    print("[Control reply]:", reply)

    # # Server full? Δεν έχουμε Player cap οποτε δεν χρησιμοποιείται για τώρα
    # if reply.get("status") == "full":
    #     SERVER_ACCEPTED = False
    #     CONTROL_ACTIVE = False
    #     DISCONNECT_SENT = True   # δεν θα γίνει DISCONNECT, είμαστε ήδη εκτός
    #     return

    # Επιτυχής σύνδεση (πάντα)
    SERVER_ACCEPTED = True

    # Μένουμε ζωντανοί μέχρι να κλείσει το παράθυρο
    while CONTROL_ACTIVE:
        await asyncio.sleep(0.1)

    # Αποσύνδεση
    try:
        await control_socket.send_json({
            "type": "disconnect",
            "id": CLIENT_PLAYER_ID
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

# Φορτώνει τα sprite sheets και τα μετατρέπει σε δομή animations[state][direction][frame]
def load_player_animations():
    idle_sheet = arcade.SpriteSheet("assets/classes/idle.png")  # Φόρτωση idle sprite sheet
    walk_sheet = arcade.SpriteSheet("assets/classes/walk.png")  # Φόρτωση walk sprite sheet

    # Παίρνουμε τα συνολικά frames για το idle animation
    idle_textures = idle_sheet.get_texture_grid(
        size=(FRAME_W, FRAME_H),
        columns=12,
        count=48
    )

    # Παίρνουμε τα συνολικά frames για το walk animation
    walk_textures = walk_sheet.get_texture_grid(
        size=(FRAME_W, FRAME_H),
        columns=6,
        count=24
    )

    # Θέτουμε τα frames στις αντίστοιχες κινήσεις/στάσεις
    animations = {
        IDLE: {
            DOWN:  idle_textures[0:12],
            LEFT:  idle_textures[12:24],
            RIGHT: idle_textures[24:36],
            UP:    idle_textures[36:40],
        },
        WALK: {
            DOWN:  walk_textures[0:6],
            LEFT:  walk_textures[6:12],
            RIGHT: walk_textures[12:18],
            UP:    walk_textures[18:24],
        }
    }

    return animations   # Παίρνουμε το animation

class PlayerSprite(arcade.Sprite):
    def __init__(self, animations):
        super().__init__(scale=SCALE)

        self.animations = animations

        self.state = IDLE           # Animation state
        self.direction = DOWN       # Tρέχουσα κατεύθυνση
        self.last_direction = DOWN  # Tελευταία κατεύθυνση (για idle)

        self.cur_frame = 0          # Index frame animation
        self.time_acc = 0.0         # Χρόνος για την αλλαγή του frame
        self.frame_time = 0.12      # Πόσο γρήγορα αλλάζει frame

        # Αρχικό texture
        self.texture = self.animations[self.state][self.direction][0]

    # Αλλάζει animation state / direction
    # Κάνει reset animation μόνο όταν αλλάζει state
    def set_state(self, state, direction=None):
        if direction:
            self.direction = direction  # Ενημερώνουμε την τρέχουσα κατεύθυνση του sprite

        # Ελέγχουμε αν αλλάζει η κατάσταση του animation
        if state != self.state:
            self.state = state  # Αποθηκεύουμε τη νέα κατάστασ
            self.cur_frame = 0  # Μηδενίζουμε το frame ώστε το animation να ξεκινήσει από το πρώτο frame της νέας κατάστασης
            self.time_acc = 0.0 # Μηδενίζουμε το χρόνο για να μην συνεχίσει από προηγούμενο state
            
        # Ορίζουμε το texture που θα εμφανιστεί στο sprite
        self.texture = self.animations[self.state][self.direction][self.cur_frame]

    #  Ενημέρωση animation με βάση τον χρόνο
    def update_animation(self, delta_time):
        frames = self.animations[self.state][self.direction]    # Παίρνουμε τη λίστα των frames για το τρέχον state και την τρέχουσα κατεύθυνση
        self.time_acc += delta_time     # Προσθέτουμε τον χρόνο που πέρασε από το προηγούμενο frame

        # Αν έχει περάσει αρκετός χρόνος ώστε να αλλάξει frame το animation
        if self.time_acc >= self.frame_time:
            self.time_acc = 0.0         # Μηδενίζουμε τη μεταβλητή για να ξεκινήσει νέα μέτρηση χρόνου
            self.cur_frame = (self.cur_frame + 1) % len(frames)     # Προχωράμε στο επόμενο frame του animation, το modulo εξασφαλίζει ότι όταν φτάσουμε στο τελευταίο frame, θα επιστρέψουμε στο πρώτο
            self.texture = frames[self.cur_frame]        # Ενημερώνουμε το texture του sprite με το νέο frame του animation

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

        self.held_keys = set()    # Set που κρατάει ποια πλήκτρα είναι πατημένα (για hold keys)

        self.actor_list = arcade.SpriteList()   # Λίστα με τα sprites που σχεδιάζονται
        
        # Tilemap layers
        self.terrain_list = None
        self.decor_list = None
        self.wall_list = None

        self.world_camera = arcade.Camera2D()   # Κάμερα για τον κόσμο

        self.elapsed_time = 0.0     # Χρόνος που έχει περάσει στο match (από server)

        self.player_animations = None   # Animations του local player
        self.player_sprite = None       # Sprite του τοπικού παίκτη

        self.other_sprites = {}         # Άλλοι παίκτες
        
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

    # Μέθοδος για την κίνηση του παίκτη πίσω από τα walls (έξω από το collision point)
    def sort_key(self, sprite):
        offset = 0
        if hasattr(sprite, "properties"):
            offset = sprite.properties.get("sort_offset", 0)

        # Αν είναι player sprite, κάνουμε sort με βάση τα "πόδια" (bottom)
        if isinstance(sprite, PlayerSprite):
            return sprite.bottom

        return sprite.center_y + offset     # Για όλα τα άλλα sprites, sort με βάση το center_y + offset
    
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

    # Μέθοδος για την αρχικοποίηση του View όταν γίνεται ενεργό
    def on_show_view(self):
        # Reset κάμερας
        self.world_camera.position = (0, 0)
        self.world_camera.zoom = 1.0

        arcade.set_background_color(arcade.color.BLACK)

        # Φόρτωση tilemap για την πρώτη περιοχή
        self.tile_map = arcade.load_tilemap(
            "assets/maps/firstRegion.tmx",
            scaling=1.0,
            use_spatial_hash=True
        )
        
        # Ανάθεση layers
        self.terrain_list = self.tile_map.sprite_lists["Terrain"]
        self.decor_list = self.tile_map.sprite_lists["Decor"]
        self.wall_list = self.tile_map.sprite_lists["Walls"]

        # Διαστάσεις χάρτη σε pixels
        self.map_width = self.tile_map.width * self.tile_map.tile_width
        self.map_height = self.tile_map.height * self.tile_map.tile_height

        # Φόρτωση animations
        if self.player_animations is None:
            self.player_animations = load_player_animations()

        # Δημιουργία player sprite
        if self.player_sprite is None:
            self.player_sprite = PlayerSprite(self.player_animations)

        # Δημιουργία του actor_list κάθε φορά που μπαίνουμε στο view
        self.actor_list = arcade.SpriteList()

        # Προσθήκη decor
        for d in self.decor_list:
            self.actor_list.append(d)

        # Προσθήκη walls
        for w in self.wall_list:
            self.actor_list.append(w)

        # Προσθήκη player
        self.actor_list.append(self.player_sprite)

        # Τοποθέτηση timer στο UI
        self.timer_text.x = 10
        self.timer_text.y = self.window.height - 30

        self.held_keys.clear()  # Καθαρισμός input

    # Καθαρίζουμε τα πατημένα πλήκτρα όταν φεύγουμε από το view
    def on_hide_view(self):
        self.held_keys.clear()

    # Ζωγραφίζουμε τα αντικείμενα
    def on_draw(self):
        self.clear()

        # Ενεργοποίηση world camera
        with self.world_camera.activate():
            self.terrain_list.draw()        # Ζωγραφίζουμε terrain

            # Ταξινόμηση αντικειμένων με βάση το Y (για σωστό βάθος)
            self.actor_list.sort(key=self.sort_key)  # Ζωγραφίζουμε όλα τα sprites
            self.actor_list.draw()

        self.timer_text.draw()      # Ζωγραφίζουμε το timer

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

        # Ενημέρωση του timer σε μορφή mm:ss
        minutes = int(self.elapsed_time) // 60
        seconds = int(self.elapsed_time) % 60
        self.timer_text.text = f"{minutes:02d}:{seconds:02d}"

        # Για κάθε παίκτη που υπάρχει στο server state
        for pid, pos in players_state.items():
            x = pos["x"]
            y = pos["y"]

            # Αν είναι ο τοπικός παίκτης, χρησιμοποιούμε το main sprite
            if pid == CLIENT_PLAYER_ID:
                sprite = self.player_sprite
            else:
                # Αν είναι άλλος παίκτης και δεν έχουμε sprite, το δημιουργούμε
                if pid not in self.other_sprites:
                    spr = PlayerSprite(self.player_animations)
                    self.other_sprites[pid] = spr
                    self.actor_list.append(spr)
                sprite = self.other_sprites[pid]

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
        existing_pids = set(players_state.keys())

        for pid in list(self.other_sprites.keys()):
            if pid not in existing_pids:
                spr = self.other_sprites[pid]
                self.actor_list.remove(spr)
                del self.other_sprites[pid]
                self.position_buffers.pop(pid, None)
                self.snapshots.pop(pid, None)
                self.interp_t.pop(pid, None)

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

        # Αποστολή input στον server
        if NETWORK_LOOP is not None:
            if arcade.key.UP in self.held_keys:
                asyncio.run_coroutine_threadsafe(send_move("UP"), NETWORK_LOOP)
            if arcade.key.DOWN in self.held_keys:
                asyncio.run_coroutine_threadsafe(send_move("DOWN"), NETWORK_LOOP)
            if arcade.key.LEFT in self.held_keys:
                asyncio.run_coroutine_threadsafe(send_move("LEFT"), NETWORK_LOOP)
            if arcade.key.RIGHT in self.held_keys:
                asyncio.run_coroutine_threadsafe(send_move("RIGHT"), NETWORK_LOOP)

        # Ενημέρωση animation τοπικού παίκτη
        if self.player_sprite:
            self.player_sprite.update_animation(delta_time)

        # Ενημέρωση animation άλλων παικτών
        for spr in self.other_sprites.values():
            spr.update_animation(delta_time)
            
        # Ενημέρωση κάμερας
        self.update_camera()

    def on_key_press(self, key, modifiers):
        self.held_keys.add(key)     

    def on_key_release(self, key, modifiers):
        if key in self.held_keys:
            self.held_keys.remove(key)

def main():
    # Χρησιμοποιούμε global μεταβλητές που ελέγχουν αν ο server δέχτηκε τον client και αν στάλθηκε DISCONNECT
    global SERVER_ACCEPTED, DISCONNECT_SENT

    window = GameWindow(1000, 800, "Celestial Lands")   # Δημιουργία του κεντρικού παραθύρου του παιχνιδιού
    window.game_mode = None                             # Μεταβλητή που δηλώνει τον τύπο παιχνιδιού
    window.network_started = False                      # Flag για να μη ξεκινήσει το networking thread πάνω από μία φορά

    # Μέθοδος που καλείται όταν ο χρήστης ξεκινά το παιχνίδι
    def start_game():
        global SERVER_ACCEPTED, CLIENT_PLAYER_ID        # Χρησιμοποιούμε global για το player id και την απάντηση του server

        # Αν ο χρήστης ξεκινά νέο παιχνίδι
        if window.game_mode == "NEW_GAME":
            # Αν δεν έχει δημιουργηθεί ακόμα player
            if not hasattr(window, "player_id"):
                # Πηγαίνουμε στο view δημιουργίας χαρακτήρα
                window.show_view(CreatePlayerView())
                return

        # Παίρνουμε το player id που δημιουργήθηκε στο menu / character creation
        CLIENT_PLAYER_ID = window.player_id

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