"""
app.py: Enterprise Tiered Business Management & Mobile Dispatch Engine.
Features:
- Model B (£0/mo + £1 fee) -> Pro Tier (£19/mo) -> Fleet Tier (£49/mo) Entitlements
- Dynamic Service Bundles & Add-On Upsells
- Automated Distance Surcharges (Beyond Free Mileage Radius)
- Multi-Van Staff & Subcontractor Route Allocation
- Automated HMRC Mileage Auto-Vault & Tax CSV Export
- Asynchronous Cryptographic Stripe Webhooks & BOLA-Isolated API
"""
import os
import io
import csv
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from flask import (
    Flask, render_template, request, redirect, url_for, 
    jsonify, abort, flash, Response
)
from flask_login import LoginManager, login_required, current_user, login_user, logout_user
from werkzeug.middleware.proxy_fix import ProxyFix

try:
    import stripe
except ImportError:
    stripe = None

from models import (
    db, User, Booking, ServiceItem, AddonItem, 
    ServiceBundle, StaffWorker, BookingStatus, SubscriptionTier
)
from geospatial import UKRoutingEngine
from security import tenant_booking_required
from webhooks import webhook_bp

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "smartroute-enterprise-secret-key-87612")

# Database URI configuration
db_uri = os.getenv("DATABASE_URL", "sqlite:///smartroute.db")
if db_uri.startswith("postgres://"):
    db_uri = db_uri.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Reverse proxy support for Render
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

if stripe:
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_mock")

app.register_blueprint(webhook_bp)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

with app.app_context():
    db.create_all()


# --- AUTHENTICATION & ONBOARDING ---

@app.route("/welcome")
def welcome():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("welcome.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        business_name = request.form.get("business_name", "").strip()
        phone = request.form.get("phone", "").strip()
        base_postcode = request.form.get("base_postcode", "").strip().upper()

        if not email or not password or not business_name or not base_postcode:
            flash("All fields are required.", "error")
            return render_template("signup.html")

        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "error")
            return render_template("signup.html")

        coords = UKRoutingEngine.get_coordinates(base_postcode)

        new_user = User(
            email=email,
            business_name=business_name,
            phone=phone,
            base_postcode=base_postcode,
            base_lat=Decimal(str(coords[0])) if coords else None,
            base_lng=Decimal(str(coords[1])) if coords else None,
            subscription_tier=SubscriptionTier.STARTER
        )
        new_user.set_password(password)

        # Preload starter services, add-ons, and bundles
        starter_services = [
            ServiceItem(name="Full Exterior Valet & Wax", description="High-gloss snow foam wash, wheel decon, and ceramic spray sealant", duration_minutes=60, base_price=Decimal("65.00"), is_popular=True),
            ServiceItem(name="Deep Interior & Upholstery Shampoo", description="Deep steam clean, leather nourishment, and stain extraction", duration_minutes=75, base_price=Decimal("85.00")),
            ServiceItem(name="Signature Full Detail (In & Out)", description="Complete paint rejuvenation, interior deep clean, and engine bay detail", duration_minutes=150, base_price=Decimal("160.00"), is_popular=True),
        ]
        starter_addons = [
            AddonItem(name="Pet Hair Specialist Extraction", price=Decimal("20.00"), extra_minutes=20, description="Dedicated mechanical pet hair removal"),
            AddonItem(name="12-Month Ceramic Gloss Shield", price=Decimal("35.00"), extra_minutes=25, description="Hydrophobic SiO2 ceramic paint protection"),
            AddonItem(name="Headlight Oxidation Restoration", price=Decimal("30.00"), extra_minutes=20, description="Wet sand & polish to crystal clear factory finish"),
        ]
        starter_bundles = [
            ServiceBundle(name="The Showroom Transformation Bundle", description="Full Interior + Ceramic Exterior + Pet Hair Treatment", bundle_price=Decimal("195.00"), savings_badge="Save £35", duration_minutes=180),
        ]

        new_user.services.extend(starter_services)
        new_user.addons.extend(starter_addons)
        new_user.bundles.extend(starter_bundles)

        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        flash("Welcome! Your business management hub and public booking portal are live.", "success")
        return redirect(url_for("dashboard"))

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user, remember=True)
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password.", "error")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("login"))


