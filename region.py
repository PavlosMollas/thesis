import arcade

class Region:
    def __init__(self, name: str, tmx_path: str, tile_scaling: float = 1.0):
        self.name = name                    # Όνομα της περιοχής
        self.tmx_path = tmx_path            # Διαδρομή του TMX αρχείου που αντιστοιχεί στη συγκεκριμένη περιοχή
        self.tile_scaling = tile_scaling    # Κλίμακα με την οποία φορτώνεται το tilemap

        # Φόρτωση του tilemap από το Tiled
        self.tile_map = arcade.load_tilemap(
            tmx_path,
            scaling=tile_scaling,
            use_spatial_hash=True   # Χρήση spatial hash για πιο αποδοτικό collision detection
        )

        # Layers που χρησιμοποιούνται για collision ή ειδική κίνηση
        self.wall_list = self.tile_map.sprite_lists.get("Walls", arcade.SpriteList())
        self.river_list = self.tile_map.sprite_lists.get("River", arcade.SpriteList())
        self.lava_list = self.tile_map.sprite_lists.get("Lava")
        self.bridge_wall_list = self.tile_map.sprite_lists.get("Bridge_wall", arcade.SpriteList())
        self.bridge_list = self.tile_map.sprite_lists.get("Bridge")

        # Υπολογισμός διαστάσεων του χάρτη σε pixels
        self.map_width = self.tile_map.width * self.tile_map.tile_width
        self.map_height = self.tile_map.height * self.tile_map.tile_height

        self.spawn_points = []      # Λίστα με default spawn points παικτών
        self.named_spawns = {}      # Dictionary με named spawn points
        self.enemy_spawns = []      # Λίστα με enemy spawns που διαβάζονται από το object layer
        self.transitions = []       # Λίστα με transition rectangles για αλλαγή περιοχής

        self.load_objects()         # Φόρτωση των objects από το Object layer του TMX

    # Μέθοδος που διαβάζει τα objects από το Object layer του Tiled και τα μετατρέπει σε spawn points, enemy spawns και transitions
    def load_objects(self):
        object_layer = self.tile_map.object_lists.get("Object")

        # Αν δεν υπάρχει Object layer, δεν μπορούμε να φορτώσουμε spawns/transitions
        if not object_layer:
            raise RuntimeError(f"No Object layer found in TMX map: {self.name}")

        enemy_spawn_counter = 0

        # Διατρέχουμε όλα τα objects που υπάρχουν στο Object layer
        for obj in object_layer:
            props = obj.properties or {}

             # Default spawn παίκτη
            if obj.name == "player_spawn":
                x, y = obj.shape
                self.spawn_points.append((x, y))
                continue

            # Transition object
            # Είναι ορθογώνια περιοχή που όταν την ακουμπήσει ο παίκτης, μεταφέρεται σε άλλη περιοχή
            if obj.name == "transition":
                target_map = props.get("target_map")
                target_spawn = props.get("target_spawn")

                # Κάθε transition πρέπει να έχει target_map και target_spawn
                if not target_map or not target_spawn:
                    raise RuntimeError(
                        f"Transition in map '{self.name}' is missing target_map or target_spawn"
                    )
                
                # Το obj.shape περιέχει τα σημεία του rectangle από το Tiled
                points = obj.shape
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]

                # Υπολογίζουμε τα όρια του rectangle
                left = min(xs)
                right = max(xs)
                bottom = min(ys)
                top = max(ys)

                # Αποθηκεύουμε το transition με θέση, μέγεθος και προορισμό
                self.transitions.append({
                    "x": left,
                    "y": bottom,
                    "width": right - left,
                    "height": top - bottom,
                    "target_map": target_map,
                    "target_spawn": target_spawn,
                })
                continue

            # Enemy spawn
            # Αν ένα object έχει custom property enemy_type, τότε θεωρείται σημείο δημιουργίας εχθρού
            enemy_type = props.get("enemy_type")
            if enemy_type:
                x, y = obj.shape

                # Δημιουργούμε μοναδικό id για τον enemy μέσα στη συγκεκριμένη περιοχή
                enemy_id = f"{self.name}_enemy_{enemy_spawn_counter}"
                enemy_spawn_counter += 1

                # Αποθηκεύουμε id, τύπο enemy και θέση spawn
                self.enemy_spawns.append((enemy_id, enemy_type, x, y))
                continue

            # Named spawn point
            # Χρησιμοποιείται από transitions, ώστε ο παίκτης να εμφανίζεται σε συγκεκριμένο σημείο όταν έρχεται από άλλη περιοχή
            if obj.name:
                x, y = obj.shape
                self.named_spawns[obj.name] = (x, y)

        # Αν δεν υπάρχει κανένα spawn point, ο χάρτης δεν μπορεί να χρησιμοποιηθεί σωστά
        if not self.spawn_points and not self.named_spawns:
            raise RuntimeError(
                f"No spawn objects found in map: {self.name}. "
                f"Expected at least one 'player_spawn' or named spawn object."
            )
        
    # Μέθοδος που επιστρέφει το πρώτο διαθέσιμο default spawn point
    def get_default_spawn(self):
        if self.spawn_points:
            return self.spawn_points[0]
        return None

    # Μέθοδος που επιστρέφει named spawn με βάση το όνομά του
    # Χρησιμοποιείται όταν ο παίκτης μεταφέρεται από άλλο region μέσω transition
    def get_named_spawn(self, spawn_name: str):
        return self.named_spawns.get(spawn_name)

    # Debug μέθοδος για εκτύπωση των βασικών δεδομένων της περιοχής
    def debug_print(self):
        print(f"Region: {self.name}")
        print(f"  TMX: {self.tmx_path}")
        print(f"  Size: {self.map_width} x {self.map_height}")
        print(f"  Player spawns: {self.spawn_points}")
        print(f"  Named spawns: {self.named_spawns}")
        print(f"  Enemy spawns: {self.enemy_spawns}")
        print(f"  Transitions: {self.transitions}")