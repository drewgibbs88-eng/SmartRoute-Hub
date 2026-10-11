import uuid
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import Index, Numeric

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    business_name = db.Column(db.String(100), nullable=False)
    dispatch_postcode = db.Column(db.String(10), nullable=False, default="SW1A 1AA")
    phone_number = db.Column(db.String(20), nullable=True)
    travel_fee_per_mile = db.Column(Numeric(10, 2), nullable=False, default=1.50)
    
    bookings = db.relationship('Booking', backref='owner', lazy=True, cascade="all, delete-orphan")
    services = db.relationship('ServiceItem', backref='provider', lazy=True, cascade="all, delete-orphan")

class ServiceItem(db.Model):
    __tablename__ = 'service_items'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(Numeric(10, 2), nullable=False)

class Booking(db.Model):
    __tablename__ = 'bookings'
    
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    client_name = db.Column(db.String(100), nullable=False)
    client_email = db.Column(db.String(120), nullable=False)
    client_phone = db.Column(db.String(20), nullable=False)
    destination_postcode = db.Column(db.String(10), nullable=False)
    
    service_name = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    
    base_cost = db.Column(Numeric(10, 2), nullable=False)
    travel_cost = db.Column(Numeric(10, 2), nullable=False, default=0.00)
    total_cost = db.Column(Numeric(10, 2), nullable=False)
    deposit_amount = db.Column(Numeric(10, 2), nullable=False)
    platform_fee = db.Column(Numeric(10, 2), nullable=False, default=1.00)
    
    distance_miles = db.Column(Numeric(6, 2), nullable=False)
    travel_time_mins = db.Column(db.Integer, nullable=False)
    
    status = db.Column(db.String(20), nullable=False, default='pending')
    stripe_session_id = db.Column(db.String(250), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_tenant_schedule', 'user_id', 'start_time', 'status'),
    )