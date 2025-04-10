# app.py
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import lru_cache, wraps
import json
import pandas as pd
import numpy as np
import os
import time

app = Flask(__name__)
app.secret_key = 'pokertracker69asjhdabhsd!@$#(*)'
app.permanent_session_lifetime = timedelta(days=7)

class PokerTracker:
    def __init__(self):
        self.users = {}
        self.user_data = {}
        self.data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'userdata')
        # Create userdata directory if it doesn't exist
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        self.load_users()

    def get_user_data_path(self, username):
        return os.path.join(self.data_dir, f'poker_data_{username}.csv')

    def get_users_file_path(self):
        return os.path.join(self.data_dir, 'users.json')

    def get_advanced_stats(self, username):
        if username not in self.user_data or len(self.user_data[username]) == 0:
            return {
                'basic_stats': self.get_stats(username),
                'advanced_stats': {
                    'location_stats': {
                        'avg_profit': {},
                        'total_profit': {},
                        'sessions': {},
                        'avg_bb_won': {}
                    },
                    'stake_distribution': {
                        'avg_profit': {},
                        'total_profit': {},
                        'sessions': {},
                        'avg_bb_won': {}
                    },
                    'stake_winrates': {},
                    'session_length_analysis': {
                        'avg_profit': {},
                        'session_count': {},
                        'avg_bb_won': {}
                    }
                }
            }

        df = self.user_data[username]
        
        try:
            # Location statistics
            location_profit_mean = df.groupby('location')['profit_loss'].mean().fillna(0)
            location_profit_sum = df.groupby('location')['profit_loss'].sum().fillna(0)
            location_profit_count = df.groupby('location')['profit_loss'].count().fillna(0)
            location_bb_mean = df.groupby('location')['bb_won'].mean().fillna(0)
            
            location_stats = {
                'avg_profit': {str(k): float(v) for k, v in location_profit_mean.items()},
                'total_profit': {str(k): float(v) for k, v in location_profit_sum.items()},
                'sessions': {str(k): int(v) for k, v in location_profit_count.items()},
                'avg_bb_won': {str(k): float(v) for k, v in location_bb_mean.items()}
            }
            
            # Stake level distribution
            stake_groups = df.groupby(['small_blind', 'big_blind'])
            stake_profit_mean = stake_groups['profit_loss'].mean().fillna(0)
            stake_profit_sum = stake_groups['profit_loss'].sum().fillna(0)
            stake_profit_count = stake_groups['profit_loss'].count().fillna(0)
            stake_bb_mean = stake_groups['bb_won'].mean().fillna(0)
            
            stake_distribution = {
                'avg_profit': {},
                'total_profit': {},
                'sessions': {},
                'avg_bb_won': {}
            }
            
            for (sb, bb) in stake_groups.groups:
                key = f"{sb},{bb}"
                stake_distribution['avg_profit'][key] = float(stake_profit_mean.get((sb, bb), 0))
                stake_distribution['total_profit'][key] = float(stake_profit_sum.get((sb, bb), 0))
                stake_distribution['sessions'][key] = int(stake_profit_count.get((sb, bb), 0))
                stake_distribution['avg_bb_won'][key] = float(stake_bb_mean.get((sb, bb), 0))
            
            # Calculate win rates by stake level
            stake_winrates_dict = {}
            for (sb, bb) in stake_groups.groups:
                stake_data = df[
                    (df['small_blind'] == sb) & 
                    (df['big_blind'] == bb)
                ]
                win_rate = (stake_data['profit_loss'] > 0).mean() * 100
                stake_winrates_dict[f"{sb},{bb}"] = {'profit_loss': float(win_rate)}
            
            # Session length analysis
            df['session_length_category'] = pd.cut(
                df['duration'], 
                bins=[0, 2, 4, 6, 8, float('inf')],
                labels=['0-2h', '2-4h', '4-6h', '6-8h', '8h+']
            )
            
            length_groups = df.groupby('session_length_category')
            length_profit_mean = length_groups['profit_loss'].mean().fillna(0)
            length_profit_count = length_groups['profit_loss'].count().fillna(0)
            length_bb_mean = length_groups['bb_won'].mean().fillna(0)
            
            session_length_analysis = {
                'avg_profit': {str(k): float(v) for k, v in length_profit_mean.items()},
                'session_count': {str(k): int(v) for k, v in length_profit_count.items()},
                'avg_bb_won': {str(k): float(v) for k, v in length_bb_mean.items()}
            }
            
            # Round all numeric values
            def round_nested_dict(d, decimals=2):
                for key, value in d.items():
                    if isinstance(value, dict):
                        round_nested_dict(value, decimals)
                    elif isinstance(value, float):
                        d[key] = round(value, decimals)

            result = {
                'basic_stats': self.get_stats(username),
                'advanced_stats': {
                    'location_stats': location_stats,
                    'stake_distribution': stake_distribution,
                    'stake_winrates': stake_winrates_dict,
                    'session_length_analysis': session_length_analysis
                }
            }
            
            round_nested_dict(result)
            return result
            
        except Exception as e:
            print(f"Error in get_advanced_stats: {str(e)}")
            return {
                'basic_stats': self.get_stats(username),
                'advanced_stats': {
                    'location_stats': {},
                    'stake_distribution': {},
                    'stake_winrates': {},
                    'session_length_analysis': {}
                }
            }

    def save_data(self, username):
        self.user_data[username].to_csv(self.get_user_data_path(username), index=False)

    def load_data(self, username):
        try:
            self.user_data[username] = pd.read_csv(self.get_user_data_path(username))
            self.user_data[username]['date'] = pd.to_datetime(self.user_data[username]['date'])
        except FileNotFoundError:
            pass

    def save_users(self):
        user_data = {username: {
            'password_hash': data['password_hash'],
            'elo': data['elo']
        } for username, data in self.users.items()}
        with open(self.get_users_file_path(), 'w') as f:
            json.dump(user_data, f)

    def load_users(self):
        try:
            with open(self.get_users_file_path(), 'r') as f:
                self.users = json.load(f)
            for username in self.users:
                self.user_data[username] = pd.DataFrame()
                self.load_data(username)
        except FileNotFoundError:
            pass

    def remove_session(self, username, session_index):
        if username not in self.user_data:
            return False
                
        try:
            # Get data sorted by date (newest first) to match frontend display
            df = self.user_data[username].sort_values('date', ascending=False)
            df = df.reset_index(drop=True)
            
            # Get the session data before removing
            session = df.iloc[session_index]
            
            # Find the original index in the unsorted dataframe
            original_index = self.user_data[username].index[
                self.user_data[username]['date'] == session['date']
            ][0]
            
            # Remove session from original dataframe
            self.user_data[username] = self.user_data[username].drop(original_index).reset_index(drop=True)
            
            # Revert ELO change
            self.users[username]['elo'] -= session['elo_change']
            
            # Recalculate cumulative profit
            self.user_data[username]['cumulative_profit'] = self.user_data[username]['profit_loss'].cumsum()
            
            # Save changes
            self.save_data(username)
            self.save_users()
            return True
        except (KeyError, IndexError) as e:
            print(f"Error removing session: {str(e)}")
            return False
                    
    def create_user(self, username, password):
        if username in self.users:
            return False
        self.users[username] = {
            'password_hash': generate_password_hash(password),
            'elo': 1000
        }
        self.user_data[username] = pd.DataFrame({
            'date': pd.Series(dtype='datetime64[ns]'),
            'location': pd.Series(dtype='str'),
            'small_blind': pd.Series(dtype='float64'),
            'big_blind': pd.Series(dtype='float64'),
            'buy_in': pd.Series(dtype='float64'),
            'buy_out': pd.Series(dtype='float64'),
            'duration': pd.Series(dtype='float64'),
            'profit_loss': pd.Series(dtype='float64'),
            'bb_won': pd.Series(dtype='float64'),
            'elo_change': pd.Series(dtype='float64'),
            'cumulative_profit': pd.Series(dtype='float64'),
            'hourly_rate': pd.Series(dtype='float64')
        })
        self.save_users()
        return True

    def verify_user(self, username, password):
        if username not in self.users:
            return False
        return check_password_hash(self.users[username]['password_hash'], password)

    def add_session(self, username, session_data):
        if username not in self.user_data:
            return None
                
        profit_loss = session_data['buy_out'] - session_data['buy_in']
        bb_won = profit_loss / session_data['big_blind']
        
        elo_change = (bb_won > 0)*2.5 + bb_won/session_data['duration']
        hourly_rate = profit_loss / session_data['duration'] if session_data['duration'] > 0 else 0

        # Parse the datetime string
        try:
            session_date = datetime.strptime(session_data['datetime'], '%Y-%m-%dT%H:%M')
        except (ValueError, KeyError):
            session_date = datetime.now()

        new_session = pd.DataFrame({
            'date': [session_date],
            'location': [session_data['location']],
            'small_blind': [session_data['small_blind']],
            'big_blind': [session_data['big_blind']],
            'buy_in': [session_data['buy_in']],
            'buy_out': [session_data['buy_out']],
            'duration': [session_data['duration']],
            'profit_loss': [profit_loss],
            'bb_won': [bb_won],
            'elo_change': [elo_change],
            'hourly_rate': [hourly_rate],
            'cumulative_profit': [0.0]
        })

        self.user_data[username] = pd.concat([self.user_data[username], new_session], ignore_index=True)
        self.user_data[username]['cumulative_profit'] = self.user_data[username]['profit_loss'].cumsum()
        self.users[username]['elo'] += elo_change
        
        self.save_data(username)
        self.save_users()
        return elo_change

    def get_stats(self, username):
        if username not in self.user_data or len(self.user_data[username]) == 0:
            return {
                'total_games': 0,
                'total_profit': 0,
                'total_bb_won': 0,
                'total_hours': 0,
                'avg_hourly': 0,
                'biggest_win': 0,
                'biggest_loss': 0,
                'win_rate': 0,
                'current_elo': self.users[username]['elo']
            }

        df = self.user_data[username]
        return {
            'total_games': len(df),
            'total_profit': float(df['profit_loss'].sum()),
            'total_bb_won': float(df['bb_won'].sum()),
            'total_hours': float(df['duration'].sum()),
            'avg_hourly': float(df['hourly_rate'].mean()),
            'biggest_win': float(df['profit_loss'].max()),
            'biggest_loss': float(df['profit_loss'].min()),
            'win_rate': float((df['profit_loss'] > 0).mean() * 100),
            'current_elo': float(self.users[username]['elo'])
        }

    def get_sessions(self, username):
        if username not in self.user_data:
            return []
            
        try:
            # Return all sessions, sorted by date (newest first)
            df = self.user_data[username].copy()
            df = df.sort_values('date', ascending=False)
            df = df.reset_index(drop=True)  # Reset index after sorting
            
            # Convert any potential NaN values to appropriate defaults
            df = df.fillna({
                'location': '',
                'small_blind': 0.0,
                'big_blind': 0.0,
                'buy_in': 0.0,
                'buy_out': 0.0,
                'duration': 0.0,
                'profit_loss': 0.0,
                'bb_won': 0.0,
                'elo_change': 0.0,
                'hourly_rate': 0.0
            })
            
            return df.to_dict('records')
        except Exception as e:
            print(f"Error in get_sessions: {str(e)}")
            return []
        




