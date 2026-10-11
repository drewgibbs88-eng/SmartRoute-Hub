import os
import urllib.parse
import resend

def send_booking_notifications(booking):
    resend.api_key = os.environ.get('RESEND_API_KEY')
    if not resend.api_key:
        print("Resend API key missing. Skipping email dispatch.")
        return

    # Action URLs for the Business Owner
    encoded_postcode = urllib.parse.quote(booking.destination_postcode)
    maps_url = f"https://www.google.com/maps/dir/?api=1&destination={encoded_postcode}"
    whatsapp_url = f"https://wa.me/{booking.client_phone.replace('+', '').replace(' ', '')}"
    tel_url = f"tel:{booking.client_phone}"

    # Email 1: Dispatch Alert to Business Owner
    owner_html = f"""
    <div style="font-family: sans-serif; padding: 20px; max-width: 600px;">
        <h2 style="color: #2563eb;">New Dispatch Alert</h2>
        <p><strong>Client:</strong> {booking.client_name}</p>
        <p><strong>Service:</strong> {booking.service_name}</p>
        <p><strong>Location:</strong> {booking.destination_postcode} ({booking.distance_miles} miles, ~{booking.travel_time_mins} mins travel)</p>
        <p><strong>Scheduled Time:</strong> {booking.start_time.strftime('%d %b %Y at %H:%M')}</p>
        <p><strong>Total Value:</strong> £{booking.total_cost:.2f} (Deposit Paid: £{booking.deposit_amount:.2f})</p>
        <hr style="border: 1px solid #eee; margin: 20px 0;">
        <a href="{maps_url}" style="background:#2563eb;color:white;padding:10px 15px;text-decoration:none;border-radius:5px;display:inline-block;margin-right:5px;">Open Google Maps</a>
        <a href="{whatsapp_url}" style="background:#22c55e;color:white;padding:10px 15px;text-decoration:none;border-radius:5px;display:inline-block;margin-right:5px;">WhatsApp Client</a>
        <a href="{tel_url}" style="background:#4b5563;color:white;padding:10px 15px;text-decoration:none;border-radius:5px;display:inline-block;">Call Client</a>
    </div>
    """

    resend.Emails.send({
        "from": "SmartRoute <onboarding@resend.dev>",
        "to": booking.owner.email,
        "subject": f"Dispatch Order: {booking.client_name} - {booking.destination_postcode}",
        "html": owner_html
    })

    # Email 2: Confirmation Receipt to Client
    client_html = f"""
    <div style="font-family: sans-serif; padding: 20px; max-width: 600px; border: 1px solid #eee; border-radius: 8px;">
        <h2 style="color: #10b981;">Booking Confirmed</h2>
        <p>Hi {booking.client_name}, your deposit has been processed and your appointment with <strong>{booking.owner.business_name}</strong> is confirmed.</p>
        <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
            <tr style="background: #f8fafc;"><td style="padding: 10px;"><strong>Service:</strong></td><td style="padding: 10px; text-align: right;">{booking.service_name}</td></tr>
            <tr><td style="padding: 10px;"><strong>Date & Time:</strong></td><td style="padding: 10px; text-align: right;">{booking.start_time.strftime('%d %b %Y at %H:%M')}</td></tr>
            <tr style="background: #f8fafc;"><td style="padding: 10px;"><strong>Location:</strong></td><td style="padding: 10px; text-align: right;">{booking.destination_postcode}</td></tr>
            <tr><td style="padding: 10px;"><strong>Total Cost:</strong></td><td style="padding: 10px; text-align: right;">£{booking.total_cost:.2f}</td></tr>
            <tr style="background: #f8fafc;"><td style="padding: 10px;"><strong>Deposit Paid:</strong></td><td style="padding: 10px; text-align: right; color: #10b981;">- £{booking.deposit_amount:.2f}</td></tr>
            <tr><td style="padding: 10px; font-weight: bold;">Balance Due on Arrival:</td><td style="padding: 10px; text-align: right; font-weight: bold; font-size: 18px;">£{(booking.total_cost - booking.deposit_amount):.2f}</td></tr>
        </table>
    </div>
    """

    resend.Emails.send({
        "from": "SmartRoute <onboarding@resend.dev>",
        "to": booking.client_email,
        "subject": f"Booking Confirmation: {booking.service_name}",
        "html": client_html
    })