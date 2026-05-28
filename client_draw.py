import arcade
from sprites import PlayerSprite, EnemySprite
import client_attackAndUI

### Το αρχείο αυτό περιέχει μεθόδους σχεδίασης για το UI του client ###

# Μέθοδος εμφάνισης ενεργών elixir buffs δεξιά από τα abilities
def draw_active_elixir_buffs(self):
    # Αν δεν υπάρχουν ενεργά ελιξήρια, δεν σχεδιάζεται τίποτα
    if not self.active_elixirs:
        return

    # Υπολογίζουμε τη θέση του panel σε σχέση με το ability bar
    ability_bar_width = 560
    ability_bar_left = self.window.width / 2 - ability_bar_width / 2
    ability_bar_right = ability_bar_left + ability_bar_width
    bottom = 10

    # Διαστάσεις panel και κάθε γραμμής buff
    panel_width = 210
    row_height = 22
    panel_height = 12 + row_height * len(self.active_elixirs)
    gap_from_abilities = 15

    panel_left = ability_bar_right + gap_from_abilities
    panel_bottom = bottom

    # Αν το panel βγαίνει έξω από τη δεξιά πλευρά της οθόνης, μετακινείται προς τα μέσα
    if panel_left + panel_width > self.window.width - 10:
        panel_left = self.window.width - panel_width - 10

    # Σχεδίαση φόντου και περιγράμματος του panel
    arcade.draw_lbwh_rectangle_filled(
        panel_left,
        panel_bottom,
        panel_width,
        panel_height,
        (0, 0, 0, 170)
    )

    arcade.draw_lbwh_rectangle_outline(
        panel_left,
        panel_bottom,
        panel_width,
        panel_height,
        arcade.color.WHITE,
        1
    )

    # Δημιουργούμε text objects μόνο όταν χρειάζεται
    while len(self.elixir_texts) < len(self.active_elixirs):
        self.elixir_texts.append(
            arcade.Text(
                "",
                0,
                0,
                arcade.color.WHITE,
                font_size=10
            )
        )

    bar_x = panel_left + 90
    bar_width = 90
    bar_height = 6

    # Σχεδιάζουμε κάθε ενεργό elixir με όνομα, χρόνο που απομένει και μπάρα διάρκειας
    for index, buff in enumerate(self.active_elixirs):
        item_name = buff.get("item_name", "")
        remaining = float(buff.get("remaining", 0.0))
        duration = float(buff.get("duration", 60.0))

        # Υπολογισμός ποσοστού διάρκειας που απομένει
        if duration <= 0:
            ratio = 0.0
        else:
            ratio = max(0.0, min(1.0, remaining / duration))

        y = panel_bottom + panel_height - 18 - index * row_height

        # Πιο σύντομο όνομα για να χωράει καλύτερα στο panel
        if item_name == "ElixirOfToughness":
            label = "Toughness"
        elif item_name == "ElixirOfMagic":
            label = "Magic"
        elif item_name == "ElixirOfPower":
            label = "Power"
        else:
            label = item_name

        # Εμφάνιση ονόματος και χρόνου
        text = self.elixir_texts[index]
        text.text = f"{label} {remaining:.0f}s"
        text.x = panel_left + 8
        text.y = y - 3
        text.draw()

        # Background και γέμισμα της μπάρας διάρκειας
        arcade.draw_lbwh_rectangle_filled(
            bar_x,
            y,
            bar_width,
            bar_height,
            arcade.color.BLACK
        )

        arcade.draw_lbwh_rectangle_filled(
            bar_x,
            y,
            bar_width * ratio,
            bar_height,
            arcade.color.WHITE
        )

