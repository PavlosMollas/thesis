import arcade
import asyncio
import threading
import zmq
import zmq.asyncio
from queue import Queue
import uuid
import sys
import time
from login import MenuView


# ============================
# Windows asyncio fix
# ============================
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Unique ID per client
PLAYER_ID = str(uuid.uuid4())[:8]

# Shared game state from server (thread-safe)no
state_queue = Queue()

# Global references
NETWORK_LOOP = None           # asyncio loop στο networking thread
SERVER_ACCEPTED = None        # True / False αφού απαντήσει ο server στο CONNECT
CONTROL_ACTIVE = True         # γίνeται False όταν κλείσει το παράθυρο
DISCONNECT_SENT = False       # γίνεται True όταν σταλεί DISCONNECT στον server

# ZeroMQ context
ctx = zmq.asyncio.Context()

# PUSH socket (send inputs)
push_socket = ctx.socket(zmq.PUSH)
push_socket.connect("tcp://127.0.0.1:5555")

# SUB socket (receive server game state)
sub_socket = ctx.socket(zmq.SUB)
sub_socket.connect("tcp://127.0.0.1:5556")
sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

# CONTROL SOCKET (REQ)
control_socket = ctx.socket(zmq.REQ)
control_socket.connect("tcp://127.0.0.1:5557")


# ========================================================
# ASYNC NETWORKING
# ========================================================

async def send_move(direction: str):
    """Send a movement event to the server."""
    await push_socket.send_json({
        "id": PLAYER_ID,
        "move": direction
    })


async def receive_state():
    """Receive full server state and put into queue."""
    while True:
        state = await sub_socket.recv_json()
        state_queue.put(state)


async def control_loop():
    """REQ socket loop: CONNECT on start, DISCONNECT on close."""
    global SERVER_ACCEPTED, CONTROL_ACTIVE, DISCONNECT_SENT

    # ---- CONNECT ----
    await control_socket.send_json({
        "type": "connect",
        "id": PLAYER_ID
    })
    reply = await control_socket.recv_json()
    print("[Control reply]:", reply)

    # Server full?
    if reply.get("status") == "full":
        SERVER_ACCEPTED = False
        CONTROL_ACTIVE = False
        DISCONNECT_SENT = True   # δεν θα γίνει DISCONNECT, είμαστε ήδη εκτός
        return

    SERVER_ACCEPTED = True

    # Μένουμε ζωντανοί μέχρι να κλείσει το παράθυρο
    while CONTROL_ACTIVE:
        await asyncio.sleep(0.1)

    # ---- DISCONNECT ----
    try:
        await control_socket.send_json({
            "type": "disconnect",
            "id": PLAYER_ID
        })
        await control_socket.recv_json()
    except Exception as e:
        print("Error sending DISCONNECT:", e)

    DISCONNECT_SENT = True
    print("[Client] Disconnect sent.")


async def io_main():
    """Main async ZMQ networking task (τρέχει στο networking thread)."""
    asyncio.create_task(receive_state())
    asyncio.create_task(control_loop())

    # Περιμένουμε να μάθουμε αν ο server μας δέχτηκε ή όχι
    global SERVER_ACCEPTED
    while SERVER_ACCEPTED is None:
        await asyncio.sleep(0.05)

    # Κρατάμε το loop ζωντανό
    while True:
        await asyncio.sleep(1)


def thread_worker():
    """Runs asyncio loop inside a separate thread."""
    global NETWORK_LOOP
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    NETWORK_LOOP = loop
    loop.create_task(io_main())
    loop.run_forever()

# Main Window
class GameWindow(arcade.Window):
    def on_close(self):
        global CONTROL_ACTIVE
        CONTROL_ACTIVE = False
        print("Window closed, will send DISCONNECT...")
        super().on_close()

# Connecting View
class ConnectingView(arcade.View):
    def __init__(self):
        super().__init__()
        self.msg = arcade.Text("Connecting to server...", 0, 0, arcade.color.WHITE, 20, anchor_x="center")

    def on_show_view(self):
        arcade.set_background_color(arcade.color.BLACK)
        self.msg.x = self.window.width // 2
        self.msg.y = self.window.height // 2

    def on_draw(self):
        self.clear()
        self.msg.draw()

    def on_update(self, delta_time: float):
        global SERVER_ACCEPTED

        # Περιμένουμε απάντηση από control_loop (στο networking thread)
        if SERVER_ACCEPTED is True:
            game_view = MyGame()
            self.window.show_view(game_view)

        elif SERVER_ACCEPTED is False:
            # Server full (ή reject)
            # Εδώ μπορείς αντί για exit να γυρίσεις στο StartView με μήνυμα
            print("Server full. Closing client.")
            self.window.close()

