import arcade

# Ρυθμίσεις Sprite sheet 
FRAME_W = 64    # Πλάτος frame στο sprite sheet
FRAME_H = 64    # Ύψος frame στο sprite sheet
SCALE = 2       # Κλίμακα sprite στο παιχνίδι

DOWN  = "down"
LEFT  = "left"
RIGHT = "right"
UP    = "up"

IDLE = "idle"
WALK = "walk"
ATTACK = "attack"
HURT = "hurt"
DEATH = "death"
WALK_ATTACK = "walk_attack"

ENEMY_TYPES = {

    "orc1": {
        # Core stats
        "hp_max": 120,
        "damage": 15,
        "resist": 10,
        "attack_speed": 1,   # attacks per second
        "move_speed": 3.2,

        # Collision 
        "hitbox_w": 46,
        "hitbox_h": 72,

        # Combat range (pixels)
        "aggro_radius": 240,
        "lose_radius": 320,
        "attack_range": 64,    # ~1 tile

        # Timing
        "windup": 0.45,        # seconds μέχρι να γίνει το hit
    },
}

def sheet_grid(path, columns, count):
    sheet = arcade.SpriteSheet(path)
    return sheet.get_texture_grid(
        size=(FRAME_W, FRAME_H),
        columns=columns,
        count=count
    )

def load_warrior_animations():
    base = "assets/classes/warrior/"

    idle = sheet_grid(base+"idle.png", 12, 40)
    walk = sheet_grid(base+"walk.png", 6, 24)
    hurt = sheet_grid(base+"hurt.png", 5, 20)
    atk  = sheet_grid(base+"attack.png", 8, 32)
    dea  = sheet_grid(base+"death.png", 7, 28)
    watk = sheet_grid(base+"walk_attack.png", 6, 24)

    return {
        IDLE: {DOWN: idle[0:12], LEFT: idle[12:24], RIGHT: idle[24:36], UP: idle[36:40]},
        WALK: {DOWN: walk[0:6], LEFT: walk[6:12], RIGHT: walk[12:18], UP: walk[18:24]},
        HURT: {DOWN: hurt[0:5], LEFT: hurt[5:10], RIGHT: hurt[10:15], UP: hurt[15:20]},
        ATTACK:{DOWN: atk[0:8], LEFT: atk[8:16], RIGHT: atk[16:24], UP: atk[24:32]},
        DEATH:{DOWN: dea[0:7], LEFT: dea[7:14], RIGHT: dea[14:21], UP: dea[21:28]},
        WALK_ATTACK:{DOWN: watk[0:6], LEFT: watk[6:12], RIGHT: watk[12:18], UP: watk[18:24]},
    }

def load_enemy_animations(enemy_name="orc1"):
    base = f"assets/enemies/{enemy_name}_"
    idle = sheet_grid(base+"idle.png", 4, 16)
    walk = sheet_grid(base+"walk.png", 6, 24)
    hurt = sheet_grid(base+"hurt.png", 6, 24)
    atk  = sheet_grid(base+"attack.png", 8, 32)
    dea  = sheet_grid(base+"death.png", 8, 32)
    watk = sheet_grid(base+"walk_attack.png", 6, 24)

    return {
        IDLE: {DOWN: idle[0:4], UP: idle[4:8], LEFT: idle[8:12], RIGHT: idle[12:16]},
        WALK: {DOWN: walk[0:6], UP: walk[6:12], LEFT: walk[12:18], RIGHT: walk[18:24]},
        HURT: {DOWN: hurt[0:6], UP: hurt[6:12], LEFT: hurt[12:18], RIGHT: hurt[18:24]},
        ATTACK:{DOWN: atk[0:8], UP: atk[8:16], LEFT: atk[16:24], RIGHT: atk[24:32]},
        DEATH:{DOWN: dea[0:8], UP: dea[8:16], LEFT: dea[16:24], RIGHT: dea[24:32]},
        WALK_ATTACK:{DOWN: watk[0:6], UP: watk[6:12], LEFT: watk[12:18], RIGHT: watk[18:24]},
    }

def load_mage_animations():
    base = "assets/classes/mage/"

    idle = sheet_grid(base + "MageIdle.png", 6, 24)
    walk = sheet_grid(base + "MageRun.png", 6, 24)
    hurt = sheet_grid(base + "MageHurt.png", 4, 16)
    atk  = sheet_grid(base + "MageAttack01.png", 5, 20)
    dea  = sheet_grid(base + "MageDeath.png", 7, 28)

    return {
        IDLE: {
            DOWN: idle[0:6],
            LEFT: idle[6:12],
            RIGHT: idle[12:18],
            UP: idle[18:24],
        },
        WALK: {
            DOWN: walk[0:6],
            LEFT: walk[6:12],
            RIGHT: walk[12:18],
            UP: walk[18:24],
        },
        HURT: {
            DOWN: hurt[0:4],
            LEFT: hurt[4:8],
            RIGHT: hurt[8:12],
            UP: hurt[12:16],
        },
        ATTACK: {
            DOWN: atk[0:5],
            LEFT: atk[5:10],
            RIGHT: atk[10:15],
            UP: atk[15:20],
        },
        DEATH: {
            DOWN: dea[0:7],
            LEFT: dea[7:14],
            RIGHT: dea[14:21],
            UP: dea[21:28],
        },
        WALK_ATTACK: {
            DOWN: atk[0:5],
            LEFT: atk[5:10],
            RIGHT: atk[10:15],
            UP: atk[15:20],
        },
    }

