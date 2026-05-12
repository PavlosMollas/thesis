import arcade
import time
from stats import (
    ENEMY_ANIMATION_CONFIGS,
    ENEMY_FAMILIES,
    ENEMY_TYPES,
    XP_REQUIREMENTS,
    PLAYER_TYPES,
)

# Διαστάσεις frame για τα sprite sheets παικτών και απλών εχθρών
FRAME_W = 64    # Πλάτος frame στο sprite sheet
FRAME_H = 64    # Ύψος frame στο sprite sheet

PROJECTILE_FRAME_W = 48 # Πλάτος frame στο projectile
PROJECTILE_FRAME_H = 48 # Ύψος frame στο projectile

# Διαστάσεις frame για dragon sprite sheets
DRAGON_FRAME_W = 256
DRAGON_FRAME_H = 256

# Κατευθύνσεις
DOWN  = "down"
LEFT  = "left"
RIGHT = "right"
UP    = "up"

# Καταστάσεις (state) παικτών/απλών εχθρών
IDLE = "idle"
WALK = "walk"
ATTACK = "attack"
HURT = "hurt"
DEATH = "death"
WALK_ATTACK = "walk_attack"

# Επιπλέον καταστάσεις για εχθρούς δράκους
RISE = "rise"
FLIGHT = "flight"
LANDING = "landing"
ATTACK_ON_AIR = "attack_on_air"

# Κλίμακα εμφάνισης των player sprites μέσα στο παιχνίδι
# Κάθε κλάση έχει διαφορετικό scale ώστε τα sprites να φαίνονται οπτικά ισορροπημένα
CLASS_SCALES = {
    "Warrior": 1.75,
    "Mage": 1.75,
    "Marksman": 2.1,
}

# Κλίμακα εμφάνισης των enemy sprites
# Οι dragons έχουν μικρότερο scale γιατί τα αρχικά frames τους είναι πολύ μεγαλύτερα
ENEMY_SCALES = {
    "orc": 1.9,
    "orc2": 1.9,
    "orc3": 1.9,

    "wolf": 1.9,
    "wolf2": 1.9,
    "wolf3": 1.9,

    "magic_goblin": 1.9,
    "magic_goblin2": 1.9,
    "magic_goblin3": 1.9,

    "dragon": 1.25,
    "dragon2": 1.25,
}

# Ρυθμίσεις για τα projectile animations
# Ορίζουν το αρχείο εικόνας, τα frames ανά κατεύθυνση, τις στήλες του sprite sheet και το scale
PROJECTILE_ANIMATION_CONFIGS = {
    "magic_goblin_projectile": {
        "path": "assets/projectiles/magic_goblin_projectile.png",
        "frames_per_dir": 9,
        "columns": 9,
        "scale": 2.0,
    }
}

# Φορτώνει frames από dragon sprite sheet
# Οι dragons έχουν διαφορετικό μέγεθος frame από τους υπόλοιπους χαρακτήρες
def dragon_sheet_grid(path, columns, count):
    sheet = arcade.SpriteSheet(path)
    return sheet.get_texture_grid(
        size=(DRAGON_FRAME_W, DRAGON_FRAME_H),
        columns=columns,
        count=count
    )

# Χωρίζει τα dragon frames σε κατευθύνσεις
# Τα dragon sprite sheets έχουν μόνο δύο κατευθύνσεις, δεξιά και αριστερά
def split_dragon_dirs(frames, frames_per_dir):
    right_frames = frames[0:frames_per_dir]
    left_frames = frames[frames_per_dir:frames_per_dir * 2]

    return {
        RIGHT: right_frames,
        LEFT: left_frames,

        # Fallback ώστε να μη γίνει error αν ζητηθεί up/down από τον κώδικα
        UP: right_frames,
        DOWN: right_frames,
    }

# Φορτώνει frames από projectile sprite sheet με βάση τις διαστάσεις frame
def projectile_sheet_grid(path, frame_w, frame_h, columns, count):
    sheet = arcade.SpriteSheet(path)
    return sheet.get_texture_grid(
        size=(frame_w, frame_h),
        columns=columns,
        count=count
    )

