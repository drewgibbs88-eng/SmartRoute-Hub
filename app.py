# --- Mobile Booking & Smart Routing Architecture ---
import json

# 1. ROUTE ESTIMATION ENGINE
def calculate_travel_time(miles):
    average_speed_mph = 30  # Standard city driving speed assumption
    minutes_per_mile = 60 / average_speed_mph
    return miles * minutes_per_mile

# 1B. PRICE MATRIX LOOKUP TABLE
# Map common services to their total baseline service costs
PRICE_MATRIX = {
    "haircut": 25.00,
    "blowdry": 10.00,
    "nails": 30.00
}

# 2. PERSISTENT SYSTEM BOOT LOADER
try:
    # Try to open the database file in read mode
    with open("database.json", "r") as file_box:
        active_bookings = json.load(file_box)
    print("🔄 Existing database loaded successfully!")
except FileNotFoundError:
    # Start with a fresh list if no database file exists yet
    active_bookings = []
    print("🆕 No existing database found. Starting fresh schedule.")

# 3. MASTER MENU & CONTROL DASHBOARD
while True:
    print("\n===============================")
    print("    MOBILE BOOKING SYSTEM")
    print("===============================")
    print("1. 📋 View Today's Itinerary")
    print("2. ➕ Add New Client Booking")
    print("3. ❌ Cancel / Delete Appointment")
    print("4. 💾 Save and Exit")
    print("===============================")
   
    choice = input("Select an option (1-4): ")

       # OPTION 1: VIEW ROUTE ITINERARY & CASH COUNTER
    if choice == "1":
        if not active_bookings:
            print("\n📭 Your schedule is currently empty.")
        else:
            print("\n--- DAILY ROUTE & FINANCIAL REPORT ---")
            total_daily_revenue = 0.0
            total_deposits_collected = 0.0
           
            for appointment in active_bookings:
                drive_minutes = calculate_travel_time(appointment["distance"])
               
                # Fetch stored financial details from the dictionary profile
                cost = appointment.get("total_cost", 50.00)
                deposit = appointment.get("deposit_required", 10.00)
               
                total_daily_revenue += cost
                total_deposits_collected += deposit
               
                print(f"👤 Client: {appointment['name']} | 🛠️ Service: {appointment['service']} | 💵 Cost: ${cost:.2f} (Dep: ${deposit:.2f}) | 🚗 Drive: {drive_minutes:.1f} mins")
           
            print("-------------------------------------------------------------")
            print(f"💰 Total Booked Revenue: ${total_daily_revenue:.2f}")
            print(f"💳 Total 20% Deposits Secured (via Stripe): ${total_deposits_collected:.2f}")
            print(f"💵 Cash Owed on Location: ${total_daily_revenue - total_deposits_collected:.2f}")
            print("-------------------------------------------------------------")

  # OPTION 2: ADD NEW BOOKING WITH AUTOMATED PRICING
    elif choice == "2":
        print("\n--- NEW CLIENT ENTRY ---")
        name = input("Client Name: ")
        
        # Read service and immediately make it lowercase to check our rate card matrix
        service = input("Service Required: ").lower().strip()
        miles = float(input("Distance to Client (miles): "))
        
        # Look up price from matrix table. If not found, default to a flat $50.00 standard rate
        total_cost = PRICE_MATRIX.get(service, 50.00)
        deposit_required = total_cost * 0.20 # Calculate 20% non-refundable deposit
        
        # Package data with our new financial profiles
        booking = {
            "name": name, 
            "service": service, 
            "distance": miles,
            "total_cost": total_cost,
            "deposit_required": deposit_required
        }
        active_bookings.append(booking)
        print(f"✅ Success! Added {name}. System estimated cost at ${total_cost:.2f} with a ${deposit_required:.2f} Stripe deposit.")

    # OPTION 3: SURGICAL CANCELLATION / WIPE
    elif choice == "3":
        if not active_bookings:
            print("\n📭 No appointments found to cancel.")
        else:
            print("\n--- SELECT APPOINTMENT TO CANCEL ---")
            # Map out each client with a targetable index number
            for index, appointment in enumerate(active_bookings):
                print(f"[{index}] - Client: {appointment['name']} ({appointment['service']})")
           
            cancel_index = int(input("\nEnter the number [#] you want to delete: "))
           
            # Extract and drop targeted index dictionary profile
            removed_client = active_bookings.pop(cancel_index)
            print(f"🗑️ Successfully cancelled appointment for: {removed_client['name']}")

    # OPTION 4: PERSISTENT STATE STORAGE & QUIT
    elif choice == "4":
        with open("database.json", "w") as file_box:
            json.dump(active_bookings, file_box, indent=4)
        print("\n💾 Data successfully backed up to database.json! Goodbye.")
        break  # Wipes loop state and terminates the shell instance

    else:
        print("⚠️ Invalid choice. Please select 1, 2, 3, or 4.")