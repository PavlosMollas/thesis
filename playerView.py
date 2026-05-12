import arcade
import uuid
import sqlite3
from classView import ClassSelectView

# Μέθοδος που ελέγχει αν υπάρχει ήδη το nickname στη βάση δεδομένων
def nickname_exists(nickname: str) -> bool:
    conn = sqlite3.connect("MMORPG_DB.db")
    cur = conn.cursor()

    # Ψάχνουμε στον πίνακα Player αν υπάρχει ήδη εγγραφή με το ίδιο nickname
    cur.execute(
        "SELECT 1 FROM Player WHERE Nickname = ? LIMIT 1;",
        (nickname,)
    )

    exists = cur.fetchone() is not None # Αν επιστραφεί αποτέλεσμα, τότε το nickname υπάρχει ήδη

    conn.close()
    return exists

class CreatePlayerView(arcade.View):
    def __init__(self):
        super().__init__()

        # Μεταβλητές για προσωρινή εμφάνιση μηνυμάτων λάθους
        self.error_timer = 0.0
        self.error_duration = 2.0

        # Text για εμφάνιση error message, π.χ. άδειο ή ήδη χρησιμοποιημένο nickname
        self.error_text = arcade.Text(
            "",
            0, 0,
            arcade.color.RED,
            14,
            anchor_x="center"
        )

        # Text επιλογής Continue
        self.continue_text = arcade.Text(
            "Continue",
            0, 0,
            arcade.color.WHITE,
            22,
            anchor_x="center"
        )

        # Flag που δείχνει αν ο δείκτης του ποντικιού βρίσκεται πάνω στο Continue
        self.continue_selected = False

        # Nickname που πληκτρολογεί ο χρήστης και id που θα δημιουργηθεί
        self.nickname = ""
        self.player_id = None

        # Μεταβλητές για το blinking caret στο input πεδίο
        self.caret_timer = 0.0
        self.caret_visible = True

        # Τίτλος οθόνης δημιουργίας χαρακτήρα
        self.title = arcade.Text(
            "Create Your Character",
            0, 0,
            arcade.color.WHITE,
            36,
            anchor_x="center"
        )

        # Label πάνω από το input
        self.label = arcade.Text(
            "Enter Nickname:",
            0, 0,
            arcade.color.WHITE,
            20,
            anchor_x="center"
        )

        # Text που εμφανίζει το nickname που πληκτρολογεί ο χρήστης
        self.input_text = arcade.Text(
            "",
            0, 0,
            arcade.color.WHITE,
            24,
            anchor_x="center"
        )

        # Βοηθητικό μήνυμα για τον χρήστη
        self.hint = arcade.Text(
            "Press ENTER to continue",
            0, 0,
            arcade.color.LIGHT_GRAY,
            14,
            anchor_x="center"
        )

    # Μέθοδος που καλείται όταν εμφανίζεται το CreatePlayerView
    def on_show_view(self):
        # Δημιουργία και φόρτωση background εικόνας
        self.background_list = arcade.SpriteList()
        self.nickname_background = arcade.Sprite("assets/backgrounds/hills&trees.png")
        self.background_list.append(self.nickname_background)

        # Τοποθέτηση background στο κέντρο του παραθύρου
        self.nickname_background.center_x = self.window.width // 2
        self.nickname_background.center_y = self.window.height // 2

        # Προσαρμογή background στο μέγεθος του παραθύρου
        self.nickname_background.width = self.window.width
        self.nickname_background.height = self.window.height

        cx = self.window.width // 2
        cy = self.window.height // 2

        # Τοποθέτηση των UI texts στην οθόνη
        self.error_text.x = cx
        self.error_text.y = cy - 65
        self.error_text.text = ""

        self.title.x = cx
        self.title.y = self.window.height - 120

        self.label.x = cx
        self.label.y = cy + 40

        self.input_text.x = cx
        self.input_text.y = cy

        self.hint.x = cx
        self.hint.y = cy - 40

        # Reset των προσωρινών στοιχείων κάθε φορά που εμφανίζεται το view
        self.nickname = ""
        self.player_id = None
        
        # Τοποθέτηση Continue επιλογής
        self.continue_text.x = self.window.width // 2
        self.continue_text.y = (self.window.height // 2) - 100

    # Μέθοδος που σχεδιάζει το background και όλα τα κείμενα του view
    def on_draw(self):
        self.clear()
        self.background_list.draw()

        self.title.draw()
        self.label.draw()

        # Προσθέτουμε caret στο nickname ώστε να φαίνεται σαν πεδίο εισαγωγής
        caret = "|" if self.caret_visible else ""
        self.input_text.text = self.nickname + caret
        self.input_text.draw()

        self.error_text.draw()
        self.hint.draw()
        self.continue_text.draw()

    # Μέθοδος που καλείται κάθε frame και ενημερώνει caret, hover χρώμα και error timer
    def on_update(self, delta_time: float):
        # Blinking caret στο input nickname
        self.caret_timer += delta_time
        if self.caret_timer > 0.4:
            self.caret_timer = 0
            self.caret_visible = not self.caret_visible

        # Αν το ποντίκι είναι πάνω στο Continue και υπάρχει nickname, το κάνουμε κίτρινο
        if self.continue_selected and self.nickname.strip():
            self.continue_text.color = arcade.color.YELLOW
        else:
            self.continue_text.color = arcade.color.WHITE

        # Αν υπάρχει error message, μειώνουμε τον χρόνο εμφάνισής του
        if self.error_timer > 0:
            self.error_timer -= delta_time
            if self.error_timer <= 0:
                self.error_text.text = ""

    # Μέθοδος που ελέγχει αν το ποντίκι βρίσκεται πάνω σε ένα text αντικείμενο
    def hit_text(self, text: arcade.Text, x, y) -> bool:
        w = text.content_width
        h = text.content_height

        # Υπολογισμός ορίων του text
        left = text.x - w / 2
        right = text.x + w / 2
        bottom = text.y - h * 0.2
        top = text.y + h * 0.8

        return left <= x <= right and bottom <= y <= top
    
    # Ενημερώνει αν το ποντίκι βρίσκεται πάνω στο Continue
    def on_mouse_motion(self, x, y, dx, dy):
        self.continue_selected = self.hit_text(self.continue_text, x, y)

    # Αν γίνει κλικ στο Continue και υπάρχει nickname, γίνεται επιβεβαίωση
    def on_mouse_press(self, x, y, button, modifiers):
        if self.continue_selected and self.nickname.strip():
            self.confirm_nickname()

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

        # Επιβεβαίωση nickname με Enter
        elif key == arcade.key.ENTER:
            self.confirm_nickname()

    # Επιβεβαιώνει το nickname και προχωρά στην επιλογή κλάσης
    def confirm_nickname(self):
        # Έλεγχος αν το nickname είναι κενό
        if not self.nickname.strip():
            self.error_text.text = "Nickname cannot be empty"
            self.error_timer = self.error_duration
            return
        
        # Έλεγχος αν το nickname υπάρχει ήδη στη βάση
        if nickname_exists(self.nickname):
            self.error_text.text = "Nickname already taken"
            self.error_timer = self.error_duration
            return

        # Δημιουργία μοναδικού player id
        self.player_id = str(uuid.uuid4())[:8]

        # Αποθήκευση player id και nickname στο window, ώστε να χρησιμοποιηθούν από τα επόμενα views και τον client
        self.window.player_id = self.player_id
        self.window.nickname = self.nickname

        print("New Player:")
        print("ID:", self.player_id)
        print("Nickname:", self.nickname)

        self.window.show_view(ClassSelectView())        # Μετάβαση στο view επιλογής κλάσης