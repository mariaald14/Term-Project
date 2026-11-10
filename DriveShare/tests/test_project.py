import os
import tempfile
import unittest
from datetime import datetime, timedelta

os.environ['DRIVESHARE_SECRET'] = 'test-secret-for-local-tests'
from app import app
from database import get_db


class DriveShareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        app.config['DATABASE'] = os.path.join(self.temp.name, 'test.db')
        app.config['TESTING'] = True
        with app.app_context():
            from database import init_db
            init_db()
        self.client = app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def post(self, path, data):
        # Every post form includes the session's form token
        self.client.get('/')
        with self.client.session_transaction() as session:
            token = session['csrf']
        return self.client.post(path, data=dict(csrf=token, **data), follow_redirects=True)

    def register(self, name, email):
        return self.post('/register', dict(name=name, email=email, password='password123',
            question1='What is your favorite color?', answer1='blue',
            question2='What city were you born in?', answer2='detroit',
            question3='What is your favorite food?', answer3='pizza'))

    def login(self,email):
        return self.post('/login', {'email':email,'password':'password123'})

    def test_home_and_login(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.register('Owner','owner@example.com')
        self.login('owner@example.com')
        response = self.client.get('/my-cars')
        self.assertEqual(response.status_code, 200)

    def test_book_pay_and_no_overlap(self):
        self.register('Owner','owner@example.com')
        self.login('owner@example.com')
        self.post('/car/new', dict(
            make='Honda', model='Civic', year='2022',
            mileage='12000', location='Dearborn', price='60',
            description='Clean car'
        ))
        self.post('/logout', {})
        self.register('Renter','renter@example.com')
        self.login('renter@example.com')
        a=(datetime.now()+timedelta(days=5)).strftime('%Y-%m-%dT12:00')
        b=(datetime.now()+timedelta(days=6)).strftime('%Y-%m-%dT12:00')
        self.post('/car/1/book',dict(start=a,end=b))
        with app.app_context():
            db=get_db()
            self.assertEqual(db.execute('SELECT COUNT(*) n FROM bookings').fetchone()['n'],1)
        self.post('/car/1/book',dict(start=a,end=b))
        with app.app_context():
            db=get_db()
            self.assertEqual(db.execute('SELECT COUNT(*) n FROM bookings').fetchone()['n'],1)
        self.post('/booking/1/pay',{})
        with app.app_context():
            db=get_db()
            self.assertEqual(db.execute('SELECT status FROM bookings WHERE id=1').fetchone()['status'],'paid')
            self.assertEqual(db.execute('SELECT balance FROM users WHERE email=?',('renter@example.com',)).fetchone()['balance'],940)

    def test_password_recovery_chain(self):
        self.register('Renter','renter@example.com')
        response = self.post('/recover', dict(
            email='renter@example.com', answer1='blue',
            answer2='detroit', answer3='pizza',
            password='newpass123'
        ))
        self.assertIn(b'Password changed',response.data)
        self.assertIn(b'Log out',self.post('/login',{'email':'renter@example.com','password':'newpass123'}).data)

    def test_watch_price_notification(self):
        self.register('Owner','owner@example.com')
        self.login('owner@example.com')
        self.post('/car/new', dict(
            make='Honda', model='Civic', year='2022',
            mileage='12000', location='Dearborn', price='60',
            description='Nice'
        ))
        self.post('/logout',{})
        self.register('Renter','renter@example.com')
        self.login('renter@example.com')
        self.post('/car/1/watch',dict(max_price='50',start='',end=''))
        self.post('/logout',{})
        self.login('owner@example.com')
        self.post('/car/1/edit',dict(mileage='12000',location='Dearborn',price='45',description='Nice'))
        with app.app_context():
            db=get_db()
            alerts=db.execute('SELECT message FROM notifications WHERE user_id=2').fetchall()
            self.assertTrue(any('Price alert' in item['message'] for item in alerts))


if __name__=='__main__':
    unittest.main()


class MediatorTests(unittest.TestCase):
    def test_ui_components_send_notifications(self):
        # The booking screen goes through the mediator to save alerts
        from patterns.mediator import (UIMediator, BookingComponent,
            PaymentComponent, MessageComponent, NotificationComponent)
        messages = []
        def save(db, user_id, message):
            messages.append((user_id, message))
        mediator = UIMediator()
        booking = BookingComponent()
        payment = PaymentComponent()
        message = MessageComponent()
        mediator.register('booking', booking)
        mediator.register('payment', payment)
        mediator.register('messages', message)
        mediator.register('notifications', NotificationComponent(save))
        car = dict(owner_id=1, make='Honda', model='Civic')
        rent = dict(renter_id=2)
        booking.booking_created(None, rent, car)
        payment.payment_completed(None, rent, car)
        message.message_sent(None, 2, 'Owner')
        self.assertEqual(len(messages), 5)
        self.assertEqual([item[0] for item in messages], [1, 2, 2, 1, 2])
