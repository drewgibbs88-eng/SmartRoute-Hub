from functools import wraps
from flask import abort
from flask_login import current_user
from models import Booking

def tenant_booking_required(f):
    @wraps(f)
    def decorated_function(booking_id, *args, **kwargs):
        booking = Booking.query.get_or_404(booking_id)
        if booking.user_id != current_user.id:
            abort(403)
        return f(booking, *args, **kwargs)
    return decorated_function