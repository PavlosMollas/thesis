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

    "dragon": {
        "idle": 7,
        "walk": 12,
        "hurt": 4,
        "attack": 10,
        "death": 3,

        "rise": 7,
        "flight": 12,
        "landing": 5,
        "attack_on_air": 13,

        "walk_attack": None,
        "directions": 2,
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

    "dragon": "dragon",
    "dragon2": "dragon",
}

# Τύποοι εχθρών και στατιστικά που έχουν
ENEMY_TYPES = {

    "orc": {
        "hp_max": 120,          # Μέγιστη ζωή του enemy. Όσο μεγαλύτερη είναι, τόσο περισσότερα χτυπήματα χρειάζεται για να πεθάνει
        "damage": 15,           # Βασική ζημιά που κάνει ο enemy στον παίκτη πριν αφαιρεθεί το resist του παίκτη
        "resist": 10,           # Άμυνα του enemy. Αφαιρείται από τη ζημιά που δέχεται από τον παίκτη
        "attack_speed": 1,      # Επιθέσεις ανά δευτερόλεπτο. Χρησιμοποιείται για τον υπολογισμό του attack cooldown
        "move_speed": 3.2,      # Ταχύτητα κίνησης του enemy σε pixels ανά server tick.

        "hitbox_w": 46,         # Πλάτος hitbox για collision με walls και παίκτη
        "hitbox_h": 72,         # Ύψος hitbox για collision με walls και παίκτη

        "aggro_radius": 240,    # Απόσταση στην οποία ο enemy εντοπίζει παίκτη και αρχίζει να τον κυνηγάει
        "lose_radius": 320,     # Απόσταση στην οποία ο enemy σταματά να κυνηγάει τον παίκτη αν αυτός απομακρυνθεί
        "attack_range": 64,     # Απόσταση στην οποία ο enemy μπορεί να ξεκινήσει melee επίθεση

        "windup": 0.45,         # Χρόνος καθυστέρησης από την αρχή του attack μέχρι να εφαρμοστεί η ζημιά
        "tier": 1,              # Βαθμίδα δυσκολίας του enemy. Χρησιμοποιείται και για XP reward αν δεν δοθεί ξεχωριστό xp_reward
        "attack_type": "melee"  # Τύπος επίθεσης. Το melee σημαίνει κοντινή επίθεση χωρίς projectile
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
        "hp_max": 65,           # Μέγιστη ζωή του enemy
        "damage": 12,           # Βασική ζημιά που κάνει το projectile ή η επίθεση του enemy
        "resist": 4,            # Άμυνα του enemy απέναντι στα χτυπήματα του παίκτη
        "attack_speed": 0.8,    # Επιθέσεις ανά δευτερόλεπτο. Μικρότερη τιμή σημαίνει πιο αργές επιθέσεις
        "move_speed": 3.0,      # Ταχύτητα κίνησης του enemy

        "hitbox_w": 40,         # Πλάτος hitbox για collision
        "hitbox_h": 58,         # Ύψος hitbox για collision

        "aggro_radius": 300,    # Απόσταση εντοπισμού παίκτη
        "lose_radius": 390,     # Απόσταση εγκατάλειψης στόχου
        "attack_range": 260,    # Απόσταση από την οποία μπορεί να επιτεθεί με ranged attack

        "windup": 0.55,             # Χρόνος μέχρι να γίνει το πραγματικό hit / spawn του projectile
        "tier": 1,                  # Βαθμίδα δυσκολίας enemy
        "attack_type": "ranged",    # Δηλώνει ότι ο enemy επιτίθεται από απόσταση

        "projectile_type": "magic_goblin_projectile", # Τύπος projectile που θα δημιουργηθεί όταν επιτεθεί
        "projectile_speed": 7.0,                      # Ταχύτητα κίνησης του projectile
        "projectile_range": 260,                      # Μέγιστη απόσταση που μπορεί να διανύσει το projectile
        "projectile_spawn_frame": 4,                  # Frame του attack animation στο οποίο εμφανίζεται το projectile
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

    "dragon": {
        "hp_max": 500,          # Μέγιστη ζωή του dragon. Είναι υψηλή επειδή λειτουργεί ως boss enemy
        "damage": 45,           # Βασική ζημιά που προκαλεί ο dragon στον παίκτη
        "resist": 25,           # Άμυνα του dragon. Μειώνει τη ζημιά που δέχεται από τον παίκτη
        "attack_speed": 0.7,    # Επιθέσεις ανά δευτερόλεπτο. Χαμηλότερη τιμή σημαίνει πιο αργές αλλά ισχυρές επιθέσεις
        "move_speed": 2.6,      # Ταχύτητα κίνησης του dragon κατά το patrol

        "hitbox_w": 130,        # Πλάτος hitbox για collision του dragon
        "hitbox_h": 60,         # Ύψος hitbox για collision του dragon

        "aggro_radius": 420,    # Απόσταση στην οποία ο dragon μπορεί να εντοπίσει παίκτη
        "lose_radius": 560,     # Απόσταση στην οποία θα μπορούσε να χάσει στόχο, αν χρησιμοποιηθεί chase λογική
        "attack_range": 110,    # Βασική απόσταση επίθεσης, κυρίως fallback τιμή

        "windup": 0.55,         # Χρόνος μέχρι να εφαρμοστεί η ζημιά της επίθεσης
        "tier": 5,              # Βαθμίδα δυσκολίας. Ο dragon είναι ισχυρό boss enemy
        "attack_type": "dragon",# Ειδικός τύπος επίθεσης, ώστε να ξεχωρίζει από melee/ranged enemies
        "special": "dragon",    # Δηλώνει ότι ο enemy χρησιμοποιεί ειδικό dragon AI αντί για το απλό chase AI

        "trigger_radius": 450,  # Απόσταση στην οποία ενεργοποιείται ο dragon όταν πλησιάσει παίκτης
        "patrol_distance": 500, # Απόσταση δεξιά και αριστερά από το spawn στην οποία κινείται ο dragon

        "ground_hits_before_rise": 3,   # Πόσα χτυπήματα πρέπει να δεχτεί στο έδαφος πριν περάσει σε rise/air phase
        "ground_phase_max_time": 10.0,  # Μέγιστη διάρκεια ground phase, αν χρησιμοποιηθεί χρονικός περιορισμός

        "ground_attack_range": 140,       # Οριζόντια απόσταση που φτάνει το ground attack
        "ground_attack_width": 90,        # Κάθετο πλάτος/lane μέσα στο οποίο μπορεί να χτυπηθεί ο παίκτης
        "ground_attack_impact_frame": 6,  # Frame του ground attack animation στο οποίο εφαρμόζεται η ζημιά

        "flight_before_air_attack_time": 1.2, # Χρόνος που πετάει πριν ξεκινήσει air attack
        "max_air_attacks": 2,                 # Πόσα air attacks εκτελεί πριν κάνει landing

        "air_attack_range": 300,        # Οριζόντια απόσταση που φτάνει το air attack
        "air_attack_width": 260,        # Κάθετο πλάτος της περιοχής ζημιάς του air attack
        "air_attack_y_offset": -100,    # Μετατόπιση στον Y άξονα ώστε το hitbox του air attack να ταιριάζει με το visual effect
        "air_attack_impact_frame": 8,   # Frame του air attack animation στο οποίο εφαρμόζεται η ζημιά

        "wall_probe_w": 130,            # Πλάτος του βοηθητικού probe hitbox που ελέγχει αν υπάρχει wall μπροστά
        "wall_probe_h": 60,             # Ύψος του βοηθητικού probe hitbox
        "wall_probe_offset": 100,       # Απόσταση του probe από το κέντρο του dragon προς την κατεύθυνση κίνησης
    },

    "dragon2": {
        "hp_max": 350,
        "damage": 32,
        "resist": 16,
        "attack_speed": 0.8,
        "move_speed": 2.8,

        "hitbox_w": 130,
        "hitbox_h": 60,

        "aggro_radius": 380,
        "lose_radius": 520,
        "attack_range": 95,

        "windup": 0.50,
        "tier": 4,
        "attack_type": "dragon",
        "special": "dragon",

        # Dragon boss behavior
        "trigger_radius": 400,
        "patrol_distance": 420,

        # Ground phase
        "ground_hits_before_rise": 3,
        "ground_phase_max_time": 9.0,

        # Ground attack area
        "ground_attack_range": 120,
        "ground_attack_width": 80,
        "ground_attack_impact_frame": 6,

        # Air phase
        "flight_before_air_attack_time": 1.2,
        "max_air_attacks": 2,

        # Air attack area
        "air_attack_range": 300,
        "air_attack_width": 120,
        "air_attack_impact_frame": 8,

        "wall_probe_w": 130,
        "wall_probe_h": 60,
        "wall_probe_offset": 100,
    },
}

# Εμπειρία (experience XP) για το επόμενο επίπεδο παίκτη (level up)
XP_REQUIREMENTS = {
    1: 100,
    2: 200,
    3: 350,
    4: 500,
    5: 700,
    6: 900,
    7: 1150,
    8: 1400,
    9: 1700,
    10: 0
}

# Είδη παικτών και στατιστικά
PLAYER_TYPES = {

    "Warrior": {
        "hp_max": 125,          # Μέγιστη ζωή του παίκτη όταν επιλέγει Warrior
        "damage": 25,           # Βασική ζημιά του Warrior πριν εφαρμοστεί multiplier από κάποιο attack
        "resist": 9,            # Άμυνα του Warrior. Μειώνει τη ζημιά που δέχεται από enemies
        "attack_speed": 0.9,    # Βασική ταχύτητα επίθεσης της κλάσης
        "move_speed": 3.2,      # Ταχύτητα κίνησης της κλάσης
        "attack_type": "melee", # Βασικός τύπος επίθεσης της κλάσης

        "level": 1,             # Αρχικό level του παίκτη
        "xp": 0,                # Αρχικό XP
        "xp_next": XP_REQUIREMENTS[1], # XP που χρειάζεται για το επόμενο level
        "max_level": 10,        # Μέγιστο level που μπορεί να φτάσει ο παίκτης

        "attacks": {
            "basic": {
                "attack_type": "melee",      # Τύπος επίθεσης. Το melee χτυπά κοντινούς εχθρούς
                "range": 70,                 # Απόσταση στην οποία μπορεί να χτυπήσει ο παίκτης
                "damage_multiplier": 1.0,    # Πολλαπλασιαστής πάνω στο βασικό damage
                "windup": 0.25,              # Χρόνος μέχρι να εφαρμοστεί το hit
                "cooldown": 0.45,            # Χρόνος αναμονής μέχρι να ξαναχρησιμοποιηθεί
                "animation": "attack",       # Animation που παίζει όταν χρησιμοποιείται η επίθεση
                "unlock_level": 1,           # Level στο οποίο ξεκλειδώνει η επίθεση
            },

            "skill1": {
                "attack_type": "melee",      # Πρώτη ειδική επίθεση κοντινής απόστασης
                "range": 120,                # Μεγαλύτερη εμβέλεια από το basic attack
                "damage_multiplier": 1.4,    # Αυξημένη ζημιά σε σχέση με το basic attack
                "windup": 0.35,              # Μεγαλύτερη καθυστέρηση επειδή είναι δυνατότερο skill
                "cooldown": 5.0,             # Μεγάλο cooldown γιατί είναι ειδική ικανότητα
                "animation": "attack",       # Animation που χρησιμοποιείται
                "unlock_level": 3,           # Ξεκλειδώνει στο level 3
            },

            "skill2": {
                "attack_type": "melee",      # Δεύτερη ειδική επίθεση του Warrior
                "range": 200,                # Ακόμα μεγαλύτερη εμβέλεια
                "damage_multiplier": 1.8,    # Μεγαλύτερη ζημιά από skill1
                "windup": 0.45,              # Μεγαλύτερος χρόνος προετοιμασίας
                "cooldown": 10.0,            # Μεγάλο cooldown λόγω ισχυρής επίθεσης
                "animation": "attack",       # Animation επίθεσης
                "unlock_level": 5,           # Ξεκλειδώνει στο level 5
            },
        },
    },

    "Mage": {
        "hp_max": 90,
        "damage": 30,
        "resist": 3,
        "attack_speed": 0.8,
        "move_speed": 3.2,
        "attack_type": "melee",

        "level": 1,
        "xp": 0,
        "xp_next": XP_REQUIREMENTS[1],
        "max_level": 10,

        "attacks": {
            "basic": {
                "attack_type": "melee",
                "range": 70,
                "damage_multiplier": 1.0,
                "windup": 0.30,
                "cooldown": 0.55,
                "animation": "attack",
                "unlock_level": 1,
                "lane_half_width": 40,
            },

            "skill1": {
                "attack_type": "melee",
                "range": 300,
                "damage_multiplier": 1.5,
                "windup": 0.45,
                "cooldown": 5.0,
                "animation": "attack",
                "unlock_level": 3,
                "lane_half_width": 50,
            },

            "skill2": {
                "attack_type": "ranged",    # Η επίθεση ελέγχει αν ο στόχος βρίσκεται στην ίδια κατεύθυνση και μπορεί να χτυπήσει από απόσταση
                "range": 360,
                "damage_multiplier": 2.0,
                "windup": 0.60,
                "cooldown": 10.0,
                "animation": "attack",
                "unlock_level": 5,
                "lane_half_width": 60,      # Μισό πλάτος της λωρίδας επίθεσης. Όσο μεγαλύτερο είναι, τόσο πιο εύκολα πετυχαίνει στόχο στην ίδια ευθεία
            },
        },
    },

    "Marksman": {
        "hp_max": 100,
        "damage": 28,
        "resist": 4,
        "attack_speed": 1.1,
        "move_speed": 3.4,
        "attack_type": "ranged",

        "level": 1,
        "xp": 0,
        "xp_next": XP_REQUIREMENTS[1],
        "max_level": 10,

        "attacks": {
            "basic": {
                "attack_type": "ranged",
                "range": 220,
                "damage_multiplier": 1.0,
                "windup": 0.20,
                "cooldown": 0.45,
                "animation": "attack",
                "unlock_level": 1,
                "lane_half_width": 32,
            },

            "skill1": {
                "attack_type": "ranged",
                "range": 180,
                "damage_multiplier": 1.35,
                "windup": 0.30,
                "cooldown": 5.0,
                "animation": "attack",
                "unlock_level": 3,
                "lane_half_width": 36,
            },

            "skill2": {
                "attack_type": "ranged",
                "range": 250,
                "damage_multiplier": 1.7,
                "windup": 0.40,
                "cooldown": 10.0,
                "animation": "attack",
                "unlock_level": 5,
                "lane_half_width": 42,
            },
        },
    },
}

# Όλα τα δυνατά animation states του dragon
DRAGON_STATES = {
    "idle",
    "walk",
    "attack",
    "hurt",
    "death",
    "rise",
    "flight",
    "landing",
    "attack_on_air",
}

# States στα οποία ο dragon βρίσκεται στο έδαφος
DRAGON_GROUND_STATES = {
    "idle",
    "walk",
    "attack",
    "hurt",
    "landing",
}

# States στα οποία ο dragon βρίσκεται στον αέρα
DRAGON_AIR_STATES = {
    "rise",
    "flight",
    "attack_on_air",
}

# States στα οποία ο dragon μπορεί να δεχτεί damage από τον παίκτη
DRAGON_DAMAGEABLE_STATES = {
    "idle",
    "walk",
    "attack",
    "hurt",
    "landing",
}

# States που δεν πρέπει να κάνουν loop animation
DRAGON_NON_LOOP_STATES = {
    "attack",
    "hurt",
    "death",
    "rise",
    "landing",
    "attack_on_air",
}

# Ελέγχει αν ένας enemy type είναι dragon με βάση το special flag
def is_dragon_type(enemy_type: str) -> bool:
    return ENEMY_TYPES.get(enemy_type, {}).get("special") == "dragon"

# Ελέγχει αν ο dragon μπορεί να δεχτεί damage στο συγκεκριμένο state
def is_dragon_damageable_state(state: str) -> bool:
    return state in DRAGON_DAMAGEABLE_STATES

# Ελέγχει αν το state ανήκει στα air states του dragon
def is_dragon_air_state(state: str) -> bool:
    return state in DRAGON_AIR_STATES

# Ελέγχει αν το state ανήκει στα ground states του dragon
def is_dragon_ground_state(state: str) -> bool:
    return state in DRAGON_GROUND_STATES

# Επιστρέφει την animation family ενός enemy
def get_enemy_animation_family(enemy_type: str) -> str:
    if enemy_type not in ENEMY_FAMILIES:
        raise ValueError(f"Unknown enemy animation type: {enemy_type}")
    return ENEMY_FAMILIES[enemy_type]

# Επιστρέφει πόσα frames έχει ένα συγκεκριμένο state ενός enemy
def get_enemy_anim_frame_count(enemy_type: str, state: str) -> int:
    family = get_enemy_animation_family(enemy_type)
    cfg = ENEMY_ANIMATION_CONFIGS[family]

    # Αν το state δεν υπάρχει στο config, χρησιμοποιούμε fallback το idle
    if state not in cfg:
        return cfg.get("idle", 1)

    value = cfg[state]

    # Αν ένα animation είναι None, χρησιμοποιούμε fallback το attack
    if value is None:
        return cfg.get("attack", 1)

    return value

# Υπολογίζει τη διάρκεια ενός animation state με βάση τα frames και το frame_time
def get_enemy_state_duration(enemy_type: str, state: str, frame_time: float = 0.12) -> float:
    frames = get_enemy_anim_frame_count(enemy_type, state)
    return frames * frame_time

# Δημιουργεί τις αρχικές runtime μεταβλητές που χρειάζεται ο dragon στο server
# Αυτές δεν είναι στατικά, αλλά τιμές που αλλάζουν κατά τη διάρκεια του παιχνιδιού
def get_dragon_runtime_defaults(defs: dict, spawn_x: float, spawn_y: float, now: float) -> dict:
    patrol_distance = defs.get("patrol_distance", 500)

    return {
        "dragon_active": False,     # Αν ο dragon έχει ενεργοποιηθεί από κοντινό παίκτη
        "dragon_mode": "ground",    # Τρέχον mode του dragon: ground ή air

        "patrol_left": spawn_x - patrol_distance,   # Αριστερό όριο patrol με βάση το spawn
        "patrol_right": spawn_x + patrol_distance,  # Δεξί όριο patrol με βάση το spawn
        "patrol_dir": "right",                      # Αρχική κατεύθυνση patrol

        "state_started_at": now,    # Χρόνος έναρξης του τρέχοντος state
        "state_duration": 0.0,      # Διάρκεια του τρέχοντος state
        "damage_applied": False,    # Αν έχει εφαρμοστεί ήδη damage στο τρέχον attack animation

        "ground_phase_started_at": now, # Χρόνος έναρξης ground phase
        "hits_taken_ground": 0,         # Πόσα hits έχει δεχτεί στο ground phase

        "air_phase_started_at": 0.0,        # Χρόνος έναρξης air phase
        "air_attacks_done": 0,              # Πόσα air attacks έγιναν στο τρέχον air phase
        "last_air_attack_finished_at": 0.0, # Πότε τελείωσε το τελευταίο air attack

        "next_ground_attack_time": 0.0, # Πότε επιτρέπεται το επόμενο ground attack
        "next_air_attack_time": 0.0,    # Πότε επιτρέπεται το επόμενο air attack

        "last_back_hit_time": 0.0,  # Πότε δέχτηκε τελευταίο hit από πίσω
        "last_back_hit_by": None,   # Ποιος παίκτης τον χτύπησε από πίσω
        "last_back_hit_dir": None,  # Προς ποια κατεύθυνση πρέπει να γυρίσει μετά από back hit
    }