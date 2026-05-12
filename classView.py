import arcade
import random
from db_game import create_player

# View επιλογής κλάσης χαρακτήρα
class ClassSelectView(arcade.View):
    def __init__(self):
        super().__init__()

        self.particles = []         # Λίστες με particles για το οπτικό εφέ κάθε κάρτας

        self.hover_index = None     # Δείκτης της κάρτας πάνω στην οποία βρίσκεται το ποντίκι

        # Background της οθόνης επιλογής κλάσης
        self.background_list = arcade.SpriteList()
        self.background = arcade.Sprite("assets/backgrounds/ruins_bg.png")
        self.background_list.append(self.background)

        # Διαθέσιμες κλάσεις και αντίστοιχες εικόνες
        self.classes = [
            {
                "name": "Warrior",
                "image": "assets/classes/sword_warrior.png"
            },
            {
                "name": "Mage",
                "image": "assets/classes/fire_mage.png"
            },
            {
                "name": "Marksman",
                "image": "assets/classes/bow_marksman.png"
            }
        ]

        # Χρώματα particle effect για κάθε κλάση
        self.class_particle_colors = {
            "Warrior": (180, 200, 255),
            "Mage": (255, 140, 90),
            "Marksman": (140, 255, 140)
        }

        self.card_list = arcade.SpriteList() # SpriteList που περιέχει τα sprites των καρτών/κλάσεων
        self.cards = []                      # Λίστα με τα sprites των κλάσεων

        self.labels = []                     # Λίστα με τα ονόματα των κλάσεων κάτω από τις κάρτες
        self.selected_index = None           # Δείκτης της κλάσης που επιλέχθηκε
    
    # Καλείται όταν εμφανίζεται το ClassSelectView
    def on_show_view(self):
        # Καθαρίζουμε παλιά δεδομένα, ώστε το view να εμφανίζεται σωστά κάθε φορά
        self.card_list.clear()
        self.cards.clear()
        self.labels.clear()
        self.selected_index = None
        self.hover_index = None
        self.particles.clear()

        # Κέντρο παραθύρου
        self.cx = self.window.width // 2
        self.cy = self.window.height // 2

        # Τοποθέτηση background στο κέντρο και προσαρμογή στο μέγεθος του παραθύρου
        self.background.center_x = self.cx
        self.background.center_y = self.cy
        self.background.scale = max(
            self.window.width / self.background.width,
            self.window.height / self.background.height
        )

        # Απόσταση μεταξύ των καρτών
        spacing = 260
        start_x = self.cx - spacing

        TARGET_HEIGHT = 220
        self.BASELINE_Y = self.cy - 20   # Κοινή βάση ώστε όλες οι εικόνες να "πατάνε" στο ίδιο ύψος
        self.CARD_WIDTH = 260
        self.CARD_HEIGHT = 320

        # Δημιουργία sprite και label για κάθε κλάση
        for i, cls in enumerate(self.classes):
            sprite = arcade.Sprite(cls["image"])

            # Κλιμάκωση εικόνας ώστε να έχει κοινό ύψος με τις υπόλοιπες
            scale = TARGET_HEIGHT / sprite.height
            
            # Ο Marksman μικραίνει λίγο παραπάνω για καλύτερη οπτική ισορροπία
            if cls["name"] == "Marksman":
                scale *= 0.75

            sprite.scale = scale

            # Τοποθέτηση κάρτας στον X άξονα
            sprite.center_x = start_x + i * spacing

            # Όλες οι κλάσεις έχουν κοινό κάτω σημείο
            sprite.bottom = self.BASELINE_Y   

            # Δημιουργία label με το όνομα της κλάσης
            label = arcade.Text(
                cls["name"],
                sprite.center_x,
                sprite.bottom - 30,
                arcade.color.WHITE,
                18,
                anchor_x="center"
            )
            self.labels.append(label)

            self.card_list.append(sprite)
            self.cards.append(sprite)

        # Δημιουργία particles για κάθε κάρτα
        for i in range(len(self.cards)):
            plist = []
            for _ in range(20):
                plist.append({
                    "x": random.uniform(0, self.CARD_WIDTH),
                    "y": random.uniform(0, self.CARD_HEIGHT),
                    "speed": random.uniform(20, 60),
                    "size": random.randint(3, 6),
                    "alpha": random.randint(40, 90)
                })
            self.particles.append(plist)
    
    # Ενημερώνει την κίνηση των particles
    def on_update(self, delta_time):
        for plist in self.particles:
            for p in plist:
                # Τα particles κινούνται προς τα πάνω
                p["y"] += p["speed"] * delta_time

                # Αν ένα particle φύγει πάνω από την κάρτα, επανέρχεται χαμηλά
                if p["y"] > self.CARD_HEIGHT:
                    p["y"] = 0
                    p["x"] = random.uniform(0, self.CARD_WIDTH)

    # Σχεδιάζει background, κάρτες, εφέ επιλογής και labels
    def on_draw(self):
        self.clear()

        # Σχεδίαση background και καρτών
        self.background_list.draw()
        self.card_list.draw()

        # Έλεγχος κάθε κάρτας για hover ή επιλογή
        for i, card in enumerate(self.cards):
            rect_left = card.center_x - self.CARD_WIDTH / 2
            rect_bottom = self.BASELINE_Y - 75

            # Αν η κάρτα είναι σε hover ή selected, εμφανίζεται particle effect και glow
            if self.hover_index == i or self.selected_index == i:
                plist = self.particles[i]
                r, g, b = self.class_particle_colors[self.classes[i]["name"]]

                # Σχεδίαση particles μέσα στην περιοχή της κάρτας
                for p in plist:
                    arcade.draw_lbwh_rectangle_filled(
                        rect_left + p["x"],
                        rect_bottom + p["y"],
                        p["size"],
                        p["size"],
                        (r, g, b, p["alpha"])
                    )
                    
                # Λευκό glow όταν ο χρήστης περνάει το ποντίκι πάνω από την κάρτα
                self.draw_glow(
                    rect_left,
                    rect_bottom,
                    self.CARD_WIDTH,
                    self.CARD_HEIGHT,
                    arcade.color.WHITE
                )

            # Αν η κάρτα έχει επιλεγεί, εμφανίζεται επιπλέον κίτρινο glow
            if self.selected_index == i:
                self.draw_glow(
                    rect_left,
                    rect_bottom,
                    self.CARD_WIDTH,
                    self.CARD_HEIGHT,
                    arcade.color.YELLOW
                )

        # Σχεδίαση των ονομάτων των κλάσεων
        for label in self.labels:
            label.draw()

    # Σχεδιάζει glow effect γύρω από μία κάρτα
    def draw_glow(self, x, y, w, h, color):
        for i in range(4):
            arcade.draw_lbwh_rectangle_outline(
                x - i,
                y - i,
                w + i * 2,
                h + i * 2,
                (*color[:3], 80 - i * 15),
                2
            )
    
    # Καλείται όταν ο χρήστης κάνει κλικ με το ποντίκι
    def on_mouse_press(self, x, y, button, modifiers):
        for i, card in enumerate(self.cards):
            # Αν το κλικ έγινε πάνω σε κάρτα κλάσης
            if card.collides_with_point((x, y)):
                self.selected_index = i

                # Αποθηκεύουμε την επιλεγμένη κλάση στο window
                self.window.class_name = self.classes[i]["name"]

                print("Class selected:", self.window.class_name)

                # Αν υπάρχουν ήδη player_id και nickname, αποθηκεύουμε τον παίκτη στη βάση
                if hasattr(self.window, "player_id") and hasattr(self.window, "nickname"):
                    create_player(
                        player_id=self.window.player_id,
                        nickname=self.window.nickname,
                        class_name=self.window.class_name
                    )

                # Ξεκινάμε το παιχνίδι μέσω της start_game του window
                start_game = getattr(self.window, "start_game", None)
                if callable(start_game):
                    start_game()

    # Καλείται όταν κινείται το ποντίκι
    def on_mouse_motion(self, x, y, dx, dy):
        self.hover_index = None

        # Ελέγχουμε αν το ποντίκι βρίσκεται πάνω σε κάποια κάρτα
        for i, card in enumerate(self.cards):
            if card.collides_with_point((x, y)):
                self.hover_index = i
                break