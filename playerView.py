import arcade
import uuid
import sqlite3
from classView import ClassSelectView

def nickname_exists(nickname: str) -> bool:
    conn = sqlite3.connect("MMORPG_DB.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM Player WHERE Nickname = ? LIMIT 1;",
        (nickname,)
    )
    exists = cur.fetchone() is not None
    conn.close()
    return exists

class CreatePlayerView(arcade.View):
    def __init__(self):
        super().__init__()

        self.error_timer = 0.0
        self.error_duration = 2.0

        self.error_text = arcade.Text(
            "",
            0, 0,
            arcade.color.RED,
            14,
            anchor_x="center"
        )

        self.continue_text = arcade.Text(
            "Continue",
            0, 0,
            arcade.color.WHITE,
            22,
            anchor_x="center"
        )

        self.continue_selected = False

        self.nickname = ""
        self.player_id = None

        self.caret_timer = 0.0
        self.caret_visible = True

        self.title = arcade.Text(
            "Create Your Character",
            0, 0,
            arcade.color.WHITE,
            36,
            anchor_x="center"
        )

        self.label = arcade.Text(
            "Enter Nickname:",
            0, 0,
            arcade.color.WHITE,
            20,
            anchor_x="center"
        )

        self.input_text = arcade.Text(
            "",
            0, 0,
            arcade.color.WHITE,
            24,
            anchor_x="center"
        )

        self.hint = arcade.Text(
            "Press ENTER to continue",
            0, 0,
            arcade.color.LIGHT_GRAY,
            14,
            anchor_x="center"
        )

    def on_show_view(self):
        self.background_list = arcade.SpriteList()
        self.nickname_background = arcade.Sprite("assets/backgrounds/hills&trees.png")
        self.background_list.append(self.nickname_background)

        self.nickname_background.center_x = self.window.width // 2
        self.nickname_background.center_y = self.window.height // 2

        self.nickname_background.width = self.window.width
        self.nickname_background.height = self.window.height

        cx = self.window.width // 2
        cy = self.window.height // 2

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

        self.nickname = ""
        self.player_id = None
        
        self.continue_text.x = self.window.width // 2
        self.continue_text.y = (self.window.height // 2) - 100

    def on_draw(self):
        self.clear()
        self.background_list.draw()

        self.title.draw()
        self.label.draw()

        caret = "|" if self.caret_visible else ""
        self.input_text.text = self.nickname + caret
        self.input_text.draw()

        self.error_text.draw()
        self.hint.draw()
        self.continue_text.draw()


    def on_update(self, delta_time: float):
        self.caret_timer += delta_time
        if self.caret_timer > 0.4:
            self.caret_timer = 0
            self.caret_visible = not self.caret_visible

        if self.continue_selected and self.nickname.strip():
            self.continue_text.color = arcade.color.YELLOW
        else:
            self.continue_text.color = arcade.color.WHITE

        if self.error_timer > 0:
            self.error_timer -= delta_time
            if self.error_timer <= 0:
                self.error_text.text = ""

    def hit_text(self, text: arcade.Text, x, y) -> bool:
        w = text.content_width
        h = text.content_height

        left = text.x - w / 2
        right = text.x + w / 2
        bottom = text.y - h * 0.2
        top = text.y + h * 0.8

        return left <= x <= right and bottom <= y <= top
    
    def on_mouse_motion(self, x, y, dx, dy):
        self.continue_selected = self.hit_text(self.continue_text, x, y)

    def on_mouse_press(self, x, y, button, modifiers):
        if self.continue_selected and self.nickname.strip():
            self.confirm_nickname()

    def on_text(self, text: str):
        if len(self.nickname) >= 12:
            return

        if text.isalnum() or text == "_":
            self.nickname += text

    def on_key_press(self, key, modifiers):
        if key == arcade.key.BACKSPACE:
            self.nickname = self.nickname[:-1]

        elif key == arcade.key.ENTER:
            self.confirm_nickname()

    def confirm_nickname(self):
        if not self.nickname.strip():
            self.error_text.text = "Nickname cannot be empty"
            self.error_timer = self.error_duration
            return
        
        if nickname_exists(self.nickname):
            self.error_text.text = "Nickname already taken"
            self.error_timer = self.error_duration
            return

        self.player_id = str(uuid.uuid4())[:8]

        self.window.player_id = self.player_id
        self.window.nickname = self.nickname

        print("New Player:")
        print("ID:", self.player_id)
        print("Nickname:", self.nickname)

        self.window.show_view(ClassSelectView())

        # Πήγαινε στο επόμενο βήμα
        # self.window.show_view(ClassSelectView())