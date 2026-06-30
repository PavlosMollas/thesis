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
import client_draw
import client_attackAndUI
from sprites import (
    PlayerSprite, EnemySprite, ProjectileSprite,
    load_player_animations, load_enemy_animations,
    load_projectile_animations, get_enemy_type_defs,
    PROJECTILE_ANIMATION_CONFIGS, CLASS_SCALES, ENEMY_SCALES, IDLE, WALK, ATTACK, DEATH, WALK_ATTACK, DOWN, UP, LEFT, RIGHT, ATTACK02, ATTACK03,
)
import os
import random

# Windows fix για να λειτουργεί το asyncio με τον κατάλληλο event loop σε Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

REGION_MAPS = {     # Αντιστοίχιση ονόματος περιοχής με το αντίστοιχο TMX map αρχείο
    "firstRegion": "assets/maps/firstRegion.tmx",
    "secondRegion": "assets/maps/secondRegion.tmx",
    "thirdRegion": "assets/maps/thirdRegion.tmx",
    "fourthRegion": "assets/maps/fourthRegion.tmx",
}

ITEM_ICON_PATHS = {     # Αντιστοίχιση ονόματος item με το αντίστοιχο αρχείο εικόνας για το inventory UI
    "Health_Potion": "assets/items/Health_Potion.png",
    "Energy_Potion": "assets/items/Energy_Potion.png",
    "ElixirOfToughness": "assets/items/ElixirOfToughness.png",
    "ElixirOfMagic": "assets/items/ElixirOfMagic.png",
    "ElixirOfPower": "assets/items/ElixirOfPower.png",
}

CLIENT_PLAYER_ID = None     # Player id
CLIENT_NICKNAME = None      # Player nickname

SERVER_REJECT_REASON = ""   # Μήνυμα απόρριψης σύνδεσης, αν ο server δεν δεχτεί τον client

state_queue = Queue()   # Queue που μεταφέρει με ασφάλεια τα game states από το networking thread στο main Arcade thread

# Global flags που συγχρονίζουν την κατάσταση σύνδεσης και αποσύνδεσης μεταξύ Arcade και networking thread
NETWORK_LOOP = None           # asyncio loop στο networking thread
SERVER_ACCEPTED = None        # True / False αφού απαντήσει ο server στο CONNECT
CONTROL_ACTIVE = True         # γίνeται False όταν κλείσει το παράθυρο
DISCONNECT_SENT = False       # γίνεται True όταν σταλεί DISCONNECT στον server
DISCONNECT_REQUESTED = False

# Επιστρέφει τον φάκελο από όπου τρέχει ο client
# Αν τρέχει ως exe, χρησιμοποιεί τον φάκελο του exe
# Αν τρέχει ως .py, χρησιμοποιεί τον φάκελο του αρχείου client.py
def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)

    return os.path.dirname(os.path.abspath(__file__))

# Φορτώνει την IP του server από το server_ip.txt
# Αν δεν υπάρχει το αρχείο ή είναι κενό, χρησιμοποιείται το 127.0.0.1 για local play
def load_server_ip():
    ip_file = os.path.join(get_base_dir(), "server_ip.txt")

    try:
        with open(ip_file, "r", encoding="utf-8") as f:
            ip = f.read().strip()

            if ip:
                return ip
    except FileNotFoundError:
        pass

    return "127.0.0.1"

SERVER_IP = load_server_ip()
print("Connecting to server IP:", SERVER_IP)

# ZeroMQ context που χρησιμοποιείται για τη δημιουργία όλων των sockets του client
ctx = zmq.asyncio.Context()

# PUSH socket: στέλνει inputs του παίκτη προς τον server, όπως κίνηση, attack και χρήση item
push_socket = ctx.socket(zmq.PUSH)
push_socket.connect(f"tcp://{SERVER_IP}:5555")

# SUB socket: λαμβάνει συνεχώς το game state που δημοσιεύει ο server
sub_socket = ctx.socket(zmq.SUB)
sub_socket.connect(f"tcp://{SERVER_IP}:5556")
sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

# CONTROL SOCKET: χρησιμοποιείται για control μηνύματα, όπως connect και disconnect
control_socket = ctx.socket(zmq.REQ)
control_socket.connect(f"tcp://{SERVER_IP}:5557")

### Ασύγχρονες μέθοδοι για το δίκτυο ###

# Στέλνει στον server την κατεύθυνση κίνησης του παίκτη
async def send_move(direction: str):
    await push_socket.send_json({
        "id": CLIENT_PLAYER_ID,
        "move": direction
    })

# Στέλνει στον server αίτημα επίθεσης μαζί με κατεύθυνση και attack id
async def send_attack(direction: str, attack_id: str = "basic"):
    await push_socket.send_json({
        "id": CLIENT_PLAYER_ID,
        "attack": True,
        "dir": direction,
        "attack_id": attack_id
    })

# Στέλνει στον server αίτημα αγοράς item από το inventory
async def send_buy_item(item_name: str):
    await push_socket.send_json({
        "id": CLIENT_PLAYER_ID,
        "buy_item": item_name
    })

# Στέλνει στον server αίτημα χρήσης item από το inventory
async def send_use_item(item_name: str):
    await push_socket.send_json({
        "id": CLIENT_PLAYER_ID,
        "use_item": item_name
    })

# Στέλνει περιοδικό heartbeat ώστε ο server να γνωρίζει ότι ο client παραμένει ενεργός
async def send_heartbeat():
    await push_socket.send_json({
        "id": CLIENT_PLAYER_ID,
        "heartbeat": True
    })

# Λαμβάνει συνεχώς game states από τον server και τα αποθηκεύει στο queue για επεξεργασία από το main thread
async def receive_state():
    while True:
        state = await sub_socket.recv_json()
        state_queue.put(state)

# Διαχειρίζεται τη διαδικασία σύνδεσης και αποσύνδεσης του client από τον server
async def control_loop():
    global SERVER_ACCEPTED, CONTROL_ACTIVE, DISCONNECT_SENT, SERVER_REJECT_REASON, DISCONNECT_REQUESTED

    # Στέλνουμε αρχικό αίτημα σύνδεσης με id, nickname και class name
    await control_socket.send_json({
        "type": "connect",
        "id": CLIENT_PLAYER_ID,
        "nickname": CLIENT_NICKNAME,
        "class_name": getattr(arcade.get_window(), "class_name", None)
    })
    reply = await control_socket.recv_json()
    print("[Control reply]:", reply)    

    # Επιτυχής σύνδεση όταν ο παίκτης δεν βρίσκεται ήδη στο παιχνίδι
    if reply.get("status") == "ok":
        SERVER_ACCEPTED = True
    # Αν η σύνδεση απορριφθεί, αποθηκεύεται ο λόγος απόρριψης για να εμφανιστεί στον χρήστη
    else:
        SERVER_REJECT_REASON = reply.get("reason", "Connection rejected")
        SERVER_ACCEPTED = False
        print(SERVER_REJECT_REASON)
        return

    # Το loop παραμένει ενεργό μέχρι να ζητηθεί αποσύνδεση ή να κλείσει το παράθυρο
    while CONTROL_ACTIVE and not DISCONNECT_REQUESTED:
        await asyncio.sleep(0.1)

    # Στέλνουμε disconnect στον server ώστε να αφαιρεθεί σωστά ο παίκτης
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

# Κεντρικό παράθυρο του παιχνιδιού
class GameWindow(arcade.Window):
    # Ενημερώνουμε το networking thread ότι ο client δεν είναι πλέον ενεργός
    def on_close(self):
        global CONTROL_ACTIVE       # Χρησιμοποιούμε global flag ώστε το networking thread να καταλάβει ότι το παράθυρο έκλεισε
        CONTROL_ACTIVE = False      # Ο client δεν είναι πλέον ενεργός και θα σταλεί DISCONNECT στον server

        print("Window closed, will send DISCONNECT...")
        super().on_close()          # Κλείσιμο παραθύρου

