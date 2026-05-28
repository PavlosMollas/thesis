import time
import arcade

from sprites import (
    get_player_type_defs,
    IDLE, WALK, ATTACK, DEATH, WALK_ATTACK,
    ATTACK02, ATTACK03,
)

### Το αρχείο αυτό περιέχει βοηθητικές μεθόδους για το UI και τις επιθέσεις του client ###

# Μέθοδος που τοποθετεί το UI των abilities στο κάτω μέρος της οθόνης
def update_ability_ui_positions(self):
    y = 38
    spacing = 170
    start_x = self.window.width / 2 - spacing

    for i, ability in enumerate(self.ability_ui):
        x = start_x + i * spacing

        ability["title_text"].x = x
        ability["title_text"].y = y + 8

        ability["status_text"].x = x
        ability["status_text"].y = y - 10

# Μέθοδος που ενημερώνει την εμφάνιση των abilities ανάλογα με level, cooldown και energy
def update_ability_ui_state(self):
    if not self.player_sprite:
        return

    # Παίρνουμε την τρέχουσα κατάσταση του παίκτη που επηρεάζει τη χρήση abilities
    now = time.time()
    player_level = int(getattr(self.player_sprite, "level", 1))
    player_energy = getattr(self.player_sprite, "energy", 1.0)

    # Φορτώνουμε τα attack definitions της επιλεγμένης κλάσης
    class_name = getattr(self.window, "class_name", "Warrior")

    try:
        class_defs = get_player_type_defs(class_name)
    except ValueError:
        class_defs = get_player_type_defs("Warrior")

    attacks = class_defs.get("attacks", {})

    # Για κάθε ability ελέγχουμε αν είναι κλειδωμένο, σε cooldown, χωρίς energy ή διαθέσιμο
    for ability in self.ability_ui:
        attack_id = ability["attack_id"]
        unlock_level = ability["unlock_level"]

        title_text = ability["title_text"]
        status_text = ability["status_text"]

        attack_defs = attacks.get(attack_id, {})
        required_level = attack_defs.get("unlock_level", unlock_level)
        energy_cost = attack_defs.get("energy_cost", 0.0)

        # Αν δεν έχει ξεκλειδωθεί ακόμα
        if player_level < required_level:
            title_text.color = arcade.color.GRAY
            status_text.color = arcade.color.GRAY
            status_text.text = f"Locked Lv.{required_level}"
            continue

        # Αν έχει ξεκλειδωθεί, ελέγχουμε πρώτα cooldown
        remaining = self.local_next_attack_times.get(attack_id, 0.0) - now

        if remaining > 0:
            title_text.color = arcade.color.LIGHT_GRAY
            status_text.color = arcade.color.ORANGE
            status_text.text = f"{remaining:.1f}s"
            continue

        # Αν έχει ξεκλειδωθεί αλλά δεν υπάρχει αρκετό energy
        if player_energy < energy_cost:
            title_text.color = arcade.color.LIGHT_GRAY
            status_text.color = arcade.color.RED
            status_text.text = "No Energy"
            continue

        # Αν είναι ξεκλειδωμένο, δεν έχει cooldown και έχει αρκετό energy
        title_text.color = arcade.color.WHITE
        status_text.color = arcade.color.LIGHT_GREEN
        status_text.text = "Ready"

# Επιστρέφει την ποσότητα ενός αντικειμένου από το inventory του παίκτη
def get_inventory_quantity(self, item_name):
    for item in self.inventory:
        if item.get("item_name") == item_name:
            return int(item.get("quantity", 0))
    return 0

# Εμφανίζει προσωρινό μήνυμα objective στο κέντρο της οθόνης
def show_objective_message(self, message, duration=2.5):
    self.objective_message = message
    self.objective_message_timer = duration

    self.objective_message_text.text = message
    self.objective_message_text.x = self.window.width / 2
    self.objective_message_text.y = self.window.height / 2 + 120

