from dataclasses import dataclass, replace
import random
from codenamesbot import CodenamesClueGiver

def load_codenames_words():
    with open('data/codenames_words.txt', 'r') as f:
        codenames_words = [word.strip().lower() for word in f.readlines()]
    
    codenames_words.remove('ice cream')
    codenames_words.remove('loch ness')
    codenames_words.remove('new york')
    codenames_words.remove('scuba diver')

    return codenames_words

@dataclass
class CodenamesState:
    is_game_over: bool
    round_num: int
    table_words: list
    target_words: list
    trap_words: list
    word_statuses: dict
    correct_guesses: list
    incorrect_guesses: list
    current_clue_word: str
    current_clue_number: int
    current_clue_targets: list
    current_guesses: list
    all_guesses: list
    all_clues: list
    active_player: str
    game_result: str
    score: int

class CodenamesBoard:

    def __init__(self, database_uri):
        self.code_words = load_codenames_words()
        self.clue_giver = CodenamesClueGiver(database_uri)

    def generate_board(self, n_table_words=16, n_target_words=7, n_trap_words=1):
        self.n_table_words = n_table_words
        self.n_target_words = n_target_words
        table_words = random.sample(self.code_words, k=self.n_table_words)
        target_words = random.sample(table_words, k=self.n_target_words)
        trap_words = random.sample([word for word in table_words if word not in target_words], k=n_trap_words)
        
        state = CodenamesState(
            is_game_over = False,
            table_words = table_words,
            target_words = target_words,
            trap_words = trap_words,
            word_statuses = {word: 'open' for word in table_words},
            correct_guesses = [],
            incorrect_guesses = [],
            current_clue_word = None,
            current_clue_number = None,
            current_clue_targets = [],
            current_guesses = [],
            all_guesses = [],
            all_clues = [],
            round_num = 1,
            active_player = "giver",
            game_result = None,
            score = 0
        )
        return state
    
    def is_convertible_to_int(self, x):
        try:
            int(x)
            return True
        except ValueError:
            return False

    def do_clue(self, game_id, state, previous_clues=None):
        s = replace(state) # copy state

        if s.is_game_over:
            return "Game is over!", s
        if s.active_player == "guesser":
            return "It's the guesser's turn!", s

        remaining_table_words = [word for word in s.table_words if word not in s.correct_guesses and word not in s.incorrect_guesses]
        remaining_target_words = [word for word in s.target_words if word not in s.correct_guesses and word not in s.incorrect_guesses]
        clue, score, curr_target = self.clue_giver.generate_best_clue(game_id, remaining_table_words, remaining_target_words, s.trap_words, previous_clues=previous_clues)

        if clue is not None:
            s.current_clue_word = clue
            s.current_clue_number = len(curr_target)
            s.current_clue_targets = curr_target
            s.all_clues.append([clue, len(curr_target), curr_target])
            s.active_player = "guesser"
        else:
            return "No clue found.", s

        # clue = "test"
        # score = 1.0
        # curr_target = [remaining_target_words[0]]

        

        return "Clue: " + clue + " " + str(len(curr_target)), s

    def do_pass(self, state):
        s = state

        if s.is_game_over:
            return "Game is over!", s
        if s.active_player == "giver":
            return "It's the giver's turn!", s
        
        if len(s.current_guesses) == 0:
            return "You must make at least one guess!", s
        
        s.all_guesses.append(s.current_guesses)
        s.current_guesses = []

        s.active_player = "giver"
        s.round_num += 1
        return "Pass!", s
    
        
    def do_guess(self, state, guess):
        s = state

        if s.is_game_over:
            return "Game is over!", s
        if s.active_player == "giver":
            return "It's the giver's turn!", s

        if guess in s.correct_guesses or guess in s.incorrect_guesses:
            response = "You already guessed that word!"
            return response, s
        
        if guess not in s.table_words:
            response = "That's not a word on the board!"
            return response, s
        
        # valid guess
        s.current_guesses.append(guess)
        
        if guess in s.target_words:
            response = "Correct!"
            s.correct_guesses.append(guess)
            s.word_statuses[guess] = 'correct'
        elif guess in s.trap_words:
            response = "You lose!"
            s.is_game_over = True
            s.game_result = "assassin"
            s.incorrect_guesses.append(guess)
            s.word_statuses[guess] = 'trap'
        else: # guess in table_words but not in target_words or trap_words
            response = "Incorrect!"
            s.incorrect_guesses.append(guess)
            s.word_statuses[guess] = 'incorrect'
            # giver's turn
            s.all_guesses.append(s.current_guesses)
            s.current_guesses = []
            s.active_player = "giver"
            s.round_num += 1

        if len(s.correct_guesses) == len(s.target_words):
            response += " All target words guessed!"
            s.is_game_over = True
            s.game_result = "win"

        return response, s
    
if __name__ == "__main__":
    board = CodenamesBoard()

    game_state = board.generate_board(n_table_words=16, n_target_words=7)

    print(game_state.table_words)
    print(game_state.target_words)

    clue_giver = CodenamesClueGiver()
    clue, score, best_target_words = clue_giver.generate_best_clue(game_state.table_words, game_state.target_words, game_state.trap_words)
    print(clue, score, best_target_words)

