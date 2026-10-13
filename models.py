import uuid
from datetime import datetime, timezone
from enum import Enum
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, ForeignKey, 
    Index, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

db = SQLAlchemy()

class BookingStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    ARRIVED = "arrived"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    public_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    business_name = Column(String(120), nullable=False)
    dispatch_postcode = Column(String(12), nullable=False, default="SW1A 1AA")
    phone_number = Column(String(20), nullable=True)
    travel_fee_per_mile = Column(Numeric(10, 2), nullable=False, default=1.50)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    services = relationship("ServiceItem", back_populates="provider", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="owner", cascade="all, delete-orphan")

class ServiceItem(db.Model):
    __tablename__ = "service_items"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)

    provider = relationship("User", back_populates="services")

class Booking(db.Model):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True)
    public_id = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    client_name = Column(String(100), nullable=False)
    client_email = Column(String(255), nullable=False)
    client_phone = Column(String(30), nullable=False)
    destination_postcode = Column(String(255), nullable=False)
    
    service_name = Column(String(100), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    
    base_cost = Column(Numeric(10, 2), nullable=False)
    travel_cost = Column(Numeric(10, 2), nullable=False, default=0.00)
    total_cost = Column(Numeric(10, 2), nullable=False)
    deposit_amount = Column(Numeric(10, 2), nullable=False)
    platform_fee = Column(Numeric(10, 2), nullable=False, default=1.00)
    
    distance_miles = Column(Numeric(6, 2), nullable=False)
    travel_time_mins = Column(Integer, nullable=False)
    
    status = Column(SQLEnum(BookingStatus), default=BookingStatus.PENDING, nullable=False, index=True)
    stripe_session_id = Column(String(255), unique=True, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="bookings")

    __table_args__ = (
        Index("idx_tenant_schedule", "user_id", "start_time", "status"),
    )