# Φορτώνει τα animations ενός projectile και τα χωρίζει σε 4 κατευθύνσεις
def load_projectile_animations(projectile_type):
    if projectile_type not in PROJECTILE_ANIMATION_CONFIGS:
        raise ValueError(f"Unknown projectile type: {projectile_type}")

    cfg = PROJECTILE_ANIMATION_CONFIGS[projectile_type]

    frames_per_dir = cfg["frames_per_dir"]
    total_frames = frames_per_dir * 4

    # Φορτώνουμε όλα τα frames του projectile από το sprite sheet
    frames = projectile_sheet_grid(
        cfg["path"],
        PROJECTILE_FRAME_W,
        PROJECTILE_FRAME_H,
        cfg["columns"],
        total_frames
    )

    return split_dirs(frames, frames_per_dir)   # Επιστρέφουμε dictionary με frames ανά κατεύθυνση

# Επιστρέφει τα στατιστικά ενός εχθρού από το stats.py
def get_enemy_type_defs(enemy_type: str):
    if enemy_type not in ENEMY_TYPES:
        raise ValueError(f"Unknown enemy type: {enemy_type}")
    return ENEMY_TYPES[enemy_type]

# Επιστρέφει τα στατιστικά ενός παίκτη από το stats.py
def get_player_type_defs(class_name: str):
    if class_name not in PLAYER_TYPES:
        raise ValueError(f"Unknown player class: {class_name}")
    return PLAYER_TYPES[class_name]

# Φορτώνει frames από κανονικό sprite sheet 64x64
def sheet_grid(path, columns, count):
    sheet = arcade.SpriteSheet(path)
    return sheet.get_texture_grid(
        size=(FRAME_W, FRAME_H),
        columns=columns,
        count=count
    )

# Φορτώνει frames για τον Marksman, ο οποίος έχει διαφορετικό frame size
def marksman_sheet_grid(path, columns, count):
    sheet = arcade.SpriteSheet(path)
    return sheet.get_texture_grid(
        size=(48, 64),
        columns=columns,
        count=count
    )

# Χωρίζει ένα sprite sheet 4 κατευθύνσεων σε DOWN, UP, LEFT, RIGHT
# Κάθε κατεύθυνση έχει frames_per_dir frames
def split_dirs(frames, frames_per_dir):
    return {
        DOWN: frames[0:frames_per_dir],
        UP: frames[frames_per_dir:frames_per_dir * 2],
        LEFT: frames[frames_per_dir * 2:frames_per_dir * 3],
        RIGHT: frames[frames_per_dir * 3:frames_per_dir * 4],
    }

# Φορτώνει όλα τα animation states του Warrior και τα χωρίζει ανά κατεύθυνση
def load_warrior_animations():
    base = "assets/classes/warrior/"

    idle = sheet_grid(base+"WarriorIdle.png", 5, 20)
    walk = sheet_grid(base+"WarriorWalk.png", 8, 32)
    atk  = sheet_grid(base+"WarriorAttack01.png", 6, 24)
    dea  = sheet_grid(base+"WarriorDeath.png", 5, 20)

    return {
        IDLE: {DOWN: idle[0:5], LEFT: idle[5:10], RIGHT: idle[10:15], UP: idle[15:20]},
        WALK: {DOWN: walk[0:8], LEFT: walk[8:16], RIGHT: walk[16:24], UP: walk[24:32]},
        ATTACK:{DOWN: atk[0:6], LEFT: atk[6:12], RIGHT: atk[12:18], UP: atk[18:24]},
        DEATH:{DOWN: dea[0:5], LEFT: dea[5:10], RIGHT: dea[10:15], UP: dea[15:20]},
    }

