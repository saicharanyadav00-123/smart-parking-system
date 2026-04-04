from flask import Flask, render_template, request, redirect, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
import requests
import os
import qrcode
import uuid

app = Flask(__name__)
app.secret_key = "secret123"

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -------- ROBOFLOW CONFIG (FIXED) -------- #

API_KEY = "d8207anxlLptFHy3mCSm"

# ✅ IMPORTANT: Use MODEL (not workflow)
MODEL = "car-motorcycle-vehicles/1"

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

with app.app_context():
    db.create_all()

# -------- ROBOFLOW DETECTION (FIXED) -------- #

def detect_vehicle_api(image_file):
    try:
        url = f"https://detect.roboflow.com/{MODEL}?api_key={API_KEY}"

        response = requests.post(
            url,
            files={"file": image_file}
        )

        result = response.json()

        print("ROBOFLOW RESPONSE:", result)  # DEBUG

        return result

    except Exception as e:
        print("ERROR:", str(e))
        return {"predictions": []}

# -------- HOME -------- #

@app.route('/')
def home():
    return redirect('/login')

# -------- REGISTER -------- #

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            flash("User already exists!")
            return redirect('/register')

        user = User(
            username=request.form['username'],
            password=request.form['password']
        )
        db.session.add(user)
        db.session.commit()

        return redirect('/login')

    return render_template('register.html')

# -------- USER LOGIN -------- #

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()

        if user and user.password == request.form['password']:
            session['user_id'] = user.id
            return redirect('/dashboard')

        flash("Invalid credentials")

    return render_template('login.html')

# -------- LOGOUT -------- #

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

    return render_template('dashboard.html', username=user.username, locations=locations)

# -------- ADMIN LOGIN -------- #

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['username'] == "admin" and request.form['password'] == "admin":
            session['admin'] = True
            return redirect('/admin')

        flash("Invalid Admin Credentials")

    return render_template('admin_login.html')

# -------- ADMIN DASHBOARD -------- #

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
        try:
            loc = Location(
                name=request.form['name'],
                latitude=float(request.form['latitude']),
                longitude=float(request.form['longitude'])
            )
            db.session.add(loc)
            db.session.commit()

            return redirect('/admin')

        except Exception as e:
            return f"ERROR: {str(e)}"

    return render_template('add_location.html')

# -------- LIVE DETECTION PAGE -------- #

@app.route('/live')
def live():
    if 'admin' not in session:
        return redirect('/admin_login')

    return render_template('admin_detect.html')

# -------- DETECTION ROUTE (FIXED) -------- #

@app.route('/detect_vehicle', methods=['POST'])
def detect_vehicle():
    try:
        if 'image' not in request.files:
            return "No image uploaded"

        file = request.files['image']

        result = detect_vehicle_api(file)

        print("RESULT:", result)  # DEBUG

        predictions = result.get("predictions", [])

        if len(predictions) > 0:
            slot = Slot.query.filter_by(status="free").first()

            if slot:
                slot.status = "booked"
                db.session.add(VehicleLog(slot_id=slot.id))
                db.session.commit()

        return render_template("admin_detect.html", result=result)

    except Exception as e:
        return f"ERROR OCCURRED: {str(e)}"

# -------- ADMIN LOGS -------- #

@app.route('/admin_logs')
def admin_logs():
    if 'admin' not in session:
        return redirect('/admin_login')

    logs = VehicleLog.query.order_by(VehicleLog.detected_at.desc()).all()
    return render_template('admin_logs.html', logs=logs)

# -------- SCAN -------- #

@app.route('/scan')
def scan():
    if 'admin' not in session:
        return redirect('/admin_login')

    return render_template('scan.html')

@app.route('/scan_qr', methods=['POST'])
def scan_qr():
    try:
        data = request.form.get('qr_data')
        user_id, slot_id = data.split("|")

        booking = Booking.query.filter_by(
            user_id=int(user_id),
            slot_id=int(slot_id)
        ).first()

        if booking:
            return render_template("scan_result.html", status="success", message="Valid QR")
        else:
            return render_template("scan_result.html", status="error", message="Invalid QR")

    except:
        return render_template("scan_result.html", status="error", message="QR Error")

# -------- RUN -------- #

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
