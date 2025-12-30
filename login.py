# Αρχείο για το αρχικό μενού με επιλογές "New player" (νέος παίκτης), "Returing player" (παίκτης που έχει ξανα παίξει)

import arcade   
import math     # Βιβλιοθήκη για pulse εφέ σε κείμενο

class MenuView(arcade.View):
    def __init__(self):
        super().__init__()

        self.options = ["New Game", "Returning Player"] # Λίστα με επιλογές για τα κουμπιά
        self.selected = 0               # Μεταβλητή για επιλογή text

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

    # Μέθοδος για την κίνηση του mouse
    def on_mouse_motion(self, x, y, dx, dy):
        self.hovered = None     # clear της κατάστασης της μεταβλητής αρχικά

        for i, text in enumerate(self.menu_texts):  # Για κάθε επιλογή στη λίστα μενού παίρνουμε το index και την επιλογή
            if self.hit_text(text, x, y):           # Αν το ποντίκι είναι πάνω σε κείμενο που βρίσκεται στη λίστα
                self.hovered = i                    # Αποθήκευση του index της επιλογής του μενού στη μεταβλητή
                self.selected = i
                break

    # Μέθοδος για έλεγχο hitbox του mouse στα text της λίστας
    def hit_text(self, text: arcade.Text, mouse_x: float, mouse_y: float) -> bool:
        w = text.content_width  # Πλάτος του κειμένου
        h = text.content_height # Ύψος του κειμένου

        # Υπολογισμός ορίων δεξιά, αριστερά
        left = text.x - w / 2
        right = text.x + w / 2

        # Υπολογισμός ορίων πάνω, κάτω
        bottom = text.y - h * 0.2
        top = text.y + h * 0.8          

        # Επιστρέφει αν το ποντίκι είναι μέσα στα παραπάνω όρια
        return left <= mouse_x <= right and bottom <= mouse_y <= top


    # Μέθοδος για mouse click επιλογή
    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        for i, text in enumerate(self.menu_texts):      # Αν ο χρήστης κάνει κλικ σε μία επιλογή της λίστας του μενού
            if self.hit_text(text, x, y):
                self.selected = i                       # αυτή επιλέγεται

                self.confirm()                          # Προχωράει στην επόμενη ενέργεια
                return

    # Μέθοδος για εφέ σε κείμενο
    def on_update(self, delta_time: float):
        self.pulseTimer += delta_time
        
        title_alpha = int(128 + 127 * math.sin(self.pulseTimer * 1.0))  # Εφέ παλμού
        self.title_text.color = (100, 150, 255, title_alpha)  # Μπλε χρώμα παλμού για την επικεφαλίδα

        alpha = int(128 + 127 * math.sin(self.pulseTimer * 4.0))  # Εφέ παλμού

        for i, text in enumerate(self.menu_texts):      # Για κάθε επιλογή στη λίστα μενού
            if i == self.selected:                      # Αν το στοιχείο είναι επιλεγμένο
                text.color = (255, 255, 0, alpha)       # Αναβοσβήνει σε κίτρινο χρώμα
            else:
                text.color = arcade.color.WHITE         # Αλλιώς μένει άσπρο 

    # Μέθοδος για την εμφάνιση των αντικειμένων της κλάσης
    def on_draw(self):
        self.clear()                # Καθαρίζει το παράθυρο από το προηγούμενο frame και ορίζει το background
        self.title_text.draw()      # Εμφάνιση τίτλου 

        for text in self.menu_texts:    # Για κάθε επιλογή που υπάρχει στη λίστα μενού
            text.draw()                 # Ζωγραφίζει το αντίστοιχο κείμενο στην οθόνη

        # self.hint_text.draw()

    # Μέθοδος για λειτουργία πλήκτρων
    def on_key_press(self, key, modifiers):
        if key == arcade.key.UP:    # Αν πατηθεί το πάνω βελάκι, μετακινούμαστε στην προηγούμενη επιλογή κυκλικά
            self.selected = (self.selected - 1) % len(self.options)
            self.hovered = None     # Γίνεται clear το hover του mouse

        elif key == arcade.key.DOWN:    # Αν πατηθεί το κάτω βελάκι, μετακινούμαστε στην επόμενη επιλογή κυκλικά
            self.selected = (self.selected + 1) % len(self.options)
            self.hovered = None     # Γίνεται clear το hover του mouse

        elif key == arcade.key.ENTER:   # Με enter πάμε στο επόμενο action
            self.confirm()

        elif key == arcade.key.ESCAPE:  # Με escape κλείνει το παράθυρο
            self.window.close()

    # Επιβεβαίωση της επιλογής και εκτέλεση του επόμενου action
    def confirm(self):
        # Αποθηκεύει την επιλογή στο παράθυρο ώστε να είναι διαθέσιμη και στα επόμενα Views
        self.window.game_mode = "NEW_GAME" if self.selected == 0 else "RETURNING_PLAYER"

        # Προσπαθεί να βρει στο window μια μέθοδο start_game (αν δεν υπάρχει, παίρνει None)
        start_game = getattr(self.window, "start_game", None)

        # Αν υπάρχει και είναι callable, ξεκινά το παιχνίδι
        if callable(start_game):
            start_game()
        else:
            # Αν δεν υπάρχει το start_game τερματίζει το πρόγραμμα
            arcade.exit()
