import asyncio
import zmq
import zmq.asyncio
import sys
import time
import arcade

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

connected = set()     # Σύνολο παικτών σε σειρά σύνδεσης

spawn_points = []     # Λίστα για το spawn παικτών
next_spawn_index = 0

object_layer = tile_map.object_lists.get("Object")  # Παίρνουμε το object layer για το spawn 

if not object_layer:
    raise RuntimeError("No Object layer found in TMX map")

for obj in object_layer:
    if obj.name == "player_spawn":  # Για κάθε object με το όνομα player_spawn (έτσι έχει ονομαστεί στο tiled), προσθέτουμε το σημείο στη λίστα
        x, y = obj.shape
        spawn_points.append((x, y))

if not spawn_points:
    raise RuntimeError("No player_spawn objects found in Object layer")

print("Spawn points loaded from TMX:", spawn_points)

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
            if pid in connected:
                await control_socket.send_json({"status": "ok"})
                continue

            # Προσθήκη του παίκτη στo σύνολο των συνδεδεμένων
            connected.add(pid)

            # Spawn place
            spawn_index = next_spawn_index
            next_spawn_index += 1

            x, y = spawn_points[spawn_index % len(spawn_points)]
            players[pid] = {"x": x, "y": y} # Αποθήκευση θέσης παίκτη

            print(f"Player {pid} CONNECTED at spawn {spawn_index}")

            await control_socket.send_json({
                "status": "ok",
            })

        # Αποσύνδεση παίκτη
        elif typ == "disconnect":
            print(f"Player {pid} DISCONNECTED")

            if pid in connected:
                connected.remove(pid)   # Αφαίρεση του παίκτη από την λίστα των συνδεδεμένων
            if pid in players:
                del players[pid]        # Αφαίρεση του παίκτη από τα δεδομένα

            await control_socket.send_json({"status": "ok"})

# Μέθοδος για το collision
def collides_with_walls(x, y):
    # Υπολογισμός ορίων του παίκτη
    # με βάση το κέντρο του (x, y) και τις διαστάσεις του sprite
    left   = x - PLAYER_WIDTH / 2
    right  = x + PLAYER_WIDTH / 2
    bottom = y - PLAYER_HEIGHT / 2
    top    = y + PLAYER_HEIGHT / 2

    # Έλεγχος σύγκρουσης με κάθε wall sprite
    for wall in wall_list:
        if (
            right  > wall.left and      # ο παίκτης δεν είναι τελείως αριστερά
            left   < wall.right and     # ο παίκτης δεν είναι τελείως δεξιά
            top    > wall.bottom and    # ο παίκτης δεν είναι τελείως κάτω
            bottom < wall.top           # ο παίκτης δεν είναι τελείως πάνω
        ):
            return True

    return False

# Μέθοδος για τα inputs
async def handle_inputs():
    while True:
        msg = await pull_socket.recv_json() # Λαμβάνει τα μηνύματα κίνησης από τους πελάτες
        pid = msg["id"]
        direction = msg["move"]

        # Αγνοεί τις κινήσεις από παίκτες που δεν είναι συνδεδεμένοι
        if pid not in players:
            continue

        p = players[pid]    # Παίκτης που στέλνει την κίνηση

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
        if not collides_with_walls(new_x, p["y"]):
            p["x"] = new_x

        if not collides_with_walls(p["x"], new_y):
            p["y"] = new_y        

# Μέθοδος για τη μετάδοση κατάστασης παιχνιδιού
async def broadcast_state():
    while True:
        global tick
        tick += 1       # Αύξηση του tick για κάθε frame

        elapsed_time = time.time() - server_start_time

        # Στέλνει την κατάσταση του παιχνιδιού σε όλους τους πελάτες
        await pub_socket.send_json({
            "tick": tick,
            "tick_dt": TICK_DT,             # Διάρκεια κάθε "tick"
            "players": dict(players),             # Κατάσταση των παικτών
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