class SportTracker:
    def __init__(self):
        self.usersbetting = {}
        self.user_bets = {}
        self.data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sportsdata')
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        self.load_users()

    def get_user_data_path(self, username):
        #returns file path for user's bets CSV File
        return os.path.join(self.data_dir, f'bet_data_{username}.csv')
    

    def get_users_file_path(self):
        #returns file path for json file that stores all users
        return os.path.join(self.data_dir, 'users.json')
    
    def add_user(self,username):
        if username in self.usersbetting:
            return False #already there

        self.usersbetting[username] = {'elo':1000}

        self.user_bets[username] = pd.DataFrame({
            'date': pd.Series(dtype='datetime64[ns]'),
            'sport': pd.Series(dtype='str'),
            '# picks': pd.Series(dtype='float64'),
            'bet amount': pd.Series(dtype='float64'),
            'amountwonlost': pd.Series(dtype='float64'),
            'elochange': pd.Series(dtype='float64'),
        })

        self.save_users()
        return True
    
    def add_bet(self, username, bet_data):
        #adds new bet, expects bet data as dictionary with content: date, sport, #picks, bet_amount, amount won/lost, elo change

        if username not in self.user_bets:
            return False

        try:
            bet_date = datetime.strptime(bet_data.get('date', ''), '%Y-%m-%dT%H:%M')
        except Exception:
            bet_date = datetime.now()

        bet_amount = bet_data.get('bet amount',0)
        picks = bet_data.get('# picks', 0)
        amountwonlost = bet_data.get('amountwonlost', 0)

        if amountwonlost > 0:
            elo_change = 2.5*picks + amountwonlost
        else:
            elo_change = (-1.6*picks) - amountwonlost

        new_bet = pd.DataFrame({
            'date': [bet_date],
            'sport': [bet_data.get('sport','')],
            '# picks': [picks],
            'bet amount': [bet_amount],
            'amountwonlost': [amountwonlost],
            'elochange': [elo_change],
            'cumulative_profit': [0.0]
        })


        self.user_bets[username] = pd.concat([self.user_bets[username], new_bet], ignore_index=True)
        self.user_bets[username]['cumulative_profit'] = self.user_bets[username]['amountwonlost'].cumsum()
        self.usersbetting[username]['elo'] += elo_change
        
        self.save_data(username)
        self.save_users()
        return elo_change
    
    def get_bettingstats(self, username):
        
        if username not in self.user_bets or self.user_bets[username].empty:
            return{
                'total_bets':0,
                'total_profit':0,
                'total_picks':0,
                'win_rate':0,
                'biggest_win':0,
                'biggest_loss':0,
                'balance':self.usersbetting.get(username,{}).get('balance',0)
            }
        
        df = self.user_bets[username]
        total_bets = len(df)
        total_profit = df['cumulative_profit']
        win_rate = (df['cumulative_profit']>0).mean()*100
        total_picks = df['# picks'].sum()
        biggest_win = df['amountwonlost'].max()
        biggest_loss = df['amountwonlost'].min()

        return {
            'total_bets':total_bets,
            'total_profit':total_profit,
            'total_picks': total_picks,
            'win_rate':win_rate,
            'biggest_win':biggest_win,
            'biggest_loss':biggest_loss,
            'current_elo':self.usersbetting[username]['elo']
        }

    def save_data(self, username):
        # Saves the user's bet data to a CSV file
        self.user_bets[username].to_csv(self.get_user_data_path(username), index=False)

    def load_data(self, username):
        # Loads bet data from a CSV file into the user's DataFrame
        try:
            self.user_bets[username] = pd.read_csv(self.get_user_data_path(username))
            self.user_bets[username]['date'] = pd.to_datetime(self.user_bets[username]['date'])
        except FileNotFoundError:
            pass

    def save_users(self):
        user_data = {username: {
            'password_hash': data['password_hash'],
            'elo': data['elo']
        } for username, data in self.usersbetting.items()}
        with open(self.get_users_file_path(), 'w') as f:
            json.dump(user_data, f)

    def load_users(self):
        # Loads user data from the JSON file and initializes bet DataFrames for each user
        try:
            with open(self.get_users_file_path(), 'r') as f:
                self.usersbetting = json.load(f)
            for username in self.usersbetting:
                self.user_bets[username] = pd.DataFrame()
                self.load_data(username)
        except FileNotFoundError:
            pass

    
    def get_all_bets(self, username):
        # Returns all bets for a user, sorted by date (newest first)
        if username not in self.user_bets:
            return []
        try:
            df = self.user_bets[username].copy()
            df = df.sort_values('date', ascending=False).reset_index(drop=True)
            df = df.reset_index(drop=True)

            df = df.fillna({
                'date':'',
                'sport':'',
                '# picks':0.0,
                'bet amount': 0.0,
                'amountwonlost':0.0,
                'elochange':0.0
            })

            return df.to_dict('records')
        except Exception as e:
            print(f"Error in get_all_bets: {str(e)}")
            return []
        
        
        
    def remove_bet(self,username, session_index):
        if username not in self.user_bets:
            return False
        
        try:
            df = self.user_bets[username].sort_values('date', ascending=False)
            df = df.reset_index(drop=True)

            session = df.iloc[session_index]
            original_index = self.user_bets[username].index[
                self.user_bets[username]['date'] == session['date']
            ][0]

            # Remove session from original dataframe
            self.user_bets[username] = self.user_bets[username].drop(original_index).reset_index(drop=True)

            self.usersbetting[username]['elo'] -= session['elo_change']
            self.user_bets[username]['cumulative_profit'] = self.user_bets[username]['amountwonlost'].cumsum()

            self.save_data(username)
            self.save_users()
            return True
        
        except(KeyError, IndexError) as e:
            print(f"Error removing session: {str(e)}")
            return False
        

    def get_advanced_bettingstats(self, username):
        if username not in self.user_bets or len(self.user_bets[username]) == 0:
            return {
                'basic_stats':self.get_bettingstats(username),
                'advanced_stats': {
                    'sports_stats': {
                        'avg_profit':{},
                        'total_profit':{},
                        'sessions':{},
                    }, 
                    'betamount_analysis':{
                        'avg_profit':{},
                        'total_profit':{},
                        'session_count':{}
                    }     
                }
            }
        
        df = self.user_bets[username]
        try:
            #sports stats
            sport_profit_mean = df.groupby('sport')['amountwonlost'].mean().fillna(0)
            sport_profit_sum = df.groupby('sport')['amountwonlost'].sum().fillna(0)
            sport_session_count = df.groupby('sport')['amountwonlost'].count().fillna(0)

            sports_stats = {
                'avg_profit': {str(k):float(v) for k,v in sport_profit_mean.items()},
                'total_profit': {str(k):float(v) for k,v in sport_profit_sum.items()}, 
                'sessions': {str(k):float(v) for k,v in sport_session_count.items()}
            }


            # bet amount analysis
            df['bet_amount_category'] = pd.cut(
                df['bet amount'], 
                bins=[0, 10, 20, 30, 40, float('inf')],
                labels=['$0-10', '$10-20', '$20-30', '$30-40', '$40+']
            )

            amount_groups = df.groupby('bet_amount_category')
            amount_profit_mean = amount_groups['amountwonlost'].mean().fillna(0)
            amount_profit_sum = amount_groups['amountwonlost'].sum().fillna(0)
            amount_profit_count = amount_groups['amountwonlost'].count().fillna(0)
            
            betamount_analysis = {
                'avg_profit': {str(k): float(v) for k, v in amount_profit_mean.items()},
                'total_profit': {str(k): int(v) for k, v in amount_profit_sum.items()},
                'session_count': {str(k): int(v) for k, v in amount_profit_count.items()},
            }

            def round_nested_dict(d, decimals =2):
                for key, value in d.items():
                    if isinstance(value, dict):
                        round_nested_dict(value, decimals)
                    elif isinstance(value, float):
                        d[key] = round(value, decimals)

            result = {
                'basic_stats':self.get_bettingstats(username), 
                'advanced_stats':{
                    'sports_stats' : sports_stats,
                    'betamount_stats': betamount_analysis
                }
            }

            round_nested_dict(result)
            return result



        except Exception as e:
            print(f"Error in get_advanced_stats: {str(e)}")
            return {
                'basic_stats': self.get_bettingstats(username),
                'advanced_stats': {
                    'sports_stats': {},
                    'betamount_analysis': {}
                }
            }
        



