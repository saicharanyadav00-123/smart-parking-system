from flask import Flask, render_template, request, redirect, session, flash, Response
from flask_sqlalchemy import SQLAlchemy
import qrcode
import uuid
import threading
import time
import os

# -------- SAFE IMPORTS (IMPORTANT FOR RENDER) -------- #

try:
    import cv2
    from ultralytics import YOLO
    model = YOLO("yolov8n.pt")
except:
    model = None

try:
    import razorpay
    client = razorpay.Client(auth=("rzp_test_xxxxx", "xxxxxxxx"))
except:
    client = None

# -------- APP CONFIG -------- #

app = Flask(__name__)
app.secret_key = "secret123"

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

latest_frame = None
vehicle_detected = False

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

# -------- AI DETECTION (SAFE) -------- #

def ai_detection():
    global latest_frame, vehicle_detected

    if model is None:
        return

    while True:
        time.sleep(2)

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
    try:
        if request.method == 'POST':
            user = User.query.filter_by(username=request.form['username']).first()

            if user and user.password == request.form['password']:
                session['user_id'] = user.id
                return redirect('/dashboard')

            flash("Invalid credentials")

        return render_template('login.html')
    except Exception as e:
        return f"Error: {str(e)}"

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

# -------- ADD LOCATION -------- #

@app.route('/add_location', methods=['GET', 'POST'])
def add_location():
    if 'admin' not in session:
        return redirect('/admin_login')

    if request.method == 'POST':
        loc = Location(
            name=request.form['name'],
            latitude=float(request.form['latitude']),
            longitude=float(request.form['longitude'])
        )
        db.session.add(loc)
        db.session.commit()
        return redirect(f'/add_slots/{loc.id}')

    return render_template('add_location.html')

# -------- ADD SLOTS -------- #

@app.route('/add_slots/<int:location_id>', methods=['GET', 'POST'])
def add_slots(location_id):
    if 'admin' not in session:
        return redirect('/admin_login')

    if request.method == 'POST':
        count = int(request.form['slots'])

        for _ in range(count):
            db.session.add(Slot(location_id=location_id))

        db.session.commit()
        return redirect('/admin')

    return render_template('add_slots.html')

# -------- VIEW SLOTS -------- #

@app.route('/location_slots/<int:loc_id>')
def location_slots(loc_id):
    if 'user_id' not in session:
        return redirect('/login')

    slots = Slot.query.filter_by(location_id=loc_id).all()
    return render_template('location_slots.html', slots=slots)

# -------- PAYMENT + QR -------- #

@app.route('/payment_success/<int:slot_id>')
def payment_success(slot_id):
    if 'user_id' not in session:
        return redirect('/login')

    slot = Slot.query.get(slot_id)

    if slot and slot.status == "free":
        slot.status = "booked"

        db.session.add(Booking(user_id=session['user_id'], slot_id=slot_id))
        db.session.commit()

        qr_data = f"{session['user_id']}|{slot_id}"
        img = qrcode.make(qr_data)

        filename = f"qr_{uuid.uuid4()}.png"
        img.save(f"static/{filename}")

        return render_template("qr.html", qr=filename)

    return redirect('/dashboard')

# -------- ADMIN DETECTION -------- #

@app.route('/admin_detect')
def admin_detect():
    if 'admin' not in session:
        return redirect('/admin_login')
    return render_template('admin_detect.html')

# -------- ADMIN LOGS -------- #

@app.route('/admin_logs')
def admin_logs():
    if 'admin' not in session:
        return redirect('/admin_login')

    logs = VehicleLog.query.order_by(VehicleLog.detected_at.desc()).all()
    return render_template('admin_logs.html', logs=logs)

# -------- QR SCAN -------- #

@app.route('/scan')
def scan_page():
    if 'admin' not in session:
        return redirect('/admin_login')
    return render_template('scan.html')

# -------- MAIN -------- #

if __name__ == "__main__":
    threading.Thread(target=ai_detection, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
