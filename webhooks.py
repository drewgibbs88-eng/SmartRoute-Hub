import os
import stripe
from flask import Blueprint, request, jsonify
from models import db, Booking
from notifications import send_booking_notifications

webhooks_bp = Blueprint('webhooks', __name__)
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
ENDPOINT_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

@webhooks_bp.route('/stripe_webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    try:
        if ENDPOINT_SECRET:
            event = stripe.Webhook.construct_event(payload, sig_header, ENDPOINT_SECRET)
        else:
            event = request.get_json()
    except Exception as e:
        return jsonify({'error': str(e)}), 400

    # Trigger action only when a client successfully pays their deposit
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        booking_id = session.get('client_reference_id')

        if booking_id:
            booking = db.session.query(Booking).filter_all(id=booking_id).with_for_update().first()
            if booking and booking.status != 'confirmed':
                booking.status = 'confirmed'
                booking.stripe_session_id = session.get('id')
                db.session.commit()
                
                # Execute Resend email pipeline
                send_booking_notifications(booking)

    return jsonify({'status': 'success'}), 200