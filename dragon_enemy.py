import time

from sprites import get_enemy_type_defs
from stats import get_enemy_state_duration

# Μέθοδος που βρίσκει τον κοντινότερο παίκτη που βρίσκεται στην ίδια περιοχή με τον εχθρό
def find_nearest_player_in_region(e, players, dist):
    nearest_pid = None      # Id του κοντινότερου παίκτη που βρίσκεται μέσα στην ίδια περιοχή
    nearest_player = None   # Δεδομένα κοντινότερου παίκτη
    nearest_d = 1e9         # Αρχική μεγάλη τιμή ώστε να βρεθεί σίγουρα μικρότερη από αυτήν

    for pid, p in players.items():
        if p.get("dead", False):    # Αγνοούμε παίκτες που είναι νεκροί
            continue

        if p.get("region") != e.get("region"):  # Αγνοούμε παίκτες που βρίσκονται σε άλλη περιοχή
            continue

        d = dist(e["x"], e["y"], p["x"], p["y"])    # Υπολογίζουμε την απόσταση εχθρού-παίκτη

        # Κρατάμε τον παίκτη με τη μικρότερη απόσταση
        if d < nearest_d:
            nearest_d = d
            nearest_pid = pid
            nearest_player = p

    return nearest_pid, nearest_player, nearest_d   # Επιστροφή κοντινότερου παίκτη με βάση: id παίκτη, στοιχεία παίκτη, απόσταση

# Μέθοδος που αλλάζει το state του dragon
def set_dragon_state(e, new_state, direction=None):
    now = time.time()   

    if direction is not None:   # Αν δόθηκε νέα κατεύθυνση, ενημερώνουμε το direction του dragon
        e["dir"] = direction

    if e.get("state") == new_state:    # Αν ο dragon είναι ήδη στο ίδιο state, δεν κάνουμε reset το animation
        return

    e["state"] = new_state          # Ορίζουμε το νέο state
    e["state_started_at"] = now     # Αποθηκεύουμε τη χρονική στιγμή που ξεκίνησε το state
    e["state_duration"] = get_enemy_state_duration(e["type"], new_state)    # Υπολογίζουμε τη διάρκεια του animation με βάση τα frames του state
    e["damage_applied"] = False     # Reset του flag ζημιάς όταν αλλάζει state

# Μέθοδος που ελέγχει αν έχει ολοκληρωθεί το τρέχον state του dragon
def dragon_state_finished(e):
    duration = e.get("state_duration", 0.0)

    if duration <= 0:   # Αν δεν υπάρχει διάρκεια, θεωρούμε ότι έχει ολοκληρωθεί
        return True

    # Αν έχει περάσει ο χρόνος διάρκειας από τότε που ξεκίνησε το state, τότε το state θεωρείται ολοκληρωμένο
    return time.time() >= e.get("state_started_at", 0.0) + duration 

# Μέθοδος που ελέγχει collision του δράκου με το περιβάλλον
def dragon_hits_wall(e, direction, collides_with_walls_aabb):
    defs = get_enemy_type_defs(e["type"])

    # Δημιουργία hitbox λίγο μπροστά από το δράκο ώστε να γυρίσει ο χαρακτήρας πριν φτάσει σε κάποιο τοίχο 
    probe_w = defs.get("wall_probe_w", e["hitbox_w"])
    probe_h = defs.get("wall_probe_h", e["hitbox_h"])

    probe_offset = defs.get("wall_probe_offset", 80)    # Απόσταση από το κέντρο του dragon

    # Θέτουμε την τιμή ανάλογα με την κατεύθυνση κίνησης
    if direction == "right":
        probe_x = e["x"] + probe_offset
    else:
        probe_x = e["x"] - probe_offset

    probe_y = e["y"]

    # Επιστρέφει True αν το που φτιάξαμε hitbox συγκρούεται με τοίχο
    return collides_with_walls_aabb(
        e["region"],
        probe_x,
        probe_y,
        probe_w,
        probe_h
    )

