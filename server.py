# --- Mobile Booking & Smart Routing Server Engine ---
from flask import Flask, render_template, request, redirect
import json

app = Flask(__name__)

# 1. FIXED PRICE MATRIX RATE CARD
PRICE_MATRIX = {
    "haircut": 25.00,
    "blowdry": 10.00,
    "nails": 30.00
}

# 2. TRANSIT LOGIC OPTIMIZATION ENGINE
def calculate_travel_time(miles):
    average_speed_mph = 30
    minutes_per_mile = 60 / average_speed_mph
    return round(miles * minutes_per_mile, 1)

# 3. HELPER FUNCTIONS: FILE PERSISTENCE CONTROL PIPELINES
def load_database():
    try:
        with open("database.json", "r") as file_box:
            return json.load(file_box)
    except FileNotFoundError:
        return []

def save_database(data):
    with open("database.json", "w") as file_box:
        json.dump(data, file_box, indent=4)

# 4. TWILIO SMS GATEWAY NOTIFICATION SIMULATOR
def simulate_sms_notification(action_type, booking_profile):
    client = booking_profile['name']
    service = booking_profile['service']
    distance = booking_profile['distance']
    deposit = booking_profile['deposit_required']
   
    print("\n📱 === TWILIO SMS GATEWAY OUTBOUND OUTBOX ===")
   
    if action_type == "NEW_BOOKING":
        print(f"✉️ [To Client {client}]: Booking confirmed! Your 20% non-refundable deposit of ${deposit:.2f} has been secured via Stripe.")
        print(f"✉️ [To Business Owner]: New job added! {client} requested {service}. Drive is {distance} miles away. Check your SmartRoute Hub for optimization paths.")
       
    elif action_type == "CANCEL_BOOKING":
        print(f"✉️ [To Client {client}]: Your appointment for {service} has been successfully canceled. Your deposit of ${deposit:.2f} has been logged under cancellation parameters.")
        print(f"✉️ [To Business Owner]: Alert! {client} canceled their appointment for {service}. Slot has been opened back up in the database.")
       
    print("============================================\n")


# --- APPLICATION WEB ROUTES ---

# ROUTE 1: DISPLAY THE MAIN DARK DASHBOARD
from datetime import date as dt_date # Make sure this import is near the top or inside the route

@app.route("/")
def dashboard():
    active_bookings = load_database()
   
    # 1. Detect the requested date from the URL parameter.
    # If no parameter is passed, default automatically to today's date!
    today_str = dt_date.today().strftime("%Y-%m-%d")
    selected_filter_date = request.args.get("filter_date", today_str)
   
    filtered_bookings = []
    revenue = 0.0
    deposits = 0.0
   
    # 2. Filter loop matrix: Only pull entries matching the active selected date
    for appt in active_bookings:
        if appt.get("date") == selected_filter_date:
            cost = appt.get("total_cost", 50.00)
            dep = appt.get("deposit_required", 10.00)
           
            revenue += cost
            deposits += dep
           
            appt["drive_time"] = calculate_travel_time(appt["distance"])
            filtered_bookings.append(appt)

    # 3. Pass both the filtered appointments AND the current active date back to HTML
    return render_template(
        "index.html",
        bookings=filtered_bookings,
        current_filter_date=selected_filter_date,
        total_revenue=f"{revenue:.2f}",
        total_deposits=f"{deposits:.2f}",
        cash_owed=f"{(revenue - deposits):.2f}"
    )
   
    # Process each client profile to inject dynamic transit calculations
    for appt in active_bookings:
        cost = appt.get("total_cost", 50.00)
        dep = appt.get("deposit_required", 10.00)
       
        revenue += cost
        deposits += dep
       
        # Inject temporary runtime variable for the HTML template engine loop to render
        appt["drive_time"] = calculate_travel_time(appt["distance"])

    return render_template(
        "index.html",
        bookings=active_bookings,
        total_revenue=f"{revenue:.2f}",
        total_deposits=f"{deposits:.2f}",
        cash_owed=f"{(revenue - deposits):.2f}"
    )


# ROUTE 2: CATCH FORM DATA SUBMISSIONS FROM THE BROWSER PORTAL
@app.route("/add_booking", methods=["POST"])
def add_booking():
    client_name = request.form.get("name")
    selected_service = request.form.get("service")
    client_distance = float(request.form.get("distance"))
    # NEW: Grab the incoming browser calendar date string selection
    selected_date = request.form.get("booking_date")
   
    total_cost = PRICE_MATRIX.get(selected_service, 50.00)
    deposit_required = total_cost * 0.20
   
    new_booking = {
        "name": client_name,
        "service": selected_service,
        "distance": client_distance,
        "total_cost": total_cost,
        "deposit_required": deposit_required,
        "date": selected_date # NEW: Link data into database profile dictionary
    }
   
    current_schedule = load_database()
    current_schedule.append(new_booking)
    save_database(current_schedule)
   
    simulate_sms_notification("NEW_BOOKING", new_booking)
    return redirect("/")
   
    # Process financial algorithm equations
    total_cost = PRICE_MATRIX.get(selected_service, 50.00)
    deposit_required = total_cost * 0.20
   
    # Package into a distinct data object profile
    new_booking = {
        "name": client_name,
        "service": selected_service,
        "distance": client_distance,
        "total_cost": total_cost,
        "deposit_required": deposit_required
    }
   
    # Update local disk state
    current_schedule = load_database()
    current_schedule.append(new_booking)
    save_database(current_schedule)
   
    # Trigger our outbound booking text alert simulator
    simulate_sms_notification("NEW_BOOKING", new_booking)
   
    # Cleanly refresh browser back to standard endpoint view
    return redirect("/")


# ROUTE 3: WEB SURGICAL WIPE ENGINE (CANCELLATIONS WITH UNIFIED NOTIFICATIONS)
@app.route("/delete_booking/<int:booking_index>")
def delete_booking(booking_index):
    current_schedule = load_database()
   
    # Structural safety optimization check: verify location index boundaries
    if 0 <= booking_index < len(current_schedule):
        # 1. First, pop the profile from the array list and hold it in a box
        removed_client_profile = current_schedule.pop(booking_index)
       
        # 2. Update local disk state memory files
        save_database(current_schedule)
        print(f" Wiped out database record index row for: {removed_client_profile['name']}")
       
        # 3. NOW trigger the notification simulator passing our isolated profile box!
        simulate_sms_notification("CANCEL_BOOKING", removed_client_profile)
       
    return redirect("/")


if __name__ == "__main__":
    # Start persistent server engine context layer
    app.run(debug=True)