# Φορτώνει όλα τα animation states του Mage και τα χωρίζει ανά κατεύθυνση.
def load_mage_animations():
    base = "assets/classes/mage/"

    idle = sheet_grid(base + "MageIdle.png", 6, 24)
    walk = sheet_grid(base + "MageRun.png", 6, 24)
    atk  = sheet_grid(base + "MageAttack01.png", 5, 20)
    dea  = sheet_grid(base + "MageDeath.png", 7, 28)

    return {
        IDLE: {DOWN: idle[0:6], LEFT: idle[6:12], RIGHT: idle[12:18], UP: idle[18:24]},
        WALK: {DOWN: walk[0:6], LEFT: walk[6:12], RIGHT: walk[12:18], UP: walk[18:24]},
        ATTACK: {DOWN: atk[0:5], LEFT: atk[5:10], RIGHT: atk[10:15], UP: atk[15:20]},
        DEATH: {DOWN: dea[0:7], LEFT: dea[7:14], RIGHT: dea[14:21], UP: dea[21:28]},
    }

# Φορτώνει όλα τα animation states του Marksman και τα χωρίζει ανά κατεύθυνση
def load_marksman_animations():
    base = "assets/classes/marksman/"

    idle = marksman_sheet_grid(base + "Idle_Gun.png", 8, 32)
    walk = marksman_sheet_grid(base + "Walk_Gun.png", 8, 32)
    atk  = marksman_sheet_grid(base + "Shooting_attack.png", 8, 32)
    dea  = marksman_sheet_grid(base + "Death_GUN.png", 8, 32)

    return {
        IDLE: {DOWN: idle[0:8], LEFT: idle[8:16], RIGHT: idle[16:24], UP: idle[24:32]},
        WALK: {DOWN: walk[0:8], LEFT: walk[8:16], RIGHT: walk[16:24], UP: walk[24:32]},
        ATTACK: {DOWN: atk[0:8], LEFT: atk[8:16], RIGHT: atk[16:24], UP: atk[24:32]},
        DEATH: {DOWN: dea[0:8], LEFT: dea[8:16], RIGHT: dea[16:24], UP: dea[24:32]},
    }

# Φορτώνει animations για enemy type
# Αν ο enemy είναι dragon, χρησιμοποιεί ξεχωριστή μέθοδο λόγω διαφορετικών states και frame size
# Για τους υπόλοιπους εχθρούς χρησιμοποιεί το family config από το stats.py
def load_enemy_animations(enemy_type="orc"):
    if enemy_type not in ENEMY_FAMILIES:
        raise ValueError(f"Unknown enemy animation type: {enemy_type}")

    family = ENEMY_FAMILIES[enemy_type]

    if family == "dragon":
        return load_dragon_animations(enemy_type)

    cfg = ENEMY_ANIMATION_CONFIGS[family]

    base = f"assets/enemies/{enemy_type}/{enemy_type}_"

    # Φόρτωση βασικών animation states του enemy
    idle = sheet_grid(base + "idle.png", cfg["idle"], cfg["idle"] * 4)
    walk = sheet_grid(base + "walk.png", cfg["walk"], cfg["walk"] * 4)
    hurt = sheet_grid(base + "hurt.png", cfg["hurt"], cfg["hurt"] * 4)
    atk  = sheet_grid(base + "attack.png", cfg["attack"], cfg["attack"] * 4)
    dea  = sheet_grid(base + "death.png", cfg["death"], cfg["death"] * 4)

    # Αν υπάρχει ξεχωριστό walk_attack animation, το φορτώνουμε
    # Αν δεν υπάρχει, χρησιμοποιούμε το attack animation ως fallback
    if cfg["walk_attack"] is not None:
        watk = sheet_grid(
            base + "walk_attack.png",
            cfg["walk_attack"],
            cfg["walk_attack"] * 4
        )
        walk_attack_frames = cfg["walk_attack"]
    else:
        watk = atk
        walk_attack_frames = cfg["attack"]

    return {
        IDLE: split_dirs(idle, cfg["idle"]),
        WALK: split_dirs(walk, cfg["walk"]),
        HURT: split_dirs(hurt, cfg["hurt"]),
        ATTACK: split_dirs(atk, cfg["attack"]),
        DEATH: split_dirs(dea, cfg["death"]),
        WALK_ATTACK: split_dirs(watk, walk_attack_frames),
    }

# Επιλέγει ποια μέθοδο φόρτωσης animations θα κληθεί με βάση την κλάση του παίκτη
def load_player_animations(class_name: str):
    if class_name == "Warrior":
        return load_warrior_animations()
    elif class_name == "Mage":
        return load_mage_animations()
    elif class_name == "Marksman":
        return load_marksman_animations()
    else:
        raise ValueError(f"Unknown class: {class_name}")
    