# Μέθοδος που κινεί τον δράκο (δεξιά-αριστερά) μέσα σε ένα όριο
def dragon_move(e, animation_state, move_enemy, collides_with_walls_aabb):
    patrol_dir = e.get("patrol_dir", "right")
    speed = e.get("move_speed", 2.5)

    # Κίνηση προς τα δεξιά
    if patrol_dir == "right":
        set_dragon_state(e, animation_state, "right")

        # Αν έφτασε στο δεξί όριο, αλλάζει κατεύθυνση
        if e["x"] >= e.get("patrol_right", e["spawn_x"] + 500):
            e["patrol_dir"] = "left"
            set_dragon_state(e, animation_state, "left")
            return

        # Αν υπάρχει wall μπροστά, αλλάζει κατεύθυνση
        if dragon_hits_wall(e, "right", collides_with_walls_aabb):
            e["patrol_dir"] = "left"
            set_dragon_state(e, animation_state, "left")
            return

        moved = move_enemy(e, speed, 0) # Προσπαθεί να κινηθεί δεξιά

        # Αν δεν κατάφερε να κινηθεί, αλλάζει κατεύθυνση
        if not moved:
            e["patrol_dir"] = "left"
            set_dragon_state(e, animation_state, "left")

    # Κίνηση προς τα αριστερά
    else:
        set_dragon_state(e, animation_state, "left")

        # Αν έφτασε στο αριστερό όριο, αλλάζει κατεύθυνση
        if e["x"] <= e.get("patrol_left", e["spawn_x"] - 500):
            e["patrol_dir"] = "right"
            set_dragon_state(e, animation_state, "right")
            return

        # Αν υπάρχει wall μπροστά, αλλάζει κατεύθυνση
        if dragon_hits_wall(e, "left", collides_with_walls_aabb):
            e["patrol_dir"] = "right"
            set_dragon_state(e, animation_state, "right")
            return

        moved = move_enemy(e, -speed, 0)    # Προσπαθεί να κινηθεί αριστερά

        # Αν δεν κατάφερε να κινηθεί, αλλάζει κατεύθυνση
        if not moved:
            e["patrol_dir"] = "right"
            set_dragon_state(e, animation_state, "right")

# Μέθοδος που εφαρμόζει τη ζημιά του δράκου προς τον παίκτη
def dragon_damage_player(p, e, damage_amount=None):
    player_resist = p.get("resist", 0)

    # Αν δεν δοθεί συγκεκριμένο damage, χρησιμοποιείται το damage του enemy
    if damage_amount is None:
        damage_amount = e.get("damage", 1)

    dmg = max(0, damage_amount - player_resist) # Τελικό damage μετά το resist του παίκτη

    # Παίρνουμε το μέγιστο και το τρέχον HP του παίκτη
    player_hp_max = p.get("hp_max", 100)        
    hp_cur = p.get("hp_cur", p.get("hp", 1.0) * player_hp_max)

    hp_cur -= dmg   # Αφαιρούμε το damage

    # Δεν αφήνουμε το HP να πέσει κάτω από 0
    if hp_cur < 0:
        hp_cur = 0

    # Ενημερώνουμε και το πραγματικό HP και το normalized HP για το UI
    p["hp_cur"] = hp_cur
    p["hp_max"] = player_hp_max
    p["hp"] = hp_cur / player_hp_max

    # Αν ο παίκτης πέθανε, αλλάζουμε state σε death
    if hp_cur <= 0:
        p["dead"] = True
        p["state"] = "death"
    else:
        p["hurt_seq"] = p.get("hurt_seq", 0) + 1    # Αλλιώς αυξάνουμε το hurt_seq ώστε ο client να δείξει hurt animation

