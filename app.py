from flask import Flask, render_template, request, redirect, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
import qrcode
import uuid
import requests
import os

# -------- APP -------- #

app = Flask(__name__)
app.secret_key = "secret123"

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -------- ROBOFLOW CONFIG -------- #

API_KEY = "d8207anxlLptFHy3mCSm"
WORKSPACE = "sais-workspace-5kbq6"
WORKFLOW = "find-car-motorcycle-vehicles"

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

# -------- ROBOFLOW DETECTION FUNCTION -------- #

def detect_vehicle(image_file):
    url = f"https://detect.roboflow.com/{WORKSPACE}/{WORKFLOW}?api_key={API_KEY}"

    response = requests.post(
        url,
        files={"file": image_file}
    )

    return response.json()

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

# -------- DETECTION ROUTE -------- #

@app.route('/detect_vehicle', methods=['POST'])
def detect_vehicle_route():
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"})

    file = request.files['image']

    result = detect_vehicle(file)

    # check if vehicles detected
    predictions = result.get("predictions", [])

    if len(predictions) > 0:
        free_slot = Slot.query.filter_by(status="free").first()

        if free_slot:
            free_slot.status = "booked"
            db.session.add(VehicleLog(slot_id=free_slot.id))
            db.session.commit()

    return jsonify(result)

# -------- ADMIN PAGES -------- #

@app.route('/admin_detect')
def admin_detect():
    if 'admin' not in session:
        return redirect('/admin_login')
    return render_template('admin_detect.html')

@app.route('/admin_logs')
def admin_logs():
    if 'admin' not in session:
        return redirect('/admin_login')

    logs = VehicleLog.query.order_by(VehicleLog.detected_at.desc()).all()
    return render_template('admin_logs.html', logs=logs)

@app.route('/scan')
def scan_page():
    if 'admin' not in session:
        return redirect('/admin_login')
    return render_template('scan.html')

# -------- RUN -------- #

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