# Ενημερώνει τα objective messages και αποφασίζει πότε θα εμφανιστούν στον παίκτη
def update_objective_messages(self, delta_time):
    if not self.objective_text:
        return

    objective_changed = (
        self.objective_text != self.last_objective_text
        or self.objective_region != self.last_objective_region
    )

    # Ελέγχουμε αν άλλαξε objective ή περιοχή, ώστε να μη μείνουν παλιά μηνύματα
    if objective_changed:
        self.objective_shown_milestones.clear()
        self.objective_intro_timer = 0.0
        self.objective_intro_shown = False
        self.last_objective_remaining = None
        self.last_objective_complete = False
        self.objective_message = ""
        self.objective_message_timer = 0.0

    # Το αρχικό objective εμφανίζεται μία φορά μετά από μικρή καθυστέρηση
    if not self.objective_complete and not self.objective_intro_shown:
        self.objective_intro_timer += delta_time

        if self.objective_intro_timer >= self.objective_intro_delay:
            self.objective_intro_shown = True
            show_objective_message(self, self.objective_text, duration=2.5)

    # Όταν ολοκληρωθεί το objective, εμφανίζεται μήνυμα μετάβασης στο portal
    if self.objective_complete and not self.last_objective_complete:
        show_objective_message(self,
            "Objective complete! Go to the portal",
            duration=3.0
        )

    # Εμφανίζονται ενδιάμεσα μηνύματα όταν απομένουν λίγοι εχθροί
    if self.objective_text == "Defeat all enemies" and not self.objective_complete:
        if self.objective_remaining in (10, 5):
            milestone_key = f"enemies_{self.objective_remaining}"

            if milestone_key not in self.objective_shown_milestones:
                self.objective_shown_milestones.add(milestone_key)

                show_objective_message(self,
                    f"{self.objective_remaining} enemies left",
                    duration=2.5
                )

    # Εμφανίζεται μήνυμα όταν έχει μείνει ένας δράκος ζωντανός
    if self.objective_text == "Defeat all dragons" and not self.objective_complete:
        if self.objective_remaining == 1:
            milestone_key = "dragons_1"

            if milestone_key not in self.objective_shown_milestones:
                self.objective_shown_milestones.add(milestone_key)

                show_objective_message(self,
                    "1 dragon left",
                    duration=2.5
                )

    # Μειώνουμε τον χρόνο εμφάνισης του μηνύματος και το κρύβουμε όταν μηδενιστεί
    if self.objective_message_timer > 0:
        self.objective_message_timer -= delta_time

        if self.objective_message_timer <= 0:
            self.objective_message_timer = 0.0
            self.objective_message = ""

    self.last_objective_text = self.objective_text
    self.last_objective_remaining = self.objective_remaining
    self.last_objective_complete = self.objective_complete
    self.last_objective_region = self.objective_region

# Ελέγχει αν ο παίκτης μπορεί να χρησιμοποιήσει το συγκεκριμένο attack τοπικά
def can_use_attack_locally(self, attack_id):
    # Αν δεν υπάρχει player sprite, δεν μπορεί να γίνει επίθεση
    if not self.player_sprite:
        return False

    class_name = getattr(self.window, "class_name", "Warrior")

    try:
        class_defs = get_player_type_defs(class_name)
    except ValueError:
        class_defs = get_player_type_defs("Warrior")

    attacks = class_defs.get("attacks", {})

    # Αν το attack δεν υπάρχει, χρησιμοποιείται fallback στο basic attack
    if attack_id not in attacks:
        attack_id = "basic"

    attack_defs = attacks[attack_id]

    required_level = attack_defs.get("unlock_level", 1)
    player_level = int(getattr(self.player_sprite, "level", 1))

    # Έλεγχος αν ο παίκτης έχει το απαιτούμενο level για το attack
    if player_level < required_level:
        return False

    energy_cost = attack_defs.get("energy_cost", 0.0)
    player_energy = getattr(self.player_sprite, "energy", 1.0)

    # Έλεγχος αν υπάρχει αρκετή ενέργεια για την εκτέλεση του attack
    if player_energy < energy_cost:
        return False

    return True

# Μετατρέπει το πλήκτρο που πατήθηκε στο αντίστοιχο attack id και animation state
def get_attack_from_key(self, key):
    if key == arcade.key.SPACE:
        return "basic", ATTACK

    if key == arcade.key.Q:
        if getattr(self.window, "class_name", "Warrior") == "Marksman":
            return "skill1", None
        return "skill1", ATTACK03

    if key == arcade.key.E:
        return "skill2", ATTACK02

    return None

# Επιστρέφει το τοπικό cooldown του attack ανάλογα με την κλάση του παίκτη
def get_local_attack_cooldown(self, attack_id):
    class_name = getattr(self.window, "class_name", "Warrior")
    class_cooldowns = self.local_attack_cooldowns.get(class_name, self.local_attack_cooldowns["Warrior"])
    cooldown = class_cooldowns.get(attack_id, 0.45)

    # Αν ο Marksman έχει ενεργό rapid fire, μειώνεται προσωρινά το cooldown του basic attack
    if (
        class_name == "Marksman"
        and attack_id == "basic"
        and time.time() < getattr(self, "local_rapid_fire_until", 0.0)
    ):
        cooldown *= 0.5

    return cooldown

# Ελέγχει αν ο παίκτης βρίσκεται ήδη σε ενεργό attack animation
def is_active_attack(self):
    if not self.player_sprite:
        return False

    return (
        self.player_sprite.state in (ATTACK, ATTACK02, ATTACK03, WALK_ATTACK)
        and self.player_sprite.attack_dir is not None
    )

# Επαναφέρει τον παίκτη σε walk ή idle μετά το τέλος μιας επίθεσης
def return_to_move_or_idle(self, reset=True):
    move_dir = self.get_current_move_dir()

    # Αν υπάρχει ακόμα ενεργό input κίνησης, ο παίκτης συνεχίζει σε walk
    if move_dir is not None:
        self.player_sprite.last_direction = move_dir
        self.player_sprite.base_state = WALK
        self.player_sprite.base_direction = move_dir
        self.player_sprite.force_state(WALK, move_dir, reset=reset)
    
    # Αν δεν υπάρχει κίνηση, επιστρέφει σε idle κοιτώντας την τελευταία κατεύθυνση
    else:
        self.player_sprite.base_state = IDLE
        self.player_sprite.base_direction = self.player_sprite.last_direction
        self.player_sprite.force_state(IDLE, self.player_sprite.last_direction, reset=reset)