# Μέθοδος που βρίσκει αν υπάρχει παίκτης μπροστά από τον dragon, ώστε να εκτελέσει επίθεση στο έδαφος
def ground_attack_target(e, players):
    defs = get_enemy_type_defs(e["type"])

    attack_range = defs.get("ground_attack_range", e.get("attack_range", 110))  # Απόσταση που φτάνει η επίθεση του dragon στο έδαφος
    attack_half_width = defs.get("ground_attack_width", 90) / 2     # Πλάτος που μπορεί να βρίσκεται ο παίκτης για να χτυπηθεί
    direction = e.get("dir", "right")   # Κατεύθυνση που κοιτάει ο dragon

    best_pid = None     # Id του κοντινότερου παίκτη που βρίσκεται μέσα στην περιοχή επίθεσης
    best_player = None  # Δεδομένα του κοντινότερου παίκτη
    best_d = 1e9        # Αρχική μεγάλη απόσταση για σύγκριση με τους παίκτες που θα ελεγχθούν

    for pid, p in players.items():
        if p.get("dead", False):    # Αγνοούμε νεκρούς παίκτες
            continue

        if p.get("region") != e.get("region"):  # Αγνοούμε παίκτες που βρίσκονται σε άλλη περιοχή
            continue

        # Υπολογίζουμε τη θέση του παίκτη σε σχέση με τον dragon
        dx = p["x"] - e["x"]
        
        attack_y = e["y"] + defs.get("ground_attack_y_offset", 0)
        dy = p["y"] - attack_y

        if abs(dy) > attack_half_width:     # Ο παίκτης πρέπει να είναι περίπου στο ίδιο ύψος με τον dragon
            continue

        if direction == "right":            # Αν ο dragon κοιτάει δεξιά, μπορεί να χτυπήσει μόνο παίκτες δεξιά του
            if dx <= 0 or dx > attack_range:
                continue
            d = dx

        elif direction == "left":           # Αν ο dragon κοιτάει αριστερά, μπορεί να χτυπήσει μόνο παίκτες αριστερά του
            if dx >= 0 or abs(dx) > attack_range:
                continue
            d = abs(dx)

        else:
            continue

        # Κρατάμε τον πιο κοντινό παίκτη μέσα στην περιοχή επίθεσης
        if d < best_d:
            best_d = d
            best_pid = pid
            best_player = p

    return best_pid, best_player, direction # Επιστρέφουμε τον παίκτη που μπορεί να χτυπηθεί και την κατεύθυνση του attack

# Μέθοδος που ελέγχει αν ο παίκτης βρίσκεται πίσω από τον dragon
def player_is_behind_dragon(p, e):
    dx = p["x"] - e["x"]
    dragon_dir = e.get("dir", "right")

    if dragon_dir == "right":   # Αν ο dragon κοιτάει δεξιά, τότε πίσω του είναι η αριστερή πλευρά
        return dx < 0

    if dragon_dir == "left":    # Αν ο dragon κοιτάει αριστερά, τότε πίσω του είναι η δεξιά πλευρά
        return dx > 0

    return False

# Μέθοδος που επιστρέφει την κατεύθυνση του dragon προς τον παίκτη
# Χρησιμοποιείται όταν ο dragon χτυπηθεί από πίσω, ώστε να γυρίσει προς τον παίκτη και να κάνει attack
def direction_from_dragon_to_player(e, p):
    return "right" if p["x"] >= e["x"] else "left"

# Μέθοδος που εφαρμόζει τη ζημιά από το ground attack του dragon
def apply_dragon_ground_attack(e, players):
    if e.get("damage_applied", False):  # Αν έχει ήδη εφαρμοστεί ζημιά για αυτό το attack animation, δεν κάνουμε τίποτα
        return

    defs = get_enemy_type_defs(e["type"])
    now = time.time()

    impact_frame = defs.get("ground_attack_impact_frame", 6)            # Frame του animation στο οποίο γίνεται το πραγματικό hit
    impact_time = e.get("state_started_at", now) + impact_frame * 0.12  # Υπολογίζουμε τη χρονική στιγμή που πρέπει να εφαρμοστεί η ζημιά

    if now < impact_time:   # Αν δεν έχει φτάσει ακόμα η στιγμή του hit, περιμένουμε
        return

    attack_range = defs.get("ground_attack_range", e.get("attack_range", 110))  # Απόσταση που φτάνει η επίθεση μπροστά από τον dragon
    attack_half_width = defs.get("ground_attack_width", 90) / 2                 # Πλάτος που μπορεί να βρίσκεται ο παίκτης για να χτυπηθεί
    direction = e.get("dir", "right")   # Κατεύθυνση στην οποία κοιτάει ο dragon

    for p in players.values():
        if p.get("dead", False):    # Αγνοούμε νεκρούς παίκτες
            continue

        if p.get("region") != e.get("region"):  # Αγνοούμε παίκτες που βρίσκονται σε άλλη περιοχή
            continue

        # Υπολογίζουμε τη θέση του παίκτη σε σχέση με τον dragon
        dx = p["x"] - e["x"]
        dy = p["y"] - e["y"]

        # Αν ο παίκτης δεν είναι στο ίδιο ύψος, δεν μπορεί να χτυπηθεί από το ground attack
        if abs(dy) > attack_half_width: 
            continue

        can_hit = False

        if direction == "right":    # Αν ο dragon κοιτάει δεξιά, χτυπάει μόνο παίκτες δεξιά του
            can_hit = dx > 0 and dx <= attack_range
        elif direction == "left":   # Αν ο dragon κοιτάει αριστερά, χτυπάει μόνο παίκτες αριστερά του
            can_hit = dx < 0 and abs(dx) <= attack_range

        # Αν ο παίκτης βρίσκεται μέσα στην περιοχή επίθεσης, εφαρμόζουμε τη ζημιά
        if can_hit:
            dragon_damage_player(p, e)

    e["damage_applied"] = True  # Το flag ενημερώνεται ότι η ζημιά εφαρμόστηκε, ώστε να μη χτυπήσει ξανά στο ίδιο attack animation