# Φορτώνει όλα τα animation states των dragons
# Οι dragons έχουν δικά τους sprite sheets, 2 κατευθύνσεις και επιπλέον states όπως rise, flight, landing και attack_on_air
def load_dragon_animations(enemy_type="dragon"):
    family = ENEMY_FAMILIES[enemy_type]
    cfg = ENEMY_ANIMATION_CONFIGS[family]

    base = f"assets/enemies/{enemy_type}/"
    prefix = "Dragon2" if enemy_type == "dragon2" else "Dragon"

    idle = dragon_sheet_grid(base + f"{prefix}_Idle.png", cfg["idle"], cfg["idle"] * 2)
    walk = dragon_sheet_grid(base + f"{prefix}_Walk.png", cfg["walk"], cfg["walk"] * 2)
    hurt = dragon_sheet_grid(base + f"{prefix}_Hurt.png", cfg["hurt"], cfg["hurt"] * 2)
    atk = dragon_sheet_grid(base + f"{prefix}_Attack.png", cfg["attack"], cfg["attack"] * 2)
    dea = dragon_sheet_grid(base + f"{prefix}_Death.png", cfg["death"], cfg["death"] * 2)

    rise = dragon_sheet_grid(base + f"{prefix}_Rise.png", cfg["rise"], cfg["rise"] * 2)
    flight = dragon_sheet_grid(base + f"{prefix}_Flight.png", cfg["flight"], cfg["flight"] * 2)
    landing = dragon_sheet_grid(base + f"{prefix}_Landing.png", cfg["landing"], cfg["landing"] * 2)
    air_atk = dragon_sheet_grid(base + f"{prefix}_AttackOnAir.png", cfg["attack_on_air"], cfg["attack_on_air"] * 2)

     # Επιστρέφουμε dictionary με όλα τα dragon states χωρισμένα σε left/right directions
    return {
        IDLE: split_dragon_dirs(idle, cfg["idle"]),
        WALK: split_dragon_dirs(walk, cfg["walk"]),
        HURT: split_dragon_dirs(hurt, cfg["hurt"]),
        ATTACK: split_dragon_dirs(atk, cfg["attack"]),
        DEATH: split_dragon_dirs(dea, cfg["death"]),

        RISE: split_dragon_dirs(rise, cfg["rise"]),
        FLIGHT: split_dragon_dirs(flight, cfg["flight"]),
        LANDING: split_dragon_dirs(landing, cfg["landing"]),
        ATTACK_ON_AIR: split_dragon_dirs(air_atk, cfg["attack_on_air"]),

        WALK_ATTACK: split_dragon_dirs(atk, cfg["attack"]),
    }

