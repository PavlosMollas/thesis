import sqlite3
from datetime import datetime

DB_PATH = "MMORPG_DB.db"        # Path της βάσης δεδομένων SQLite

# Μέθοδος που δημιουργεί και επιστρέφει σύνδεση με τη βάση δεδομένων
def db_conn():
    conn = sqlite3.connect(DB_PATH)

    # Ενεργοποιούμε τα foreign keys της SQLite, ώστε να εφαρμόζονται οι σχέσεις μεταξύ πινάκων
    conn.execute("PRAGMA foreign_keys = ON;")

    return conn

# Μέθοδος που εξασφαλίζει ότι οι βασικές κλάσεις υπάρχουν στον πίνακα Class
def ensure_classes_exist():
    conn = db_conn()
    cur = conn.cursor()

    # Εισάγουμε τις διαθέσιμες κλάσεις μόνο αν δεν υπάρχουν ήδη
    for name in ("Warrior", "Mage", "Marksman"):
        cur.execute("INSERT OR IGNORE INTO Class(Class_name) VALUES (?);", (name,))

    conn.commit()
    conn.close()

# Μέθοδος που εξασφαλίζει ότι τα βασικά items υπάρχουν στον πίνακα Item
def ensure_items_exist():
    conn = db_conn()
    cur = conn.cursor()

    # Τα potions είναι stackable, ενώ τα elixirs κρατιούνται ένα-ένα
    items = [
        # Item_name, Price, Category, Stackable, Max_stack
        ("Health_Potion", 50, "Potion", 1, 2),
        ("Energy_Potion", 50, "Potion", 1, 2),

        ("ElixirOfToughness", 200, "Elixir", 0, 1),
        ("ElixirOfMagic", 200, "Elixir", 0, 1),
        ("ElixirOfPower", 200, "Elixir", 0, 1),
    ]

    cur.executemany("""
        INSERT OR IGNORE INTO Item(Item_name, Price, Category, Stackable, Max_stack)
        VALUES (?, ?, ?, ?, ?);
    """, items)

    conn.commit()
    conn.close()

# Μέθοδος που προσθέτει gold σε έναν παίκτη
def add_gold_to_player(player_id: str, amount: int):
    conn = db_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE Player
        SET Gold = Gold + ?
        WHERE Player_id = ?;
    """, (amount, player_id))

    conn.commit()
    conn.close()

# Επιστρέφει το διαθέσιμο gold του παίκτη
def get_player_gold(player_id: str):
    conn = db_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT Gold
        FROM Player
        WHERE Player_id = ?;
    """, (player_id,))

    row = cur.fetchone()
    conn.close()

    # Αν δεν βρεθεί ο παίκτης, επιστρέφεται 0 ως fallback
    if row is None:
        return 0

    return row[0]

# Μέθοδος που προσθέτει item στο inventory του παίκτη, χωρίς να ξεπερνά το Max_stack
def add_item_to_player(player_id: str, item_name: str, quantity: int = 1):
    conn = db_conn()
    cur = conn.cursor()

    # Παίρνουμε το μέγιστο επιτρεπτό stack του item από τον πίνακα Item
    cur.execute("""
        SELECT Max_stack
        FROM Item
        WHERE Item_name = ?;
    """, (item_name,))

    row = cur.fetchone()

    # Αν το item δεν υπάρχει στη βάση, σταματάμε με error
    if row is None:
        conn.close()
        raise ValueError(f"Item does not exist: {item_name}")

    max_stack = row[0]

    # Ελέγχουμε αν ο παίκτης έχει ήδη το item
    cur.execute("""
        SELECT Quantity
        FROM Item_Inventory
        WHERE Player_id = ? AND Item_name = ?;
    """, (player_id, item_name))

    inv_row = cur.fetchone()

    # Αν ο παίκτης δεν έχει ήδη το item, δημιουργείται νέα εγγραφή στο inventory
    if inv_row is None:
        new_quantity = min(quantity, max_stack)

        cur.execute("""
            INSERT INTO Item_Inventory(Player_id, Item_name, Quantity)
            VALUES (?, ?, ?);
        """, (player_id, item_name, new_quantity))

    # Αν υπάρχει ήδη, αυξάνεται η ποσότητα μέχρι το όριο του max stack
    else:
        current_quantity = inv_row[0]
        new_quantity = min(current_quantity + quantity, max_stack)

        cur.execute("""
            UPDATE Item_Inventory
            SET Quantity = ?
            WHERE Player_id = ? AND Item_name = ?;
        """, (new_quantity, player_id, item_name))

    conn.commit()
    conn.close()

