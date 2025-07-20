from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
import speech_recognition as sr
import tempfile
from pydub import AudioSegment
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
app.secret_key = 'your-secret-key'  # Change this to a secure random key

# Setup SQLite database config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///transcriptions.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Flask-Login setup
login_manager = LoginManager()
login_manager.login_view = 'login'  # redirect to login page if not logged in
login_manager.init_app(app)

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)  # We'll store hashed passwords

# Transcription model linked to User
class Transcription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('transcriptions', lazy=True))

with app.app_context():
    db.create_all()

# Quick fix for Apple silicone (Breaks on default so we use FLAC)
sr.AudioFile.FLAC_CONVERTER = "flac"

# User loader callback for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Route: Home page (redirects to login if not logged in)
@app.route('/')
@login_required
def index():
    return render_template('index.html')

# Route: Signup
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('signup'))

        # Hash password (use werkzeug.security)
        from werkzeug.security import generate_password_hash
        hashed_password = generate_password_hash(password, method= 'pbkdf2:sha256')

        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        flash('Account created! Please log in.')
        return redirect(url_for('login'))

    return render_template('signup.html')

# Route: Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if not user:
            flash('Username not found')
            return redirect(url_for('login'))

        from werkzeug.security import check_password_hash
        if not check_password_hash(user.password, password):
            flash('Incorrect password')
            return redirect(url_for('login'))

        login_user(user)
        return redirect(url_for('index'))

    return render_template('login.html')

# Route: Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('login'))

# Route: Show user's transcriptions with delete option
@app.route('/transcriptions')
@login_required
def show_transcriptions():
    transcriptions = Transcription.query.filter_by(user_id=current_user.id).order_by(Transcription.timestamp.desc()).all()
    return render_template('transcriptions.html', transcriptions=transcriptions)

# Route: Delete transcription (POST)
@app.route('/transcriptions/delete/<int:id>', methods=['POST'])
@login_required
def delete_transcription(id):
    transcription = Transcription.query.get_or_404(id)
    if transcription.user_id != current_user.id:
        return "Unauthorized", 403

    db.session.delete(transcription)
    db.session.commit()
    flash('Transcription deleted.')
    return redirect(url_for('show_transcriptions'))

# Route: Handle transcription requests
@app.route('/transcribe', methods=['POST'])
@login_required
def transcribe():
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400

    audio_file = request.files['audio']
    recognizer = sr.Recognizer()

    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp:
        audio_file.save(temp.name)

        sound = AudioSegment.from_file(temp.name)
        sound.export(temp.name, format="wav")

        with sr.AudioFile(temp.name) as source:
            audio_data = recognizer.record(source)

    try:
        text = recognizer.recognize_google(audio_data)

        # Save transcription linked to current user
        new_entry = Transcription(content=text, user_id=current_user.id)
        db.session.add(new_entry)
        db.session.commit()

        return jsonify({'transcription': text})
    except sr.UnknownValueError:
        return jsonify({'error': 'Could not understand audio'}), 400
    except sr.RequestError:
        return jsonify({'error': 'API unavailable'}), 503

if __name__ == '__main__':
    app.run(debug=True)