poktracker = PokerTracker()
sportstracker = SportTracker()



# require login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if poktracker.verify_user(username, password):
            session['username'] = username
            return redirect(url_for('home'))
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Input validation
        if not username or not password:
            return render_template('register.html', error='Username and password are required')
            
        if len(password) < 6:
            return render_template('register.html', error='Password must be at least 6 characters')
            
        if not username.isalnum():
            return render_template('register.html', error='Username must contain only letters and numbers')
        
        if password != confirm_password:
            return render_template('register.html', error='Passwords do not match')

        # Try to create user
        if poktracker.create_user(username, password):
            session['username'] = username
            return redirect(url_for('home'))  # Make sure this matches your main route function name
        
        return render_template('register.html', error='Username already exists')
    
    # GET request
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    stats = poktracker.get_stats(session['username'])
    return render_template('home.html', total_profit = stats['total_profit'])


#poker functions

@app.route('/poker')
@login_required
def poker():
    return render_template('poker.html')

@app.route('/api/stats')
@login_required
def get_stats():
    return jsonify({
        'modified': True,
        'data': poktracker.get_stats(session['username'])
    })

@app.route('/api/sessions')
@login_required
def get_sessions():
    try:
        sessions = poktracker.get_sessions(session['username'])
        return jsonify({
            'modified': True,
            'data': [{
                'date': s['date'].isoformat() if hasattr(s['date'], 'isoformat') else str(s['date']),
                'location': str(s['location']),
                'small_blind': float(s['small_blind']),
                'big_blind': float(s['big_blind']),
                'buy_in': float(s['buy_in']),
                'buy_out': float(s['buy_out']),
                'duration': float(s['duration']),
                'profit_loss': float(s['profit_loss']),
                'bb_won': float(s['bb_won']),
                'elo_change': float(s['elo_change']),
                'hourly_rate': float(s['hourly_rate'])
            } for s in sessions]
        })
    except Exception as e:
        app.logger.error(f'Error in get_sessions: {str(e)}')
        return jsonify({
            'error': 'Failed to fetch sessions',
            'data': []
        }), 500