# Μέθοδος που εφαρμόζει τη ζημιά από το air attack του dragon
def apply_dragon_air_attack(e, players):
    if e.get("damage_applied", False):  # Αν έχει ήδη εφαρμοστεί ζημιά για αυτό το air attack animation, δεν κάνουμε τίποτα
        return

    defs = get_enemy_type_defs(e["type"])
    now = time.time()

    impact_frame = defs.get("air_attack_impact_frame", 8)   # Frame του animation στο οποίο γίνεται το πραγματικό hit
    impact_time = e.get("state_started_at", now) + impact_frame * 0.12  # Υπολογίζουμε τη χρονική στιγμή που πρέπει να εφαρμοστεί η ζημιά

    if now < impact_time:   # Αν δεν έχει φτάσει ακόμα η στιγμή του hit, περιμένουμε
        return

    attack_range = defs.get("air_attack_range", 300)            # Απόσταση που φτάνει η επίθεση μπροστά από τον dragon
    attack_half_width = defs.get("air_attack_width", 120) / 2   # Πλάτος που μπορεί να βρίσκεται ο παίκτης για να χτυπηθεί
    direction = e.get("dir", "right")       # Κατεύθυνση στην οποία κοιτάει ο dragon

    # Το οπτικό air attack φαίνεται πιο κάτω από το κέντρο του dragon και για αυτό βάζουμε offset για τον Υ άξονα
    attack_y = e["y"] + defs.get("air_attack_y_offset", 0)

    for p in players.values():
        if p.get("dead", False):    # Αγνοούμε νεκρούς παίκτες
            continue

        if p.get("region") != e.get("region"):  # Αγνοούμε παίκτες που βρίσκονται σε άλλη περιοχή
            continue

        dx = p["x"] - e["x"]    # Υπολογίζουμε τη θέση του παίκτη σε σχέση με τον dragon στον X άξονα
        dy = p["y"] - attack_y  # Υπολογίζουμε τη θέση του παίκτη σε σχέση με το κέντρο της air attack περιοχής

        # Αν ο παίκτης δεν είναι στο ύψος της επίθεσης, δεν μπορεί να χτυπηθεί από το air attack
        if abs(dy) > attack_half_width:
            continue

        can_hit = False

        if direction == "right":    # Αν ο dragon κοιτάει δεξιά, χτυπάει μόνο παίκτες δεξιά του
            can_hit = dx > 0 and dx <= attack_range
        elif direction == "left":   # Αν ο dragon κοιτάει αριστερά, χτυπάει μόνο παίκτες αριστερά του
            can_hit = dx < 0 and abs(dx) <= attack_range

        # Αν ο παίκτης βρίσκεται μέσα στην περιοχή επίθεσης, εφαρμόζουμε τη ζημιά
        if can_hit:
            dragon_damage_player(p, e)

    e["damage_applied"] = True  # Το flag ενημερώνεται ότι η ζημιά εφαρμόστηκε, ώστε να μη χτυπήσει ξανά στο ίδιο attack animation

