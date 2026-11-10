# Observer Pattern
# This pattern is used when renters want updates about cars
# The Subject keeps track of the renters watching a car
# When something changes the Subject notifies the Observers
# For example a renter can get notified when the price drops
# This means renters do not have to keep checking the car themselves
class CarObserver:
    def update(self, car, event):
        raise NotImplementedError


class CarSubject:
    def __init__(self):
        self.observers = []

    def attach(self, observer):
        # Add an Observer to the list of objects watching
        # for car changes
        self.observers.append(observer)

    def notify(self, car, event):
        # Go through the Observer list and tell each one 
        # what changed
        for observer in self.observers:
            observer.update(car, event)

# This class checks whether a car matches what the renter wants
# The renter can choose a price limit and rental dates
# When the car changes the update method checks those choices
# If the car matches the renter receives a notification
class WatchObserver(CarObserver):
    def __init__(self, database, notification_function, available_function):
        self.db = database
        self.send = notification_function
        self.is_available = available_function

    def update(self, car, event):
        # Look up the renters watching this car and check 
        # their saved price or dates
        watches = self.db.execute(
            'SELECT * FROM watches WHERE car_id=?',
            (car['id'],)
        ).fetchall()

        for watch in watches:
            price_match = (
                event == 'price'
                and car['price'] <= watch['max_price']
            )
            dates_match = (
                event == 'availability'
                and watch['start_at']
                and watch['end_at']
                and self.is_available(
                    self.db,
                    car['id'],
                    watch['start_at'],
                    watch['end_at']
                )
            )

            if price_match:
                message = (
                    f"Price alert: {car['make']} {car['model']} "
                    f"is now ${car['price']:.2f}/day."
                )
                self.send(self.db, watch['user_id'], message)

            if dates_match:
                message = (
                    f"Availability alert: {car['make']} {car['model']} "
                    'is available for your dates!'
                )
                self.send(self.db, watch['user_id'], message)