# Ενδιάμεσο view που εμφανίζεται όσο ο client περιμένει απάντηση σύνδεσης από τον server
class ConnectingView(arcade.View):
    def __init__(self):
        super().__init__()

        global SERVER_ACCEPTED, SERVER_REJECT_REASON, DISCONNECT_REQUESTED, DISCONNECT_SENT

        # Reset των global flags ώστε κάθε νέα προσπάθεια σύνδεσης να ξεκινά καθαρά
        SERVER_ACCEPTED = None
        SERVER_REJECT_REASON = ""
        DISCONNECT_REQUESTED = False
        DISCONNECT_SENT = False

        # Timer που χρησιμοποιείται για επιστροφή στο menu αν η σύνδεση απορριφθεί
        self.reject_timer = 0.0
        self.connection_started = False

        # Text αντικείμενο που εμφανίζει μήνυμα σύνδεσης
        self.msg = arcade.Text("Connecting to server...", 0, 0, arcade.color.WHITE, 20, anchor_x="center")

    def on_show_view(self):
        # Όταν ο παίκτης μπαίνει στο παιχνίδι, σταματάμε τη μουσική του main menu
        if hasattr(self.window, "menu_music_player") and self.window.menu_music_player is not None:
            arcade.stop_sound(self.window.menu_music_player)
            self.window.menu_music_player = None

        arcade.set_background_color(arcade.color.BLACK) # Ορίζουμε μαύρο φόντο

        # Κεντράρουμε το μήνυμα σύνδεσης στο παράθυρο
        self.msg.x = self.window.width // 2
        self.msg.y = self.window.height // 2

    def on_draw(self):  # Καθαρίζει την οθόνη και σχεδιάζει το μήνυμα σύνδεσης
        self.clear()
        self.msg.draw() 

    def on_update(self, delta_time: float):
        global SERVER_ACCEPTED      # Χρησιμοποιούμε global μεταβλητή που ενημερώνεται από το networking thread (control_loop)

        # Όταν το networking loop είναι έτοιμο, ξεκινά το control_loop για σύνδεση στον server
        if not self.connection_started and NETWORK_LOOP is not None:
            self.connection_started = True
            asyncio.run_coroutine_threadsafe(control_loop(), NETWORK_LOOP)

        # Αν ο server δεχτεί τον client
        if SERVER_ACCEPTED is True:
            game_view = MyGame()                # Δημιουργούμε το βασικό Game View
            self.window.show_view(game_view)    # Αλλάζουμε view από Connecting → Game

        # Αν ο server απορρίψει τη σύνδεση, εμφανίζεται το μήνυμα λάθους και μετά επιστρέφει στο menu
        elif SERVER_ACCEPTED is False:
            self.msg.text = SERVER_REJECT_REASON or "Connection rejected"
            self.msg.color = arcade.color.RED

            self.reject_timer += delta_time

            if self.reject_timer >= 3.0:
                self.window.show_view(MenuView())