@app.route('/api/add_session', methods=['POST'])
@login_required
def add_session():
    try:
        data = request.get_json()
        if not all(k in data for k in ['location', 'small_blind', 'big_blind', 'buy_in', 'buy_out', 'duration', 'datetime']):
            return jsonify({'error': 'Missing required fields'}), 400
            
        elo_change = poktracker.add_session(session['username'], {
            'location': data['location'],
            'small_blind': float(data['small_blind']),
            'big_blind': float(data['big_blind']),
            'buy_in': float(data['buy_in']),
            'buy_out': float(data['buy_out']),
            'duration': float(data['duration']),
            'datetime': data['datetime']
        })
        
        if elo_change is None:
            return jsonify({'error': 'Failed to add session'}), 400
            
        return jsonify({'success': True, 'elo_change': elo_change})
    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Invalid data format: {str(e)}'}), 400
    except Exception as e:
        app.logger.error(f'Error adding session: {str(e)}')
        return jsonify({'error': 'Server error'}), 500
    
@app.route('/api/remove_session', methods=['POST'])
@login_required
def remove_session():
    data = request.get_json()
    session_index = data.get('session_index')
    
    if session_index is None:
        return jsonify({'error': 'Session index required'}), 400
        
    success = poktracker.remove_session(session['username'], session_index)
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Failed to remove session'}), 400

@app.route('/api/advanced_stats')
@login_required
def get_advanced_stats():
    return jsonify({
        'data': poktracker.get_advanced_stats(session['username'])
    })

#sports functions

@app.route('/sports')
@login_required
def sports():
    return render_template('sports.html')


if __name__ == '__main__':
    app.run(debug=True, threaded=True)