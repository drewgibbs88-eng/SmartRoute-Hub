import unittest
from server import app, db
from models import User, Booking
from geospatial import calculate_uk_route

class SmartRouteTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.client = app.test_client()
        with app.app_context():
            db.create_all()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_routing_calculation(self):
        route = calculate_uk_route("SA1 18A", "SA3 4EN")
        self.assertGreater(route['distance_miles'], 0)
        self.assertGreater(route['travel_time_mins'], 5)

    def test_public_booking_flow(self):
        with app.app_context():
            user = User(email="test@example.com", password_hash="12345", business_name="Test Business", dispatch_postcode="SA1 18A")
            db.session.add(user)
            db.session.commit()

        response = self.client.get('/book/1')
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()