# Μέθοδος που επιστρέφει όλα τα items που έχει ο παίκτης
def get_player_inventory(player_id: str):
    conn = db_conn()
    cur = conn.cursor()

    # Γίνεται JOIN ώστε να επιστραφούν και πληροφορίες όπως τιμή, κατηγορία και max stack
    cur.execute("""
        SELECT 
            ii.Item_name,
            ii.Quantity,
            i.Price,
            i.Category,
            i.Stackable,
            i.Max_stack
        FROM Item_Inventory ii
        JOIN Item i ON ii.Item_name = i.Item_name
        WHERE ii.Player_id = ?;
    """, (player_id,))

    rows = cur.fetchall()
    conn.close()

    return rows

# Μέθοδος που εκτελεί αγορά item για έναν παίκτη, ελέγχοντας gold και διαθέσιμο χώρο στο stack
def buy_item_for_player(player_id: str, item_name: str, quantity: int = 1):
    # Δεν επιτρέπεται αγορά μηδενικής ή αρνητικής ποσότητας
    if quantity <= 0:
        return False, "Invalid quantity"

    conn = db_conn()
    cur = conn.cursor()

    try:
        # Παίρνουμε gold παίκτη
        cur.execute("""
            SELECT Gold
            FROM Player
            WHERE Player_id = ?;
        """, (player_id,))

        player_row = cur.fetchone()

        # Αν δεν υπάρχει ο παίκτης, η αγορά αποτυγχάνει
        if player_row is None:
            return False, "Player not found"

        player_gold = player_row[0]

        # Παίρνουμε τιμή και στοιχεία stack του item
        cur.execute("""
            SELECT Price, Stackable, Max_stack
            FROM Item
            WHERE Item_name = ?;
        """, (item_name,))

        item_row = cur.fetchone()

        if item_row is None:
            return False, "Item not found"

        price, stackable, max_stack = item_row

        # Υπολογίζεται το συνολικό κόστος αγοράς
        total_cost = price * quantity

        # Έλεγχος αν έχει αρκετό gold
        if player_gold < total_cost:
            return False, "Not enough gold"

        # Έλεγχος υπάρχουσας ποσότητας στο inventory
        cur.execute("""
            SELECT Quantity
            FROM Item_Inventory
            WHERE Player_id = ? AND Item_name = ?;
        """, (player_id, item_name))

        inv_row = cur.fetchone()

        if inv_row is None:
            current_quantity = 0
        else:
            current_quantity = inv_row[0]

        # Αν η νέα ποσότητα ξεπερνά το max stack, η αγορά απορρίπτεται
        if current_quantity + quantity > max_stack:
            return False, "Item stack is full"

        # Αφαιρείται το gold από τον παίκτη
        cur.execute("""
            UPDATE Player
            SET Gold = Gold - ?
            WHERE Player_id = ?;
        """, (total_cost, player_id))

        # Αν το item δεν υπάρχει στο inventory, δημιουργείται νέα εγγραφή
        if inv_row is None:
            cur.execute("""
                INSERT INTO Item_Inventory(Player_id, Item_name, Quantity)
                VALUES (?, ?, ?);
            """, (player_id, item_name, quantity))

        # Αν υπάρχει ήδη, αυξάνεται η ποσότητα
        else:
            cur.execute("""
                UPDATE Item_Inventory
                SET Quantity = Quantity + ?
                WHERE Player_id = ? AND Item_name = ?;
            """, (quantity, player_id, item_name))

        conn.commit()
        return True, "Purchase successful"

    # Σε οποιοδήποτε σφάλμα γίνεται rollback για να μη μείνει η βάση σε λάθος κατάσταση
    except Exception as ex:
        conn.rollback()
        return False, str(ex)

    finally:
        conn.close()

