import sqlite3
from db_path import get_db_path

# Αρχείο αρχικοποίησης της βάσης δεδομένων
# Δημιουργεί τους απαραίτητους πίνακες του παιχνιδιού αν δεν υπάρχουν ήδη, ώστε ο server να μπορεί να ξεκινήσει ακόμα και αν η βάση έχει διαγραφεί
def initialize_database():
    connection = sqlite3.connect(get_db_path())
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Class (
            Class_name TEXT PRIMARY KEY
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Player (
            Player_id TEXT PRIMARY KEY,
            Nickname TEXT UNIQUE NOT NULL,
            Gold INTEGER NOT NULL CHECK (Gold >= 0),
            Experience INTEGER NOT NULL CHECK (Experience >= 0),
            Level INTEGER NOT NULL CHECK (Level BETWEEN 1 AND 10),
            Created_at TEXT NOT NULL,
            Last_login TEXT NOT NULL,
            Class_name TEXT NOT NULL,
            FOREIGN KEY (Class_name) REFERENCES Class(Class_name)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Item (
            Item_name TEXT PRIMARY KEY,
            Price INTEGER NOT NULL CHECK (Price >= 0),
            Category TEXT NOT NULL,
            Stackable INTEGER NOT NULL CHECK (Stackable IN (0, 1)),
            Max_stack INTEGER NOT NULL CHECK (Max_stack BETWEEN 1 AND 3)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Item_Inventory (
            Player_id TEXT NOT NULL,
            Item_name TEXT NOT NULL,
            Quantity INTEGER NOT NULL CHECK (Quantity BETWEEN 1 AND 3),
            PRIMARY KEY (Player_id, Item_name),
            FOREIGN KEY (Player_id) REFERENCES Player(Player_id) ON DELETE CASCADE,
            FOREIGN KEY (Item_name) REFERENCES Item(Item_name)
        );
    """)

    connection.commit()
    connection.close()