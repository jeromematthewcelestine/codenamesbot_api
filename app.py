from flask import Flask, render_template, redirect, url_for, jsonify, request, abort
from flask_sqlalchemy import SQLAlchemy
import os
import json
from codenames import CodenamesBoard, CodenamesState
from dataclasses import dataclass, asdict
import hashids
from functools import wraps

if "DATABASE_URL" in os.environ:
    DATABASE_URL = os.environ['DATABASE_URL']
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    import local_config
    DATABASE_URL = local_config.DATABASE_URL

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
db = SQLAlchemy(app)

if "HASHIDS_SALT" in os.environ:
    hashids_salt = os.environ['HASHIDS_SALT']
else:
    import local_config
    hashids_salt = local_config.HASHIDS_SALT

if 'API_KEY' in os.environ:
    api_key = os.environ['API_KEY']
else:
    import local_config
    api_key = local_config.API_KEY

hashids_instance = hashids.Hashids(salt=hashids_salt,
                                   min_length=8)

def require_appkey(view_function):
    @wraps(view_function)
    def decorated_function(*args, **kwargs):
        if not request.headers.get('x-api-key') or not request.headers.get('x-api-key') == api_key:
            abort(401)
        else:
            return view_function(*args, **kwargs)
    return decorated_function

board = CodenamesBoard(DATABASE_URL)

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    state = db.Column(db.Text)
    username = db.Column(db.Text)
    status = db.Column(db.Text)

class Guess(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer)
    # timestamp = db.Column(db.DateTime)
    # clue_word = db.Column(db.Text)
    # clue_number = db.Column(db.Integer)
    # clue_targets = db.Column(db.Text)

class WordGuessed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    guess_id = db.Column(db.Integer, db.ForeignKey('guess.id'))
    clue_word = db.Column(db.Text)
    table_word = db.Column(db.Text)
    guessed = db.Column(db.Boolean)
    correct = db.Column(db.Boolean)

def write_guess_to_db(game_id, game_state, guess_word):
    guess = Guess(
        game_id = game_id,
    )
    db.session.add(guess)
    db.session.commit()

    clue_word = game_state.current_clue_word
    clue_number = game_state.current_clue_number

    for table_word in game_state.table_words:
        # if word was not on table, skip
        if table_word in game_state.correct_guesses or table_word in game_state.incorrect_guesses:
            continue
        guessed = (table_word == guess_word)
        word_guessed = WordGuessed(
            guess_id = guess.id,
            clue_word = clue_word,
            table_word = table_word,
            guessed = (table_word == guess_word),
            correct = (table_word == guess_word and guess_word in game_state.target_words)
        )
        db.session.add(word_guessed)
    db.session.commit()

def to_frontend(state_dict):
    frontend_state = state_dict.copy()
    new_table_words = []
    if not frontend_state['is_game_over']:
        for word in frontend_state['table_words']:
            if word in frontend_state['incorrect_guesses']:
                if word in frontend_state['trap_words']:
                    new_table_words.append({'word': word, 'status': 'trap'})
                else:
                    new_table_words.append({'word': word, 'status': 'incorrect'})
            elif word in frontend_state['correct_guesses']:
                new_table_words.append({'word': word, 'status': 'correct'})
            else:
                new_table_words.append({'word': word, 'status': 'open'})
    else:
        for word in frontend_state['table_words']:
            if word in frontend_state['trap_words']:
                new_table_words.append({'word': word, 'status': 'trap'})
            elif word in frontend_state['target_words']:
                new_table_words.append({'word': word, 'status': 'correct'})
            else:
                new_table_words.append({'word': word, 'status': 'incorrect'})
    frontend_state['table_words'] = new_table_words

    # don't return list of target words or trap words or current clue targets
    frontend_state['num_target_words'] = len(frontend_state['target_words'])
    frontend_state.pop('target_words')
    frontend_state.pop('trap_words')
    frontend_state.pop('current_clue_targets')

    return frontend_state

@app.route('/games')
@require_appkey
def list_games():
    games = Game.query.all()
    return jsonify([{ 'id': hashids_instance.encode(game.id), 'username': game.username, 'status': game.status } for game in games])

@app.route('/new-game', methods=['POST'])
@require_appkey
def new_game():
    game_state = board.generate_board(n_table_words = 20, n_target_words = 8, n_trap_words = 2)
    print(game_state)
    game = Game(state=json.dumps(asdict(game_state)), username='jeromew', status='active')
    db.session.add(game)
    db.session.commit()
    encoded_game_id = hashids_instance.encode(game.id)
    return {'game_id': encoded_game_id}

@app.route('/game', methods=['POST'])
@require_appkey
def game_state():
    print(f"/game")
    if 'game_id' not in request.json:
        print("No game id")
        return "No game_id provided", 400
    else:
        print("request.json", request.json)
    encoded_game_id = request.json['game_id']
    print("encoded_game_id", encoded_game_id)
    game_id = hashids_instance.decode(encoded_game_id)[0]
    game = Game.query.get(game_id)
    if game is None:
        print("Game not found")
        return "Game not found", 404
    else:
        game_state = json.loads(game.state)
        return to_frontend(game_state)

@app.route('/game/action', methods=['POST'])
@require_appkey
def game_action():
    print(f"/game/action!!")
    print(f"request.json")

    print(f"request", request)

    if not request.data:
        return "No request data", 400

    if 'game_id' not in request.json:
        print("No game id")
        return "No game_id provided", 400
    else:
        print("game_id", request.json['game_id'])
        print("request.json", request.json)
        
    encoded_game_id = request.json['game_id']
    game_id = hashids_instance.decode(encoded_game_id)[0]

    # check if valid action type
    action_type = request.json['action_type']
    print(f'action_type {action_type}')
    if action_type != "guess" and action_type != "pass" and action_type != "resign":
        return "Invalid action type", 400

    # get game state from db
    game = Game.query.get(game_id)
    game_state_dict = json.loads(game.state)
    game_state = CodenamesState(**game_state_dict)

    # handle guess action
    if action_type == "guess":
        guess = request.json['guess']
        write_guess_to_db(game_id, game_state, guess)
        response, new_state = board.do_guess(game_state, guess)
    elif action_type == "pass":
        write_guess_to_db(game_id, game_state, "")
        response, new_state = board.do_pass(game_state)
    elif action_type == "resign":
        response, new_state = board.do_resign(game_state)

    new_state_dict = asdict(new_state)

    game.state = json.dumps(new_state_dict)
    db.session.commit()

    return {"response": response, "state": to_frontend(new_state_dict)}

@app.route('/game/next', methods=['POST'])
@require_appkey
def game_next():        
    print(f"/game/next")
    if 'game_id' not in request.json:
        return "No game_id provided", 400
    
    encoded_game_id = request.json['game_id']
    print("encoded_game_id", encoded_game_id)
    
    try:
        game_id = hashids_instance.decode(encoded_game_id)[0]
    except:
        return "Invalid game_id", 400

    game = Game.query.get(game_id)
    game_state_dict = json.loads(game.state)
    game_state = CodenamesState(**game_state_dict)

    response, new_state = board.do_clue(encoded_game_id, game_state, previous_clues=[clue[0] for clue in game_state.all_clues])
    
    new_state_dict = asdict(new_state)
    game.state = json.dumps(new_state_dict)
    db.session.commit()
    
    return {"response": response, "state": to_frontend(new_state_dict)}

if __name__ == '__main__':
    app.run(port = 5001, debug=True)