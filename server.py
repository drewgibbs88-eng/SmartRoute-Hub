### --- SmartRoute SaaS Multi-Tenant Server Engine ---
import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import stripe
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

from models import db, User, Booking, ServiceItem
from webhooks import webhooks_bp

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-key-change-in-production')

# PostgreSQL Compatibility Fix
raw_db_url = os.environ.get('DATABASE_URL', 'sqlite:///smartroute.db')
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = raw_db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
app.register_blueprint(webhooks_bp)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

with app.app_context():
    db.create_all()

# Automated Spatial Geocoding Engine
geolocator = Nominatim(user_agent="smartroute_hub_app")

def calculate_distance_from_addresses(biz_address, client_address):
    try:
        biz_loc = geolocator.geocode(biz_address)
        client_loc = geolocator.geocode(client_address)
        if biz_loc and client_loc:
            biz_coords = (biz_loc.latitude, biz_loc.longitude)
            client_coords = (client_loc.latitude, client_loc.longitude)
            distance_miles = geodesic(biz_coords, client_coords).miles
            return round(distance_miles, 1)
    except Exception as e:
        print(f"⚠️ Geocoding lookup failed: {str(e)}")
    return 5.0

def calculate_travel_time(miles):
    average_speed_mph = 30
    minutes_per_mile = 60 / average_speed_mph
    return round(miles * minutes_per_mile, 1)

@app.route('/')
@login_required
def dashboard():
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.start_time.asc()).all()
    total_revenue = sum(b.total_cost for b in bookings if b.status in ['confirmed', 'arrived'])
    total_miles = sum(b.distance_miles for b in bookings if b.status in ['confirmed', 'arrived'])
    return render_template('index.html', bookings=bookings, revenue=total_revenue, miles=total_miles)

@app.route('/update_booking_status/<int:booking_id>/<new_status>', methods=['POST'])
@login_required
def update_booking_status(booking_id, new_status):
    booking = Booking.query.filter_by(id=booking_id, user_id=current_user.id).first_or_404()
    if new_status in ['cancelled', 'arrived']:
        booking.status = new_status
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/calendar')
@login_required
def calendar():
    bookings = Booking.query.filter_by(user_id=current_user.id).all()
    events = []
    for b in bookings:
        events.append({
            'id': b.id,
            'title': f"{b.client_name} ({b.service_name})",
            'start': b.start_time.isoformat(),
            'url': f"https://www.google.com/maps/dir/?api=1&destination={b.destination_postcode}",
            'backgroundColor': '#16a34a' if b.status == 'confirmed' else '#ca8a04',
            'borderColor': '#16a34a' if b.status == 'confirmed' else '#ca8a04',
        })
    return render_template('calendar.html', events_json=json.dumps(events))

@app.route('/financials')
@login_required
def financials():
    confirmed_bookings = Booking.query.filter_by(user_id=current_user.id).filter(Booking.status.in_(['confirmed', 'arrived'])).all()
    total_gbv = sum(b.total_cost for b in confirmed_bookings)
    deposits_held = sum(b.deposit_amount for b in confirmed_bookings)
    total_miles = sum(b.distance_miles for b in confirmed_bookings)
    hmrc_tax_deduction = float(total_miles) * 0.45
    
    return render_template('financials.html', gbv=total_gbv, deposits=deposits_held, miles=total_miles, tax_deduction=hmrc_tax_deduction, bookings=confirmed_bookings)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        if 'add_service' in request.form:
            name = request.form.get('service_name')
            price = float(request.form.get('service_price'))
            new_service = ServiceItem(user_id=current_user.id, name=name, price=price)
            db.session.add(new_service)
            db.session.commit()
            flash('Service added successfully.', 'success')
        else:
            current_user.business_name = request.form.get('business_name')
            current_user.dispatch_postcode = request.form.get('dispatch_postcode')
            current_user.phone_number = request.form.get('phone_number')
            current_user.travel_fee_per_mile = float(request.form.get('travel_fee_per_mile', 1.50))
            db.session.commit()
            flash('Settings updated successfully.', 'success')
        return redirect(url_for('settings'))
    
    services = ServiceItem.query.filter_by(user_id=current_user.id).all()
    return render_template('settings.html', services=services)

