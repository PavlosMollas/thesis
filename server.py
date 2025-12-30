import asyncio
import zmq
import zmq.asyncio
import sys
import time

# Windows fix για να λειτουργεί το asyncio με τον κατάλληλο event loop σε Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

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

connected = []        # Λίστα παικτών σε σειρά σύνδεσης
SPEED = 5             # Ταχύτητα κίνησης του παίκτη

MAX_PLAYERS = 2  # limit players

# Fixed spawn points
LEFT_SPAWN  = (200, 300)
RIGHT_SPAWN = (600, 300)

match_started = False       # Ελέγχει αν το παιχνίδι έχει ξεκινήσει
match_start_time = None     # Χρόνος που ξεκίνησε το παιχνίδι

TICK_DT = 0.02      # Η διάρκεια κάθε "tick" σε δευτερόλεπτα (ρυθμίζει το frame rate)
tick = 0            # Μετρητής "tick" για το παιχνίδι

# Μέθοδος για το state των παικτών
async def handle_control():
    global match_started, match_start_time

    while True:
        msg = await control_socket.recv_json()  # Περιμένει και λαμβάνει τα μηνύματα ελέγχου
        pid = msg["id"]     # Το id του παίκτη
        typ = msg["type"]   # Τύπος αιτήματος (σύνδεση ή αποσύνδεση)

        # Σύνδεση παίκτη
        if typ == "connect":
            # Αν ο server είναι γεμάτος, απορρίπτει τη σύνδεση
            if len(connected) >= MAX_PLAYERS:
                print(f"Player {pid} rejected: server full.")
                await control_socket.send_json({"status": "full"})
                continue

            # Προσθήκη του παίκτη στη λίστα των συνδεδεμένων
            connected.append(pid)
            slot = len(connected)       # Δημιουργία της θέσης του παίκτη (slot)
            print(f"Player {pid} CONNECTED as slot {len(connected)}")

            # Ανάθεση θέσης παικτών
            if len(connected) == 1:      # first player
                x, y = LEFT_SPAWN
            else:                        # second player
                x, y = RIGHT_SPAWN

            players[pid] = {"x": x, "y": y} # Αποθήκευση θέσης παίκτη

            # Ξεκινάει το παιχνίδι μόλις μπουν 2 παίκτες
            if len(connected) == MAX_PLAYERS and not match_started:
                match_started = True
                match_start_time = time.time()  # Χρόνος έναρξης παιχνιδιού
                print("MATCH STARTED")

            await control_socket.send_json({
                "status": "ok",
                "slot": slot        # Επιστρέφει την θέση του παίκτη (slot)
            })

        # Αποσύνδεση παίκτη
        elif typ == "disconnect":
            print(f"Player {pid} DISCONNECTED")

            if pid in connected:
                connected.remove(pid)   # Αφαίρεση του παίκτη από την λίστα των συνδεδεμένων
            if pid in players:
                del players[pid]        # Αφαίρεση του παίκτη από τα δεδομένα

            await control_socket.send_json({"status": "ok"})

            # Αν δεν υπάρχουν άλλοι παίκτες, κλείνει ο server
            if len(connected) == 0:
                print("All players left. Shutting down server.")
                sys.exit(0)

# Μέθοδος για τα inputs
async def handle_inputs():
    while True:
        msg = await pull_socket.recv_json() # Λαμβάνει τα μηνύματα κίνησης από τους πελάτες
        pid = msg["id"]
        direction = msg["move"]

        # Αγνοούμε input αν το match δεν ξεκίνησε
        if not match_started:
            continue

        # Αγνοεί τις κινήσεις από παίκτες που δεν είναι συνδεδεμένοι
        if pid not in players:
            continue

        p = players[pid]    # Παίκτης που στέλνει την κίνηση

        # Κίνηση του παίκτη με βάση την εισερχόμενη εντολή
        if direction == "UP":
            p["y"] += SPEED
        elif direction == "DOWN":
            p["y"] -= SPEED
        elif direction == "LEFT":
            p["x"] -= SPEED
        elif direction == "RIGHT":
            p["x"] += SPEED


# Μέθοδος για τη μετάδοση κατάστασης παιχνιδιού
async def broadcast_state():
    while True:
        # Υπολογισμός του χρόνου παιχνιδιού
        if match_started and match_start_time is not None:
            elapsed_time = time.time() - match_start_time
        else:
            elapsed_time = 0.0

        global tick
        tick += 1       # Αύξηση του tick για κάθε frame

        # Στέλνει την κατάσταση του παιχνιδιού σε όλους τους πελάτες
        await pub_socket.send_json({
            "tick": tick,
            "tick_dt": TICK_DT,             # Διάρκεια κάθε "tick"
            "players": players,             # Κατάσταση των παικτών
            "match_started": match_started, # Αν έχει ξεκινήσει το παιχνίδι
            "elapsed_time": elapsed_time    # Χρόνος που έχει περάσει από την έναρξη
        })

        await asyncio.sleep(TICK_DT)  # 50 FPS, ρυθμός ανανέωσης 20ms

async def main():
    print("Server running with max 2 players.") # Ενημέρωση για τον server
    await asyncio.gather(
        handle_control(),       # Επεξεργασία αιτημάτων σύνδεσης/αποσύνδεσης
        handle_inputs(),        # Επεξεργασία των κινήσεων των παικτών
        broadcast_state()       # Μετάδοση της κατάστασης του παιχνιδιού
    )

if __name__ == "__main__":
    asyncio.run(main())