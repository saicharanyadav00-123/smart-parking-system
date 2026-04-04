from flask import Flask, render_template, request, redirect, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
import qrcode
import uuid
import os
import requests

# -------- APP CONFIG -------- #

app = Flask(__name__)
app.secret_key = "secret123"

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -------- DATABASE -------- #

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

class Slot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), default="free")
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'))

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    slot_id = db.Column(db.Integer)

class VehicleLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slot_id = db.Column(db.Integer)
    detected_at = db.Column(db.DateTime, default=db.func.current_timestamp())

# -------- INIT DB -------- #

with app.app_context():
    db.create_all()

# -------- AUTH -------- #

@app.route('/')
def home():
    return redirect('/login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            flash("User already exists!")
            return redirect('/register')

        db.session.add(User(
            username=request.form['username'],
            password=request.form['password']
        ))
        db.session.commit()
        return redirect('/login')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()

        if user and user.password == request.form['password']:
            session['user_id'] = user.id
            return redirect('/dashboard')

        flash("Invalid credentials")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# -------- DASHBOARD -------- #

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')

    user = User.query.get(session['user_id'])

    locations = []
    for loc in Location.query.all():
        total = Slot.query.filter_by(location_id=loc.id).count()
        free = Slot.query.filter_by(location_id=loc.id, status="free").count()

        locations.append({
            "id": loc.id,
            "name": loc.name,
            "total": total,
            "free": free
        })

    return render_template('dashboard.html',
                           username=user.username,
                           locations=locations)

# -------- ADMIN -------- #

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['username'] == "projectsai" and request.form['password'] == "teamproject":
            session['admin'] = True
            return redirect('/admin')

        flash("Invalid Admin Credentials")

    return render_template('admin_login.html')

@app.route('/admin')
def admin():
    if 'admin' not in session:
        return redirect('/admin_login')

    locations = []
    for loc in Location.query.all():
        total = Slot.query.filter_by(location_id=loc.id).count()
        free = Slot.query.filter_by(location_id=loc.id, status="free").count()

        locations.append({
            "name": loc.name,
            "total": total,
            "free": free
        })

    return render_template('admin.html', locations=locations)

# -------- LIVE DETECTION PAGE -------- #

@app.route('/live')
def live_page():
    if 'admin' not in session:
        return redirect('/admin_login')
    return render_template('detect_live.html')

# -------- ROBOfLOW DETECTION -------- #

@app.route('/detect_live', methods=['POST'])
def detect_live():
    file = request.files['image']

    try:
        response = requests.post(
            "https://detect.roboflow.com/YOUR_MODEL/1?api_key=YOUR_API_KEY",
            files={"file": file}
        )
        return jsonify(response.json())

    except Exception as e:
        return jsonify({"error": str(e)})

# -------- RUN -------- #

if __name__ == "__main__":
    app.run(debug=True)
