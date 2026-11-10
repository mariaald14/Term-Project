# Builder Pattern
# This class helps create a car listing one step at a time
# A car has important information like its model and year
# It can also have other information like mileage, locationand price
# The set methods add these details to the car
# The build method returns the finished car listing
class CarBuilder:
    def __init__(self, owner_id, make, model, year):
        # Create the car with its owner, make, model and year
        # before adding other details
        self.car = {
            'owner_id': owner_id,
            'make': make,
            'model': model,
            'year': year,
            'mileage': 0,
            'location': '',
            'price': 0,
            'description': ''
        }

    # Each set method adds one detail and returns this Builder 
    # for the next step
    def set_mileage(self, mileage):
        self.car['mileage'] = mileage
        return self

    def set_location(self, location):
        self.car['location'] = location
        return self

    def set_price(self, price):
        self.car['price'] = price
        return self

    def set_description(self, description):
        self.car['description'] = description
        return self

    def build(self):
        # Return the finished car information after the Builder
        # methods fill in the details
        return self.car