# Game View
class MyGame(arcade.View):
    def __init__(self):
        super().__init__()

        self.held_keys = set()      

        self.match_started = False
        self.elapsed_time = 0.0

        # PLAYER SPRITE
        tex_red = arcade.make_soft_square_texture(40, arcade.color.RED, 255)
        self.player_sprite = arcade.Sprite()
        self.player_sprite.append_texture(tex_red)
        self.player_sprite.set_texture(0)

        self.player_list = arcade.SpriteList()
        self.player_list.append(self.player_sprite)

        # OTHER PLAYERS
        self.other_sprites = {}        # pid -> Sprite
        self.other_list = arcade.SpriteList()
        self.green_tex = arcade.make_soft_square_texture(40, arcade.color.GREEN, 255)

        # --- SMOOTHING STRUCTURES ---
        # pid -> [(x0, y0, t0), (x1, y1, t1)]
        self.position_buffers = {}
        # pid -> (snap_x, snap_y)  : θέση sprite όταν ήρθε ΤΟ ΤΕΛΕΥΤΑΙΟ update
        self.snapshots = {}
        # pid -> time since last update (για το x του LERP)
        self.interp_t = {}

        # === UI TEXT OBJECTS ===
        self.timer_text = arcade.Text(
            "00:00",
            10, 10,
            arcade.color.WHITE,
            font_size=20
        )

        self.waiting_text = arcade.Text(
            "Waiting for player 2 to connect...",
            0, 0,
            arcade.color.WHITE,
            font_size=24,
            anchor_x="center",
            anchor_y="center"
        )

    def on_show_view(self):
        # σωστές θέσεις αφού το view “δέθηκε” στο window
        self.timer_text.x = 10
        self.timer_text.y = self.window.height - 30

        self.waiting_text.x = self.window.width // 2
        self.waiting_text.y = self.window.height // 2

        self.held_keys.clear()

    def on_hide_view(self):
        self.held_keys.clear()

    def on_draw(self):
        self.clear()
        self.player_list.draw()
        self.other_list.draw()

        # HUD
        self.timer_text.draw()
        if not self.match_started:
            self.waiting_text.draw()

    def _process_server_state(self):
        """
        Παίρνει ΤΕΛΕΥΤΑΙΟ state από την ουρά και
        ενημερώνει τα buffers / snapshots.
        """
        if state_queue.empty():
            return None

        # Πάρε το πιο πρόσφατο state (άδειασε την ουρά)
        latest_state = None
        while not state_queue.empty():
            latest_state = state_queue.get()

        if latest_state is None:
            return None
        
        tick = latest_state.get("tick")
        if tick is None:
            return None
        
        tick_dt = latest_state.get("tick_dt", 0.02)
        self.tick_dt = tick_dt

        # ===== ΝΕΟ: match state από server =====
        self.match_started = latest_state["match_started"]
        self.elapsed_time = latest_state["elapsed_time"]
        players_state = latest_state["players"]

        # Update timer text
        minutes = int(self.elapsed_time) // 60
        seconds = int(self.elapsed_time) % 60
        self.timer_text.text = f"{minutes:02d}:{seconds:02d}"

        # Δημιουργία / ενημέρωση buffers για κάθε παίκτη
        for pid, pos in players_state.items():
            x = pos["x"]
            y = pos["y"]

            # Διάλεξε το σωστό sprite
            if pid == PLAYER_ID:
                sprite = self.player_sprite
            else:
                if pid not in self.other_sprites:
                    spr = arcade.Sprite()
                    spr.append_texture(self.green_tex)
                    spr.set_texture(0)
                    self.other_sprites[pid] = spr
                    self.other_list.append(spr)
                sprite = self.other_sprites[pid]

            # Buffer θέσεων
            buf = self.position_buffers.setdefault(pid, [])
            buf.append((x, y, tick))
            if len(buf) > 2:
                buf.pop(0)  # κρατάμε μόνο 2

            # Snapshot: η τρέχουσα θέση του sprite όταν ήρθε το update
            self.snapshots[pid] = (sprite.center_x, sprite.center_y)
            self.interp_t[pid] = 0.0

        # ===== Cleanup: παίκτες που έφυγαν =====
        existing_pids = set(players_state.keys())

        for pid in list(self.other_sprites.keys()):
            if pid not in existing_pids:
                spr = self.other_sprites[pid]
                self.other_list.remove(spr)
                del self.other_sprites[pid]
                self.position_buffers.pop(pid, None)
                self.snapshots.pop(pid, None)
                self.interp_t.pop(pid, None)

        return players_state

    def _apply_smoothing(self, delta_time):
        """
        Κάνει extrapolation + interpolation για ΟΛΟΥΣ τους παίκτες.
        """
        # Μαζεύουμε όλα τα sprites (εσύ + άλλοι)
        all_sprites = {PLAYER_ID: self.player_sprite}
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

            # Δύο πιο πρόσφατες θέσεις
            (x0, y0, tick0), (x1, y1, tick1) = buf[0], buf[1]
            dt_ticks = tick1 - tick0
            dt_server = dt_ticks * getattr(self, "tick_dt", 0.02)

            if dt_ticks <= 0 or dt_server <= 0:
                # Κάτι περίεργο με τα timestamps, πήγαινε απευθείας στην τελευταία
                target_x, target_y = x1, y1
            else:
                # Ταχύτητα (velocity)
                vx = (x1 - x0) / dt_server
                vy = (y1 - y0) / dt_server

                # Extrapolation: 1 "frame" μπροστά = dt_server
                prediction_dt = getattr(self, "tick_dt", 0.02)
                target_x = x1 + vx * prediction_dt
                target_y = y1 + vy * prediction_dt

            # Πόσος χρόνος πέρασε από το τελευταίο update
            t_local = self.interp_t.get(pid, 0.0) + delta_time
            self.interp_t[pid] = t_local

            if dt_server > 0:
                x_param = t_local / dt_server
            else:
                x_param = 1.0

            # clamp 0..1
            if x_param > 1.0:
                x_param = 1.0
            elif x_param < 0.0:
                x_param = 0.0

            # Snapshot θέση όταν ήρθε το update
            snap_x, snap_y = self.snapshots.get(pid, (sprite.center_x, sprite.center_y))

            # LERP από snapshot → predicted
            sprite.center_x = snap_x + (target_x - snap_x) * x_param
            sprite.center_y = snap_y + (target_y - snap_y) * x_param

    def on_update(self, delta_time):
        """
        1) Διαβάζει το πιο πρόσφατο server state και ενημερώνει buffers
        2) Κάνει prediction + interpolation
        3) Στέλνει input προς τον server
        """
        # 1) Επεξεργασία τελευταίου server state (γεμίζει buffers)
        self._process_server_state()

        # 2) Εφαρμογή smoothing σε όλους
        self._apply_smoothing(delta_time)

        # 3) Συνεχές input προς τον server
        if NETWORK_LOOP is not None and self.match_started:
            if arcade.key.UP in self.held_keys:
                asyncio.run_coroutine_threadsafe(send_move("UP"), NETWORK_LOOP)
            if arcade.key.DOWN in self.held_keys:
                asyncio.run_coroutine_threadsafe(send_move("DOWN"), NETWORK_LOOP)
            if arcade.key.LEFT in self.held_keys:
                asyncio.run_coroutine_threadsafe(send_move("LEFT"), NETWORK_LOOP)
            if arcade.key.RIGHT in self.held_keys:
                asyncio.run_coroutine_threadsafe(send_move("RIGHT"), NETWORK_LOOP)

    def on_key_press(self, key, modifiers):
        self.held_keys.add(key)

    def on_key_release(self, key, modifiers):
        if key in self.held_keys:
            self.held_keys.remove(key)
    
    # def on_deactivate(self):
    #     self.held_keys.clear()

    # def on_activate(self):
    #     self.held_keys.clear()

    # def on_hide(self):
    #     self.held_keys.clear()

    # def on_show(self):
    #     self.held_keys.clear()

    # def on_close(self):
    #     """Arcade window closed → ενημερώνουμε το control_loop να στείλει DISCONNECT."""
    #     global CONTROL_ACTIVE
    #     CONTROL_ACTIVE = False
    #     print("Window closed, will send DISCONNECT...")
    #     super().on_close()


# ========================================================
# MAIN ENTRY
# ========================================================

def main():
    global SERVER_ACCEPTED, DISCONNECT_SENT

    window = GameWindow(800, 600, "Celestial Lands")
    window.game_mode = None
    window.network_started = False

    def start_game():
        global SERVER_ACCEPTED

        # Αποφεύγουμε να ξεκινήσει 2 φορές thread αν πατηθεί ξανά Enter
        if not window.network_started:
            window.network_started = True
            SERVER_ACCEPTED = None  # reset πριν το connect
            t = threading.Thread(target=thread_worker, daemon=True)
            t.start()

        # Αντί να περιμένουμε εδώ (freeze), δείχνουμε ConnectingView
        window.show_view(ConnectingView())

    window.start_game = start_game

    window.show_view(MenuView())
    arcade.run()

    # Εδώ έχει κλείσει το παράθυρο
    # Περιμένουμε να σταλεί το DISCONNECT πριν τερματίσει η διαδικασία
    if window.network_started:
        timeout = time.time() + 5  # safety timeout 5s
        while not DISCONNECT_SENT and time.time() < timeout:
            time.sleep(0.01)

    sys.exit(0)


if __name__ == "__main__":
    main()