@app.route('/delete_service/<int:service_id>', methods=['POST'])
@login_required
def delete_service(service_id):
    service = ServiceItem.query.get_or_404(service_id)
    if service.user_id == current_user.id:
        db.session.delete(service)
        db.session.commit()
    return redirect(url_for('settings'))

@app.route('/book/<public_id>', methods=['GET', 'POST'])
def public_book(public_id):
    owner = User.query.filter_by(id=1).first_or_404()
    services = ServiceItem.query.filter_by(user_id=owner.id).all()
    
    if request.method == 'POST':
        client_name = request.form.get('client_name')
        client_email = request.form.get('client_email')
        client_phone = request.form.get('client_phone')
        dest_postcode = request.form.get('destination_postcode')
        start_time_str = request.form.get('start_time')
        service_id = request.form.get('service_id')
        
        selected_service = ServiceItem.query.filter_by(id=service_id, user_id=owner.id).first()
        if not selected_service:
            return "Invalid service selected.", 400
            
        start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
        distance_miles = calculate_distance_from_addresses(owner.dispatch_postcode, dest_postcode)
        travel_time_mins = calculate_travel_time(distance_miles)
        
        base_cost = float(selected_service.price)
        travel_cost = float(distance_miles) * float(owner.travel_fee_per_mile)
        total_cost = base_cost + travel_cost
        deposit_amount = (total_cost * 0.20) + 1.00
        
        new_booking = Booking(
            user_id=owner.id,
            client_name=client_name,
            client_email=client_email,
            client_phone=client_phone,
            destination_postcode=dest_postcode,
            service_name=selected_service.name,
            start_time=start_time,
            base_cost=base_cost,
            travel_cost=travel_cost,
            total_cost=total_cost,
            deposit_amount=deposit_amount,
            platform_fee=1.00,
            distance_miles=distance_miles,
            travel_time_mins=travel_time_mins,
            status='pending'
        )
        db.session.add(new_booking)
        db.session.commit()
        
        stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
        domain = request.host_url.rstrip('/')
        
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            client_reference_id=str(new_booking.id),
            line_items=[{
                'price_data': {
                    'currency': 'gbp',
                    'product_data': {'name': f"Deposit: {selected_service.name} ({dest_postcode})"},
                    'unit_amount': int(deposit_amount * 100),
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f"{domain}/booking_success/{new_booking.public_id}",
            cancel_url=f"{domain}/book/{public_id}",
        )
        return redirect(session.url, code=303)

    return render_template('public_book.html', owner=owner, services=services)

@app.route('/booking_success/<public_id>')
def booking_success(public_id):
    booking = Booking.query.filter_by(public_id=public_id).first_or_404()
    return render_template('public_success.html', booking=booking)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email_input = request.form.get('email', '').lower().strip()
        raw_password = request.form.get('password')
        business_name = request.form.get('business_name') or request.form.get('name')
        dispatch_postcode = request.form.get('dispatch_postcode') or 'SW1A 1AA'
        
        if not business_name or not email_input or not raw_password:
            flash('Missing required registration fields.', 'danger')
            return redirect(url_for('signup'))
        
        existing_user = db.session.execute(db.select(User).filter_by(email=email_input)).scalar_one_or_none()
        if existing_user:
            flash('This email is already registered. Please log in.', 'danger')
            return redirect(url_for('login'))

        hashed_pw = generate_password_hash(raw_password)
        new_user = User(
            email=email_input,
            password_hash=hashed_pw,
            business_name=business_name,
            dispatch_postcode=dispatch_postcode
        )
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        return redirect(url_for('dashboard'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email_input = request.form.get('email', '').lower().strip()
        user = db.session.execute(db.select(User).filter_by(email=email_input)).scalar_one_or_none()
        if user and check_password_hash(user.password_hash, request.form.get('password')):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)