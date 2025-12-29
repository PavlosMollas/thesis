import asyncio
import zmq
import zmq.asyncio
import sys
import time

# Windows fix
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ctx = zmq.asyncio.Context()

# Movement input (PULL)
pull_socket = ctx.socket(zmq.PULL)
pull_socket.bind("tcp://*:5555")

# Broadcast state (PUB)
pub_socket = ctx.socket(zmq.PUB)
pub_socket.bind("tcp://*:5556")

# Control socket (REQ/REP)
control_socket = ctx.socket(zmq.REP)
control_socket.bind("tcp://*:5557")

# Player data
players = {}          # pid → {x, y}
connected = []        # ORDERED list of connected players
SPEED = 5

MAX_PLAYERS = 2  # limit players

# Fixed spawn points
LEFT_SPAWN  = (200, 300)
RIGHT_SPAWN = (600, 300)

# ===== MATCH STATE =====
match_started = False
match_start_time = None

TICK_DT = 0.02
tick = 0


# ============================================================
# CONTROL SOCKET (CONNECT / DISCONNECT)
# ============================================================
async def handle_control():
    global match_started, match_start_time

    while True:
        msg = await control_socket.recv_json()
        pid = msg["id"]
        typ = msg["type"]

        # ------------------------
        # CONNECT
        # ------------------------
        if typ == "connect":
            # Server full
            if len(connected) >= MAX_PLAYERS:
                print(f"Player {pid} rejected: server full.")
                await control_socket.send_json({"status": "full"})
                continue

            # Add player in order
            connected.append(pid)
            slot = len(connected)
            print(f"Player {pid} CONNECTED as slot {len(connected)}")

            # Assign spawn position
            if len(connected) == 1:      # first player
                x, y = LEFT_SPAWN
            else:                        # second player
                x, y = RIGHT_SPAWN

            players[pid] = {"x": x, "y": y}

            # START MATCH όταν μπουν 2
            if len(connected) == MAX_PLAYERS and not match_started:
                match_started = True
                match_start_time = time.time()
                print("MATCH STARTED")

            await control_socket.send_json({
                "status": "ok",
                "slot": slot
            })

        # ------------------------
        # DISCONNECT
        # ------------------------
        elif typ == "disconnect":
            print(f"Player {pid} DISCONNECTED")

            if pid in connected:
                connected.remove(pid)
            if pid in players:
                del players[pid]

            await control_socket.send_json({"status": "ok"})

            # If no players left → shutdown
            if len(connected) == 0:
                print("All players left. Shutting down server.")
                sys.exit(0)


# ============================================================
# INPUT HANDLING (no spawn here anymore)
# ============================================================
async def handle_inputs():
    while True:
        msg = await pull_socket.recv_json()
        pid = msg["id"]
        direction = msg["move"]

        # Αγνοούμε input αν το match δεν ξεκίνησε
        if not match_started:
            continue

        # Ignore movement from unconnected players
        if pid not in players:
            continue

        p = players[pid]

        if direction == "UP":
            p["y"] += SPEED
        elif direction == "DOWN":
            p["y"] -= SPEED
        elif direction == "LEFT":
            p["x"] -= SPEED
        elif direction == "RIGHT":
            p["x"] += SPEED


# ============================================================
# BROADCAST GAME STATE
# ============================================================
async def broadcast_state():
    while True:
        if match_started and match_start_time is not None:
            elapsed_time = time.time() - match_start_time
        else:
            elapsed_time = 0.0

        global tick
        tick += 1

        await pub_socket.send_json({
            "tick": tick,
            "tick_dt": TICK_DT,
            "players": players,
            "match_started": match_started,
            "elapsed_time": elapsed_time
        })

        await asyncio.sleep(TICK_DT)  # 50 FPS, server tick rate 20ms


# ============================================================
# MAIN
# ============================================================
async def main():
    print("Server running with max 2 players.")
    await asyncio.gather(
        handle_control(),
        handle_inputs(),
        broadcast_state()
    )

if __name__ == "__main__":
    asyncio.run(main())