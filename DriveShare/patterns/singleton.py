from flask import session
# Singleton Pattern
# This class is used to manage the users session
# The Singleton pattern makes sure we use only one SessionManager object
# Instead of creating a new manager each time we use get_instance()
# This should help keep login and logout in one spot
class SessionManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls):
        return cls()

    def login(self, user_id):
        session.clear()
        session['user_id'] = user_id

    def current_user_id(self):
        # Each user keeps their own login because Flask saves 
        # the user ID in their own session
        return session.get('user_id')

    def logout(self):
        session.clear()
