# The Proxy and real payment class use the same pay method
class PaymentService:
    def pay(self, db, booking, car, current_user_id=None):
        raise NotImplementedError

# This class handles the actual payment simulation
# The project does not use real money or a bank
# When the renter pays the renters demo balance goes down
# The owners demo balance goes up by the payment amount
# The booking is also updated to show that it has been paid
class RealPaymentService(PaymentService):
    def pay(self, db, booking, car, current_user_id=None):
        # Take demo money from the renter add it to the 
        # owner and mark the booking paid
        amount = booking['total']
        db.execute(
            'UPDATE users SET balance=balance-? WHERE id=?',
            (amount, booking['renter_id'])
        )
        db.execute(
            'UPDATE users SET balance=balance+? WHERE id=?',
            (amount, car['owner_id'])
        )
        db.execute(
            "UPDATE bookings SET status='paid' WHERE id=?",
            (booking['id'],)
        )
        return True

# The Proxy works between the renter and the real payment service
# Before making a payment it checks if the payment is allowed
# It makes sure the booking belongs to the renter
# It also checks the payment amount and available balance
# If everything is correct the real payment service completes it
class PaymentProxy(PaymentService):
    def __init__(self):
        self.real_payment = RealPaymentService()

    def pay(self, db, booking, car, current_user_id=None):
        # Check that this renter owns the booking before letting 
        # the payment continue
        if current_user_id != booking['renter_id']:
            raise ValueError('You can only pay for your own booking.')

        if booking['status'] != 'pending':
            raise ValueError('This booking has already been paid or cancelled.')

        if booking['total'] <= 0:
            raise ValueError('Invalid payment amount.')

        balance = db.execute(
            'SELECT balance FROM users WHERE id=?',
            (current_user_id,)
        ).fetchone()['balance']

        if balance < booking['total']:
            raise ValueError('Not enough demo balance to pay.')

        # If the booking and balance are correc let the real 
        # payment service update the money
        return self.real_payment.pay(db, booking, car, current_user_id)
