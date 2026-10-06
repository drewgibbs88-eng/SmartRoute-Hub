### --- SmartRoute SaaS Multi-Tenant Server Engine ---
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date as dt_date
from flask_sqlalchemy import SQLAlchemy
import stripe
import os
import uuid

app = Flask(__name__)

### 🔐 CLOUD APP SECURITY LAYER CONFIGURATIONS
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super-secure-dev-fallback-string")
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "sk_test_51...") # Replace with your test key if using env vars

### DATABASE CONFIGURATION (Render PostgreSQL or Local SQLite)
database_url = os.environ.get("DATABASE_URL", "sqlite:///smartroute.db")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

### 1. CORE ENTERPRISE SESSION MANAGER INITIALIZATION
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

### 2. STANDARDIZED PRICE MATRIX RATE CARD
PRICE_MATRIX = {
    "haircut": 25.00,
    "blowdry": 10.00,
    "nails": 30.00
}

### 3. TRANSIT LOGIC OPTIMIZATION ENGINE
def calculate_travel_time(miles):
    average_speed_mph = 30
    minutes_per_mile = 60 / average_speed_mph
    return round(miles * minutes_per_mile, 1)

### 4. RELATIONAL DATABASE MODELS
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    platform_fee_pence = db.Column(db.Integer, default=100) # Founder's Club 50p or standard £1.00 fee
    
    bookings = db.relationship('Booking', backref='owner', lazy=True, cascade="all, delete-orphan")

class Booking(db.Model):
    __tablename__ = 'bookings'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    booking_uuid = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    service = db.Column(db.String(50), nullable=False)
    distance = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    deposit_required = db.Column(db.Float, nullable=False)
    date = db.Column(db.String(20), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Automatically create database tables if they don't exist yet
with app.app_context():
    db.create_all()

### --- APPLICATION WEB ROUTES (AUTHENTICATION ENGINE) ---

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email").lower().strip()
        raw_password = request.form.get("password")
        
        existing_user = db.session.execute(db.select(User).filter_by(email=email)).scalar_one_or_none()
        if existing_user:
            return "⚠️ This business email is already registered."
            
        user_count = db.session.query(User).count()
        assigned_fee = 50 if user_count < 10 else 100 # Founder's Club 50p fee for first 10 users

        hashed_password = generate_password_hash(raw_password)
        new_user = User(name=name, email=email, password=hashed_password, platform_fee_pence=assigned_fee)
        
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        return redirect(url_for("dashboard"))
        
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email").lower().strip()
        password = request.form.get("password")
        
        user = db.session.execute(db.select(User).filter_by(email=email)).scalar_one_or_none()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("dashboard"))
                
        return "⚠️ Invalid business credentials provided."
        
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

### --- CORE OPERATIONAL APPLICATION BUSINESS ROUTES ---

@app.route("/")
@login_required
def dashboard():
    today_str = dt_date.today().strftime("%Y-%m-%d")
    selected_filter_date = request.args.get("filter_date", today_str)
    
    user_bookings = Booking.query.filter_by(user_id=current_user.id, date=selected_filter_date).all()
    
    filtered_bookings = []
    revenue = 0.0
    deposits = 0.0
    
    for appt in user_bookings:
        revenue += appt.total_cost
        deposits += appt.deposit_required
        
        booking_data = {
            "id": appt.booking_uuid,
            "name": appt.name,
            "service": appt.service,
            "distance": appt.distance,
            "total_cost": appt.total_cost,
            "deposit_required": appt.deposit_required,
            "date": appt.date,
            "drive_time": calculate_travel_time(appt.distance)
        }
        filtered_bookings.append(booking_data)

    return render_template(
        "index.html", 
        bookings=filtered_bookings, 
        current_filter_date=selected_filter_date,
        total_revenue=f"{revenue:.2f}", 
        total_deposits=f"{deposits:.2f}",
        cash_owed=f"{(revenue - deposits):.2f}",
        user_profile=current_user
    )

@app.route("/add_booking", methods=["POST"])
@login_required
def add_booking():
    client_name = request.form.get("name")
    selected_service = request.form.get("service")
    client_distance = float(request.form.get("distance"))
    selected_date = request.form.get("booking_date")
    
    total_cost = PRICE_MATRIX.get(selected_service, 50.00)
    deposit_required = total_cost * 0.20
    deposit_in_cents = int(deposit_required * 100)
    platform_fee_in_pence = getattr(current_user, 'platform_fee_pence', 100)

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price_data': {
                        'currency': 'gbp',
                        'product_data': {
                            'name': f"20% Secure Deposit for {selected_service.capitalize()}",
                            'description': f"Client Intake Profile: {client_name}",
                        },
                        'unit_amount': deposit_in_cents,
                    },
                    'quantity': 1,
                },
                {
                    'price_data': {
                        'currency': 'gbp',
                        'product_data': {
                            'name': "SmartRoute Secure Booking Fee",
                        },
                        'unit_amount': platform_fee_in_pence,
                    },
                    'quantity': 1,
                }
            ],
            mode='payment',
            success_url=url_for(
                'payment_success', 
                name=client_name, 
                service=selected_service, 
                distance=client_distance, 
                date=selected_date, 
                cost=total_cost, 
                dep=deposit_required, 
                owner=current_user.id, 
                _external=True
            ),
            cancel_url=url_for('dashboard', _external=True)
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        print(f"⚠️ Stripe API Session Creation Failed: {str(e)}")
        return redirect(url_for("dashboard"))

@app.route("/payment_success")
def payment_success():
    new_booking = Booking(
        user_id=request.args.get("owner"),
        booking_uuid=uuid.uuid4().hex[:8],
        name=request.args.get("name"),
        service=request.args.get("service"),
        distance=float(request.args.get("distance")),
        total_cost=float(request.args.get("cost")),
        deposit_required=float(request.args.get("dep")),
        date=request.args.get("date")
    )
    db.session.add(new_booking)
    db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/delete_booking/<booking_uuid>")
@login_required
def delete_booking(booking_uuid):
    booking = Booking.query.filter_by(booking_uuid=booking_uuid, user_id=current_user.id).first()
    if booking:
        db.session.delete(booking)
        db.session.commit()
    return redirect(url_for("dashboard"))

### ROUTE: LIVE FINANCIAL SPOT CHECK & P&L
@app.route("/financials", methods=["GET", "POST"])
@login_required
def financials():
    user_bookings = Booking.query.filter_by(user_id=current_user.id).all()
    
    today_str = dt_date.today().strftime("%Y-%m-%d")
    current_month = today_str[:7]
    current_year = today_str[:4]
    
    daily_rev = sum(b.total_cost for b in user_bookings if b.date == today_str)
    monthly_rev = sum(b.total_cost for b in user_bookings if b.date.startswith(current_month))
    annual_rev = sum(b.total_cost for b in user_bookings if b.date.startswith(current_year))
    
    cogs = 0.0
    overhead = 0.0
    
    if request.method == "POST":
        cogs = float(request.form.get("cogs", 0))
        overhead = float(request.form.get("overhead", 0))
        
    monthly_net_profit = monthly_rev - (cogs + overhead)

    return render_template(
        "financials.html",
        daily=f"{daily_rev:.2f}",
        monthly=f"{monthly_rev:.2f}",
        annual=f"{annual_rev:.2f}",
        cogs=f"{cogs:.2f}",
        overhead=f"{overhead:.2f}",
        net_profit=f"{monthly_net_profit:.2f}",
        user_profile=current_user
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)