# Μέθοδος εμφάνισης inventory panel
def draw_inventory_ui(self):
    # Το inventory σχεδιάζεται μόνο όταν είναι ανοιχτό
    if not self.inventory_open:
        return

    # Διαστάσεις και θέση του κεντρικού panel
    panel_width = 430
    panel_height = 250

    panel_left = self.window.width / 2 - panel_width / 2
    panel_bottom = self.window.height / 2 - panel_height / 2

    panel_center_x = self.window.width / 2
    panel_top = panel_bottom + panel_height

    # Σχεδίαση φόντου και περιγράμματος inventory
    arcade.draw_lbwh_rectangle_filled(
        panel_left,
        panel_bottom,
        panel_width,
        panel_height,
        (0, 0, 0, 210)
    )

    arcade.draw_lbwh_rectangle_outline(
        panel_left,
        panel_bottom,
        panel_width,
        panel_height,
        arcade.color.WHITE,
        2
    )

    # Τοποθέτηση και σχεδίαση τίτλου
    self.inventory_title_text.x = panel_center_x
    self.inventory_title_text.y = panel_top - 38
    self.inventory_title_text.draw()

    # Μήνυμα οδηγιών αγοράς, χρήσης
    self.inventory_help_text.x = panel_center_x
    self.inventory_help_text.y = panel_top - 62
    self.inventory_help_text.draw()

    # Ρυθμίσεις των slots αντικειμένων
    slot_size = 62
    icon_size = 40
    gap = 14
    group_gap = 34   # Κενό ανάμεσα σε potions και elixirs

    slot_y = panel_bottom + 105

    # Υπολογισμός αρχικής θέσης ώστε όλα τα slots να είναι κεντραρισμένα
    total_width = (slot_size * 5) + (gap * 4) + group_gap
    start_x = panel_center_x - total_width / 2 + slot_size / 2

    # Λίστα με τα αντικείμενα που εμφανίζονται στο shop/inventory
    shop_items = [
        ("Health_Potion", "1", 50),
        ("Energy_Potion", "2", 50),
        ("ElixirOfToughness", "3", 200),
        ("ElixirOfMagic", "4", 200),
        ("ElixirOfPower", "5", 200),
    ]

    # Τίτλοι κατηγοριών
    potions_title = arcade.Text(
        "Potions",
        0,
        0,
        arcade.color.WHITE,
        font_size=14,
        anchor_x="center"
    )

    elixirs_title = arcade.Text(
        "Elixirs",
        0,
        0,
        arcade.color.WHITE,
        font_size=14,
        anchor_x="center"
    )

    # Κέντρα ομάδων
    potions_center_x = start_x + (slot_size + gap) / 2
    elixirs_start_x = start_x + 2 * (slot_size + gap) + group_gap
    elixirs_center_x = elixirs_start_x + (slot_size + gap)

    # Σχεδιάζουμε τίτλους ομάδων
    potions_title.x = potions_center_x
    potions_title.y = slot_y + 58
    potions_title.draw()

    elixirs_title.x = elixirs_center_x
    elixirs_title.y = slot_y + 58
    elixirs_title.draw()

    # Δημιουργία text objects για ποσότητα και τιμή, μόνο όταν χρειάζεται
    while len(self.inventory_item_texts) < len(shop_items):
        self.inventory_item_texts.append({
            "qty": arcade.Text(
                "",
                0,
                0,
                arcade.color.WHITE,
                font_size=12,
                anchor_x="right"
            ),
            "name": arcade.Text(
                "",
                0,
                0,
                arcade.color.WHITE,
                font_size=9,
                anchor_x="center"
            )
        })

    # Σχεδίαση κάθε slot αντικειμένου
    for index, (item_name, key_name, price) in enumerate(shop_items):
        # Παίρνουμε την ποσότητα του αντικειμένου από το inventory του παίκτη
        quantity = client_attackAndUI.get_inventory_quantity(self, item_name)

        # Τα πρώτα 2 είναι potions, τα άλλα 3 είναι elixirs
        if index < 2:
            slot_x = start_x + index * (slot_size + gap)
        else:
            slot_x = start_x + index * (slot_size + gap) + group_gap

        slot_left = slot_x - slot_size / 2
        slot_bottom = slot_y - slot_size / 2

        # Slot background
        arcade.draw_lbwh_rectangle_filled(
            slot_left,
            slot_bottom,
            slot_size,
            slot_size,
            (40, 40, 40, 220)
        )

        # Slot border
        arcade.draw_lbwh_rectangle_outline(
            slot_left,
            slot_bottom,
            slot_size,
            slot_size,
            arcade.color.LIGHT_GRAY,
            1
        )

        # Εικονίδιο
        texture = self.item_textures.get(item_name)

        if texture is not None:
            icon_left = slot_x - icon_size / 2
            icon_bottom = (slot_y + 8) - icon_size / 2

            arcade.draw_texture_rect(
                texture,
                arcade.LBWH(
                    icon_left,
                    icon_bottom,
                    icon_size,
                    icon_size
                )
            )

        # Ποσότητα
        qty_text = self.inventory_item_texts[index]["qty"]
        qty_text.text = f"x{quantity}"
        qty_text.x = slot_left + slot_size - 5
        qty_text.y = slot_bottom + 5
        qty_text.draw()

        # Όνομα και κόστος
        name_text = self.inventory_item_texts[index]["name"]
        name_text.text = f"{key_name}: {price}G"
        name_text.x = slot_x
        name_text.y = slot_bottom - 18
        name_text.draw()