# Μέθοδος που αφαιρεί ένα item από το inventory του παίκτη, όταν το χρησιμοποιεί
def consume_item_for_player(player_id: str, item_name: str):
    conn = db_conn()
    cur = conn.cursor()

    try:
        # Ελέγχουμε αν ο παίκτης έχει το item
        cur.execute("""
            SELECT Quantity
            FROM Item_Inventory
            WHERE Player_id = ? AND Item_name = ?;
        """, (player_id, item_name))

        row = cur.fetchone()

        # Αν δεν υπάρχει στο inventory, η χρήση αποτυγχάνει
        if row is None:
            return False, "Item not in inventory"

        quantity = row[0]

        # Αν υπάρχουν περισσότερα από ένα, μειώνεται η ποσότητα κατά 1
        if quantity > 1:
            cur.execute("""
                UPDATE Item_Inventory
                SET Quantity = Quantity - 1
                WHERE Player_id = ? AND Item_name = ?;
            """, (player_id, item_name))

        # Αν υπάρχει μόνο ένα, διαγράφεται η εγγραφή από το inventory
        else:
            cur.execute("""
                DELETE FROM Item_Inventory
                WHERE Player_id = ? AND Item_name = ?;
            """, (player_id, item_name))

        conn.commit()
        return True, "Item consumed"

    except Exception as ex:
        conn.rollback()
        return False, str(ex)

    finally:
        conn.close()

# Μέθοδος που μηδενίζει την πρόοδο του παίκτη και καθαρίζει το inventory του
def reset_player_progress(player_id: str):
    conn = db_conn()
    cur = conn.cursor()

    # Επαναφέρει gold, experience και level στις αρχικές τιμές
    cur.execute("""
        UPDATE Player
        SET Gold = 0,
            Experience = 0,
            Level = 1
        WHERE Player_id = ?;
    """, (player_id,))

    # Διαγράφει όλα τα items του παίκτη από το inventory
    cur.execute("""
        DELETE FROM Item_Inventory
        WHERE Player_id = ?;
    """, (player_id,))

    conn.commit()
    conn.close()

# Μέθοδος που ενημερώνει την πρόοδο του παίκτη στη βάση
def update_player_progress(player_id: str, gold: int, experience: int, level: int):
    conn = db_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE Player
        SET Gold = ?, Experience = ?, Level = ?
        WHERE Player_id = ?;
    """, (gold, experience, level, player_id))

    conn.commit()
    conn.close()

# Μέθοδος που επιστρέφει τα στοιχεία παίκτη με βάση το Player_id
def get_player_by_id(player_id: str):
    conn = db_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT Player_id, Nickname, Class_name, Gold, Experience, Level
        FROM Player
        WHERE Player_id = ?;
    """, (player_id,))

    row = cur.fetchone()
    conn.close()

    return row

# Μέθοδος που δημιουργεί νέο παίκτη στη βάση δεδομένων
def create_player(player_id: str, nickname: str, class_name: str):
    # Χρησιμοποιούμε UTC timestamp για Created_at και Last_login
    now = datetime.utcnow().isoformat(timespec="seconds")

    conn = db_conn()
    cur = conn.cursor()

    # Εξασφαλίζει ότι η κλάση του παίκτη υπάρχει πριν δημιουργηθεί ο παίκτης
    cur.execute("INSERT OR IGNORE INTO Class(Class_name) VALUES (?);", (class_name,))

    # Εισαγωγή νέου παίκτη με αρχικές τιμές
    # Gold = 0, Experience = 0, Level = 1
    cur.execute("""
        INSERT INTO Player(Player_id, Nickname, Gold, Experience, Level, Created_at, Last_login, Class_name)
        VALUES (?, ?, 0, 0, 1, ?, ?, ?);
    """, (player_id, nickname, now, now, class_name))

    conn.commit()
    conn.close()

# Μέθοδος που επιστρέφει τα στοιχεία παίκτη με βάση το nickname
def get_player_by_nickname(nickname: str):
    conn = db_conn()
    cur = conn.cursor()

    # Αναζήτηση παίκτη στον πίνακα Player
    cur.execute("""
        SELECT Player_id, Nickname, Class_name, Gold, Experience, Level
        FROM Player
        WHERE Nickname = ?;
    """, (nickname,))

    row = cur.fetchone()

    conn.close()

    # Επιστρέφει None αν δεν βρεθεί παίκτης ή tuple με τα στοιχεία του παίκτη
    return row  

# Μέθοδος που ενημερώνει την τελευταία σύνδεση ενός παίκτη
def update_last_login(player_id: str):
    # Τρέχουσα ημερομηνία, ώρα σε μορφή ISO
    now = datetime.utcnow().isoformat(timespec="seconds")

    conn = db_conn()

    # Ενημέρωση του πεδίου Last_login για τον συγκεκριμένο παίκτη
    conn.execute("UPDATE Player SET Last_login = ? WHERE Player_id = ?;", (now, player_id))
    
    conn.commit()
    conn.close()