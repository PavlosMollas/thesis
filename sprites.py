import arcade
import time

# Ρυθμίσεις Sprite sheet 
FRAME_W = 64    # Πλάτος frame στο sprite sheet
FRAME_H = 64    # Ύψος frame στο sprite sheet

PROJECTILE_FRAME_W = 48 # Πλάτος frame στο projectile
PROJECTILE_FRAME_H = 48 # Ύψος frame στο projectile

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

# Φόρτωμα projectiles 
PROJECTILE_ANIMATION_CONFIGS = {
    "magic_goblin_projectile": {
        "path": "assets/projectiles/magic_goblin_projectile.png",
        "frames_per_dir": 9,
        "columns": 9,
        "scale": 2.0,
    }
}

# Frames για τα state του κάθε εχθρού
ENEMY_ANIMATION_CONFIGS = {
    "orc": {
        "idle": 4,
        "walk": 6,
        "hurt": 6,
        "attack": 8,
        "death": 8,
        "walk_attack": 6,
    },

    "wolf": {
        "idle": 4,
        "walk": 6,
        "hurt": 4,
        "attack": 10,
        "death": 6,
        "walk_attack": None,
    },

    "magic_goblin": {
        "idle": 4,
        "walk": 6,
        "hurt": 4,
        "attack": 8,
        "death": 10,
        "walk_attack": None,
    },
}

# Κατηγορίες εχθρών
ENEMY_FAMILIES = {
    "orc": "orc",
    "orc2": "orc",
    "orc3": "orc",

    "wolf": "wolf",
    "wolf2": "wolf",
    "wolf3": "wolf",

    "magic_goblin": "magic_goblin",
    "magic_goblin2": "magic_goblin",
    "magic_goblin3": "magic_goblin",
}

# Τύποοι εχθρών και στατιστικά που έχουν
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
        "tier": 1,
        "attack_type": "melee"
    },

    "orc2": {
        "hp_max": 170,
        "damage": 23,
        "resist": 15,
        "attack_speed": 1,
        "move_speed": 3.3,
        "hitbox_w": 46,
        "hitbox_h": 72,
        "aggro_radius": 260,
        "lose_radius": 340,
        "attack_range": 64,
        "windup": 0.42,
        "tier": 2,
        "attack_type": "melee"
    },

    "orc3": {
        "hp_max": 240,
        "damage": 32,
        "resist": 22,
        "attack_speed": 1.1,
        "move_speed": 3.5,
        "hitbox_w": 46,
        "hitbox_h": 72,
        "aggro_radius": 280,
        "lose_radius": 360,
        "attack_range": 70,
        "windup": 0.38,
        "tier": 3,
        "attack_type": "melee"
    },

    "wolf": {
        "hp_max": 70,
        "damage": 10,
        "resist": 3,
        "attack_speed": 1.2,
        "move_speed": 4.2,
        "hitbox_w": 46,
        "hitbox_h": 72,
        "aggro_radius": 260,
        "lose_radius": 340,
        "attack_range": 50,
        "windup": 0.30,
        "tier": 1,
        "attack_type": "melee"
    },

    "wolf2": {
        "hp_max": 100,
        "damage": 15,
        "resist": 5,
        "attack_speed": 1.3,
        "move_speed": 4.5,
        "hitbox_w": 46,
        "hitbox_h": 72,
        "aggro_radius": 280,
        "lose_radius": 360,
        "attack_range": 54,
        "windup": 0.28,
        "tier": 2,
        "attack_type": "melee"
    },

    "wolf3": {
        "hp_max": 140,
        "damage": 21,
        "resist": 8,
        "attack_speed": 1.4,
        "move_speed": 4.8,
        "hitbox_w": 46,
        "hitbox_h": 72,
        "aggro_radius": 300,
        "lose_radius": 380,
        "attack_range": 58,
        "windup": 0.25,
        "tier": 3,
        "attack_type": "melee"
    },

    "magic_goblin": {
        "hp_max": 65,
        "damage": 12,
        "resist": 4,
        "attack_speed": 0.8,
        "move_speed": 3.0,
        "hitbox_w": 40,
        "hitbox_h": 58,
        "aggro_radius": 300,
        "lose_radius": 390,
        "attack_range": 260,
        "windup": 0.55,
        "tier": 1,
        "attack_type": "ranged",
        "projectile_type": "magic_goblin_projectile",
        "projectile_speed": 7.0,
        "projectile_range": 260,
        "projectile_spawn_frame": 4,
    },

    "magic_goblin2": {
        "hp_max": 90,
        "damage": 18,
        "resist": 6,
        "attack_speed": 0.85,
        "move_speed": 3.1,
        "hitbox_w": 40,
        "hitbox_h": 58,
        "aggro_radius": 330,
        "lose_radius": 420,
        "attack_range": 260,
        "windup": 0.50,
        "tier": 2,
        "attack_type": "ranged",
        "projectile_type": "magic_goblin_projectile",
        "projectile_speed": 7.5,
        "projectile_range": 300,
        "projectile_spawn_frame": 4,
    },

    "magic_goblin3": {
        "hp_max": 125,
        "damage": 25,
        "resist": 9,
        "attack_speed": 0.9,
        "move_speed": 3.2,
        "hitbox_w": 42,
        "hitbox_h": 60,
        "aggro_radius": 360,
        "lose_radius": 450,
        "attack_range": 260,
        "windup": 0.45,
        "tier": 3,
        "attack_type": "ranged",
        "projectile_type": "magic_goblin_projectile",
        "projectile_speed": 8.0,
        "projectile_range": 340,
        "projectile_spawn_frame": 4,
    },
}

