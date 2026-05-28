import time

# Κλάση που διαχειρίζεται τη ροή ενός game session 
class GameSessionManager:
    # Σταθερές που δηλώνουν τις πιθανές καταστάσεις του session
    PHASE_IDLE = "idle"
    PHASE_LOBBY = "lobby"
    PHASE_LOADING = "loading"
    PHASE_PLAYING = "playing"
    PHASE_FINISHED = "finished"

    def __init__(self, lobby_duration=15.0, loading_duration=3.0, finish_duration=3.0):
        # Διάρκεια κάθε φάσης σε δευτερόλεπτα
        self.lobby_duration = lobby_duration
        self.loading_duration = loading_duration
        self.finish_duration = finish_duration

        # Αρχική κατάσταση του session
        self.phase = self.PHASE_IDLE
        self.result = None

        # Χρονικές στιγμές έναρξης των φάσεων
        self.lobby_started_at = 0.0
        self.loading_started_at = 0.0
        self.finished_started_at = 0.0

        # Παίκτες που περιμένουν στο lobby και παίκτες που συμμετέχουν ενεργά στο παιχνίδι
        self.lobby_players = set()
        self.active_players = set()

    # Σύνδεση παίκτη
    def connect_player(self, pid):
        # Αν δεν υπάρχει ενεργό session, ξεκινά νέο lobby
        if self.phase == self.PHASE_IDLE:
            self.start_lobby()

        # Αν το session βρίσκεται στο lobby, ο παίκτης προστίθεται στους παίκτες αναμονής
        if self.phase == self.PHASE_LOBBY:
            self.lobby_players.add(pid)
            return self.PHASE_LOBBY

        # Αν το παιχνίδι έχει ήδη προχωρήσει, ο παίκτης δεν μπαίνει στο τρέχον session
        return None

    # Αποσύνδεση παίκτη
    def disconnect_player(self, pid):
        # Αφαιρούμε τον παίκτη από το lobby, αν βρισκόταν εκεί
        self.lobby_players.discard(pid)

        # Ελέγχουμε αν ο παίκτης ήταν ενεργός μέσα στο παιχνίδι
        was_active = pid in self.active_players
        self.active_players.discard(pid)

        # Αν είμαστε στο lobby και φύγουν όλοι, ακυρώνεται το lobby
        if self.phase == self.PHASE_LOBBY and not self.lobby_players:
            self.phase = self.PHASE_IDLE
            self.lobby_started_at = 0.0
            return "lobby_cancelled"

        # Αν είμαστε ingame και φύγουν όλοι οι active players, το game εγκαταλείπεται
        if self.phase == self.PHASE_PLAYING and was_active and not self.active_players:
            self.phase = self.PHASE_IDLE
            return "game_abandoned"

        return None

    # Ξεκινά νέα φάση lobby
    def start_lobby(self):
        self.phase = self.PHASE_LOBBY
        self.result = None

        # Αποθηκεύεται η χρονική στιγμή έναρξης του lobby
        self.lobby_started_at = time.time()
        self.loading_started_at = 0.0
        self.finished_started_at = 0.0

        # Καθαρίζονται οι λίστες παικτών για νέο session
        self.lobby_players.clear()
        self.active_players.clear()

    # Η μέθοδος καλείται από τον server και ενημερώνει τη φάση του session
    def update(self):
        events = []
        now = time.time()

        if self.phase == self.PHASE_LOBBY:
            # Αν δεν υπάρχουν παίκτες στο lobby, το lobby ακυρώνεται
            if not self.lobby_players:
                self.phase = self.PHASE_IDLE
                events.append("lobby_cancelled")
                return events

            # Όταν τελειώσει ο χρόνος του lobby, οι παίκτες μεταφέρονται στους active players
            if now - self.lobby_started_at >= self.lobby_duration:
                self.active_players = set(self.lobby_players)
                self.lobby_players.clear()

                # Μετά το lobby ξεκινά η φάση loading
                self.phase = self.PHASE_LOADING
                self.loading_started_at = now
                events.append("loading_started")

        elif self.phase == self.PHASE_LOADING:
            # Όταν ολοκληρωθεί το loading, το παιχνίδι ξεκινά
            if now - self.loading_started_at >= self.loading_duration:
                self.phase = self.PHASE_PLAYING
                events.append("playing_started")

        elif self.phase == self.PHASE_FINISHED:
            # Μετά από μικρή καθυστέρηση, το session καθαρίζεται και επιστρέφει σε idle
            if now - self.finished_started_at >= self.finish_duration:
                self.active_players.clear()
                self.result = None
                self.phase = self.PHASE_IDLE
                events.append("finished_cleared")

        return events

    # Τέλος παιχνιδιού
    def finish_game(self, result):
        # Αν το παιχνίδι έχει ήδη τελειώσει, δεν ξαναεκτελείται η διαδικασία τερματισμού
        if self.phase == self.PHASE_FINISHED:
            return False

        # Ορίζει το session ως finished και αποθηκεύει το αποτέλεσμα
        self.phase = self.PHASE_FINISHED
        self.result = result
        self.finished_started_at = time.time()
        return True

    # Επιστρέφει True μόνο αν ο παίκτης ανήκει στους active players και το παιχνίδι είναι στη φάση playing
    def can_player_play(self, pid):
        return self.phase == self.PHASE_PLAYING and pid in self.active_players

    # Ελέγχει αν ένας παίκτης ανήκει στους ενεργούς παίκτες του session
    def is_active_player(self, pid):
        return pid in self.active_players

    # Αν ο παίκτης βρίσκεται στο lobby, επιστρέφεται η φάση lobby
    def get_player_phase(self, pid):
        if pid in self.lobby_players:
            return self.PHASE_LOBBY

        # Αν ο παίκτης είναι ενεργός, επιστρέφεται η τρέχουσα φάση του session
        if pid in self.active_players:
            return self.phase

        # Για παίκτες εκτός session, επιστρέφεται η τρέχουσα φάση του παιχνιδιού
        return self.phase

    # Αντίστροφη μέτρηση για να ξεκινήσει το lobby
    def get_lobby_countdown(self):
        # Αν δεν είμαστε στο lobby, δεν υπάρχει countdown
        if self.phase != self.PHASE_LOBBY:
            return 0

        # Υπολογίζει πόσος χρόνος απομένει μέχρι να ξεκινήσει το loading
        elapsed = time.time() - self.lobby_started_at
        return max(0, int(self.lobby_duration - elapsed) + 1)

    # Αντίστροφη μέτρηση για να ξεκινήσει το παιχνίδι
    def get_loading_progress(self):
        # Αν δεν είμαστε στο loading, η πρόοδος είναι 0
        if self.phase != self.PHASE_LOADING:
            return 0

        # Υπολογίζει την πρόοδο του loading σε ποσοστό 0-100
        elapsed = time.time() - self.loading_started_at
        progress = elapsed / self.loading_duration
        progress = max(0.0, min(1.0, progress))

        return int(progress * 100)

    # Επιστρέφει τα βασικά δεδομένα του session που μπορούν να σταλούν στους clients
    def get_public_state(self):
        return {
            "phase": self.phase,
            "result": self.result,
            "lobby_countdown": self.get_lobby_countdown(),
            "loading_progress": self.get_loading_progress(),
            "lobby_players_count": len(self.lobby_players),
            "active_players_count": len(self.active_players),
        }
    
    # Επαναφέρει πλήρως το session στην αρχική κατάσταση
    def reset_to_idle(self):
        self.phase = self.PHASE_IDLE
        self.result = None
        self.lobby_started_at = 0.0
        self.loading_started_at = 0.0
        self.finished_started_at = 0.0
        self.lobby_players.clear()
        self.active_players.clear()