def load_player_animations(class_name: str):
    if class_name == "Warrior":
        return load_warrior_animations()
    elif class_name == "Mage":
        return load_mage_animations()
    else:
        raise ValueError(f"Unknown class: {class_name}")

class PlayerSprite(arcade.Sprite):
    def __init__(self, animations):
        super().__init__(scale=SCALE)

        self.attack_finished = False
        self.attack_dir = None

        self.hp = 1.0
        self.energy = 1.0

        self.animations = animations

        self.state = IDLE           # Animation state
        self.direction = DOWN       # Tρέχουσα κατεύθυνση
        self.last_direction = DOWN  # Tελευταία κατεύθυνση (για idle)

        self.cur_frame = 0          # Index frame animation
        self.time_acc = 0.0         # Χρόνος για την αλλαγή του frame
        self.frame_time = 0.12      # Πόσο γρήγορα αλλάζει frame

        # Αρχικό texture
        self.texture = self.animations[self.state][self.direction][0]

        # Text για το nickname
        self.nickname_text = arcade.Text(
            "",
            0, 0,
            arcade.color.WHITE,
            font_size=12,
            anchor_x="center",
            anchor_y="bottom"
        )

        # Text για το level
        self.level_text = arcade.Text(
            "",
            0, 0,
            arcade.color.RED,
            font_size=12,
            anchor_x="right",
            anchor_y="center"
        )

    # Αλλάζει animation state / direction
    # Κάνει reset animation μόνο όταν αλλάζει state
    def set_state(self, state, direction=None):
        if direction:
            self.direction = direction  # Ενημερώνουμε την τρέχουσα κατεύθυνση του sprite
            self.last_direction = direction

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

        # Τrue μόνο για 1 frame όταν τελειώσει attack
        self.attack_finished = False

        # Αν έχει περάσει αρκετός χρόνος ώστε να αλλάξει frame το animation
        if self.time_acc >= self.frame_time:
            self.time_acc = 0.0         # Μηδενίζουμε τη μεταβλητή για να ξεκινήσει νέα μέτρηση χρόνου

            if self.state == DEATH:

                # Στο death animation δεν γίνεται loop
                if self.cur_frame < len(frames) - 1:
                    self.cur_frame += 1

            elif self.state in (ATTACK, WALK_ATTACK):
                # ATTACK: δεν κάνει loop, και όταν τελειώσει γυρνάει σε IDLE
                if self.cur_frame < len(frames) - 1:
                    self.cur_frame += 1
                else:
                    self.attack_finished = True
                    return  # μην συνεχίσεις να γράφεις texture από τα παλιά frames
            
            else:
                self.cur_frame = (self.cur_frame + 1) % len(frames)     # Προχωράμε στο επόμενο frame του animation, το modulo εξασφαλίζει ότι όταν φτάσουμε στο τελευταίο frame, θα επιστρέψουμε στο πρώτο
            self.texture = frames[self.cur_frame]        # Ενημερώνουμε το texture του sprite με το νέο frame του animation

class EnemySprite(arcade.Sprite):
    def __init__(self, animations):
        super().__init__(scale=SCALE)

        self.dead = False

        # Οπτικά Στατιστικά (Client)
        self.hp = 1.0
        self.hp_max = 1.0
        self.nickname = "Orc"
        self.energy = 0.0

        self.nickname_text = arcade.Text("", 0, 0, arcade.color.WHITE, 12, anchor_x="center")
        self.level_text = arcade.Text("", 0, 0, arcade.color.WHITE, 12, anchor_x="right")

        self.animations = animations
        self.state = IDLE
        self.direction = DOWN
        self.last_direction = DOWN

        self.cur_frame = 0
        self.time_acc = 0.0
        self.frame_time = 0.12

        self.texture = self.animations[self.state][self.direction][0]

    def set_state(self, state, direction=None):
        if direction:
            self.direction = direction
            self.last_direction = direction

        if state != self.state:
            self.state = state
            self.cur_frame = 0
            self.time_acc = 0.0

        self.texture = self.animations[self.state][self.direction][self.cur_frame]

    def update_animation(self, delta_time: float):
        frames = self.animations[self.state][self.direction]
        self.time_acc += delta_time

        if self.time_acc >= self.frame_time:
            self.time_acc = 0.0

            if self.state == DEATH:
                # Αν δεν είμαστε στο τελευταίο frame
                if self.cur_frame < len(frames) - 1:
                    self.cur_frame += 1

                else:
                    # animation finished
                    self.dead = True
            else:
                self.cur_frame = (self.cur_frame + 1) % len(frames)

            self.texture = frames[self.cur_frame]