# Σχεδιάζει προσωρινό μήνυμα objective στο κέντρο της οθόνης
def draw_objective_message(self):
    if not self.objective_message:
        return

    box_width = 460
    box_height = 70

    center_x = self.window.width / 2
    center_y = self.window.height / 2 + 120

    left = center_x - box_width / 2
    bottom = center_y - box_height / 2

    arcade.draw_lbwh_rectangle_filled(
        left,
        bottom,
        box_width,
        box_height,
        (0, 0, 0, 170)
    )

    arcade.draw_lbwh_rectangle_outline(
        left,
        bottom,
        box_width,
        box_height,
        arcade.color.WHITE,
        1
    )

    self.objective_message_text.x = center_x
    self.objective_message_text.y = center_y
    self.objective_message_text.draw()

# Σχεδιάζει full-screen overlay όταν ο παίκτης βρίσκεται σε lobby, loading ή waiting state
def draw_session_screen(self):
    if self.my_session_phase == "playing":
        return

    screen_w = self.window.width
    screen_h = self.window.height

    arcade.draw_lbwh_rectangle_filled(
        0,
        0,
        screen_w,
        screen_h,
        (0, 0, 0, 230)
    )

    if self.my_session_phase == "lobby":
        self.session_title_text.text = "Waiting for players..."
        self.session_subtitle_text.text = f"Game starts in {self.lobby_countdown}s"
        self.session_progress_text.text = f"Players ready: {self.lobby_players_count}"

    elif self.my_session_phase == "loading":
        self.session_title_text.text = "Loading Celestial Lands..."
        self.session_subtitle_text.text = "Preparing world"
        self.session_progress_text.text = f"{self.loading_progress}%"

        bar_width = 360
        bar_height = 18
        left = screen_w / 2 - bar_width / 2
        bottom = screen_h / 2 - 70

        arcade.draw_lbwh_rectangle_filled(
            left,
            bottom,
            bar_width,
            bar_height,
            arcade.color.BLACK
        )

        arcade.draw_lbwh_rectangle_filled(
            left,
            bottom,
            bar_width * (self.loading_progress / 100),
            bar_height,
            arcade.color.WHITE
        )

        arcade.draw_lbwh_rectangle_outline(
            left,
            bottom,
            bar_width,
            bar_height,
            arcade.color.WHITE,
            1
        )

    elif self.my_session_phase == "waiting_next":
        self.session_title_text.text = "Game in progress"
        self.session_subtitle_text.text = "You will join the next round"
        self.session_progress_text.text = "Please wait..."

    else:
        return

    self.session_title_text.x = screen_w / 2
    self.session_title_text.y = screen_h / 2 + 60

    self.session_subtitle_text.x = screen_w / 2
    self.session_subtitle_text.y = screen_h / 2 + 15

    self.session_progress_text.x = screen_w / 2
    self.session_progress_text.y = screen_h / 2 - 35

    self.session_title_text.draw()
    self.session_subtitle_text.draw()
    self.session_progress_text.draw()

# Σχεδιάζει overlay τέλους παιχνιδιού, δηλαδή victory ή game over
def draw_game_end_overlay(self):
    status = self.final_game_status or self.game_status

    if not self.returning_to_menu and self.game_status == "playing":
        return

    screen_w = self.window.width
    screen_h = self.window.height

    arcade.draw_lbwh_rectangle_filled(
        0,
        0,
        screen_w,
        screen_h,
        (0, 0, 0, 190)
    )

    if status == "win":
        self.game_end_title_text.text = "VICTORY"
        self.game_end_subtitle_text.text = "You completed the final area!"
    elif status == "loss":
        self.game_end_title_text.text = "GAME OVER"
        self.game_end_subtitle_text.text = "All players have died."
    else:
        return

    self.game_end_title_text.x = screen_w / 2
    self.game_end_title_text.y = screen_h / 2 + 35

    self.game_end_subtitle_text.x = screen_w / 2
    self.game_end_subtitle_text.y = screen_h / 2 - 20

    self.game_end_title_text.draw()
    self.game_end_subtitle_text.draw()

