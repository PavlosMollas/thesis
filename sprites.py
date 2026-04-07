import arcade
import time

# Ρυθμίσεις Sprite sheet 
FRAME_W = 64    # Πλάτος frame στο sprite sheet
FRAME_H = 64    # Ύψος frame στο sprite sheet

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

# Κλίμακα sprite στο παιχνίδι
CLASS_SCALES = {
    "Warrior": 2.0,
    "Mage": 1.75,
}

ENEMY_TYPES = {

    "orc": {
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

def get_enemy_type_defs(enemy_type: str):
    if enemy_type not in ENEMY_TYPES:
        raise ValueError(f"Unknown enemy type: {enemy_type}")
    return ENEMY_TYPES[enemy_type]

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

def load_enemy_animations(enemy_type="orc"):
    base = f"assets/enemies/{enemy_type}_"
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
    def __init__(self, animations, scale=2):
        super().__init__(scale=scale)

        self.attack_finished = False
        self.attack_dir = None

        self.hp = 1.0
        self.energy = 1.0

        self.animations = animations

        # Ορατό state
        self.state = IDLE           # Animation state
        self.direction = DOWN       # Tρέχουσα κατεύθυνση
        self.last_direction = DOWN  # Tελευταία κατεύθυνση (για idle)

        # Βασικό state
        self.base_state = IDLE
        self.base_direction = DOWN

        # Flags για hurt και death states
        self.hurt_active = False
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

    # Αλλάζει animation state / direction
    # Κάνει reset animation μόνο όταν αλλάζει state
    def force_state(self, state, direction=None, reset=False):
        if direction:
            self.direction = direction
            self.last_direction = direction

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

    def set_base_state(self, state, direction=None):
        if direction:
            self.base_direction = direction

        self.base_state = state

        # death υπερισχύει όλων
        if self.death_started:
            return

        # όσο παίζει hurt, δεν το κόβουμε
        if self.hurt_active:
            return

        # αλλιώς δείξε το base αμέσως
        self.force_state(self.base_state, self.base_direction, reset=(self.state != state))

    def set_state(self, state, direction=None):
        # compatibility wrapper για το υπάρχον code
        # αργότερα θα αντικατασταθεί σταδιακά με set_base_state / trigger_hurt / trigger_death
        if state == HURT:
            self.trigger_hurt(direction)
        elif state == DEATH:
            self.trigger_death(direction)
        else:
            self.set_base_state(state, direction)

    def trigger_hurt(self, direction=None):
        if self.death_started:
            return

        # αν ήδη παίζει hurt, ignore
        if self.hurt_active:
            return

        self.hurt_active = True
        hurt_dir = direction or self.base_direction or self.last_direction
        self.force_state(HURT, hurt_dir, reset=True)

    def trigger_death(self, direction=None):
        if self.death_started:
            return

        self.death_started = True
        self.hurt_active = False
        self.attack_finished = False
        self.attack_dir = None

        death_dir = direction or self.direction or self.base_direction or self.last_direction
        self.force_state(DEATH, death_dir, reset=True)

    def update_animation(self, delta_time):
        frames = self.animations[self.state][self.direction]
        self.time_acc += delta_time

        self.attack_finished = False

        # αν έχει τελειώσει death animation, κράτα το τελευταίο frame μέχρι να περάσει το hold
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
                    # κράτα το τελευταίο frame
                    if not self.death_anim_finished:
                        self.death_anim_finished = True
                        self.death_hold_until = time.time() + 1.5
                    self.texture = frames[self.cur_frame]
                return

            if self.state == HURT:
                # one-shot hurt
                if self.cur_frame < len(frames) - 1:
                    self.cur_frame += 1
                    self.texture = frames[self.cur_frame]
                else:
                    # τέλος hurt -> επιστροφή στο τρέχον base
                    self.hurt_active = False
                    self.force_state(self.base_state, self.base_direction, reset=True)
                return

            if self.state in (ATTACK, WALK_ATTACK):
                if self.cur_frame < len(frames) - 1:
                    self.cur_frame += 1
                    self.texture = frames[self.cur_frame]
                else:
                    self.attack_finished = True
                return

            # loop για idle/walk
            self.cur_frame = (self.cur_frame + 1) % len(frames)
            self.texture = frames[self.cur_frame]

class EnemySprite(arcade.Sprite):
    def __init__(self, enemy_type, animations, scale=1.9):
        super().__init__(scale=scale)

        self.enemy_type = enemy_type

        self.dead = False
        self.despawn = False

        # Οπτικό UI Εχθρών
        self.hp = 1.0
        self.hp_max = 1.0
        self.nickname = enemy_type

        self.nickname_text = arcade.Text("", 0, 0, arcade.color.WHITE, 12, anchor_x="center")

        self.animations = animations

        # Ορατό State
        self.state = IDLE
        self.direction = DOWN
        self.last_direction = DOWN

        # Βασικό State
        self.base_state = IDLE
        self.base_direction = DOWN

        # Flags για hurt και death states
        self.hurt_active = False
        self.death_started = False
        self.death_anim_finished = False
        self.death_hold_until = 0.0

        self.last_hurt_seq = 0

        self.cur_frame = 0
        self.time_acc = 0.0
        self.frame_time = 0.12

        self.texture = self.animations[self.state][self.direction][0]

    def force_state(self, state, direction=None, reset=False):
        if direction:
            self.direction = direction
            self.last_direction = direction

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

    def set_base_state(self, state, direction=None):
        if direction:
            self.base_direction = direction

        self.base_state = state

        if self.death_started:
            return

        if self.hurt_active:
            return

        self.force_state(self.base_state, self.base_direction, reset=(self.state != state))

    def set_state(self, state, direction=None):
        # compatibility wrapper
        if state == HURT:
            self.trigger_hurt(direction)
        elif state == DEATH:
            self.trigger_death(direction)
        else:
            self.set_base_state(state, direction)

    def trigger_hurt(self, direction=None):
        if self.death_started:
            return

        if self.hurt_active:
            return

        self.hurt_active = True
        hurt_dir = direction or self.base_direction or self.last_direction
        self.force_state(HURT, hurt_dir, reset=True)

    def trigger_death(self, direction=None):
        if self.death_started:
            return

        self.death_started = True
        self.hurt_active = False

        death_dir = direction or self.direction or self.base_direction or self.last_direction
        self.force_state(DEATH, death_dir, reset=True)

    def update_animation(self, delta_time: float):
        frames = self.animations[self.state][self.direction]
        self.time_acc += delta_time

        # έχει τελειώσει το death animation, περίμενε το hold
        if self.death_started and self.death_anim_finished:
            if time.time() >= self.death_hold_until:
                self.dead = True
                self.despawn = True
            return

        if self.time_acc >= self.frame_time:
            self.time_acc = 0.0

            if self.state == DEATH:
                if self.cur_frame < len(frames) - 1:
                    self.cur_frame += 1
                    self.texture = frames[self.cur_frame]
                else:
                    if not self.death_anim_finished:
                        self.death_anim_finished = True
                        self.death_hold_until = time.time() + 1.5
                    self.texture = frames[self.cur_frame]
                return

            if self.state == HURT:
                if self.cur_frame < len(frames) - 1:
                    self.cur_frame += 1
                    self.texture = frames[self.cur_frame]
                else:
                    self.hurt_active = False
                    self.force_state(self.base_state, self.base_direction, reset=True)
                return

            if self.state in (ATTACK, WALK_ATTACK):
                self.cur_frame = (self.cur_frame + 1) % len(frames)
                self.texture = frames[self.cur_frame]
                return

            self.cur_frame = (self.cur_frame + 1) % len(frames)
            self.texture = frames[self.cur_frame]