# Sprite class για τον τοπικό και τους remote παίκτες
# Διαχειρίζεται animation states, direction, hurt feedback, death animation και UI texts
class PlayerSprite(arcade.Sprite):
    def __init__(self, animations, scale=2):
        super().__init__(scale=scale)

        self.attack_finished = False    # Γίνεται True όταν ολοκληρωθεί το attack animation
        self.attack_dir = None          # Κατεύθυνση που έχει κλειδώσει κατά τη διάρκεια του attack

        self.hp = 1.0           # Normalized HP για UI bar
        self.energy = 1.0       # Normalized energy για UI bar

        self.animations = animations

        # Ορατό state που χρησιμοποιείται για το τρέχον animation
        self.state = IDLE           # Animation state
        self.direction = DOWN       # Tρέχουσα κατεύθυνση
        self.last_direction = DOWN  # Tελευταία κατεύθυνση (για idle)

        # Base state που δείχνει τι πρέπει να παίζει όταν δεν υπάρχει hurt/death override
        self.base_state = IDLE
        self.base_direction = DOWN

        # Μεταβλητές για hurt flash effect
        self.hurt_active = False
        self.hurt_flash_timer = 0.0
        self.hurt_flash_duration = 0.35
        self.hurt_flash_interval = 0.035
        self.hurt_flash_min_alpha = 60

        self.normal_color = (255, 255, 255)
        self.hurt_color = (255, 80, 80)

        # Μεταβλητές για death animation και καθυστερημένο despawn
        self.death_started = False
        self.death_anim_finished = False
        self.death_hold_until = 0.0
        self.despawn = False

        self.last_hurt_seq = 0

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

    # Αλλάζει άμεσα animation state και προαιρετικά direction
    def force_state(self, state, direction=None, reset=False):
        # Αν δόθηκε κατεύθυνση, ενημερώνουμε και την τρέχουσα και την τελευταία κατεύθυνση
        if direction:
            self.direction = direction
            self.last_direction = direction

        # Αν ζητείται reset ή αλλάζει state, ξεκινάμε το animation από το frame 0
        if reset or state != self.state:
            self.state = state
            self.cur_frame = 0
            self.time_acc = 0.0
        else:
            self.state = state

        frames = self.animations[self.state][self.direction]
        if self.cur_frame >= len(frames):
            self.cur_frame = len(frames) - 1

        self.texture = frames[self.cur_frame]

    # Ορίζει το βασικό animation state του sprite
    # Το base state χρησιμοποιείται όταν δεν υπάρχει death/hurt/attack override
    def set_base_state(self, state, direction=None):
        if direction:
            self.base_direction = direction

        self.base_state = state

        # Το death animation έχει προτεραιότητα και δεν διακόπτεται
        if self.death_started:
            return

        # αλλιώς δείξε το base αμέσως, το hurt flash δεν μπλοκάρει πλέον το base animation
        self.force_state(self.base_state, self.base_direction, reset=(self.state != state))

    # Αντί να αλλάζει πάντα state απευθείας, καλεί την κατάλληλη μέθοδο για hurt/death
    def set_state(self, state, direction=None):
        if state == HURT:
            self.trigger_hurt(direction)
        elif state == DEATH:
            self.trigger_death(direction)
        else:
            self.set_base_state(state, direction)

    # Ενεργοποιεί visual hurt feedback
    # Για τον player δεν αλλάζει απαραίτητα το main animation, απλώς εμφανίζει flash effect
    def trigger_hurt(self, direction=None):
        if self.death_started:
            return

        # Hurt για local player = visual feedback, όχι main animation state
        self.hurt_active = True
        self.hurt_flash_timer = self.hurt_flash_duration

    # Ξεκινά το death animation και ακυρώνει hurt/attack states
    def trigger_death(self, direction=None):
        if self.death_started:
            return

        self.death_started = True
        self.hurt_active = False
        self.attack_finished = False
        self.attack_dir = None

        death_dir = direction or self.direction or self.base_direction or self.last_direction
        self.force_state(DEATH, death_dir, reset=True)

    # Ενημερώνει το animation του player με βάση τον χρόνο που πέρασε
    # Χειρίζεται hurt flash, attack completion, looping animations και death despawn
    def update_animation(self, delta_time):
        frames = self.animations[self.state][self.direction]
        self.time_acc += delta_time

        # Reset του attack_finished σε κάθε update
        # Θα γίνει True μόνο όταν το attack φτάσει στο τελευταίο frame
        self.attack_finished = False

        # Ενημέρωση hurt flash effect
        if self.hurt_flash_timer > 0:
            self.hurt_flash_timer -= delta_time

            if self.hurt_flash_timer <= 0:
                self.hurt_flash_timer = 0
                self.hurt_active = False

            phase = int(self.hurt_flash_timer / self.hurt_flash_interval)

            if phase % 2 == 0:
                self.color = self.hurt_color
            else:
                self.color = self.normal_color

            self.alpha = 255

        else:
            self.color = self.normal_color
            self.alpha = 255

        # Αν έχει τελειώσει το death animation, κρατάμε το τελευταίο frame για λίγο και μετά ζητάμε despawn.
        if self.death_started and self.death_anim_finished:
            if time.time() >= self.death_hold_until:
                self.despawn = True
            return

        if self.time_acc >= self.frame_time:
            self.time_acc = 0.0

            if self.state == DEATH:
                if self.cur_frame < len(frames) - 1:
                    self.cur_frame += 1
                    self.texture = frames[self.cur_frame]
                else:
                     # Το death animation δεν κάνει loop, φτάνει στο τελευταίο frame και μένει εκεί
                    if not self.death_anim_finished:
                        self.death_anim_finished = True
                        self.death_hold_until = time.time() + 1.5
                    self.texture = frames[self.cur_frame]
                return

            # Το attack animation δεν κάνει loop, όταν φτάσει στο τελευταίο frame ενημερώνουμε ότι ολοκληρώθηκε
            if self.state == ATTACK:
                if self.cur_frame < len(frames) - 1:
                    self.cur_frame += 1
                    self.texture = frames[self.cur_frame]
                else:
                    self.attack_finished = True
                return

            # Τα idle/walk animations κάνουν loop
            self.cur_frame = (self.cur_frame + 1) % len(frames)
            self.texture = frames[self.cur_frame]