# --- CORE BUSINESS MANAGEMENT DASHBOARD ---

@app.route("/")
@login_required
def dashboard():
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.start_time.desc()).all()
    
    total_gbv = sum(b.total_cost for b in bookings if b.status != BookingStatus.CANCELLED)
    total_deposits = sum(b.deposit_amount for b in bookings if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
    total_platform_fees = sum(b.platform_fee for b in bookings if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
    net_earnings = total_gbv - total_platform_fees
    confirmed_count = sum(1 for b in bookings if b.status == BookingStatus.CONFIRMED)
    
    # HMRC Mileage
    total_miles = sum((b.travel_miles or Decimal("0.0")) for b in bookings if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
    hmrc_savings = total_miles * Decimal("0.45")

    workers = StaffWorker.query.filter_by(user_id=current_user.id).all()

    return render_template(
        "index.html",
        user=current_user,
        bookings=bookings,
        total_gbv=total_gbv,
        total_deposits=total_deposits,
        net_earnings=net_earnings,
        confirmed_count=confirmed_count,
        total_miles=total_miles,
        hmrc_savings=hmrc_savings,
        workers=workers
    )


# --- FINANCIALS & HMRC TAX VAULT ---

@app.route("/financials")
@login_required
def financials():
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.start_time.desc()).all()
    
    gbv = sum(b.total_cost for b in bookings if b.status != BookingStatus.CANCELLED)
    deposits_held = sum(b.deposit_amount for b in bookings if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
    platform_fees = sum(b.platform_fee for b in bookings if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
    cash_to_collect = sum((b.total_cost - b.deposit_amount) for b in bookings if b.status == BookingStatus.CONFIRMED)
    net_profit = gbv - platform_fees

    total_miles = sum((b.travel_miles or Decimal("0.0")) for b in bookings if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
    hmrc_deduction = total_miles * Decimal("0.45")

    return render_template(
        "financials.html",
        user=current_user,
        bookings=bookings,
        gbv=gbv,
        deposits_held=deposits_held,
        platform_fees=platform_fees,
        cash_to_collect=cash_to_collect,
        net_profit=net_profit,
        total_miles=total_miles,
        hmrc_deduction=hmrc_deduction
    )

@app.route("/financials/export_hmrc_csv")
@login_required
def export_hmrc_csv():
    """Generates an HMRC-compliant mileage & revenue audit export."""
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.start_time.asc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Booking Ref", "Date", "Client Name", "Client Postcode", 
        "Miles Logged", "HMRC Rate", "Allowable Travel Expense (£)", 
        "Gross Booked (£)", "Deposit Collected (£)", "Status"
    ])

    for b in bookings:
        miles = float(b.travel_miles or 0.0)
        expense = round(miles * 0.45, 2)
        writer.writerow([
            b.booking_reference,
            b.start_time.strftime("%Y-%m-%d %H:%M"),
            b.client_name,
            b.client_postcode,
            f"{miles:.2f}",
            "£0.45/mile",
            f"£{expense:.2f}",
            f"£{float(b.total_cost):.2f}",
            f"£{float(b.deposit_amount):.2f}",
            b.status.value
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=HMRC_Tax_Ledger_{current_user.business_name.replace(' ', '_')}.csv"}
    )


# --- SUBSCRIPTION TIERS & BUNDLE MONETIZATION ---

@app.route("/billing")
@login_required
def billing():
    """Tier plan overview & upgrade management."""
    return render_template("billing.html", user=current_user)

@app.route("/upgrade/<tier_name>", methods=["POST"])
@login_required
def upgrade_tier(tier_name):
    """Simulated/Live Tier Upgrade Handler."""
    tier_map = {
        "starter": SubscriptionTier.STARTER,
        "pro_solo": SubscriptionTier.PRO_SOLO,
        "fleet_pro": SubscriptionTier.FLEET_PRO
    }
    target_tier = tier_map.get(tier_name.lower())
    if not target_tier:
        flash("Invalid subscription plan requested.", "error")
        return redirect(url_for("billing"))

    current_user.subscription_tier = target_tier
    db.session.commit()
    flash(f"Success! Your plan has been upgraded to {target_tier.value.upper().replace('_', ' ')}.", "success")
    return redirect(url_for("billing"))


# --- SERVICE CATALOG & BUNDLE BUILDER ---

@app.route("/services", methods=["GET", "POST"])
@login_required
def manage_services():
    """Allows business owners to manage services, add-ons, and bundles."""
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "add_service":
            name = request.form.get("name", "").strip()
            price = Decimal(request.form.get("price", "50.00"))
            duration = int(request.form.get("duration", 60))
            desc = request.form.get("description", "").strip()
            item = ServiceItem(user_id=current_user.id, name=name, base_price=price, duration_minutes=duration, description=desc)
            db.session.add(item)
            db.session.commit()
            flash(f"Service '{name}' added successfully.", "success")
            
        elif action == "add_addon":
            name = request.form.get("name", "").strip()
            price = Decimal(request.form.get("price", "20.00"))
            extra_min = int(request.form.get("extra_minutes", 15))
            desc = request.form.get("description", "").strip()
            addon = AddonItem(user_id=current_user.id, name=name, price=price, extra_minutes=extra_min, description=desc)
            db.session.add(addon)
            db.session.commit()
            flash(f"Add-on '{name}' added successfully.", "success")

        elif action == "add_bundle":
            name = request.form.get("name", "").strip()
            price = Decimal(request.form.get("price", "150.00"))
            badge = request.form.get("savings_badge", "Save £25")
            desc = request.form.get("description", "").strip()
            bundle = ServiceBundle(user_id=current_user.id, name=name, bundle_price=price, savings_badge=badge, description=desc)
            db.session.add(bundle)
            db.session.commit()
            flash(f"Promotional Bundle '{name}' created.", "success")

        return redirect(url_for("manage_services"))

    services = ServiceItem.query.filter_by(user_id=current_user.id).all()
    addons = AddonItem.query.filter_by(user_id=current_user.id).all()
    bundles = ServiceBundle.query.filter_by(user_id=current_user.id).all()

    return render_template("services.html", user=current_user, services=services, addons=addons, bundles=bundles)

@app.route("/delete_item/<item_type>/<int:item_id>", methods=["POST"])
@login_required
def delete_service_item(item_type, item_id):
    if item_type == "service":
        item = ServiceItem.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    elif item_type == "addon":
        item = AddonItem.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    elif item_type == "bundle":
        item = ServiceBundle.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    else:
        abort(400)

    db.session.delete(item)
    db.session.commit()
    flash("Item removed from catalog.", "info")
    return redirect(url_for("manage_services"))


# --- MULTI-VAN FLEET & STAFF MANAGEMENT ---

@app.route("/fleet", methods=["GET", "POST"])
@login_required
def fleet_management():
    if current_user.subscription_tier != SubscriptionTier.FLEET_PRO:
        flash("Multi-van fleet dispatch is available exclusively on the Fleet Pro Tier (£49/mo).", "info")
        return redirect(url_for("billing"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        van_reg = request.form.get("van_registration", "").strip().upper()
        commission = Decimal(request.form.get("commission_rate_percent", "60.0"))

        worker = StaffWorker(
            user_id=current_user.id,
            name=name,
            phone=phone,
            van_registration=van_reg,
            commission_rate_percent=commission
        )
        db.session.add(worker)
        db.session.commit()
        flash(f"Staff / Van Driver '{name}' added to your fleet.", "success")
        return redirect(url_for("fleet_management"))

    workers = StaffWorker.query.filter_by(user_id=current_user.id).all()
    return render_template("fleet.html", user=current_user, workers=workers)

@app.route("/assign_worker/<int:booking_id>", methods=["POST"])
@login_required
@tenant_booking_required
def assign_worker(booking):
    worker_id = request.form.get("worker_id")
    if worker_id:
        worker = StaffWorker.query.filter_by(id=int(worker_id), user_id=current_user.id).first_or_404()
        booking.worker_id = worker.id
    else:
        booking.worker_id = None
    db.session.commit()
    flash(f"Route for {booking.client_name} updated.", "success")
    return redirect(request.referrer or url_for("dashboard"))


# --- CALENDAR & SETTINGS ---

@app.route("/calendar")
@login_required
def calendar():
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.start_time.asc()).all()
    workers = StaffWorker.query.filter_by(user_id=current_user.id).all()
    return render_template("calendar.html", user=current_user, bookings=bookings, workers=workers)

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        current_user.business_name = request.form.get("business_name", current_user.business_name).strip()
        current_user.phone = request.form.get("phone", current_user.phone).strip()
        current_user.base_postcode = request.form.get("base_postcode", current_user.base_postcode).strip().upper()
        current_user.free_travel_radius_miles = Decimal(request.form.get("free_travel_radius_miles", "5.0"))
        current_user.travel_charge_per_mile = Decimal(request.form.get("travel_charge_per_mile", "1.50"))
        current_user.bio = request.form.get("bio", "").strip()

        coords = UKRoutingEngine.get_coordinates(current_user.base_postcode)
        if coords:
            current_user.base_lat = Decimal(str(coords[0]))
            current_user.base_lng = Decimal(str(coords[1]))

        db.session.commit()
        flash("Dispatch settings updated successfully.", "success")
        return redirect(url_for("settings"))

    return render_template("settings.html", user=current_user)

@app.route("/delete_booking/<int:booking_id>", methods=["POST"])
@login_required
@tenant_booking_required
def delete_booking(booking):
    db.session.delete(booking)
    db.session.commit()
    flash(f"Booking {booking.booking_reference} removed.", "info")
    return redirect(request.referrer or url_for("dashboard"))


# --- ADVANCED CLIENT PUBLIC BOOKING PORTAL (DYNAMIC BUNDLE & ADD-ON ENGINE) ---

@app.route("/book/<uuid:public_uuid>", methods=["GET", "POST"])
def public_book(public_uuid):
    provider = User.query.filter_by(public_uuid=public_uuid).first_or_404()
    services = ServiceItem.query.filter_by(user_id=provider.id).all()
    addons = AddonItem.query.filter_by(user_id=provider.id).all()
    bundles = ServiceBundle.query.filter_by(user_id=provider.id).all()

    if request.method == "POST":
        client_name = request.form.get("client_name", "").strip()
        client_email = request.form.get("client_email", "").strip()
        client_phone = request.form.get("client_phone", "").strip()
        client_address = request.form.get("client_address", "").strip()
        client_postcode = request.form.get("client_postcode", "").strip().upper()
        vehicle_details = request.form.get("vehicle_details", "").strip()
        booking_time_str = request.form.get("booking_time", "")
        selection_type = request.form.get("selection_type", "service")  # 'service' or 'bundle'
        selected_service_id = request.form.get("service_id")
        selected_bundle_id = request.form.get("bundle_id")
        selected_addon_ids = request.form.getlist("addon_ids")
        notes = request.form.get("notes", "").strip()

        if not client_name or not client_email or not client_phone or not client_postcode or not booking_time_str:
            flash("Please complete all required fields.", "error")
            return render_template("public_book.html", provider=provider, services=services, addons=addons, bundles=bundles)

        try:
            start_time = datetime.fromisoformat(booking_time_str)
        except ValueError:
            flash("Invalid date format.", "error")
            return render_template("public_book.html", provider=provider, services=services, addons=addons, bundles=bundles)

        # 1. Base / Bundle Calculation
        if selection_type == "bundle" and selected_bundle_id:
            bundle_obj = ServiceBundle.query.filter_by(id=int(selected_bundle_id), user_id=provider.id).first_or_404()
            service_name = f"BUNDLE: {bundle_obj.name}"
            service_subtotal = bundle_obj.bundle_price
            duration = bundle_obj.duration_minutes
        else:
            service_obj = ServiceItem.query.filter_by(id=int(selected_service_id), user_id=provider.id).first() if selected_service_id else None
            if service_obj:
                service_name = service_obj.name
                service_subtotal = service_obj.base_price
                duration = service_obj.duration_minutes
            else:
                service_name = "Mobile Valet Service"
                service_subtotal = Decimal("65.00")
                duration = 60

        # 2. Add-Ons Calculation
        addons_subtotal = Decimal("0.00")
        addon_names = []
        if selected_addon_ids:
            for aid in selected_addon_ids:
                addon_obj = AddonItem.query.filter_by(id=int(aid), user_id=provider.id).first()
                if addon_obj:
                    addons_subtotal += addon_obj.price
                    duration += addon_obj.extra_minutes
                    addon_names.append(f"{addon_obj.name} (+£{addon_obj.price:.2f})")

        # 3. Travel Distance & Congestion-Aware Surcharge Calculation
        travel = UKRoutingEngine.calculate_travel(provider.base_postcode, client_postcode)
        travel_miles = Decimal(str(travel["miles"]))
        
        # Calculate travel surcharge beyond free radius
        free_radius = provider.free_travel_radius_miles or Decimal("5.0")
        per_mile_fee = provider.travel_charge_per_mile or Decimal("1.50")
        
        if travel_miles > free_radius:
            excess_miles = travel_miles - free_radius
            travel_surcharge = round(excess_miles * per_mile_fee, 2)
        else:
            travel_surcharge = Decimal("0.00")

        # 4. Total Cost, Deposit & Platform Fees
        total_cost = service_subtotal + addons_subtotal + travel_surcharge
        deposit = round(total_cost * Decimal("0.20"), 2)
        platform_fee = Decimal(str(provider.platform_fee_amount))

        booking = Booking(
            user_id=provider.id,
            service_name=service_name,
            selected_addons_summary=", ".join(addon_names) if addon_names else "None",
            client_name=client_name,
            client_email=client_email,
            client_phone=client_phone,
            client_address=client_address,
            client_postcode=client_postcode,
            vehicle_details=vehicle_details,
            notes=notes,
            start_time=start_time,
            end_time=start_time + timedelta(minutes=duration),
            service_subtotal=service_subtotal,
            addons_subtotal=addons_subtotal,
            travel_surcharge=travel_surcharge,
            total_cost=total_cost,
            deposit_amount=deposit,
            platform_fee=platform_fee,
            travel_miles=travel_miles,
            travel_minutes=travel["minutes"],
            hmrc_allowable_expense=round(travel_miles * Decimal("0.45"), 2),
            status=BookingStatus.PENDING_PAYMENT
        )
        db.session.add(booking)
        db.session.commit()

        # Build Stripe Checkout Session
        try:
            line_items = [
                {
                    "price_data": {
                        "currency": "gbp",
                        "unit_amount": int(deposit * 100),
                        "product_data": {
                            "name": f"20% Deposit: {service_name}",
                            "description": f"Ref: {booking.booking_reference} ({provider.business_name})"
                        },
                    },
                    "quantity": 1,
                }
            ]

            # Ingest convenience fee if on Starter Tier
            if platform_fee > 0:
                line_items.append({
                    "price_data": {
                        "currency": "gbp",
                        "unit_amount": int(platform_fee * 100),
                        "product_data": {
                            "name": "SmartRoute Hub Convenience Fee",
                            "description": "Secure slot protection & route dispatch"
                        },
                    },
                    "quantity": 1,
                })

            checkout_session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=line_items,
                mode="payment",
                client_reference_id=booking.booking_reference,
                customer_email=client_email,
                success_url=url_for("payment_success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=url_for("public_book", public_uuid=public_uuid, _external=True),
            )

            booking.stripe_session_id = checkout_session.id
            db.session.commit()

            return redirect(checkout_session.url, code=303)

        except Exception:
            # Local simulator fallback
            booking.status = BookingStatus.CONFIRMED
            db.session.commit()
            return redirect(url_for("payment_success", ref=booking.booking_reference))

    return render_template(
        "public_book.html",
        provider=provider,
        services=services,
        addons=addons,
        bundles=bundles
    )

@app.route("/payment_success")
def payment_success():
    session_id = request.args.get("session_id")
    ref = request.args.get("ref")
    booking = None

    if session_id:
        booking = Booking.query.filter_by(stripe_session_id=session_id).first()
    elif ref:
        booking = Booking.query.filter_by(booking_reference=ref).first()

    return render_template("public_success.html", booking=booking)

@app.route("/api/calculate_travel", methods=["POST"])
def api_calculate_travel():
    data = request.get_json() or {}
    origin = data.get("origin_postcode", "")
    dest = data.get("dest_postcode", "")
    metrics = UKRoutingEngine.calculate_travel(origin, dest)
    return jsonify(metrics)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
