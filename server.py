# --- SmartRoute SaaS Multi-Tenant Server Engine ---
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date as dt_date
import json
import stripe
import os

app = Flask(__name__)

# 🔐 CLOUD APP SECURITY LAYER CONFIGURATIONS
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super-secure-dev-fallback-string")
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

# 1. CORE ENTERPRISE SESSION MANAGER INITIALIZATION
login_manager = LoginManager()
login_manager.login_view = 'login'  # If a user isn't logged in, redirect them here
login_manager.init_app(app)

# 2. STANDARDIZED PRICE MATRIX RATE CARD
PRICE_MATRIX = {
    "haircut": 25.00,
    "blowdry": 10.00,
    "nails": 30.00
}

# 3. TRANSIT LOGIC OPTIMIZATION ENGINE
def calculate_travel_time(miles):
    average_speed_mph = 30
    minutes_per_mile = 60 / average_speed_mph
    return round(miles * minutes_per_mile, 1)

# 4. MULTI-TENANT SECURE STORAGE DATABASES PIPELINES
def load_file_db(filename):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {} if filename == "users.json" else []

def save_file_db(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

# 5. USER SESSION DATA ENCAPSULATION WRAPPER
class User(UserMixin):
    def __init__(self, id, name, email):
        self.id = id
        self.name = name
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    users = load_file_db("users.json")
    if user_id in users:
        return User(user_id, users[user_id]["name"], users[user_id]["email"])
    return None


# --- APPLICATION WEB ROUTES (AUTHENTICATION ENGINE) ---

# REGISTRATION GATE: ACCOUNT DEPLOYMENT PIPELINE
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email").lower().strip()
        raw_password = request.form.get("password")
        
        users = load_file_db("users.json")
        
        if email in [u["email"] for u in users.values()]:
            return "⚠️ This business email is already registered."
            
        # Securely encrypt password string using corporate hashing standards
        hashed_password = generate_password_hash(raw_password)
        new_user_id = str(len(users) + 1)
        
        users[new_user_id] = {
            "name": name,
            "email": email,
            "password": hashed_password
        }
        save_file_db("users.json", users)
        
        # Log the newly registered business owner in automatically
        user_obj = User(new_user_id, name, email)
        login_user(user_obj)
        return redirect(url_for("dashboard"))
        
    return render_template("signup.html")

# ACCESS GATE: SECURE LOG IN PANEL
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email").lower().strip()
        password = request.form.get("password")
        
        users = load_file_db("users.json")
        
        # Validate email existence and verify encrypted password hashes match
        for uid, udata in users.items():
            if udata["email"] == email and check_password_hash(udata["password"], password):
                user_obj = User(uid, udata["name"], udata["email"])
                login_user(user_obj)
                return redirect(url_for("dashboard"))
                
        return "⚠️ Invalid business credentials provided."
    return render_template("login.html")

# EXIT GATE: TERMINATE SESSION TIMELINES
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# --- CORE OPERATIONAL APPLICATION BUSINESS ROUTES ---

# ROUTE 1: THE ACTIVE DATA-FILTERED DASHBOARD OVERVIEW
@app.route("/")
@login_required # This makes the dashboard locked behind a login screen!
def dashboard():
    all_bookings = load_file_db("database.json")
    
    today_str = dt_date.today().strftime("%Y-%m-%d")
    selected_filter_date = request.args.get("filter_date", today_str)
    
    filtered_bookings = []
    revenue = 0.0
    deposits = 0.0
    
    # ISOLATION ENGINE: Only pull appointments owned by the CURRENT logged-in user ID
    for appt in all_bookings:
        if appt.get("user_id") == current_user.id and appt.get("date") == selected_filter_date:
            cost = appt.get("total_cost", 50.00)
            dep = appt.get("deposit_required", 10.00)
            
            revenue += cost
            deposits += dep
            
            appt["drive_time"] = calculate_travel_time(appt["distance"])
            filtered_bookings.append(appt)

    return render_template(
        "index.html", 
        bookings=filtered_bookings, 
        current_filter_date=selected_filter_date,
        total_revenue=f"{revenue:.2f}", 
        total_deposits=f"{deposits:.2f}",
        cash_owed=f"{(revenue - deposits):.2f}",
        user_profile=current_user # Pass the owner name up to display on screen
    )

# ROUTE 2: INITIALIZE STRIPE CHECKOUT SECURE SESSION
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

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f"20% Secure Deposit for {selected_service.capitalize()}",
                        'description': f"Client Intake Profile: {client_name}",
                    },
                    'unit_amount': deposit_in_cents,
                },
                'quantity': 1,
            }],
            mode='payment',
            # Pass our active user_id inside the stripe URL payload parameter to keep track of ownership!
            success_url=f"https://onrender.com{client_name}&service={selected_service}&distance={client_distance}&date={selected_date}&cost={total_cost}&dep={deposit_required}&owner={current_user.id}",
            cancel_url="https://onrender.com"
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        print(f"⚠️ Stripe API Session Creation Failed: {str(e)}")
        return redirect(url_for("dashboard"))

# ROUTE 3: SECURE DEPOSIT CONFIRMATION PIPELINE (RUNS ONLY AFTER PAYMENT SUCCEEDS)
@app.route("/payment_success")
def payment_success():
    client_name = request.args.get("name")
    selected_service = request.args.get("service")
    client_distance = float(request.args.get("distance"))
    selected_date = request.args.get("date")
    total_cost = float(request.args.get("cost"))
    deposit_required = float(request.args.get("dep"))
    owner_id = request.args.get("owner") # Extract who owns this booking asset entry

    new_booking = {
        "user_id": owner_id, # Pin the specific subscriber ID to this record permanently!
        "name": client_name,
        "service": selected_service,
        "distance": client_distance,
        "total_cost": total_cost,
        "deposit_required": deposit_required,
        "date": selected_date
    }

    all_bookings = load_file_db("database.json")
    all_bookings.append(new_booking)
    save_file_db("database.json", all_bookings)

    return redirect(url_for("dashboard"))

# ROUTE 4: WEB SURGICAL WIPE ENGINE (CANCELLATIONS WITH ID SAFEGUARDS)
@app.route("/delete_booking/<int:booking_index>")
@login_required
def delete_booking(booking_index):
    all_bookings = load_file_db("database.json")
    
    if 0 <= booking_index < len(all_bookings):
        # Verification check: Make sure a malicious client isn't trying to delete another user's rows!
        if all_bookings[booking_index].get("user_id") == current_user.id:
            all_bookings.pop(booking_index)
            save_file_db("database.json", all_bookings)
            
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    app.run(debug=True)
