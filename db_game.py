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

# Μέθοδος που δημιουργεί νέο παίκτη στη βάση δεδομένων
def create_player(player_id: str, nickname: str, class_name: str):
    # Τρέχουσα ημερομηνία/ώρα σε μορφή ISO για Created_at και Last_login
    now = datetime.utcnow().isoformat(timespec="seconds")

    conn = db_conn()
    cur = conn.cursor()

    # Σιγουρευόμαστε ότι η κλάση του παίκτη υπάρχει στον πίνακα Class
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
    # Τρέχουσα ημερομηνία/ώρα σε μορφή ISO
    now = datetime.utcnow().isoformat(timespec="seconds")

    conn = db_conn()

    # Ενημέρωση του πεδίου Last_login για τον συγκεκριμένο παίκτη
    conn.execute("UPDATE Player SET Last_login = ? WHERE Player_id = ?;", (now, player_id))
    
    conn.commit()
    conn.close()