# Game View
class MyGame(arcade.View):
    def __init__(self):
        super().__init__()

        self.player_animation_dict = {}     # Dictionary που κρατάει τα animations κάθε κλάσης ώστε να μη φορτώνονται ξανά από τον δίσκο
        self.heartbeat_timer = 0.0          # Timer για heartbeat προς τον server #

        ### Input state ###
        self.held_keys = set()     # Set που κρατάει ποια πλήκτρα είναι πατημένα (για hold keys)
        self.held_move = set()     # πατημένα WASD
        self.move_order = []       # σειρά πατημάτων WASD (τελευταίο στο τέλος)
        self.last_sent_move = None # για να μη στέλνουμε συνέχεια το ίδιο

        ### Sprite lists ###
        self.actor_list = arcade.SpriteList()   # Λίστα με όλα τα sprites που σχεδιάζονται με κοινό depth sorting
        self.enemy_list = arcade.SpriteList()   # Λίστα με τα sprites των εχθρών
        self.enemy_animation_dict = {}          # Λεξικό για animation ανά είδος εχθρού

        ### Projectiles ###
        self.enemy_projectiles = arcade.SpriteList()    # Λίστα για τις μακρινές επιθέσεις των magic goblins
        self.projectile_animation_dict = {}             # Λεξικό για το animation των επιθέσεων των magic goblins

        ### Local attack / ability state ###
        self.attack_buffered = False            # Χρησιμοποιείται για buffering επίθεσης στο τέλος του animation
        self.attack_buffer_threshold = 0.70     # Το τελευταίο 30% του attack επιτρέπει buffer

        self.local_rapid_fire_until = 0.0       # Προσωρινό buff του Marksman για γρηγορότερες basic επιθέσεις

        # Χρονική στιγμή που θα επιτρέπεται ξανά τοπικά νέο attack
        self.local_next_attack_times = {
            "basic": 0.0,
            "skill1": 0.0,
            "skill2": 0.0,
        }     

        # Τοπικό cooldown επίθεσης, ώστε να μην στέλνονται συνεχόμενα attack requests στον server
        self.local_attack_cooldowns = {
            "Warrior": {
                "basic": 0.45,
                "skill1": 5.0,
                "skill2": 10.0,
            },
            "Mage": {
                "basic": 0.55,
                "skill1": 6.0,
                "skill2": 12.0,
            },
            "Marksman": {
                "basic": 0.45,
                "skill1": 8.0,
                "skill2": 6.0,
            },
        }

        self.buffer_attack_state = None         # Αποθηκεύει προσωρινά attack input που πατήθηκε λίγο πριν τελειώσει το τρέχον attack animation
        self.buffer_attack_id = None            # Είδος επίθεσης (basic/skill)

        ### Player economy / items ###
        self.gold = 0                   # Αρχικό gold
        self.inventory_open = False     # State για ανοιχτό inventory
        self.inventory = []             # Λίστα για το inventory

        self.active_elixirs = []    # Ενεργά ελιξήρια
        self.elixir_texts = []      # Περιγραφή ελιξήριων

        # Φόρτωση των icons για τα items μία φορά κατά την αρχικοποίηση
        self.item_textures = {}
        for item_name, path in ITEM_ICON_PATHS.items():
            try:
                self.item_textures[item_name] = arcade.load_texture(path)
            except Exception as e:
                print(f"Could not load item icon {path}: {e}")

        ### Session state ###
        # Κατάσταση του session όπως έρχεται από τον server
        self.session_phase = "idle"
        self.my_session_phase = "idle"
        self.lobby_countdown = 0
        self.loading_progress = 0
        self.lobby_players_count = 0
        self.waiting_players_count = 0

        # Μεταβλητές που χρησιμοποιούνται όταν το παιχνίδι τελειώσει και επιστρέφει στο menu
        self.game_end_return_timer = 0.0
        self.returning_to_menu = False
        self.final_game_status = None

        ### Objectives ###
        self.objective_text = ""
        self.objective_remaining = 0
        self.objective_complete = False

        # Προηγούμενες τιμές για να εντοπίζονται αλλαγές στο objective
        self.last_objective_text = ""
        self.last_objective_remaining = None
        self.last_objective_complete = False

        # Προσωρινό μήνυμα objective που εμφανίζεται στην οθόνη
        self.objective_message = ""
        self.objective_message_timer = 0.0

        # Καθυστέρηση πριν εμφανιστεί το αρχικό objective message
        self.objective_intro_delay = 25.0
        self.objective_intro_timer = 0.0
        self.objective_intro_shown = False

        # Περιοχή στην οποία ανήκει το objective
        self.objective_region = None
        self.last_objective_region = None

        self.objective_shown_milestones = set()     # Milestones που έχουν ήδη εμφανιστεί, ώστε να μη βγαίνουν ξανά τα ίδια μηνύματα
        
        ### Map / region state ###
        # Tilemap layers
        self.terrain_list = None
        self.road_list = None
        self.river_list = None
        self.wall_list = None
        self.bridge_list = None
        self.lava_list = None

        # Τρέχουσα περιοχή και tilemap
        self.current_region_name = None
        self.tile_map = None

        self.world_camera = arcade.Camera2D()   # Κάμερα για τον κόσμο

        ### Game state from server ###
        self.elapsed_time = 0.0         # Χρόνος που έχει περάσει στο match (από server)
        self.game_status = "playing"    # Κατάσταση παιχνιδιού

        self.player_animations = None   # Animations του local player
        self.player_sprite = None       # Sprite του τοπικού παίκτη

        self.other_sprites = {}         # Λεξικό για τους remote παίκτες
        self.enemy_sprites = {}         # Λεξικό για εχθρούς

        ### Network smoothing ###
        # Buffers για interpolation/smoothing της κίνησης των enemies 
        self.enemy_position_buffers = {}
        self.enemy_snapshots = {}
        self.enemy_interp_t = {}
        
        # Buffers για interpolation/smoothing της κίνησης των παικτών
        self.position_buffers = {}      # Λεξικό που κρατά για κάθε παίκτη τις δύο πιο πρόσφατες θέσεις του με server tick για εξομάλυνση κίνησης
        self.snapshots = {}             # Θέση sprite τη στιγμή που ήρθε το τελευταίο update
        self.interp_t = {}              # Xρόνος που πέρασε από το τελευταίο server update

        ### Text objects / UI ###
        # Text για objective
        self.objective_message_text = arcade.Text("", 0, 0, arcade.color.WHITE, font_size=20, anchor_x="center", anchor_y="center")

        # Text για inventory
        self.inventory_title_text = arcade.Text("Inventory", 0, 0, arcade.color.WHITE, font_size=22, anchor_x="center")
        self.inventory_empty_text = arcade.Text("No items", 0, 0, arcade.color.LIGHT_GRAY, font_size=16, anchor_x="center")
        self.inventory_help_text = arcade.Text("Use: 1-5 | Buy: Shift+1-5", 0, 0, arcade.color.LIGHT_GRAY, font_size=11, anchor_x="center")
        self.inventory_item_texts = []

        self.gold_text = arcade.Text("Gold: 0", 10, 0, arcade.color.YELLOW, font_size=16)   # Text για gold

        # Text για session/lobby/loading screens
        self.session_title_text = arcade.Text("", 0, 0, arcade.color.WHITE, font_size=34, anchor_x="center", anchor_y="center")
        self.session_subtitle_text = arcade.Text("", 0, 0, arcade.color.LIGHT_GRAY, font_size=18, anchor_x="center", anchor_y="center")
        self.session_progress_text = arcade.Text("", 0, 0, arcade.color.WHITE, font_size=22, anchor_x="center", anchor_y="center")

        # Text για timer παιχνιδιού
        self.timer_text = arcade.Text("00:00",10, 10, arcade.color.WHITE, font_size=20)

        # Μήνυμα αλλαγής περιοχής
        self.region_message = ""
        self.region_message_timer = 0.0
        self.region_message_text = arcade.Text("", 0, 0, arcade.color.WHITE, font_size=20, anchor_x="center", anchor_y="center")

        # UI για abilities
        self.ability_ui = []
        self.ability_labels = [
            ("basic", "SPACE", "Basic", 1),
            ("skill1", "Q", "Skill 1", 3),
            ("skill2", "E", "Skill 2", 5),
        ]

        # Δημιουργία text αντικειμένων για κάθε ability
        for attack_id, key_name, ability_name, unlock_level in self.ability_labels:
            title_text = arcade.Text(f"[{key_name}] {ability_name}", 0, 0, arcade.color.WHITE, font_size=14, anchor_x="center", anchor_y="center")

            status_text = arcade.Text("", 0, 0, arcade.color.LIGHT_GRAY, font_size=11, anchor_x="center", anchor_y="center")

            self.ability_ui.append({
                "attack_id": attack_id,
                "key": key_name,
                "name": ability_name,
                "unlock_level": unlock_level,
                "title_text": title_text,
                "status_text": status_text,
            })
        
        # Text για τα μεγάλα HP, Energy και XP bars του local player
        self.hud_hp_label_text = arcade.Text("HP", 0,  0, arcade.color.WHITE, font_size=12)
        self.hud_hp_value_text = arcade.Text("100%", 0, 0, arcade.color.WHITE, font_size=11, anchor_x="right")
        self.hud_energy_label_text = arcade.Text("EN", 0, 0, arcade.color.WHITE, font_size=12)
        self.hud_energy_value_text = arcade.Text("100%", 0, 0, arcade.color.WHITE, font_size=11, anchor_x="right")
        self.hud_xp_label_text = arcade.Text("XP", 0, 0, arcade.color.WHITE, font_size=12)
        self.hud_xp_value_text = arcade.Text("0 / 100", 0, 0, arcade.color.WHITE, font_size=11, anchor_x="right")

        # Text που εμφανίζονται στο τέλος του παιχνιδιού
        self.game_end_title_text = arcade.Text("", 0, 0, arcade.color.WHITE, font_size=44, anchor_x="center", anchor_y="center")
        self.game_end_subtitle_text = arcade.Text("", 0, 0, arcade.color.LIGHT_GRAY, font_size=18, anchor_x="center", anchor_y="center")

        ### Sound effects ###
        self.sounds = {
            "gold_gain": arcade.load_sound("assets/sounds/goldGain.ogg"),
            "item_buy": arcade.load_sound("assets/sounds/itemBuy.wav"),
            "potion_use": arcade.load_sound("assets/sounds/potionUse.mp3"),
            "level_up": arcade.load_sound("assets/sounds/levelUp.ogg"),

            "warrior_basic": arcade.load_sound("assets/sounds/swordBasic.mp3"),
            "warrior_q": arcade.load_sound("assets/sounds/swordQ.mp3"),
            "warrior_e": arcade.load_sound("assets/sounds/swordE.mp3"),

            "mage_basic": arcade.load_sound("assets/sounds/mageBasic.ogg"),
            "mage_q": arcade.load_sound("assets/sounds/mageQ.ogg"),
            "mage_e": arcade.load_sound("assets/sounds/mageE.ogg"),

            "marksman_basic": arcade.load_sound("assets/sounds/gunShot.mp3"),
            "marksman_q": arcade.load_sound("assets/sounds/gunQ.ogg"),
            "marksman_e": arcade.load_sound("assets/sounds/gunE.ogg"),

            "victory": arcade.load_sound("assets/sounds/Victory.ogg"),
            "defeat": arcade.load_sound("assets/sounds/Defeat.mp3"),

            "warrior_entry": arcade.load_sound("assets/sounds/Character/warriorEntry.wav"),
            "warrior_hurt_1": arcade.load_sound("assets/sounds/Character/warriorHurt1.wav"),
            "warrior_hurt_2": arcade.load_sound("assets/sounds/Character/warriorHurt2.wav"),
            "warrior_hurt_3": arcade.load_sound("assets/sounds/Character/warriorHurt3.wav"),
            "warrior_death_1": arcade.load_sound("assets/sounds/Character/warriorDeath1.wav"),
            "warrior_death_2": arcade.load_sound("assets/sounds/Character/warriorDeath2.wav"),
            "warrior_death_3": arcade.load_sound("assets/sounds/Character/warriorDeath3.wav"),
            "warrior_moving_1": arcade.load_sound("assets/sounds/Character/warriorMoving1.wav"),
            "warrior_moving_2": arcade.load_sound("assets/sounds/Character/warriorMoving2.wav"),
            "warrior_moving_3": arcade.load_sound("assets/sounds/Character/warriorMoving3.wav"),
            "warrior_buy_failed": arcade.load_sound("assets/sounds/Character/warriorItemBuyFailed.wav"),
            "warrior_use_failed": arcade.load_sound("assets/sounds/Character/warriorItemUseFailed.wav"),

            "mage_entry": arcade.load_sound("assets/sounds/Character/mageEntry.wav"),
            "mage_hurt_1": arcade.load_sound("assets/sounds/Character/mageHurt1.wav"),
            "mage_hurt_2": arcade.load_sound("assets/sounds/Character/mageHurt2.wav"),
            "mage_hurt_3": arcade.load_sound("assets/sounds/Character/mageHurt3.wav"),
            "mage_death_1": arcade.load_sound("assets/sounds/Character/mageDeath1.wav"),
            "mage_death_2": arcade.load_sound("assets/sounds/Character/mageDeath2.wav"),
            "mage_death_3": arcade.load_sound("assets/sounds/Character/mageDeath3.wav"),
            "mage_moving_1": arcade.load_sound("assets/sounds/Character/mageMoving1.wav"),
            "mage_moving_2": arcade.load_sound("assets/sounds/Character/mageMoving2.wav"),
            "mage_moving_3": arcade.load_sound("assets/sounds/Character/mageMoving3.wav"),
            "mage_buy_failed": arcade.load_sound("assets/sounds/Character/mageItemBuyFailed.wav"),
            "mage_use_failed": arcade.load_sound("assets/sounds/Character/mageItemUseFailed.wav"),

            "marksman_entry": arcade.load_sound("assets/sounds/Character/marksmanEntry.wav"),
            "marksman_hurt_1": arcade.load_sound("assets/sounds/Character/marksmanHurt1.wav"),
            "marksman_hurt_2": arcade.load_sound("assets/sounds/Character/marksmanHurt2.wav"),
            "marksman_hurt_3": arcade.load_sound("assets/sounds/Character/marksmanHurt3.wav"),
            "marksman_death_1": arcade.load_sound("assets/sounds/Character/marksmanDeath1.wav"),
            "marksman_death_2": arcade.load_sound("assets/sounds/Character/marksmanDeath2.wav"),
            "marksman_death_3": arcade.load_sound("assets/sounds/Character/marksmanDeath3.wav"),
            "marksman_moving_1": arcade.load_sound("assets/sounds/Character/marksmanMoving1.wav"),
            "marksman_moving_2": arcade.load_sound("assets/sounds/Character/marksmanMoving2.wav"),
            "marksman_moving_3": arcade.load_sound("assets/sounds/Character/marksmanMoving3.wav"),
            "marksman_buy_failed": arcade.load_sound("assets/sounds/Character/marksmanItemBuyFailed.wav"),
            "marksman_use_failed": arcade.load_sound("assets/sounds/Character/marksmanItemUseFailed.wav"),
        }

        self.last_gold_for_sound = None
        self.last_level_for_sound = None
        self.game_end_sound_played = False
        self.defeat_sound_played = False

        # Character voice flags
        self.character_entry_played = False
        self.character_move_voice_timer = 0.0
        self.character_move_voice_interval = 4.0
        self.character_move_voice_index = 0
        self.local_death_voice_played = False

        ### Music ###
        self.music_tracks = {
            "firstRegion": "assets/music/firstRegionMusic.ogg",
            "secondRegion": "assets/music/secondRegionMusic.ogg",
            "thirdRegion": "assets/music/thirdRegionMusic.ogg",
            "fourthRegion": "assets/music/fourthRegionMusic.ogg",

            "five_remaining": "assets/music/5remaining.ogg",
            "objective_finish": "assets/music/objectiveFinish.wav",
            "player_dead": "assets/music/playerDeadMusic.mp3",

            "dragon_trigger": "assets/music/dragonTrigger.wav",
        }

        # Τρέχουσα μουσική που παίζει
        self.current_music_key = None
        self.current_music_player = None
        self.dragon_active_in_region = False

    # Παίζει ηχητικό εφέ 
    def play_sfx(self, sound_name, volume=0.5):
        sound = self.sounds.get(sound_name) # Αναζητούμε το sound object από το dictionary των φορτωμένων ήχων

        if sound is None:   # Αν δεν βρεθεί ήχος με αυτό το όνομα, δεν κάνουμε τίποτα
            return

        try:
            arcade.play_sound(sound, volume=volume) # Αναπαραγωγή του ήχου με την ένταση που δίνεται ως παράμετρος
        except Exception as ex:
            print(f"Could not play sound {sound_name}:", ex)    # Αν υπάρξει πρόβλημα στην αναπαραγωγή, εμφανίζεται μήνυμα στο console

    # Παίζει τον κατάλληλο ήχο επίθεσης ανάλογα με την κλάση του παίκτη και το είδος της επίθεσης
    def play_attack_sound(self, attack_id):
        class_name = getattr(self.window, "class_name", "") # Παίρνουμε την κλάση που έχει επιλέξει ο παίκτης από το window

        # Αντιστοίχιση κάθε κλάσης και κάθε επίθεσης με το αντίστοιχο sound key
        attack_sounds = {
            "Warrior": {
                "basic": "warrior_basic",
                "skill1": "warrior_q",
                "skill2": "warrior_e",
            },
            "Mage": {
                "basic": "mage_basic",
                "skill1": "mage_q",
                "skill2": "mage_e",
            },
            "Marksman": {
                "basic": "marksman_basic",
                "skill1": "marksman_q",
                "skill2": "marksman_e",
            },
        }

        sound_name = attack_sounds.get(class_name, {}).get(attack_id)   # Βρίσκουμε ποιο sound key αντιστοιχεί στην κλάση και στο attack_id

        # Αν υπάρχει αντίστοιχος ήχος, τον αναπαράγουμε
        if sound_name:
            self.play_sfx(sound_name, volume=0.45)

    # Επιστρέφει την ποσότητα ενός item που υπάρχει στο inventory του παίκτη
    def inventory_quantity(self, item_name):
        for item in self.inventory:     # Διατρέχουμε όλα τα items του inventory
            if isinstance(item, dict):  # Ελέγχουμε ότι το item είναι dictionary, όπως έρχεται από το server state
                if item.get("item_name") == item_name:  # Αν το όνομα του item ταιριάζει με αυτό που ψάχνουμε
                    return int(item.get("quantity", 0)) # Επιστρέφουμε την ποσότητα του item

        return 0    # Αν δεν βρεθεί το item στο inventory, επιστρέφουμε 0

    # Ελέγχει τοπικά αν μπορεί να γίνει αγορά item
    def can_buy_item_locally(self, item_name):
        item_prices = {
            "Health_Potion": 50,
            "Energy_Potion": 50,
            "ElixirOfToughness": 200,
            "ElixirOfMagic": 200,
            "ElixirOfPower": 200,
        }

        item_max_stacks = {
            "Health_Potion": 2,
            "Energy_Potion": 2,
            "ElixirOfToughness": 1,
            "ElixirOfMagic": 1,
            "ElixirOfPower": 1,
        }

        price = item_prices.get(item_name, 0)
        max_stack = item_max_stacks.get(item_name, 1)

        # Αν δεν έχει αρκετό gold, δεν παίζουμε ήχο αγοράς
        if self.gold < price:
            return False

        # Αν το item έχει ήδη φτάσει max stack, δεν παίζουμε ήχο αγοράς
        if self.inventory_quantity(item_name) >= max_stack:
            return False

        return True
    
    # Ελέγχει τοπικά αν έχει νόημα να χρησιμοποιηθεί ένα item
    def can_use_item_locally(self, item_name):
        # Πρώτα ελέγχουμε αν υπάρχει το item στο inventory
        if self.inventory_quantity(item_name) <= 0:
            return False

        # Health Potion: αν ο παίκτης έχει ήδη full HP, δεν παίζει use sound
        if item_name == "Health_Potion":
            if self.player_sprite is not None and self.player_sprite.hp >= 0.999:
                return False

        # Energy Potion: αν ο παίκτης έχει ήδη full Energy, δεν παίζει use sound
        if item_name == "Energy_Potion":
            if self.player_sprite is not None and self.player_sprite.energy >= 0.999:
                return False

        # Για elixirs αρκεί να υπάρχει το item
        return True
    
    # Σταματάει την τρέχουσα background μουσική
    def stop_current_music(self):
        if self.current_music_player is not None:
            try:
                arcade.stop_sound(self.current_music_player)
            except Exception as ex:
                print("Could not stop music:", ex)

        self.current_music_player = None
        self.current_music_key = None


    # Παίζει background μουσική με loop
    # Αν η ίδια μουσική παίζει ήδη, δεν την ξαναξεκινάει
    def play_background_music(self, music_key, volume=0.25):
        if self.current_music_key == music_key:
            return

        music_path = self.music_tracks.get(music_key)

        if music_path is None:
            return

        self.stop_current_music()

        try:
            music = arcade.load_sound(music_path)
            self.current_music_player = arcade.play_sound(music, volume=volume)
            self.current_music_player.loop = True
            self.current_music_key = music_key

            print("Playing music:", music_key)

        except Exception as ex:
            print(f"Could not play music {music_key}:", ex)


    # Επιλέγει ποια μουσική πρέπει να παίζει με βάση region, objective και death state
    def update_background_music(self):
        # Αν έχει παιχτεί defeat sound, δεν επιτρέπουμε να παίξει οποιαδήποτε άλλη background μουσική γιατί το παιχνίδι τελείωσε
        if self.defeat_sound_played:
            self.stop_current_music()
            return

        # Αν δεν έχει φορτωθεί ακόμα περιοχή, δεν παίζουμε τίποτα
        if self.current_region_name is None:
            return

        # Αν το παιχνίδι τελείωσε, σταματάμε την background μουσική γιατί θα παίξουν Victory / Defeat sounds
        if self.game_status in ("win", "loss"):
            self.stop_current_music()
            return

        # Αν ο local player είναι νεκρός, παίζει death music
        if self.player_sprite is not None and getattr(self.player_sprite, "dead", False):
            self.play_background_music("player_dead", volume=0.25)
            return

        # Αν ολοκληρώθηκε το objective της περιοχής, παίζει objective finish μουσική μέχρι να αλλάξει περιοχή
        if self.objective_complete:
            self.play_background_music("objective_finish", volume=0.30)
            return
        
        # Αν υπάρχει ενεργός δράκος στην περιοχή, παίζει dragon trigger music
        if self.dragon_active_in_region:
            self.play_background_music("dragon_trigger", volume=0.30)
            return

        # Αν απομένουν 5 ή λιγότεροι στόχοι, παίζει πιο έντονη μουσική
        if self.objective_remaining > 0 and self.objective_remaining <= 5:
            self.play_background_music("five_remaining", volume=0.28)
            return

        # Αλλιώς παίζει η κανονική μουσική της περιοχής
        self.play_background_music(self.current_region_name, volume=0.25)

    # Επιστρέφει prefix για τα voice sounds με βάση την κλάση του τοπικού παίκτη
    def get_local_class_voice_prefix(self):
        class_name = getattr(self.window, "class_name", "")

        class_prefixes = {
            "Warrior": "warrior",
            "Mage": "mage",
            "Marksman": "marksman",
        }

        return class_prefixes.get(class_name)


    # Παίζει την entry ατάκα της κλάσης μόνο μία φορά, στο πρώτο movement input
    def play_class_entry_once(self):
        prefix = self.get_local_class_voice_prefix()

        if prefix is None:
            return

        if self.character_entry_played:
            return

        self.play_sfx(f"{prefix}_entry", volume=0.55)
        self.character_entry_played = True


    # Παίζει τυχαίο hurt voice της κλάσης
    def play_class_hurt_voice(self):
        prefix = self.get_local_class_voice_prefix()

        if prefix is None:
            return

        sound_name = random.choice([
            f"{prefix}_hurt_1",
            f"{prefix}_hurt_2",
            f"{prefix}_hurt_3",
        ])

        self.play_sfx(sound_name, volume=0.55)


    # Παίζει τυχαίο death voice της κλάσης
    def play_class_death_voice(self):
        prefix = self.get_local_class_voice_prefix()

        if prefix is None:
            return

        sound_name = random.choice([
            f"{prefix}_death_1",
            f"{prefix}_death_2",
            f"{prefix}_death_3",
        ])

        self.play_sfx(sound_name, volume=0.6)


    # Παίζει κυκλικά moving voice όσο ο χαρακτήρας κινείται
    def update_class_movement_voice(self, delta_time):
        prefix = self.get_local_class_voice_prefix()

        if prefix is None:
            return

        if self.game_status != "playing":
            return

        if self.player_sprite is not None and getattr(self.player_sprite, "dead", False):
            return

        is_moving = len(self.held_move) > 0

        # Αν ο παίκτης σταματήσει, μηδενίζεται ο timer
        # Όταν ξανακινηθεί, θα αρχίσει να μετράει από την αρχή
        if not is_moving:
            self.character_move_voice_timer = 0.0
            return

        self.character_move_voice_timer += delta_time

        if self.character_move_voice_timer < self.character_move_voice_interval:
            return

        moving_sounds = [
            f"{prefix}_moving_1",
            f"{prefix}_moving_2",
            f"{prefix}_moving_3",
        ]

        sound_name = moving_sounds[self.character_move_voice_index]
        self.play_sfx(sound_name, volume=0.45)

        # Πηγαίνει στο επόμενο moving sound κυκλικά
        self.character_move_voice_index = (self.character_move_voice_index + 1) % len(moving_sounds)

        # Reset timer μέχρι την επόμενη ατάκα
        self.character_move_voice_timer = 0.0


    # Παίζει ήχο αποτυχίας αγοράς item για την τρέχουσα κλάση
    def play_class_buy_fail_sound(self):
        prefix = self.get_local_class_voice_prefix()

        if prefix is None:
            return

        self.play_sfx(f"{prefix}_buy_failed", volume=0.55)


    # Παίζει ήχο αποτυχίας χρήσης item για την τρέχουσα κλάση
    def play_class_use_fail_sound(self):
        prefix = self.get_local_class_voice_prefix()

        if prefix is None:
            return

        self.play_sfx(f"{prefix}_use_failed", volume=0.55)

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

    # Μέθοδος που καθαρίζει όλα τα τοπικά inputs του παίκτη
    def stop_local_input(self):
        self.held_keys.clear()      # Καθαρίζουμε τα πλήκτρα που θεωρούνται πατημένα
        self.held_move.clear()      # Καθαρίζουμε τις ενεργές κατευθύνσεις κίνησης
        self.move_order.clear()     # Καθαρίζουμε τη σειρά με την οποία πατήθηκαν τα πλήκτρα κίνησης

        # Ακυρώνουμε τυχόν buffered attack
        self.attack_buffered = False
        self.buffer_attack_state = None
        self.buffer_attack_id = None

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

        # Καθαρίζουμε τυχόν παλιά input states, ώστε το νέο game view να ξεκινήσει χωρίς κρατημένα πλήκτρα
        self.held_keys.clear()  
        self.held_move.clear()
        self.move_order.clear()
        self.last_sent_move = None

        client_attackAndUI.update_ability_ui_positions(self)    # Τοποθετούμε τα ability UI texts στο κάτω μέρος της οθόνης

    # Μέθοδος που καλείται όταν το συγκεκριμένο view παύει να εμφανίζεται
    def on_hide_view(self):
        self.stop_local_input()

    # Μέθοδος που καλείται όταν το παράθυρο χάνει focus
    def on_deactivate(self):
        self.stop_local_input()

    # Ζωγραφίζουμε τα αντικείμενα
    def on_draw(self):
        self.clear()    # Καθαρίζει την οθόνη πριν ξανασχεδιαστεί το νέο frame

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

            # Ταξινομούμε τα sprites με βάση το Y, ώστε όσα βρίσκονται πιο κάτω στην οθόνη να εμφανίζονται μπροστά από όσα βρίσκονται πιο πάνω
            self.actor_list.sort(key=self.sort_key)  # Ζωγραφίζουμε όλα τα sprites
            self.actor_list.draw()

            # Projectiles εχθρών
            self.enemy_projectiles.draw()

            # Μπάρες για local player
            if self.player_sprite:
                client_draw.draw_player_status_bars(self, self.player_sprite)

            # Μπάρες για άλλους παίκτες
            for spr in self.other_sprites.values():
                if isinstance(spr, PlayerSprite):
                    client_draw.draw_player_status_bars(self, spr)

            # Μπάρες για enemies
            for spr in self.enemy_sprites.values():
                if isinstance(spr, EnemySprite) and not getattr(spr, "dead", False):
                    client_draw.draw_enemy_status_bars(self, spr)

        self.timer_text.draw()      # Χρονόμετρο παιχνιδιού

        # Εμφάνιση gold πάνω αριστερά
        self.gold_text.x = 10
        self.gold_text.y = self.window.height - 55
        self.gold_text.draw()

        client_draw.draw_objective_message(self)        # Προσωρινό μήνυμα objective στο κέντρο της οθόνης

        client_draw.draw_local_player_hud_bars(self)    # Μεγάλες μπάρες HP / Energy αριστερά από τα abilities

        # Background panel για τα abilities στο κάτω μέρος της οθόνης
        bar_width = 560
        bar_height = 58
        left = self.window.width / 2 - bar_width / 2
        bottom = 10

        arcade.draw_lbwh_rectangle_filled(
            left,
            bottom,
            bar_width,
            bar_height,
            (0, 0, 0, 160)
        )

        # Σχεδίαση τίτλου και κατάστασης κάθε ability
        for ability in self.ability_ui:
            ability["title_text"].draw()
            ability["status_text"].draw()

        # Εμφάνιση μηνύματος στο κέντρο της οθόνης όταν ο παίκτης αλλάζει περιοχή
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
        
        client_draw.draw_active_elixir_buffs(self)  # Ενεργά elixir buffs δεξιά από τα abilities
        client_draw.draw_inventory_ui(self)         # Inventory panel, αν είναι ανοιχτό
        client_draw.draw_session_screen(self)       # Οθόνες lobby / loading / waiting
        client_draw.draw_game_end_overlay(self)     # Overlay νίκης ή ήττας

    # Μέθοδος που διαβάζει το πιο πρόσφατο state που έστειλε ο server και ενημερώνει τις τοπικές δομές του client
    def process_server_state(self):
        # Αν δεν υπάρχει διαθέσιμο state από τον server, δεν γίνεται καμία ενημέρωση
        if state_queue.empty():
            return None

        # Παίρνουμε μόνο το πιο πρόσφατο state και αγνοούμε τα παλαιότερα, ώστε ο client να μη μένει πίσω αν έχουν μαζευτεί πολλά states
        latest_state = None
        while not state_queue.empty():
            latest_state = state_queue.get()

        # Αν για κάποιο λόγο δεν πήραμε state, σταματάμε
        if latest_state is None:
            return None
        
        # Παίρνουμε το tick του server (αύξων αριθμός ενημέρωσης του server)
        tick = latest_state.get("tick")
        if tick is None:
            return None
        
        # Διάρκεια ενός tick στον server
        tick_dt = latest_state.get("tick_dt", 0.02)
        self.tick_dt = tick_dt

        # Ενημερώνουμε τον χρόνο και την κατάσταση του παιχνιδιού όπως τα στέλνει ο server
        self.elapsed_time = latest_state.get("elapsed_time", self.elapsed_time) 
        self.game_status = latest_state.get("game_status", "playing")           

        # Παίρνουμε τη γενική κατάσταση του game session από τον server και το ξεχωριστό session status κάθε παίκτη
        session_state = latest_state.get("session", {})
        player_session_status = latest_state.get("player_session_status", {})

        self.session_phase = session_state.get("phase", "idle")     # Συνολική φάση του παιχνιδιού
        self.my_session_phase = player_session_status.get(CLIENT_PLAYER_ID, self.session_phase) # Φάση που ισχύει ειδικά για τον τοπικό παίκτη, αν δεν υπάρχει χρησιμοποιείται default

        self.lobby_countdown = int(session_state.get("lobby_countdown", 0))
        self.loading_progress = int(session_state.get("loading_progress", 0))
        self.lobby_players_count = int(session_state.get("lobby_players_count", 0))
        self.waiting_players_count = int(session_state.get("waiting_players_count", 0))

        # Κατάσταση όλων των παικτών από τον server
        players_state = latest_state.get("players", {})
        enemies_state = latest_state.get("enemies", {})

        # Ελέγχουμε αν ο τοπικός παίκτης άλλαξε περιοχή σύμφωνα με τον server
        local_player_state = players_state.get(CLIENT_PLAYER_ID)
        if local_player_state is not None:
            # Αν η περιοχή που έστειλε ο server είναι διαφορετική από την τρέχουσα, φορτώνουμε το νέο map στον client
            new_region = local_player_state.get("region", "firstRegion")
            if new_region != self.current_region_name:
                self.load_region(new_region)

                # Εμφανίζεται σύντομο μήνυμα αλλαγής περιοχής στο κέντρο της οθόνης
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

        # Μετατροπή elapsed time σε μορφή λεπτά:δευτερόλεπτα
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
            level = int(pos.get("level", 1))
            hp = pos.get("hp", 1.0)
            energy = pos.get("energy", 1.0)
            xp = int(pos.get("xp", 0))
            xp_next = int(pos.get("xp_next", 0))
            gold = pos.get("gold", 0)
            inventory = pos.get("inventory", [])
            active_elixirs = pos.get("active_elixirs", [])

            pstate = pos.get("state", IDLE)
            pdir = pos.get("dir", DOWN)
            phurt_seq = pos.get("hurt_seq", 0)
            pdead = bool(pos.get("dead", False))

            # Αν είναι ο τοπικός παίκτης, χρησιμοποιούμε το βασικό player_sprite
            if pid == CLIENT_PLAYER_ID:
                sprite = self.player_sprite
            else:
                # Αν είναι remote player και δεν υπάρχει ακόμα sprite για αυτόν, φορτώνουμε τα animations της κλάσης του και δημιουργούμε νέο PlayerSprite
                if pid not in self.other_sprites:
                    if class_name not in self.player_animation_dict:
                        self.player_animation_dict[class_name] = load_player_animations(class_name)

                    player_scale = CLASS_SCALES.get(class_name, 2.0)
                    spr = PlayerSprite(self.player_animation_dict[class_name], scale=player_scale)
                    self.other_sprites[pid] = spr
                    self.actor_list.append(spr)
                sprite = self.other_sprites[pid]

            sprite.dead = pdead

            # Ενημερώνονται τα στοιχεία που εμφανίζονται πάνω στον παίκτη και στο UI
            sprite.nickname = nickname
            sprite.level = level
            sprite.hp = hp
            sprite.energy = energy
            sprite.xp = xp
            sprite.xp_next = xp_next

            # Για τον local player ενημερώνουμε επιπλέον στοιχεία του HUD, όπως gold, inventory, ενεργά elixirs και objective
            if pid == CLIENT_PLAYER_ID:
                new_gold = int(gold)
                new_level = int(level)

                new_objective_text = pos.get("objective_text", "")
                new_objective_remaining = int(pos.get("objective_remaining", 0))
                new_objective_complete = bool(pos.get("objective_complete", False))
                new_objective_region = pos.get("region", self.current_region_name)

                # Ήχος όταν αυξάνεται το gold
                if self.last_gold_for_sound is not None and new_gold > self.last_gold_for_sound:
                    self.play_sfx("gold_gain", volume=0.55)

                # Ήχος όταν ανεβαίνει level
                if self.last_level_for_sound is not None and new_level > self.last_level_for_sound:
                    self.play_sfx("level_up", volume=0.6)

                # Αποθηκεύουμε τις τελευταίες τιμές για τον επόμενο έλεγχο
                self.last_gold_for_sound = new_gold
                self.last_level_for_sound = new_level

                # Κανονική ενημέρωση HUD/state
                self.gold = new_gold
                self.inventory = inventory
                self.active_elixirs = active_elixirs
                self.gold_text.text = f"Gold: {self.gold}"

                self.objective_text = new_objective_text
                self.objective_remaining = new_objective_remaining
                self.objective_complete = new_objective_complete
                self.objective_region = new_objective_region

            # Για τους remote players το animation state συγχρονίζεται απευθείας από τον server
            # Για τον local player αποφεύγουμε να το κάνουμε εδώ, ώστε να μη χαλάει το τοπικό attack animation
            if pid != CLIENT_PLAYER_ID:
                sprite.set_base_state(pstate, pdir)

            # Αν ο server δηλώσει ότι ο παίκτης πέθανε, ξεκινάμε death animation
            # Αν αυξήθηκε το hurt_seq, σημαίνει ότι δέχτηκε νέο hit και ενεργοποιούμε hurt feedback
            if pdead:
                if pid == CLIENT_PLAYER_ID and not self.local_death_voice_played:
                    self.play_class_death_voice()
                    self.local_death_voice_played = True

                sprite.trigger_death(pdir)

            else:
                if pid == CLIENT_PLAYER_ID:
                    self.local_death_voice_played = False

                # Αν ο server έκανε revive τον παίκτη, καθαρίζουμε τα death flags ώστε το sprite να μπορεί να ξαναεμφανιστεί και να κινηθεί
                if getattr(sprite, "death_started", False) or getattr(sprite, "despawn", False):
                    sprite.death_started = False
                    sprite.death_anim_finished = False
                    sprite.death_hold_until = 0.0
                    sprite.despawn = False
                    sprite.attack_finished = False
                    sprite.attack_dir = None

                    sprite.alpha = 255
                    sprite.color = arcade.color.WHITE

                    sprite.force_state(IDLE, pdir, reset=True)

                    # Αν το sprite είχε αφαιρεθεί από τα sprite lists λόγω death/despawn, το ξαναβάζουμε στο actor_list
                    if sprite not in self.actor_list:
                        self.actor_list.append(sprite)

                elif phurt_seq > getattr(sprite, "last_hurt_seq", 0):
                    sprite.last_hurt_seq = phurt_seq

                    if pid == CLIENT_PLAYER_ID:
                        self.play_class_hurt_voice()

                    sprite.trigger_hurt(pdir)

            # Αποθηκεύουμε τις δύο πιο πρόσφατες server θέσεις του παίκτη, αυτές χρησιμοποιούνται για ομαλή κίνηση αντί για απότομη τηλεμεταφορά
            buf = self.position_buffers.setdefault(pid, [])
            buf.append((x, y, tick))
            if len(buf) > 2:
                buf.pop(0)

            # Snapshot της τρέχουσας θέσης του sprite τη στιγμή που έφτασε νέο server state και από αυτή τη θέση θα ξεκινήσει το interpolation
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

        self.dragon_active_in_region = False

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
            
            # Αν υπάρχει ζωντανός δράκος στην τρέχουσα περιοχή, ενεργοποιείται η dragon trigger μουσική
            if "dragon" in etype.lower() and not dead:
                self.dragon_active_in_region = True

            # Αν δεν υπάρχει ακόμα sprite για τον συγκεκριμένο εχθρό, το δημιουργούμε
            if eid not in self.enemy_sprites:
                if etype not in self.enemy_animation_dict:
                    self.enemy_animation_dict[etype] = load_enemy_animations(etype)

                enemy_scale = ENEMY_SCALES.get(etype, 1.9)
                espr = EnemySprite(etype, self.enemy_animation_dict[etype], scale=enemy_scale)
                
                self.enemy_sprites[eid] = espr
                self.enemy_list.append(espr)
                self.actor_list.append(espr)   # Ο εχθρός προστίθεται και στο actor_list, ώστε να συμμετέχει στο depth sorting

            espr = self.enemy_sprites[eid]

            # Αν είναι νέος enemy, βάζουμε αρχικά τη θέση του απευθείας
            if eid not in self.enemy_position_buffers:
                espr.center_x = ex
                espr.center_y = ey
                self.enemy_position_buffers[eid] = [(ex, ey, tick)]
                self.enemy_snapshots[eid] = (ex, ey)
                self.enemy_interp_t[eid] = 0.0
            else:
                buf = self.enemy_position_buffers[eid]

                # Προσθέτουμε νέα θέση μόνο αν άλλαξε πραγματικά η θέση του enemy, ετσι αποφεύγουμε να γεμίζει το buffer με ίδιες θέσεις
                last_x, last_y, last_tick = buf[-1]

                if abs(ex - last_x) > 0.01 or abs(ey - last_y) > 0.01:
                    buf.append((ex, ey, tick))

                    if len(buf) > 2:
                        buf.pop(0)

                    # Snapshot της τρέχουσας θέσης του enemy για να ξεκινήσει σωστά το smoothing
                    self.enemy_snapshots[eid] = (espr.center_x, espr.center_y)
                    self.enemy_interp_t[eid] = 0.0

            # Τα υπόλοιπα στοιχεία ενημερώνονται κανονικά
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

            # Αν ξεκίνησε νέο attack σύμφωνα με τον server, κάνουμε reset το attack animation ώστε να παίξει από την αρχή
            elif (
                estate in (ATTACK, WALK_ATTACK)
                and attack_seq > getattr(espr, "last_attack_seq", 0)
                and not getattr(espr, "hurt_active", False)
            ):
                espr.last_attack_seq = attack_seq
                espr.force_state(estate, edir, reset=True)

            # Αν δεν υπάρχει νέο attack/hurt/death, απλά συγχρονίζουμε το base state
            else:
                if estate in (ATTACK, WALK_ATTACK) and getattr(espr, "attack_finished", False):
                    espr.set_base_state(WALK, edir)
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

                self.enemy_position_buffers.pop(eid, None)
                self.enemy_snapshots.pop(eid, None)
                self.enemy_interp_t.pop(eid, None)

    # Μέθοδος που κάνει interpolation και extrapolation ώστε η κίνηση των εχθρών να φαίνεται ομαλή
    def apply_enemy_smoothing(self, delta_time):
        # Διατρέχουμε όλα τα enemy sprites που υπάρχουν στον client
        for eid, sprite in self.enemy_sprites.items():
            # Παίρνουμε το position buffer του συγκεκριμένου εχθρού
            # Το buffer κρατά τις πιο πρόσφατες θέσεις που έστειλε ο server
            buf = self.enemy_position_buffers.get(eid)

            if not buf:     # Αν δεν υπάρχουν διαθέσιμες θέσεις για τον εχθρό, δεν κάνουμε τίποτα
                continue

            # Αν έχουμε μόνο μία θέση, πάμε απευθείας εκεί
            if len(buf) == 1:
                x, y, _ = buf[0]
                sprite.center_x = x
                sprite.center_y = y
                continue

            # Παίρνουμε τις δύο πιο πρόσφατες θέσεις, κάθε θέση περιλαμβάνει x, y και server tick
            (x0, y0, tick0), (x1, y1, tick1) = buf[0], buf[1]

            dt_ticks = tick1 - tick0    # Υπολογίζουμε πόσα server ticks πέρασαν ανάμεσα στις δύο θέσεις

            # Μετατρέπουμε τη διαφορά των ticks σε πραγματικό χρόνο με βάση τη διάρκεια κάθε server tick
            dt_server = dt_ticks * getattr(self, "tick_dt", 0.02)

            # Αν για οποιονδήποτε λόγο τα ticks ή ο χρόνος δεν είναι έγκυρα, το sprite μεταφέρεται απευθείας στην τελευταία γνωστή θέση
            if dt_ticks <= 0 or dt_server <= 0:
                sprite.center_x = x1
                sprite.center_y = y1
                continue

            # Αυξάνουμε τον τοπικό χρόνο interpolation για τον συγκεκριμένο εχθρό
            # Το delta_time είναι ο χρόνος που πέρασε από το προηγούμενο frame του client
            t_local = self.enemy_interp_t.get(eid, 0.0) + delta_time
            self.enemy_interp_t[eid] = t_local

            # Υπολογίζουμε την παράμετρο interpolation στο διάστημα 0..1
            # Όσο το t πλησιάζει το 1, το sprite πλησιάζει περισσότερο τη νέα θέση
            t = t_local / dt_server

            # Περιορίζουμε την τιμή του t ώστε να μην ξεπερνά τα όρια 0..1
            if t > 1.0:
                t = 1.0
            elif t < 0.0:
                t = 0.0

            # Παίρνουμε τη θέση του sprite τη στιγμή που έφτασε η νέα θέση από τον server, αυτή χρησιμοποιείται ως αφετηρία για την ομαλή μετάβαση
            snap_x, snap_y = self.enemy_snapshots.get(eid, (sprite.center_x, sprite.center_y))

            # Ομαλή μετάβαση προς τη νέα θέση
            sprite.center_x = snap_x + (x1 - snap_x) * t
            sprite.center_y = snap_y + (y1 - snap_y) * t

    # Μέθοδος που κάνει interpolation και extrapolation ώστε η κίνηση των παικτών να φαίνεται ομαλή
    def apply_player_smoothing(self, delta_time):
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

    # Μέθοδος που καλείται κάθε frame και συγχρονίζει τον client με τον server, στέλνει inputs, ενημερώνει animations, projectiles, UI και κάμερα
    def on_update(self, delta_time):
        self.process_server_state()         # Παίρνουμε το πιο πρόσφατο state από τον server και ενημερώνουμε sprites, UI και game status
        self.update_background_music()      # Ενημέρωση μουσικής
        self.update_class_movement_voice(delta_time) 

        self.heartbeat_timer += delta_time  

        # Heartbeat προς τον server μία φορά το δευτερόλεπτο, ώστε ο server να γνωρίζει ότι ο client παραμένει συνδεδεμένος
        if self.heartbeat_timer >= 1.0:
            self.heartbeat_timer = 0.0

            if NETWORK_LOOP is not None and CLIENT_PLAYER_ID is not None:
                asyncio.run_coroutine_threadsafe(
                    send_heartbeat(),
                    NETWORK_LOOP
                )

        # Αν έχει ξεκινήσει επιστροφή στο main menu, συνεχίζουμε τον timer ανεξάρτητα από το αν ο server άλλαξε ξανά game_status σε playing
        if self.returning_to_menu:
            self.game_end_return_timer -= delta_time

            if self.game_end_return_timer <= 0:
                global DISCONNECT_REQUESTED

                # Ζητάμε αποσύνδεση και επιστρέφουμε στο αρχικό menu
                self.stop_local_input()
                DISCONNECT_REQUESTED = True
                self.window.show_view(MenuView())
                return

            return

        # Όταν ο server στείλει για πρώτη φορά win/loss, αποθηκεύουμε το τελικό αποτέλεσμα και ξεκινάμε μικρό timer πριν την επιστροφή στο menu
        if self.game_status in ("win", "loss"):
            self.returning_to_menu = True
            self.game_end_return_timer = 6.0
            self.final_game_status = self.game_status

            if not self.game_end_sound_played:
                # Όταν τελειώσει το παιχνίδι, σταματάμε οποιαδήποτε background μουσική
                self.stop_current_music()

                if self.game_status == "win":
                    self.play_sfx("victory", volume=0.7)
                else:
                    self.play_sfx("defeat", volume=0.7)

                    self.defeat_sound_played = True

                self.game_end_sound_played = True

            return

        # Εφαρμόζουμε interpolation/smoothing ώστε η κίνηση παικτών και εχθρών να φαίνεται ομαλή ανάμεσα στα server updates
        self.apply_player_smoothing(delta_time)
        self.apply_enemy_smoothing(delta_time)

        # Αν ο client βρίσκεται σε ενεργό παιχνίδι, στέλνουμε movement input στον server μόνο όταν αλλάξει η κατεύθυνση κίνησης
        if (
            NETWORK_LOOP is not None
            and self.player_sprite
            and self.game_status == "playing"
            and self.my_session_phase == "playing"
        ):
            s = self.player_sprite.state

            if s == DEATH or getattr(self.player_sprite, "death_started", False):   # Αν ο παίκτης είναι νεκρός, δεν στέλνουμε κίνηση
                move_dir = None

            # Αν ο παίκτης βρίσκεται σε στάσιμο attack animation, σταματάμε την κίνηση μέχρι να ολοκληρωθεί το attack
            elif s in (ATTACK, ATTACK02, ATTACK03) and self.player_sprite.attack_dir is not None: 
                move_dir = None

            else:
                # Παίρνουμε την τρέχουσα κατεύθυνση από τα WASD και τη μετατρέπουμε σε string που καταλαβαίνει ο server
                current_move_dir = self.get_current_move_dir()
                move_dir = self.dir_to_move_str(current_move_dir)

            # Αν δεν υπάρχει κίνηση, στέλνουμε STOP μία φορά ώστε ο server να σταματήσει την server-side κίνηση του παίκτη
            if move_dir is None:
                if self.last_sent_move is not None:
                    self.last_sent_move = None
                    asyncio.run_coroutine_threadsafe(send_move("STOP"), NETWORK_LOOP)

            # Αν υπάρχει νέα κατεύθυνση και είναι διαφορετική από την τελευταία που στάλθηκε, τη στέλνουμε στον server
            else:
                if move_dir != self.last_sent_move:
                    self.last_sent_move = move_dir
                    asyncio.run_coroutine_threadsafe(send_move(move_dir), NETWORK_LOOP)

        # Αν το game δεν είναι πλέον σε κατάσταση playing, βεβαιωνόμαστε ότι έχει σταλεί STOP στον server         
        elif NETWORK_LOOP is not None and self.player_sprite and self.game_status != "playing":
            if self.last_sent_move is not None:
                self.last_sent_move = None
                asyncio.run_coroutine_threadsafe(send_move("STOP"), NETWORK_LOOP)

        # Ενημέρωση του local animation state με βάση το input, μόνο όταν δεν παίζει attack ή death animation
        if self.player_sprite:
            active_attack = (
                self.player_sprite.state in (ATTACK, ATTACK02, ATTACK03, WALK_ATTACK)
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

        # Ενημέρωση animation του τοπικού παίκτη με βάση το delta_time
        if self.player_sprite:
            self.player_sprite.update_animation(delta_time)

            # Αν το sprite έχει ολοκληρώσει death/despawn διαδικασία, αφαιρείται από τα sprite lists
            if getattr(self.player_sprite, "despawn", False):
                self.player_sprite.remove_from_sprite_lists()

            # Όταν ολοκληρωθεί ένα attack animation, ελέγχουμε αν υπάρχει αποθηκευμένο buffered attack
            if self.player_sprite.attack_finished:
                self.player_sprite.attack_finished = False

                # Αν υπάρχει buffered attack, προσπαθούμε να το ξεκινήσουμε αμέσως
                if self.attack_buffered:
                    attack_id = self.buffer_attack_id or "basic"
                    attack_state = self.buffer_attack_state
                    if attack_state is None:
                        attack_state = ATTACK

                    started = client_attackAndUI.start_local_attack(self, attack_id, attack_state)

                    # Αν το buffered attack δεν μπορεί να ξεκινήσει, καθαρίζουμε το buffer και επιστρέφουμε σε walk ή idle
                    if not started:
                        self.attack_buffered = False
                        self.buffer_attack_state = None
                        self.buffer_attack_id = None
                        self.player_sprite.attack_dir = None
                        client_attackAndUI.return_to_move_or_idle(self, reset=True)

                # Αν δεν υπάρχει buffered attack, το attack τελείωσε κανονικά και ο παίκτης επιστρέφει σε walk ή idle
                else:
                    self.player_sprite.attack_dir = None
                    client_attackAndUI.return_to_move_or_idle(self, reset=True)

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

        # Ενημερώνουμε την κατάσταση των ability UI texts, όπως Ready, cooldown, Locked ή No Energy
        client_attackAndUI.update_ability_ui_state(self)

        # Ενημερώνουμε τα objective messages και τους timers εμφάνισής τους
        client_attackAndUI.update_objective_messages(self, delta_time)
            
        # Ενημέρωση κάμερας
        self.update_camera()

        # Μειώνουμε τον timer του μηνύματος αλλαγής περιοχής και το κρύβουμε όταν λήξει
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
    
    # Βοηθητική μέθοδος που στέλνει attack request στον server μέσω του networking thread
    def send_attack_to_server(self, direction, attack_id):
        if NETWORK_LOOP is not None:
            self.play_attack_sound(attack_id)   # Ηχητικό εφέ επίθεσης
            asyncio.run_coroutine_threadsafe(send_attack(direction, attack_id), NETWORK_LOOP)
    
    # Μέθοδος για τα projectile των ranged εχθρών
    def spawn_enemy_projectile_if_needed(self, enemy: EnemySprite):
        enemy_def = get_enemy_type_defs(enemy.enemy_type)

        if enemy_def.get("attack_type") != "ranged":    # Θέλουμε μόνο ranged χαρακτήρες
            return

        if enemy.state not in (ATTACK, ATTACK02, ATTACK03, WALK_ATTACK):    # Το projectile πρέπει να δημιουργείται μόνο όταν ο enemy βρίσκεται σε attack animation
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
        # Αν το παιχνίδι δεν είναι σε κατάσταση playing, αγνοούμε όλα τα inputs
        if self.game_status != "playing":
            return

        # Το TAB ανοίγει ή κλείνει το inventory panel
        if key == arcade.key.TAB:
            self.inventory_open = not self.inventory_open
            return
        
        # Αν το inventory είναι ανοιχτό, τα πλήκτρα 1-5 αντιστοιχούν σε items
        # Με Shift + αριθμό γίνεται αγορά, ενώ με απλό αριθμό γίνεται χρήση item
        if self.inventory_open:
            item_to_buy = None

            # Αντιστοίχιση αριθμητικών πλήκτρων με τα διαθέσιμα consumable items
            if key == arcade.key.KEY_1:
                item_to_buy = "Health_Potion"
            elif key == arcade.key.KEY_2:
                item_to_buy = "Energy_Potion"
            elif key == arcade.key.KEY_3:
                item_to_buy = "ElixirOfToughness"
            elif key == arcade.key.KEY_4:
                item_to_buy = "ElixirOfMagic"
            elif key == arcade.key.KEY_5:
                item_to_buy = "ElixirOfPower"

            # Αν επιλέχθηκε item και υπάρχει ενεργό network loop, στέλνουμε το αντίστοιχο request στον server
            if item_to_buy is not None and NETWORK_LOOP is not None:
                # Με Shift γίνεται αγορά item
                if modifiers & arcade.key.MOD_SHIFT:
                    # Παίζει ήχος αγοράς μόνο αν τοπικά φαίνεται ότι υπάρχει αρκετό gold και δεν έχει γεμίσει το max stack
                    if self.can_buy_item_locally(item_to_buy):
                        self.play_sfx("item_buy", volume=0.5)
                    
                    # Αν δεν υπάρχει αρκετό gold ή έχει γεμίσει το stack, παίζει fail voice
                    else:
                        self.play_class_buy_fail_sound()

                    asyncio.run_coroutine_threadsafe(
                        send_buy_item(item_to_buy),
                        NETWORK_LOOP
                    ) 

                # Χωρίς Shift γίνεται χρήση item
                else:
                    # Παίζει ήχος χρήσης μόνο αν ο client βλέπει ότι το item υπάρχει στο inventory.
                    if self.can_use_item_locally(item_to_buy):
                        self.play_sfx("potion_use", volume=0.5)

                    # Αν ο παίκτης δεν έχει το item, παίζει fail voice
                    else:
                        self.play_class_use_fail_sound()

                    asyncio.run_coroutine_threadsafe(
                        send_use_item(item_to_buy),
                        NETWORK_LOOP
                    )

                return

        # Πλήκτρα κίνησης WASD
        # Τα αποθηκεύουμε πάντα, ακόμα και αν ο παίκτης βρίσκεται σε attack animation, ώστε να ξέρουμε ποια κατεύθυνση κρατάει ο χρήστης
        if key in (arcade.key.W, arcade.key.A, arcade.key.S, arcade.key.D):
            self.play_class_entry_once()
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
                    self.player_sprite.state in (ATTACK, ATTACK02, ATTACK03, WALK_ATTACK)
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
    
        # Πλήκτρα επίθεσης / abilities
        # SPACE = basic, Q = skill1, E = skill2
        attack_data = client_attackAndUI.get_attack_from_key(self, key)

        # Αν υπάρχει αντιστοίχιση attack και υπάρχει player sprite, προωθούμε το αίτημα επίθεσης στο client_attackAndUI
        if attack_data is not None and self.player_sprite:
            attack_id, attack_state = attack_data
            client_attackAndUI.request_attack(self, attack_id, attack_state)
            return

        # Όλα τα υπόλοιπα πλήκτρα αποθηκεύονται γενικά για πιθανή μελλοντική χρήση
        self.held_keys.add(key)

    # Μέθοδος για τις λειτουργίες με το που αφήσουμε κάποιο κουμπί
    def on_key_release(self, key, modifiers):
        # Αν το παιχνίδι δεν είναι σε κατάσταση playing, αγνοούμε το input
        if self.game_status != "playing":
            return

        # Απελευθέρωση πλήκτρων κίνησης WASD
        if key in (arcade.key.W, arcade.key.A, arcade.key.S, arcade.key.D):
            self.held_move.discard(key)     # Αφαιρούμε το πλήκτρο από τις ενεργές κατευθύνσεις

            if key in self.move_order:      # Αφαιρούμε το πλήκτρο και από τη σειρά πατημένων κινήσεων
                self.move_order.remove(key)

            if self.player_sprite:
                active_attack = (           # Αν παίζει attack animation, δεν αλλάζουμε το animation state από την κίνηση
                    self.player_sprite.state in (ATTACK, ATTACK02, ATTACK03, WALK_ATTACK)
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
                            attack_id = self.buffer_attack_id or "basic"
                            attack_state = self.buffer_attack_state
                            if attack_state is None:
                                attack_state = ATTACK

                            started = client_attackAndUI.start_local_attack(self, attack_id, attack_state)

                            if started:
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

    window = GameWindow(1280, 720, "Celestial Lands")   # Δημιουργία του κεντρικού παραθύρου του παιχνιδιού
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