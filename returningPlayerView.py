import arcade
import sqlite3
from db_path import get_db_path

DB_PATH = get_db_path()

# Μέθοδος που αναζητά παίκτη στη βάση με βάση το nickname
def get_player_by_nickname(nickname: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Αναζήτηση του παίκτη στον πίνακα Player
    cur.execute("""
        SELECT Player_id, Nickname, Class_name
        FROM Player
        WHERE Nickname = ?;
    """, (nickname,))

    # Αν βρεθεί παίκτης, επιστρέφεται tuple με τα στοιχεία του αλλιώς επιστρέφεται None
    row = cur.fetchone()

    conn.close()
    return row  # None ή (player_id, nickname, class_name)

# View για σύνδεση παίκτη που έχει ήδη δημιουργηθεί
class ReturningPlayerView(arcade.View):
    def __init__(self):
        super().__init__()

        self.nickname = ""          # Nickname που πληκτρολογεί ο χρήστης

        # Μεταβλητές για προσωρινή εμφάνιση μηνύματος λάθους
        self.error_timer = 0.0
        self.error_duration = 2.0

        # Μεταβλητές για blinking caret στο input πεδίο
        self.caret_timer = 0.0
        self.caret_visible = True

        # Background
        self.background_list = arcade.SpriteList()
        self.bg = None

        # Τίτλος της οθόνης επιστροφής παίκτη
        self.title = arcade.Text(
            "Returning Player",
            0, 0, arcade.color.WHITE, 36,
            anchor_x="center"
        )

        # Label για το input nickname
        self.label = arcade.Text(
            "Enter your Nickname:",
            0, 0, arcade.color.WHITE, 20,
            anchor_x="center"
        )

        # Text που εμφανίζει το nickname που πληκτρολογεί ο χρήστης
        self.input_text = arcade.Text(
            "",
            0, 0, arcade.color.WHITE, 24,
            anchor_x="center"
        )

        # Βοηθητικό μήνυμα
        self.hint = arcade.Text(
            "Press ENTER to login",
            0, 0, arcade.color.LIGHT_GRAY, 14,
            anchor_x="center"
        )

        # Κουμπί για σύνδεση στο παιχνίδι
        self.join_button_width = 170
        self.join_button_height = 38
        self.join_button_x = 0
        self.join_button_y = 0
        self.join_selected = False

        self.join_button_text = arcade.Text(
            "Join Game",
            0, 0, arcade.color.WHITE, 16,
            anchor_x="center",
            anchor_y="center"
        )

        # Tip για επιστροφή στο main menu
        self.escape_hint = arcade.Text(
            "ESC: Main Menu",
            0, 0, arcade.color.LIGHT_GRAY, 13,
            anchor_x="center"
        )

        # Text για μηνύματα λάθους
        self.error_text = arcade.Text(
            "",
            0, 0, arcade.color.RED, 14,
            anchor_x="center"
        )

    # Καλείται όταν εμφανίζεται το ReturningPlayerView
    def on_show_view(self):
        # Φόρτωση και εμφάνιση background
        self.bg = arcade.Sprite("assets/backgrounds/hills&trees.png")
        self.background_list = arcade.SpriteList()
        self.background_list.append(self.bg)

        # Τοποθέτηση και προσαρμογή background στο μέγεθος του παραθύρου
        self.bg.center_x = self.window.width // 2
        self.bg.center_y = self.window.height // 2
        self.bg.width = self.window.width
        self.bg.height = self.window.height

        cx = self.window.width // 2
        cy = self.window.height // 2

        # Τοποθέτηση των UI texts
        self.title.x = cx
        self.title.y = self.window.height - 120

        self.label.x = cx
        self.label.y = cy + 40

        self.input_text.x = cx
        self.input_text.y = cy

        self.hint.x = cx
        self.hint.y = cy - 40

        # Τοποθέτηση κουμπιού Join Game κάτω από το input
        self.join_button_x = cx
        self.join_button_y = cy - 85

        self.join_button_text.x = self.join_button_x
        self.join_button_text.y = self.join_button_y

        # Tip επιστροφής στο main menu
        self.escape_hint.x = cx
        self.escape_hint.y = cy - 155

        self.error_text.x = cx
        self.error_text.y = cy - 130
        self.error_text.text = ""

        self.nickname = ""  # Καθαρισμός nickname κάθε φορά που εμφανίζεται το view

    # Σχεδιάζει background και κείμενα στην οθόνη
    def on_draw(self):
        self.clear()
        self.background_list.draw()

        self.title.draw()
        self.label.draw()

        # Προσθέτουμε caret ώστε το input να φαίνεται ενεργό
        caret = "|" if self.caret_visible else ""
        self.input_text.text = self.nickname + caret
        self.input_text.draw()

        self.hint.draw()

        # Σχεδιάζουμε το κουμπί Join Game
        button_left = self.join_button_x - self.join_button_width / 2
        button_bottom = self.join_button_y - self.join_button_height / 2

        arcade.draw_lbwh_rectangle_filled(
            button_left,
            button_bottom,
            self.join_button_width,
            self.join_button_height,
            (0, 0, 0, 170)
        )

        # Το περίγραμμα γίνεται κίτρινο όταν το ποντίκι βρίσκεται πάνω στο κουμπί
        outline_color = arcade.color.YELLOW if self.join_selected else arcade.color.WHITE

        arcade.draw_lbwh_rectangle_outline(
            button_left,
            button_bottom,
            self.join_button_width,
            self.join_button_height,
            outline_color,
            2
        )

        self.join_button_text.draw()
        self.escape_hint.draw()

        self.error_text.draw()

    # Καλείται κάθε frame και ενημερώνει caret και error timer
    def on_update(self, delta_time: float):
        # Blinking caret για το input nickname
        self.caret_timer += delta_time
        if self.caret_timer > 0.4:
            self.caret_timer = 0.0
            self.caret_visible = not self.caret_visible

        # Αν υπάρχει error message, μειώνουμε τον χρόνο εμφάνισής του
        if self.error_timer > 0:
            self.error_timer -= delta_time
            if self.error_timer <= 0:
                self.error_text.text = ""
        # Αν δεν υπάρχει nickname, το κουμπί φαίνεται ανενεργό
        if not self.nickname.strip():
            self.join_button_text.color = arcade.color.GRAY
        else:
            self.join_button_text.color = arcade.color.YELLOW if self.join_selected else arcade.color.WHITE

    # Καλείται όταν ο χρήστης πληκτρολογεί χαρακτήρες
    def on_text(self, text: str):
        # Περιορισμός nickname σε 12 χαρακτήρες
        if len(self.nickname) >= 12:
            return
        
        # Επιτρέπουμε μόνο γράμματα, αριθμούς και κάτω παύλα
        if text.isalnum() or text == "_":
            self.nickname += text

    # Χειρισμός ειδικών πλήκτρων
    def on_key_press(self, key, modifiers):
        # Διαγραφή τελευταίου χαρακτήρα
        if key == arcade.key.BACKSPACE:
            self.nickname = self.nickname[:-1]

        # Προσπάθεια σύνδεσης με Enter
        elif key == arcade.key.ENTER:
            self.try_login()

        # Επιστροφή στο κεντρικό μενού με Escape
        elif key == arcade.key.ESCAPE:
            # Καθαρίζουμε τυχόν προσωρινό player id από τη διαδικασία δημιουργίας χαρακτήρα
            if hasattr(self.window, "player_id"):
                del self.window.player_id

            # Καθαρίζουμε το προσωρινό nickname
            if hasattr(self.window, "nickname"):
                del self.window.nickname

            # Καθαρίζουμε την προσωρινή επιλογή κλάσης
            if hasattr(self.window, "class_name"):
                del self.window.class_name

            # Επιστρέφουμε στο main menu
            from login import MenuView
            self.window.show_view(MenuView())

    # Ελέγχει αν ένα σημείο βρίσκεται μέσα στο κουμπί Join Game
    def point_in_join_button(self, x, y):
        button_left = self.join_button_x - self.join_button_width / 2
        button_right = self.join_button_x + self.join_button_width / 2
        button_bottom = self.join_button_y - self.join_button_height / 2
        button_top = self.join_button_y + self.join_button_height / 2

        return button_left <= x <= button_right and button_bottom <= y <= button_top
    
    # Ενημερώνει αν το ποντίκι βρίσκεται πάνω στο Join Game
    def on_mouse_motion(self, x, y, dx, dy):
        self.join_selected = self.point_in_join_button(x, y)

    # Χειρισμός click στο κουμπί Join Game
    def on_mouse_press(self, x, y, button, modifiers):
        if button != arcade.MOUSE_BUTTON_LEFT:
            return

        if self.point_in_join_button(x, y):
            self.try_login()

    # Προσπαθεί να συνδέσει υπάρχοντα παίκτη με βάση το nickname
    def try_login(self):
        nick = self.nickname.strip()

        # Έλεγχος αν το nickname είναι κενό
        if not nick:
            self.error_text.text = "Nickname cannot be empty"
            self.error_timer = self.error_duration
            return

        # Αναζήτηση παίκτη στη βάση δεδομένων
        row = get_player_by_nickname(nick)

        # Αν δεν βρεθεί παίκτης, εμφανίζεται μήνυμα λάθους
        if row is None:
            self.error_text.text = "Player not found"
            self.error_timer = self.error_duration
            return

        # Αν βρεθεί, παίρνουμε τα στοιχεία του παίκτη
        player_id, nickname, class_name = row

        # Αποθηκεύουμε τα στοιχεία στο window, ώστε να τα χρησιμοποιήσει το client.py στο start_game()
        self.window.player_id = player_id
        self.window.nickname = nickname
        self.window.class_name = class_name

        print("Returning Player:")
        print("ID:", player_id)
        print("Nickname:", nickname)
        print("Class:", class_name)

        # Ξεκινάμε το παιχνίδι
        start_game = getattr(self.window, "start_game", None)
        if callable(start_game):
            start_game()
        else:
            arcade.exit()