# Sprite class για τους εχθρούς
# Διαχειρίζεται animation states, hurt/death animations και projectile spawn flag
class EnemySprite(arcade.Sprite):
    def __init__(self, enemy_type, animations, scale=1.9):
        super().__init__(scale=scale)

        self.projectile_spawned = False     # Χρησιμοποιείται ώστε κάθε attack animation ranged enemy να δημιουργεί μόνο ένα projectile

        self.enemy_type = enemy_type        # Τύπος enemy

        self.dead = False       # Flag για νεκρούς εχθρούς
        self.despawn = False    # Flag για να διαγράψουμε νεκρούς εχθρούς

        # UI στοιχεία εχθρού
        self.hp = 1.0
        self.hp_max = 1.0
        self.nickname = enemy_type

        self.nickname_text = arcade.Text("", 0, 0, arcade.color.WHITE, 12, anchor_x="center")

        self.animations = animations

        # Ορατό animation state
        self.state = IDLE
        self.direction = DOWN
        self.last_direction = DOWN

        # Base state στο οποίο επιστρέφει μετά από hurt animation
        self.base_state = IDLE
        self.base_direction = DOWN

        # Flags για hurt και death states
        self.hurt_active = False
        self.death_started = False
        self.death_anim_finished = False
        self.death_hold_until = 0.0

        self.last_hurt_seq = 0      # Τελευταίο hurt sequence που έχει εμφανιστεί, ώστε κάθε νέο hit να ενεργοποιεί hurt μόνο μία φορά
        self.last_attack_seq = 0    # Τελευταίο attack_seq που έχει δει ο client για να κάνει reset το attack animation σε κάθε νέο attack

        self.cur_frame = 0      # Τρέχον frame του animation
        self.time_acc = 0.0     # Χρόνος που έχει περάσει από την τελευταία αλλαγή frame
        self.frame_time = 0.12  # Διάρκεια κάθε frame animation σε δευτερόλεπτα

        self.texture = self.animations[self.state][self.direction][0]   # Ορίζουμε ως αρχικό texture το πρώτο frame του αρχικού state/direction

    # Αλλάζει άμεσα το animation state και την κατεύθυνση του enemy
    def force_state(self, state, direction=None, reset=False):
        # Αν δοθεί νέα κατεύθυνση, ενημερώνουμε την τρέχουσα και την τελευταία κατεύθυνση
        if direction:
            self.direction = direction
            self.last_direction = direction

        # Αν ζητηθεί reset ή αλλάξει state, ξεκινάμε το animation από την αρχή
        if reset or state != self.state:
            self.state = state
            self.cur_frame = 0
            self.time_acc = 0.0

            # Αν ξεκινά νέο attack, επιτρέπουμε ξανά τη δημιουργία projectile
            if state == ATTACK:
                self.projectile_spawned = False

        else:
            # Αν είναι το ίδιο state, δεν μηδενίζουμε το animation
            self.state = state

        frames = self.animations[self.state][self.direction]    # Παίρνουμε τα frames του τρέχοντος state και direction
        
        # Έλεγχος ώστε το cur_frame να μην ξεπεράσει τα διαθέσιμα frames
        if self.cur_frame >= len(frames):
            self.cur_frame = len(frames) - 1

        self.texture = frames[self.cur_frame]   # Ενημερώνουμε το texture με βάση το τρέχον frame

    # Ορίζει το βασικό state του enemy, στο οποίο επιστρέφει μετά από hurt ή άλλα προσωρινά states
    def set_base_state(self, state, direction=None):
        # Αν δοθεί direction, ενημερώνουμε τη βασική κατεύθυνση
        if direction:
            self.base_direction = direction

        self.base_state = state     # Αποθηκεύουμε το νέο βασικό state

        # Αν έχει ξεκινήσει death animation, δεν το διακόπτουμε
        if self.death_started:
            return

        # Αν παίζει hurt animation, δεν το διακόπτουμε
        if self.hurt_active:
            return

        # Αλλάζουμε στο βασικό state, κάνοντας reset μόνο αν άλλαξε state
        self.force_state(self.base_state, self.base_direction, reset=(self.state != state))

    # Αντί να αλλάζει πάντα state απευθείας, καλεί την κατάλληλη μέθοδο για hurt/death
    def set_state(self, state, direction=None):
        # Αν ζητηθεί hurt, καλούμε την ειδική μέθοδο hurt
        if state == HURT:
            self.trigger_hurt(direction)
        
        # Αν ζητηθεί death, καλούμε την ειδική μέθοδο death
        elif state == DEATH:
            self.trigger_death(direction)

        # Για όλα τα υπόλοιπα states, ενημερώνουμε το base state
        else:
            self.set_base_state(state, direction)

    # Ενεργοποιεί το hurt animation του enemy
    def trigger_hurt(self, direction=None):
        # Αν έχει ήδη ξεκινήσει death, δεν παίζει hurt
        if self.death_started:
            return

        # Αν είναι ήδη σε hurt animation, δεν το ξανακάνουμε reset
        if self.hurt_active:
            return

        self.hurt_active = True

        hurt_dir = direction or self.base_direction or self.last_direction  # Επιλέγουμε κατεύθυνση hurt: πρώτα αυτή που δόθηκε, αλλιώς base ή last direction
        self.force_state(HURT, hurt_dir, reset=True)                        # Ξεκινάμε το hurt animation από την αρχή

    # Ενεργοποιεί το death animation του enemy
    def trigger_death(self, direction=None):
        # Αν έχει ήδη ξεκινήσει death, δεν το ξαναξεκινάμε
        if self.death_started:
            return

        self.death_started = True
        self.hurt_active = False

        death_dir = direction or self.direction or self.base_direction or self.last_direction   # Επιλέγουμε την καλύτερη διαθέσιμη κατεύθυνση για το death animation
        self.force_state(DEATH, death_dir, reset=True)                                          # Ξεκινάμε το death animation από την αρχή

    # Ενημερώνει το animation του enemy με βάση τον χρόνο που πέρασε
    def update_animation(self, delta_time: float):
        frames = self.animations[self.state][self.direction]    # Παίρνουμε τα frames του τρέχοντος state/direction
        self.time_acc += delta_time                             # Προσθέτουμε τον χρόνο που πέρασε από το προηγούμενο frame

        # Αν έχει τελειώσει το death animation, κρατάμε το τελευταίο frame για λίγο πριν γίνει despawn
        if self.death_started and self.death_anim_finished:
            if time.time() >= self.death_hold_until:
                self.dead = True
                self.despawn = True
            return

        # Αλλάζουμε frame μόνο όταν περάσει ο απαιτούμενος χρόνος
        if self.time_acc >= self.frame_time:
            self.time_acc = 0.0

            # Το death animation δεν κάνει loop
            if self.state == DEATH:
                # Αν δεν είμαστε στο τελευταίο frame, προχωράμε στο επόμενο
                if self.cur_frame < len(frames) - 1:
                    self.cur_frame += 1
                    self.texture = frames[self.cur_frame]
                else:
                    # Όταν φτάσει στο τελευταίο frame, ξεκινάει χρόνος αναμονής πριν αφαιρεθεί
                    if not self.death_anim_finished:
                        self.death_anim_finished = True
                        self.death_hold_until = time.time() + 1.5
                    self.texture = frames[self.cur_frame]
                return

            # Το hurt animation παίζει μία φορά και μετά επιστρέφει στο base state
            if self.state == HURT:
                if self.cur_frame < len(frames) - 1:
                    self.cur_frame += 1
                    self.texture = frames[self.cur_frame]
                else:
                    # Όταν τελειώσει το hurt, επιστρέφουμε στο προηγούμενο βασικό state
                    self.hurt_active = False
                    self.force_state(self.base_state, self.base_direction, reset=True)
                return

            # Αυτά τα states δεν κάνουν loop, μένουν στο τελευταίο frame μέχρι να αλλάξει state από τον server
            if self.state in (ATTACK, RISE, LANDING, ATTACK_ON_AIR):
                if self.cur_frame < len(frames) - 1:
                    self.cur_frame += 1
                    self.texture = frames[self.cur_frame]
                    
                else:
                    self.texture = frames[self.cur_frame]   # Κρατάμε το τελευταίο frame

                    # Όταν ολοκληρωθεί attack animation, επιτρέπουμε μελλοντικό projectile στο επόμενο attack
                    if self.state == ATTACK:
                        self.projectile_spawned = False

                return

            # Τα υπόλοιπα states, όπως idle/walk/flight, κάνουν loop
            self.cur_frame = (self.cur_frame + 1) % len(frames)
            self.texture = frames[self.cur_frame]