# Μέθοδος που ενημερώνει τη συνολική συμπεριφορά του dragon
def update_dragon(e, players, dist, move_enemy, collides_with_walls_aabb):
    if e.get("dead"):   # Αν ο dragon είναι νεκρός, δεν εκτελεί καμία συμπεριφορά
        return

    now = time.time()
    defs = get_enemy_type_defs(e["type"])

    # Βρίσκουμε τον κοντινότερο παίκτη στην ίδια περιοχή με τον dragon
    nearest_pid, nearest_player, nearest_d = find_nearest_player_in_region(e, players, dist)

    trigger_radius = defs.get("trigger_radius", 450)    # Απόσταση στην οποία ενεργοποιείται ο dragon όταν πλησιάσει παίκτης

    # Αν ο dragon δεν έχει ενεργοποιηθεί ακόμα, μένει σε idle state
    if not e.get("dragon_active", False):
        e["state"] = "idle"

        # Αν υπάρχει παίκτης μέσα στο trigger radius, ο dragon ενεργοποιείται
        if nearest_player is not None and nearest_d <= trigger_radius:
            e["dragon_active"] = True
            e["dragon_mode"] = "ground"
            e["ground_phase_started_at"] = now
            e["hits_taken_ground"] = 0

            # Υπολογίζουμε σε ποια πλευρά έχει περισσότερο χώρο 
            right_space = e.get("patrol_right", e["x"]) - e["x"]
            left_space = e["x"] - e.get("patrol_left", e["x"])

            # Ξεκινάει προς τη μεριά που έχει περισσότερο διαθέσιμο χώρο
            if right_space >= left_space:
                e["patrol_dir"] = "right"
                set_dragon_state(e, "walk", "right")
            else:
                e["patrol_dir"] = "left"
                set_dragon_state(e, "walk", "left")

        return

    # Αν ο dragon βρίσκεται σε rise state, περιμένουμε να ολοκληρωθεί το rise animation
    if e.get("state") == "rise":
        if dragon_state_finished(e):
            # Μόλις τελειώσει το rise, περνάει σε air mode
            e["dragon_mode"] = "air"
            e["air_phase_started_at"] = now
            e["air_attacks_done"] = 0
            e["last_air_attack_finished_at"] = now

            set_dragon_state(e, "flight", e.get("dir", "right"))    # Μετά το rise ξεκινάει flight

        return

    # Αν ο dragon βρίσκεται σε flight state
    if e.get("state") == "flight":
        e["dragon_mode"] = "air"

        flight_delay = defs.get("flight_before_air_attack_time", 1.2)   # Χρόνος που πρέπει να περάσει σε flight πριν κάνει air attack
        air_attacks_done = e.get("air_attacks_done", 0)                 # Πόσα air attacks έχει κάνει ήδη σε αυτό το air phase
        max_air_attacks = defs.get("max_air_attacks", 2)                # Μέγιστος αριθμός air attacks πριν προσγειωθεί

        # Αν δεν έχει φτάσει το όριο των air attacks και έχει περάσει ο απαιτούμενος χρόνος, ξεκινάει attack_on_air
        if (
            air_attacks_done < max_air_attacks
            and now - e.get("last_air_attack_finished_at", now) >= flight_delay
        ):
            set_dragon_state(e, "attack_on_air", e.get("patrol_dir", e.get("dir", "right")))
            return

        # Αν δεν κάνει air attack, συνεχίζει να πετάει δεξιά-αριστερά στα όρια
        dragon_move(e, "flight", move_enemy, collides_with_walls_aabb)
        return

    # Αν ο dragon βρίσκεται σε attack_on_air state
    if e.get("state") == "attack_on_air":
        e["dragon_mode"] = "air"

        apply_dragon_air_attack(e, players) # Ελέγχουμε αν έφτασε το impact frame ώστε να εφαρμοστεί η ζημιά

        # Αν ολοκληρώθηκε το attack_on_air animation
        if dragon_state_finished(e):
            # Αυξάνουμε τον αριθμό των air attacks που έγιναν
            e["air_attacks_done"] = e.get("air_attacks_done", 0) + 1
            e["last_air_attack_finished_at"] = now

            max_air_attacks = defs.get("max_air_attacks", 2)

            # Αν έγιναν όλα τα air attacks, ξεκινάει landing
            if e["air_attacks_done"] >= max_air_attacks:
                set_dragon_state(e, "landing", e.get("dir", "right"))
            else:
                # Αν δεν έγιναν όλα τα air attacks, γυρίζει πλευρά ώστε το επόμενο air attack να γίνει από την άλλη κατεύθυνση
                if e.get("dir") == "right":
                    e["patrol_dir"] = "left"
                    set_dragon_state(e, "flight", "left")
                else:
                    e["patrol_dir"] = "right"
                    set_dragon_state(e, "flight", "right")

        return

    # Αν ο dragon βρίσκεται σε landing state
    if e.get("state") == "landing":
        e["dragon_mode"] = "air"

        # Περιμένουμε να ολοκληρωθεί το landing animation
        if dragon_state_finished(e):
            e["dragon_mode"] = "ground"         # Μετά το landing επιστρέφει σε ground mode
            e["hits_taken_ground"] = 0          # Μηδενίζουμε τα hits που είχε δεχτεί στη ground phase
            e["ground_phase_started_at"] = now  # Ξεκινά νέα ground phase
            e["damage_applied"] = False         # Reset του damage flag

            # Συνεχίζει το ground phase
            set_dragon_state(e, "walk", e.get("patrol_dir", e.get("dir", "right")))

        return

    # Αν ο dragon βρίσκεται σε ground attack state
    if e.get("state") == "attack":
        e["dragon_mode"] = "ground"

        apply_dragon_ground_attack(e, players)  # Ελέγχουμε αν έφτασε το impact frame ώστε να εφαρμοστεί η ζημιά

        # Αν τελείωσε το attack animation, επιστρέφει σε walk
        if dragon_state_finished(e):
            e["patrol_dir"] = e.get("dir", "right")
            set_dragon_state(e, "walk", e["patrol_dir"])

        return

    # Ο dragon θεωρείται ότι βρίσκεται σε ground mode
    e["dragon_mode"] = "ground"

    hits_needed = defs.get("ground_hits_before_rise", 5)    # Πόσα hits πρέπει να δεχτεί στο έδαφος πριν κάνει rise

    # Αν έχει δεχτεί αρκετά hits, περνάει σε rise state
    if e.get("hits_taken_ground", 0) >= hits_needed:
        set_dragon_state(e, "rise", e.get("dir", "right"))
        return

    # Έλεγχος αν ο dragon χτυπήθηκε πρόσφατα από πίσω
    back_hit_time = e.get("last_back_hit_time", 0.0)
    back_hit_dir = e.get("last_back_hit_dir")

    # Αν δέχτηκε hit από πίσω και δεν έχει cooldown, γυρίζει προς τον παίκτη και κάνει ground attack
    if (
        back_hit_dir is not None
        and now - back_hit_time <= 0.8
        and now >= e.get("next_ground_attack_time", 0.0)
    ):
        e["patrol_dir"] = back_hit_dir
        e["next_ground_attack_time"] = now + e.get("attack_cooldown", 1.0)

        # Καθαρίζουμε το event του back hit για να μη γίνει ξανά από το ίδιο χτύπημα
        e["last_back_hit_time"] = 0.0
        e["last_back_hit_dir"] = None

        set_dragon_state(e, "attack", back_hit_dir)
        return

    # Ελέγχουμε αν υπάρχει παίκτης μπροστά από τον dragon, ώστε να κάνει ground attack
    target_pid, target_player, attack_dir = ground_attack_target(e, players)

    # Αν υπάρχει στόχος μπροστά και έχει περάσει το cooldown, ξεκινάει ground attack
    if target_player is not None and now >= e.get("next_ground_attack_time", 0.0):
        e["target"] = target_pid
        e["patrol_dir"] = attack_dir
        e["next_ground_attack_time"] = now + e.get("attack_cooldown", 1.0)
        set_dragon_state(e, "attack", attack_dir)
        return

    # Αν δεν κάνει rise ή attack, συνεχίζει το ground phase
    dragon_move(e, "walk", move_enemy, collides_with_walls_aabb)