# Σχεδιάζει nickname, level, HP και energy πάνω από κάθε player sprite
def draw_player_status_bars(self, spr: PlayerSprite):
    # Θέση πάνω από το κεφάλι
    x = spr.center_x
    y = spr.top + 18

    # Διαστάσεις
    w = 54
    hp_h = 7
    energy_h = 3
    gap = 2

    # Values 
    hp = max(0.0, min(1.0, getattr(spr, "hp", 1.0)))
    en = max(0.0, min(1.0, getattr(spr, "energy", 1.0)))

    left = x - w / 2

    # Nickname
    spr.nickname_text.text = getattr(spr, "nickname", "")
    spr.nickname_text.x = x
    spr.nickname_text.y = y + hp_h
    spr.nickname_text.draw()

    # Level
    spr.level_text.text = str(getattr(spr, "level", 1))
    spr.level_text.x = left - gap
    spr.level_text.y = y + hp_h / 2
    spr.level_text.draw()

    # Backgrounds
    arcade.draw_lbwh_rectangle_filled(left - 1, y - 1, w + 2, hp_h + 2, arcade.color.BLACK)
    arcade.draw_lbwh_rectangle_filled(left - 1, y - (energy_h + gap) - 1, w + 2, energy_h + 2, arcade.color.BLACK)

    # HP
    arcade.draw_lbwh_rectangle_filled(left, y, w, hp_h, arcade.color.DARK_GREEN)
    arcade.draw_lbwh_rectangle_filled(left, y, w * hp, hp_h, arcade.color.GREEN)

    # ENERGY
    y2 = y - (energy_h + gap)
    arcade.draw_lbwh_rectangle_filled(left, y2, w, energy_h, arcade.color.DARK_YELLOW)
    arcade.draw_lbwh_rectangle_filled(left, y2, w * en, energy_h, arcade.color.YELLOW)

# Σχεδιάζει nickname και HP bar πάνω από κάθε enemy sprite
def draw_enemy_status_bars(self, spr: EnemySprite):
    # Θέση πάνω από το κεφάλι
    x = spr.center_x
    y = spr.top + 18

    # Διαστάσεις
    w = 54
    hp_h = 7

    hp_ratio = 0.0                          # Υπολογίζουμε το ποσοστό ζωής του sprite για τη μπάρα HP
    if getattr(spr, "hp_max", 0) > 0:       # Αν υπάρχει έγκυρο μέγιστο HP, υπολογίζουμε τρέχον HP / μέγιστο HP
        hp_ratio = spr.hp / spr.hp_max
    hp_ratio = max(0.0, min(1.0, hp_ratio)) # Περιορίζουμε το ποσοστό ζωής στο διάστημα 0.0 - 1.0

    left = x - w / 2

    # Nickname
    spr.nickname_text.text = getattr(spr, "nickname", "")
    spr.nickname_text.x = x
    spr.nickname_text.y = y + hp_h + 3
    spr.nickname_text.draw()

    # HP background
    arcade.draw_lbwh_rectangle_filled(left - 1, y - 1, w + 2, hp_h + 2, arcade.color.BLACK)

    # HP bar
    arcade.draw_lbwh_rectangle_filled(left, y, w, hp_h, arcade.color.BLACK)
    arcade.draw_lbwh_rectangle_filled(left, y, w * hp_ratio, hp_h, arcade.color.RED)