def projectile_sheet_grid(path, frame_w, frame_h, columns, count):
    sheet = arcade.SpriteSheet(path)
    return sheet.get_texture_grid(
        size=(frame_w, frame_h),
        columns=columns,
        count=count
    )

def load_projectile_animations(projectile_type):
    if projectile_type not in PROJECTILE_ANIMATION_CONFIGS:
        raise ValueError(f"Unknown projectile type: {projectile_type}")

    cfg = PROJECTILE_ANIMATION_CONFIGS[projectile_type]

    frames_per_dir = cfg["frames_per_dir"]
    total_frames = frames_per_dir * 4

    frames = projectile_sheet_grid(
        cfg["path"],
        PROJECTILE_FRAME_W,
        PROJECTILE_FRAME_H,
        cfg["columns"],
        total_frames
    )

    return split_dirs(frames, frames_per_dir)

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

def split_dirs(frames, frames_per_dir):
    return {
        DOWN: frames[0:frames_per_dir],
        UP: frames[frames_per_dir:frames_per_dir * 2],
        LEFT: frames[frames_per_dir * 2:frames_per_dir * 3],
        RIGHT: frames[frames_per_dir * 3:frames_per_dir * 4],
    }

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

def load_mage_animations():
    base = "assets/classes/mage/"

    idle = sheet_grid(base + "MageIdle.png", 6, 24)
    walk = sheet_grid(base + "MageRun.png", 6, 24)
    hurt = sheet_grid(base + "MageHurt.png", 4, 16)
    atk  = sheet_grid(base + "MageAttack01.png", 5, 20)
    dea  = sheet_grid(base + "MageDeath.png", 7, 28)

    return {
        IDLE: {DOWN: idle[0:6], LEFT: idle[6:12], RIGHT: idle[12:18], UP: idle[18:24]},
        WALK: {DOWN: walk[0:6], LEFT: walk[6:12], RIGHT: walk[12:18], UP: walk[18:24]},
        HURT: {DOWN: hurt[0:4], LEFT: hurt[4:8], RIGHT: hurt[8:12], UP: hurt[12:16]},
        ATTACK: {DOWN: atk[0:5], LEFT: atk[5:10], RIGHT: atk[10:15], UP: atk[15:20]},
        DEATH: {DOWN: dea[0:7], LEFT: dea[7:14], RIGHT: dea[14:21], UP: dea[21:28]},
        WALK_ATTACK: {DOWN: atk[0:5], LEFT: atk[5:10], RIGHT: atk[10:15], UP: atk[15:20]},
    }

def load_enemy_animations(enemy_type="orc"):
    if enemy_type not in ENEMY_FAMILIES:
        raise ValueError(f"Unknown enemy animation type: {enemy_type}")

    family = ENEMY_FAMILIES[enemy_type]
    cfg = ENEMY_ANIMATION_CONFIGS[family]

    base = f"assets/enemies/{enemy_type}/{enemy_type}_"

    idle = sheet_grid(base + "idle.png", cfg["idle"], cfg["idle"] * 4)
    walk = sheet_grid(base + "walk.png", cfg["walk"], cfg["walk"] * 4)
    hurt = sheet_grid(base + "hurt.png", cfg["hurt"], cfg["hurt"] * 4)
    atk  = sheet_grid(base + "attack.png", cfg["attack"], cfg["attack"] * 4)
    dea  = sheet_grid(base + "death.png", cfg["death"], cfg["death"] * 4)

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
        self.hurt_flash_timer = 0.0
        self.hurt_flash_duration = 0.35
        self.hurt_flash_interval = 0.035
        self.hurt_flash_min_alpha = 60

        self.normal_color = (255, 255, 255)
        self.hurt_color = (255, 80, 80)

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

        # αλλιώς δείξε το base αμέσως, το hurt flash δεν μπλοκάρει πλέον το base animation
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

        # Hurt για local player = visual feedback, όχι main animation state
        self.hurt_active = True
        self.hurt_flash_timer = self.hurt_flash_duration

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

        # Update hurt flash timer
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

    def should_draw(self):
        if self.hurt_flash_timer <= 0:
            return True

        # Αναβόσβημα ανά hurt_flash_interval
        phase = int(self.hurt_flash_timer / self.hurt_flash_interval)
        return phase % 2 == 0

class EnemySprite(arcade.Sprite):
    def __init__(self, enemy_type, animations, scale=1.9):
        super().__init__(scale=scale)

        self.projectile_spawned = False

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

            if state in (ATTACK, WALK_ATTACK):
                self.projectile_spawned = False

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

                 # Αν το attack animation έκανε loop από την αρχή,
                # επιτρέπουμε νέο projectile στο επόμενο cast.
                if self.cur_frame == 0:
                    self.projectile_spawned = False

                self.texture = frames[self.cur_frame]
                return

            self.cur_frame = (self.cur_frame + 1) % len(frames)
            self.texture = frames[self.cur_frame]

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

        self.animations = animations
        self.direction = direction

        self.speed = speed
        self.damage = damage
        self.max_range = max_range

        self.distance_traveled = 0
        self.remove_me = False

        self.cur_frame = 0
        self.time_acc = 0.0
        self.frame_time = 0.06

        self.texture = self.animations[self.direction][0]

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

    def update(self, delta_time=0):
        self.center_x += self.change_x
        self.center_y += self.change_y

        self.distance_traveled += abs(self.change_x) + abs(self.change_y)

        if self.distance_traveled >= self.max_range:
            self.remove_me = True

    def update_animation(self, delta_time):
        frames = self.animations[self.direction]

        self.time_acc += delta_time

        if self.time_acc >= self.frame_time:
            self.time_acc = 0.0
            self.cur_frame = (self.cur_frame + 1) % len(frames)
            self.texture = frames[self.cur_frame]