# Sprite για projectile επίθεση ranged enemy
class ProjectileSprite(arcade.Sprite):
    def __init__(
        self,
        animations,
        direction,
        speed,
        damage,
        max_range,
        scale=2.0
    ):
        super().__init__(scale=scale)

        self.animations = animations    # Animation frames του projectile ανά κατεύθυνση
        self.direction = direction      # Κατεύθυνση προς την οποία κινείται το projectile

        self.speed = speed              # Ταχύτητα κίνησης projectile
        self.damage = damage            # Ζημιά projectile
        self.max_range = max_range      # Μέγιστη απόσταση που μπορεί να διανύσει

        self.distance_traveled = 0      # Απόσταση που έχει διανύσει μέχρι τώρα
        self.remove_me = False          # Γίνεται True όταν πρέπει να αφαιρεθεί

        self.cur_frame = 0              # Τρέχον animation frame
        self.time_acc = 0.0             # Χρόνος από την τελευταία αλλαγή frame
        self.frame_time = 0.06          # Ταχύτητα αλλαγής frames projectile

        self.texture = self.animations[self.direction][0]   # Αρχικό texture: πρώτο frame της αντίστοιχης κατεύθυνσης

        # Ορίζουμε την κίνηση του projectile στον X/Y άξονα με βάση την κατεύθυνση
        if direction == DOWN:
            self.change_x = 0
            self.change_y = -speed
        elif direction == UP:
            self.change_x = 0
            self.change_y = speed
        elif direction == LEFT:
            self.change_x = -speed
            self.change_y = 0
        elif direction == RIGHT:
            self.change_x = speed
            self.change_y = 0

    # Ενημερώνει τη θέση του projectile
    def update(self, delta_time=0):
        # Μετακίνηση projectile με βάση την κατεύθυνση και την ταχύτητα
        self.center_x += self.change_x
        self.center_y += self.change_y

        # Υπολογίζουμε πόση απόσταση έχει διανύσει συνολικά
        self.distance_traveled += abs(self.change_x) + abs(self.change_y)

        # Αν ξεπεράσει το μέγιστο range, σημαδεύεται για αφαίρεση
        if self.distance_traveled >= self.max_range:
            self.remove_me = True

    # Ενημερώνει το animation του projectile
    def update_animation(self, delta_time):
        frames = self.animations[self.direction]    # Παίρνουμε τα frames για την κατεύθυνση του projectile

        self.time_acc += delta_time                 # Προσθέτουμε τον χρόνο που πέρασε

        # Αν πέρασε αρκετός χρόνος, αλλάζουμε frame
        if self.time_acc >= self.frame_time:
            self.time_acc = 0.0

            # Το projectile animation κάνει loop
            self.cur_frame = (self.cur_frame + 1) % len(frames)
            self.texture = frames[self.cur_frame]