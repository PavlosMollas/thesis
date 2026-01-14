import arcade
import random

class ClassSelectView(arcade.View):
    def __init__(self):
        super().__init__()

        self.particles = []     # Εφέ όταν επιλέγεται κλάση

        self.hover_index = None

        # Background scale
        self.background_list = arcade.SpriteList()
        self.background = arcade.Sprite("assets/backgrounds/ruins_bg.png")
        self.background_list.append(self.background)

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

        self.class_particle_colors = {
            "Warrior": (180, 200, 255),
            "Mage": (255, 140, 90),
            "Marksman": (140, 255, 140)
        }

        self.card_list = arcade.SpriteList()
        self.cards = []

        self.labels = []
        self.selected_index = None
    
    def on_show_view(self):
        self.card_list.clear()
        self.cards.clear()
        self.labels.clear()
        self.selected_index = None
        self.hover_index = None
        self.particles.clear()

        self.cx = self.window.width // 2
        self.cy = self.window.height // 2

        self.background.center_x = self.cx
        self.background.center_y = self.cy
        self.background.scale = max(
            self.window.width / self.background.width,
            self.window.height / self.background.height
        )

        spacing = 260
        start_x = self.cx - spacing

        TARGET_HEIGHT = 220
        self.BASELINE_Y = self.cy - 20   # όλα "πατάνε" εδώ
        self.CARD_WIDTH = 260
        self.CARD_HEIGHT = 320

        for i, cls in enumerate(self.classes):
            sprite = arcade.Sprite(cls["image"])

            scale = TARGET_HEIGHT / sprite.height
            
            if cls["name"] == "Marksman":
                scale *= 0.75

            sprite.scale = scale

            sprite.center_x = start_x + i * spacing
            sprite.bottom = self.BASELINE_Y   # ΤΟ ΚΛΕΙΔΙ

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
    
    def on_update(self, delta_time):
        for plist in self.particles:
            for p in plist:
                p["y"] += p["speed"] * delta_time

                if p["y"] > self.CARD_HEIGHT:
                    p["y"] = 0
                    p["x"] = random.uniform(0, self.CARD_WIDTH)

    def on_draw(self):
        self.clear()
        self.background_list.draw()

        self.card_list.draw()

        for i, card in enumerate(self.cards):
            rect_left = card.center_x - self.CARD_WIDTH / 2
            rect_bottom = self.BASELINE_Y - 75

            if self.hover_index == i or self.selected_index == i:
                plist = self.particles[i]
                r, g, b = self.class_particle_colors[self.classes[i]["name"]]

                for p in plist:
                    arcade.draw_lbwh_rectangle_filled(
                        rect_left + p["x"],
                        rect_bottom + p["y"],
                        p["size"],
                        p["size"],
                        (r, g, b, p["alpha"])
                    )
                    
                self.draw_glow(
                    rect_left,
                    rect_bottom,
                    self.CARD_WIDTH,
                    self.CARD_HEIGHT,
                    arcade.color.WHITE
                )

            if self.selected_index == i:
                self.draw_glow(
                    rect_left,
                    rect_bottom,
                    self.CARD_WIDTH,
                    self.CARD_HEIGHT,
                    arcade.color.YELLOW
                )

        for label in self.labels:
            label.draw()

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
    
    def on_mouse_press(self, x, y, button, modifiers):
        for i, card in enumerate(self.cards):
            if card.collides_with_point((x, y)):
                self.selected_index = i
                self.window.class_name = self.classes[i]["name"]

                print("Class selected:", self.window.class_name)

                # game start
                start_game = getattr(self.window, "start_game", None)
                if callable(start_game):
                    start_game()

    def on_mouse_motion(self, x, y, dx, dy):
        self.hover_index = None
        for i, card in enumerate(self.cards):
            if card.collides_with_point((x, y)):
                self.hover_index = i
                break

    # def on_key_press(self, key, modifiers):
    #     if key == arcade.key.ENTER and self.selected_index is not None:
    #         from weaponSelectView import WeaponSelectView
    #         self.window.show_view(WeaponSelectView())