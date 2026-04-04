from flask import Flask, render_template, request, redirect, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
import qrcode
import uuid
import requests
import os

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

with app.app_context():
    db.create_all()

# -------- ROBOFLOW DETECTION -------- #

def detect_vehicle_api(image_bytes):
    url = f"https://detect.roboflow.com/{WORKSPACE}/{WORKFLOW}?api_key={API_KEY}"

    response = requests.post(url, files={"file": image_bytes})
    return response.json()

# -------- AUTH -------- #

@app.route('/')
def home():
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()

        if user and user.password == request.form['password']:
            session['user_id'] = user.id
            return redirect('/admin')

        flash("Invalid credentials")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# -------- ADMIN -------- #

@app.route('/admin')
def admin():
    if 'user_id' not in session:
        return redirect('/login')

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
    if 'user_id' not in session:
        return redirect('/login')

    if request.method == 'POST':
        loc = Location(
            name=request.form['name'],
            latitude=float(request.form['latitude']),
            longitude=float(request.form['longitude'])
        )
        db.session.add(loc)
        db.session.commit()

        return redirect('/admin')

    return render_template('add_location.html')

# -------- LIVE DETECTION PAGE -------- #

@app.route('/admin_detect')
def admin_detect():
    return render_template('admin_detect.html')

# -------- DETECTION API -------- #

@app.route('/detect_vehicle', methods=['POST'])
def detect_vehicle():
    file = request.files['image']
    result = detect_vehicle_api(file)

    predictions = result.get("predictions", [])

    if len(predictions) > 0:
        slot = Slot.query.filter_by(status="free").first()

        if slot:
            slot.status = "booked"
            db.session.add(VehicleLog(slot_id=slot.id))
            db.session.commit()

    return jsonify(result)

# -------- RUN -------- #

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