# Ξεκινά τοπικά μια επίθεση, ενημερώνει animation, cooldown και στέλνει την εντολή στον server
def start_local_attack(self, attack_id, attack_state):
    # Επίθεση επιτρέπεται μόνο όταν ο παίκτης συμμετέχει ενεργά στο παιχνίδι
    if self.my_session_phase != "playing":
        return

    # Αν το game δεν είναι σε κατάσταση playing, δεν ξεκινά επίθεση
    if self.game_status != "playing":
        return False

    now = time.time()

    # Έλεγχος τοπικού cooldown ώστε να μη σταλούν συνεχόμενα attacks
    if now < self.local_next_attack_times.get(attack_id, 0.0):
        return False

    cooldown = get_local_attack_cooldown(self, attack_id)

    # Αποθηκεύουμε το επόμενο χρονικό σημείο που επιτρέπεται το ίδιο attack
    self.local_next_attack_times[attack_id] = now + cooldown

    self.attack_buffered = False
    self.buffer_attack_state = None
    self.buffer_attack_id = None

    current_move_dir = self.get_current_move_dir()

    # Η κατεύθυνση επίθεσης είναι η τρέχουσα κίνηση ή η τελευταία κατεύθυνση του παίκτη
    attack_dir = current_move_dir or self.player_sprite.last_direction

    # Αν δεν υπάρχει animation state, σημαίνει ότι είναι skill χωρίς animation
    if attack_state is None:
        dir_str = self.dir_to_move_str(attack_dir)
        if dir_str is not None:
            self.send_attack_to_server(dir_str, attack_id)

        # Για τον Marksman, το skill1 ενεργοποιεί προσωρινά rapid fire
        if getattr(self.window, "class_name", "Warrior") == "Marksman" and attack_id == "skill1":
            self.local_rapid_fire_until = now + 5.0     

        return True

    self.player_sprite.attack_dir = attack_dir
    self.player_sprite.last_direction = self.player_sprite.attack_dir

    self.player_sprite.base_state = attack_state
    self.player_sprite.base_direction = self.player_sprite.attack_dir

    # Ενημερώνεται το τοπικό animation του παίκτη ώστε να ξεκινήσει η επίθεση
    self.player_sprite.force_state(attack_state, self.player_sprite.attack_dir, reset=True)

    dir_str = self.dir_to_move_str(self.player_sprite.attack_dir)
    if dir_str is not None:
        self.send_attack_to_server(dir_str, attack_id)  # Στέλνουμε την επίθεση στον server μέσω μεθόδου του MyGame

    return True

# Διαχειρίζεται το αίτημα επίθεσης όταν ο χρήστης πατήσει πλήκτρο ability
def request_attack(self, attack_id, attack_state):
    # Δεν επιτρέπονται attacks όταν ο παίκτης δεν είναι στο ενεργό παιχνίδι
    if self.my_session_phase != "playing":
        return

    if self.game_status != "playing":
        return

    if not self.player_sprite:
        return

    spr = self.player_sprite

    # Αν ο παίκτης είναι νεκρός ή σε death animation, αγνοούμε το attack input
    if spr.state == DEATH or getattr(spr, "death_started", False):
        return
    
    # Ελέγχουμε level και energy πριν επιτρέψουμε το attack
    if not can_use_attack_locally(self, attack_id):
        return

    active_attack = is_active_attack(self)

    # Αν υπάρχει ήδη ενεργό attack, εξετάζουμε αν το νέο attack μπορεί να γίνει buffer
    if active_attack:
        # Αν είναι skill χωρίς animation, όπως το Marksman Q, το στέλνουμε άμεσα στον server και δεν το βάζουμε σε buffer
        if attack_state is None:
            start_local_attack(self, attack_id, attack_state)
            return

        frames = spr.animations[spr.state][spr.direction]

        # Υπολογισμός προόδου του τρέχοντος attack animation
        progress = spr.cur_frame / (len(frames) - 1) if len(frames) > 1 else 1.0

        # Αν το attack animation βρίσκεται στο τελευταίο μέρος του, αποθηκεύουμε το επόμενο attack ως buffered
        if progress >= self.attack_buffer_threshold and not self.attack_buffered:
            self.attack_buffered = True
            self.buffer_attack_state = attack_state
            self.buffer_attack_id = attack_id

        return

    now = time.time()
    if now < self.local_next_attack_times.get(attack_id, 0.0):
        return

    # Αν ο παίκτης κινείται, αποθηκεύουμε την επίθεση ώστε να εκτελεστεί όταν σταματήσει ή ολοκληρωθεί η τρέχουσα κατάσταση
    if self.is_moving_input() and attack_state is not None:
        self.attack_buffered = True
        self.buffer_attack_state = attack_state
        self.buffer_attack_id = attack_id
        return

    start_local_attack(self, attack_id, attack_state)