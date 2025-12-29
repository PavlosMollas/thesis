# Αρχείο για το αρχικό μενού με επιλογές "New player" (νέος παίκτης), "Returing player" (παίκτης που έχει ξανα παίξει)

import arcade   
import math     # Βιβλιοθήκη για pulse εφέ σε text

class MenuView(arcade.View):
    def __init__(self):
        super().__init__()

        self.options = ["New Game", "Returning Player"]
        self.selected = 0

        self.pulseTimer = 0.0           # Μεταβλητή για pulse timer

        self.hovered = None             # Μεταβλητή για επιλογή στο μενού με το ποντίκι (αρχικοποίηση)

        # Δημιουργία texts για το αρχικό μενού
        self.title_text = arcade.Text(
            "Welcome to Celestial Lands",   # Επικεφαλίδα 
            0, 0,
            arcade.color.WHITE,             # Χρώμα γραμματοσειράς
            font_size=36,                   # Μέγεθος γραμματοσειράς
            anchor_x="center",              # Στο κέντρο
        )

        # self.hint_text = arcade.Text(       # Hint text
        #     "Use ↑ / ↓ and ENTER",
        #     0, 0,
        #     arcade.color.LIGHT_GRAY,
        #     font_size=14,
        #     anchor_x="center",
        # )

        # Λίστα επιλογών μενού
        self.menu_texts = [
            arcade.Text("New Game", 0, 0, arcade.color.WHITE, 24, anchor_x="center"),
            arcade.Text("Returning Player", 0, 0, arcade.color.WHITE, 24, anchor_x="center"),
        ]

    # Μέθοδος για την εμφάνιση επικεφαλίδας και επιλογών για το μενού
    def on_show_view(self):
        arcade.set_background_color(arcade.color.BLACK)

        # Μεταβλητές για να πάρουμε το κέντρο του παραθύρου
        cx = self.window.width // 2
        cy = self.window.height // 2

        # Ο τίτλος μπαίνει ψηλά στο παράθυρο
        self.title_text.x = cx
        self.title_text.y = self.window.height - 150

        # # Οι οδηγίες μπαίνουν χαμηλά στο παράθυρο
        # self.hint_text.x = cx
        # self.hint_text.y = 90

        # Η πρώτη επιλογή του μενού είναι λίγο πάνω από το κέντρο του παραθύρου
        self.menu_texts[0].x = cx
        self.menu_texts[0].y = cy + 20

        # Η δεύτερη επιλογή του μενού είναι λίγο κάτω από το κέντρο του παραθύρου
        self.menu_texts[1].x = cx
        self.menu_texts[1].y = cy - 40

    # Μέθοδος 
    def on_mouse_motion(self, x, y, dx, dy):
        self.hovered = None     # clear της κατάστασης της μεταβλητής αρχικά

        for i, text in enumerate(self.menu_texts):  # Για κάθε επιλογή στη λίστα μενού παίρνουμε το index και την επιλογή
            if self._hit_text(text, x, y):          # Αν το ποντίκι είναι πάνω σε κείμενο που βρίσκεται στη λίστα
                self.hovered = i                    # Αποθήκευση του index της επιλογής του μενού στη μεταβλητή
                self.selected = i
                break

    def _hit_text(self, text: arcade.Text, mouse_x: float, mouse_y: float) -> bool:
        # Πλάτος/ύψος του κειμένου
        w = text.content_width
        h = text.content_height

        # Επειδή έχεις anchor_x="center", το x είναι το κέντρο
        left = text.x - w / 2
        right = text.x + w / 2

        # Για y: Arcade Text χρησιμοποιεί y σαν "baseline" περίπου,
        # οπότε για hitbox παίρνουμε ένα πρακτικό κουτί γύρω του:
        bottom = text.y - h * 0.2
        top = text.y + h * 0.8

        return left <= mouse_x <= right and bottom <= mouse_y <= top


    # 3) Mouse click επιλογή
    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        # Αν ο χρήστης κάνει κλικ σε μία επιλογή, την επιλέγουμε
        for i, text in enumerate(self.menu_texts):
            if self._hit_text(text, x, y):
                self.selected = i

                # Αν θες ΜΕ ΕΝΑ κλικ να κάνει και confirm, ξεσχόλιασε:
                self._confirm()
                return

    def on_update(self, delta_time: float):
        # Blink (alpha pulse) only on selected option
        self.pulseTimer += delta_time
        alpha = int(128 + 127 * math.sin(self.pulseTimer * 4.0))  # 0..255 pulse

        for i, text in enumerate(self.menu_texts):
            if i == self.selected:
                # Yellow with pulsing alpha
                text.color = (255, 255, 0, alpha)
            else:
                text.color = arcade.color.WHITE

    def on_draw(self):
        self.clear()
        self.title_text.draw()

        for text in self.menu_texts:
            text.draw()

        # self.hint_text.draw()

    def on_key_press(self, key, modifiers):
        if key == arcade.key.UP:
            self.selected = (self.selected - 1) % len(self.options)
            self.hovered = None

        elif key == arcade.key.DOWN:
            self.selected = (self.selected + 1) % len(self.options)
            self.hovered = None

        elif key == arcade.key.ENTER:
            self._confirm()

        elif key == arcade.key.ESCAPE:
            self.window.close()

    def _confirm(self):
        # Store selection on window so the rest of the client can read it later
        self.window.game_mode = "NEW_GAME" if self.selected == 0 else "RETURNING_PLAYER"

        # Move on (client.py defines window.start_game)
        start_game = getattr(self.window, "start_game", None)
        if callable(start_game):
            start_game()
        else:
            # Safety fallback if start_game wasn't attached
            print("[StartView] window.start_game() not found. Did you attach it in main()?")
            arcade.exit()