# Σχεδιάζει το κάτω αριστερό HUD panel του local player με HP, Energy και XP
def draw_local_player_hud_bars(self):
    if not self.player_sprite:
        return

    # Ίδιες διαστάσεις με το ability panel, για να τοποθετηθεί σωστά αριστερά του
    ability_bar_width = 560
    ability_bar_left = self.window.width / 2 - ability_bar_width / 2
    bottom = 10

    # Διαστάσεις του νέου panel
    panel_width = 210
    panel_height = 82
    gap_from_abilities = 15

    panel_left = ability_bar_left - panel_width - gap_from_abilities
    panel_bottom = bottom

    # Αν για κάποιο λόγο βγει πολύ αριστερά, το κρατάμε μέσα στην οθόνη
    if panel_left < 10:
        panel_left = 10

    # Τιμές HP, Energy από τον παίκτη
    hp = max(0.0, min(1.0, getattr(self.player_sprite, "hp", 1.0)))
    energy = max(0.0, min(1.0, getattr(self.player_sprite, "energy", 1.0)))

    # Τιμές XP από τον παίκτη
    xp = int(getattr(self.player_sprite, "xp", 0))
    xp_next = int(getattr(self.player_sprite, "xp_next", 0))

    # Υπολογισμός ποσοστού XP μέχρι το επόμενο level
    if xp_next > 0:
        xp_ratio = max(0.0, min(1.0, xp / xp_next))
        xp_text = f"{xp}/{xp_next}"
    else:
        xp_ratio = 1.0
        xp_text = "MAX"

    hp_percent = int(round(hp * 100))
    energy_percent = int(round(energy * 100))

    # Background panel
    arcade.draw_lbwh_rectangle_filled(
        panel_left,
        panel_bottom,
        panel_width,
        panel_height,
        (0, 0, 0, 180)
    )

    # Bar settings
    label_x = panel_left + 10
    bar_x = panel_left + 55
    value_x = panel_left + panel_width - 12

    hp_y = panel_bottom + 58
    energy_y = panel_bottom + 38
    xp_y = panel_bottom + 20

    bar_width = 95
    bar_height = 9
    xp_bar_height = 5

    # HP background και fill bar
    arcade.draw_lbwh_rectangle_filled(
        bar_x - 1,
        hp_y - 1,
        bar_width + 2,
        bar_height + 2,
        arcade.color.BLACK
    )

    arcade.draw_lbwh_rectangle_filled(
        bar_x,
        hp_y,
        bar_width,
        bar_height,
        arcade.color.DARK_GREEN
    )

    arcade.draw_lbwh_rectangle_filled(
        bar_x,
        hp_y,
        bar_width * hp,
        bar_height,
        arcade.color.GREEN
    )

    # Energy background και fill bar
    arcade.draw_lbwh_rectangle_filled(
        bar_x - 1,
        energy_y - 1,
        bar_width + 2,
        bar_height + 2,
        arcade.color.BLACK
    )

    arcade.draw_lbwh_rectangle_filled(
        bar_x,
        energy_y,
        bar_width,
        bar_height,
        arcade.color.DARK_YELLOW
    )

    arcade.draw_lbwh_rectangle_filled(
        bar_x,
        energy_y,
        bar_width * energy,
        bar_height,
        arcade.color.YELLOW
    )

    # XP background και fill bar
    arcade.draw_lbwh_rectangle_filled(
        bar_x - 1,
        xp_y - 1,
        bar_width + 2,
        xp_bar_height + 2,
        arcade.color.BLACK
    )

    arcade.draw_lbwh_rectangle_filled(
        bar_x,
        xp_y,
        bar_width,
        xp_bar_height,
        arcade.color.BLACK
    )

    arcade.draw_lbwh_rectangle_filled(
        bar_x,
        xp_y,
        bar_width * xp_ratio,
        xp_bar_height,
        arcade.color.WHITE
    )

    # Ενημέρωση text objects για HP
    self.hud_hp_label_text.x = label_x
    self.hud_hp_label_text.y = hp_y - 2

    self.hud_hp_value_text.text = f"{hp_percent}%"
    self.hud_hp_value_text.x = value_x
    self.hud_hp_value_text.y = hp_y - 3

    # Ενημέρωση text objects για Energy
    self.hud_energy_label_text.x = label_x
    self.hud_energy_label_text.y = energy_y - 2

    self.hud_energy_value_text.text = f"{energy_percent}%"
    self.hud_energy_value_text.x = value_x
    self.hud_energy_value_text.y = energy_y - 3

    # Ενημέρωση text objects για XP
    self.hud_xp_label_text.x = label_x
    self.hud_xp_label_text.y = xp_y - 4

    self.hud_xp_value_text.text = xp_text
    self.hud_xp_value_text.x = value_x
    self.hud_xp_value_text.y = xp_y - 6

    # Σχεδιάζουμε τα texts στο τέλος, ώστε να μη σκεπάζονται από τις μπάρες
    self.hud_hp_label_text.draw()
    self.hud_hp_value_text.draw()

    self.hud_energy_label_text.draw()
    self.hud_energy_value_text.draw()

    self.hud_xp_label_text.draw()
    self.hud_xp_value_text.draw()