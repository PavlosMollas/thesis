import arcade

class Region:
    def __init__(self, name: str, tmx_path: str, tile_scaling: float = 1.0):
        self.name = name
        self.tmx_path = tmx_path
        self.tile_scaling = tile_scaling

        # Φόρτωση tilemap
        self.tile_map = arcade.load_tilemap(
            tmx_path,
            scaling=tile_scaling,
            use_spatial_hash=True   # Το collision γίνεται μόνο με κοντινά αντικείμενα (βελτίωση απόδοσης)
        )

        # Layers που χρειάζονται για collision / movement
        self.wall_list = self.tile_map.sprite_lists.get("Walls", arcade.SpriteList())
        self.river_list = self.tile_map.sprite_lists.get("River", arcade.SpriteList())
        self.lava_list = self.tile_map.sprite_lists.get("Lava")
        self.bridge_wall_list = self.tile_map.sprite_lists.get("Bridge_wall", arcade.SpriteList())
        self.bridge_list = self.tile_map.sprite_lists.get("Bridge")

        # Διαστάσεις map σε pixels
        self.map_width = self.tile_map.width * self.tile_map.tile_width
        self.map_height = self.tile_map.height * self.tile_map.tile_height

        # Spawn / transition data
        self.spawn_points = []
        self.named_spawns = {}
        self.enemy_spawns = []
        self.transitions = []

        self.load_objects()

    def load_objects(self):
        object_layer = self.tile_map.object_lists.get("Object")
        if not object_layer:
            raise RuntimeError(f"No Object layer found in TMX map: {self.name}")

        enemy_spawn_counter = 0

        for obj in object_layer:
            props = obj.properties or {}

            # 1. Default player spawn
            if obj.name == "player_spawn":
                x, y = obj.shape
                self.spawn_points.append((x, y))
                continue

            # 2. Transition rectangle
            if obj.name == "transition":
                target_map = props.get("target_map")
                target_spawn = props.get("target_spawn")

                if not target_map or not target_spawn:
                    raise RuntimeError(
                        f"Transition in map '{self.name}' is missing target_map or target_spawn"
                    )
                
                points = obj.shape
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]

                left = min(xs)
                right = max(xs)
                bottom = min(ys)
                top = max(ys)

                self.transitions.append({
                    "x": left,
                    "y": bottom,
                    "width": right - left,
                    "height": top - bottom,
                    "target_map": target_map,
                    "target_spawn": target_spawn,
                })
                continue

            # 3. Enemy spawn (object με custom property enemy_type)
            enemy_type = props.get("enemy_type")
            if enemy_type:
                x, y = obj.shape
                enemy_id = f"{self.name}_enemy_{enemy_spawn_counter}"
                enemy_spawn_counter += 1
                self.enemy_spawns.append((enemy_id, enemy_type, x, y))
                continue

            # 4. Named spawn points (πχ from_first_region)
            # Οτιδήποτε έχει όνομα και ΔΕΝ είναι player_spawn/transition/enemy spawn
            if obj.name:
                x, y = obj.shape
                self.named_spawns[obj.name] = (x, y)

        if not self.spawn_points and not self.named_spawns:
            raise RuntimeError(
                f"No spawn objects found in map: {self.name}. "
                f"Expected at least one 'player_spawn' or named spawn object."
            )
    def get_default_spawn(self):
        if self.spawn_points:
            return self.spawn_points[0]
        return None

    def get_named_spawn(self, spawn_name: str):
        return self.named_spawns.get(spawn_name)

    def debug_print(self):
        print(f"Region: {self.name}")
        print(f"  TMX: {self.tmx_path}")
        print(f"  Size: {self.map_width} x {self.map_height}")
        print(f"  Player spawns: {self.spawn_points}")
        print(f"  Named spawns: {self.named_spawns}")
        print(f"  Enemy spawns: {self.enemy_spawns}")
        print(f"  Transitions: {self.transitions}")
    