# Mediator Pattern
# The Mediator helps different parts of the website communicate
# Instead of every component talking directly to another component
# they can send information through the Mediator
# For DriveShare this includes bookings, payments and messages
# The Mediator helps decide which notifications should be sent
class UIMediator:
    def __init__(self):
        self.components = {}

    def register(self, name, component):
        # Give each component the same Mediator so it
        # knows where to send updates
        self.components[name] = component
        component.mediator = self

    def notify(self, db, sender, event, details):
        # The Mediator decides which user gets an alert after
        # a booking, payment, or message
        notifications = self.components['notifications']

        if event == 'booking':
            booking, car = details
            owner_message = (
                f"New booking request for {car['make']} {car['model']}."
            )
            renter_message = (
                'Your booking was created. Please complete payment.'
            )
            notifications.show(db, car['owner_id'], owner_message)
            notifications.show(db, booking['renter_id'], renter_message)

        elif event == 'payment':
            booking, car = details
            owner_message = (
                f"Payment received for {car['make']} {car['model']}."
            )
            notifications.show(
                db, booking['renter_id'],
                'Your payment was successful!'
            )
            notifications.show(db, car['owner_id'], owner_message)

        elif event == 'message':
            recipient_id, sender_name = details
            notifications.show(
                db, recipient_id,
                f'You have a new message from {sender_name}.'
            )


class BookingComponent:
    def booking_created(self, db, booking, car):
        # Tell the Mediator a renter made a booking so
        # it can alert both users
        self.mediator.notify(db, self, 'booking', (booking, car))


class PaymentComponent:
    def payment_completed(self, db, booking, car):
        # Tell the Mediator a payment finished so it can
        # alert the renter and owner
        self.mediator.notify(db, self, 'payment', (booking, car))


class MessageComponent:
    def message_sent(self, db, recipient_id, sender_name):
        # Tell the Mediator someone sent a message so the 
        # other user gets an alert
        self.mediator.notify(
            db, self, 'message', (recipient_id, sender_name)
        )


class NotificationComponent:
    def __init__(self, send_notification):
        self.send_notification = send_notification

    def show(self, db, user_id, message):
        # Save the notification in the database so it 
        # appears on the Alerts page
        self.send_notification(db, user_id, message)
