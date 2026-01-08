# Αρχείο για το αρχικό μενού με επιλογές "New player" (νέος παίκτης), "Returing player" (παίκτης που έχει ξανα παίξει)

import arcade   
import math     # Βιβλιοθήκη για pulse εφέ σε κείμενο

class MenuView(arcade.View):
    def __init__(self):
        super().__init__()

        self.ui_sprites = arcade.SpriteList()   # Λίστα για Sprites

        # Sound toggle
        self.sound_enabled = True

        self.sound_on_icon = arcade.Sprite(     # Sprite sound on
            "assets/soundOn.png",
            scale=0.15
        )
        self.sound_off_icon = arcade.Sprite(    # Sprite sound off
            "assets/soundOff.png",
            scale=0.2
        )

        self.sound_button = self.sound_on_icon  # Κουμπί για τον ήχο (on/off)

        self.ui_sprites.append(self.sound_on_icon)  # Προσθήκη Sprites στη λίστα
        self.ui_sprites.append(self.sound_off_icon)

        self.hover_sound = arcade.load_sound(   # Ήχος για mouse hover
            "assets/sounds/glitch_004.ogg"
        )

        self.menu_music_player = None           # Reference για το music player

        self.menu_music = arcade.load_sound(    # Μουσική μενού
            "assets/music/main_menu_music.wav"
        )

        self.options = ["New Game", "Returning Player"] # Λίστα με επιλογές για τα κουμπιά
        self.selected = 0               # Μεταβλητή για επιλογή text

        self.pulseTimer = 0.0           # Μεταβλητή για pulse timer

        self.hovered = None             # Μεταβλητή για επιλογή στο μενού με το ποντίκι (αρχικοποίηση)

        self.last_selected = self.selected  # Μεταβλητή για ήχο επιλογής

        # Δημιουργία texts για το αρχικό μενού
        self.title_text = arcade.Text(
            "Welcome to Celestial Lands",   # Επικεφαλίδα 
            0, 0,
            arcade.color.WHITE,             # Χρώμα γραμματοσειράς
            font_size=36,                   # Μέγεθος γραμματοσειράς
            anchor_x="center",              # Στο κέντρο
        )

        # Λίστα επιλογών μενού
        self.menu_texts = [
            arcade.Text("New Game", 0, 0, arcade.color.WHITE, 24, anchor_x="center"),
            arcade.Text("Returning Player", 0, 0, arcade.color.WHITE, 24, anchor_x="center"),
        ]

    # Μέθοδος για την εμφάνιση επικεφαλίδας και επιλογών για το μενού
    def on_show_view(self):
        self.sound_on_icon.visible = True       # Στην εκκίνση φαίνεται το sound on Sprite
        self.sound_off_icon.visible = False

        self.background_list = arcade.SpriteList()
        self.background = arcade.Sprite("assets/backgrounds/Battleground1.png")
        self.background_list.append(self.background)

        self.background.center_x = self.window.width // 2
        self.background.center_y = self.window.height // 2

        self.background.width = self.window.width
        self.background.height = self.window.height

        # Αν παίζει ήδη, σταμάτα το
        if self.menu_music_player:
            arcade.stop_sound(self.menu_music_player)

        # Παίζει η μουσική και κρατάμε τον music player σε μεταβλητή
        self.menu_music_player = arcade.play_sound(
            self.menu_music,
            volume=0.2,
        )

        self.menu_music_player.loop = True  # Η μουσική συνεχίζει από την αρχή όταν τελειώσει το κομμάτι

        # Μεταβλητές για να πάρουμε το κέντρο του παραθύρου
        cx = self.window.width // 2
        cy = self.window.height // 2

        # Ο τίτλος μπαίνει ψηλά στο παράθυρο
        self.title_text.x = cx
        self.title_text.y = self.window.height - 150

        # Η πρώτη επιλογή του μενού είναι λίγο πάνω από το κέντρο του παραθύρου
        self.menu_texts[0].x = cx
        self.menu_texts[0].y = cy + 20

        # Η δεύτερη επιλογή του μενού είναι λίγο κάτω από το κέντρο του παραθύρου
        self.menu_texts[1].x = cx
        self.menu_texts[1].y = cy - 40

        # Το sprite ήχου είναι κάτω δεξιά στην οθόνη
        margin = 30
        self.sound_on_icon.center_x = self.window.width - margin
        self.sound_on_icon.center_y = margin

        self.sound_off_icon.center_x = self.window.width - margin
        self.sound_off_icon.center_y = margin

    # Μέθοδος για την κίνηση του mouse
    def on_mouse_motion(self, x, y, dx, dy):
        self.hovered = None
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
        # sound button click
        if self.sound_button.collides_with_point((x, y)):   # Έλεγχος για το hitbox του sound sprite
            self.toggle_sound()                             # Αλλάζει η κατάσταση του ήχου από on σε off και το αντίστροφο
            return

        for i, text in enumerate(self.menu_texts):      # Αν ο χρήστης κάνει κλικ σε μία επιλογή της λίστας του μενού
            if self.hit_text(text, x, y):
                self.selected = i                       # αυτή επιλέγεται
                self.confirm()                          # Προχωράει στην επόμενη ενέργεια
                return

    # Μέθοδος για εφέ σε κείμενο
    def on_update(self, delta_time: float):
        self.pulseTimer += delta_time

        # Όταν επιλέγεται text από το menu παίζεται ήχος
        if self.selected != self.last_selected:
            if self.sound_enabled:
                arcade.play_sound(self.hover_sound, volume=0.4)
            self.last_selected = self.selected
        
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
        self.background_list.draw()
        self.title_text.draw()      # Εμφάνιση τίτλου 

        for text in self.menu_texts:    # Για κάθε επιλογή που υπάρχει στη λίστα μενού
            text.draw()                 # Ζωγραφίζει το αντίστοιχο κείμενο στην οθόνη

        self.ui_sprites.draw()          # Ζωγραφίζει τα sound sprites

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

    # Μέθοδος για την αλλαγή κατάστασης του ήχου
    def toggle_sound(self):
        self.sound_enabled = not self.sound_enabled

        self.sound_on_icon.visible = self.sound_enabled
        self.sound_off_icon.visible = not self.sound_enabled

        if self.menu_music_player:
            self.menu_music_player.volume = 0.2 if self.sound_enabled else 0.0

    # Επιβεβαίωση της επιλογής και εκτέλεση του επόμενου action
    def confirm(self):
        # Αποθηκεύει την επιλογή στο παράθυρο ώστε να είναι διαθέσιμη και στα επόμενα Views
        self.window.game_mode = "NEW_GAME" if self.selected == 0 else "RETURNING_PLAYER"

        # Προσπαθεί να βρει στο window μια μέθοδο start_game (αν δεν υπάρχει, παίρνει None)
        start_game = getattr(self.window, "start_game", None)

        if self.menu_music_player:
            arcade.stop_sound(self.menu_music_player)
            self.menu_music_player = None

        # Αν υπάρχει και είναι callable, ξεκινά το παιχνίδι
        if callable(start_game):
            start_game()
        else:
            # Αν δεν υπάρχει το start_game τερματίζει το πρόγραμμα
            arcade.exit()
