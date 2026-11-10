import sqlite3
from flask import g, current_app


# Open one SQLite connection for the current request
def connect():
    db = sqlite3.connect(current_app.config['DATABASE'], timeout=20)
    # Let us use column names like user 'email' when reading a row
    db.row_factory = sqlite3.Row
    # Make SQLite check that related users and cars exist
    db.execute('PRAGMA foreign_keys=ON')
    return db


# Reuse the database connection during the same website request
def get_db():
    if 'db' not in g:
        g.db = connect()
    return g.db


# Close the connection when the website finishes this request
def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()



# This function creates the database tables used by DriveShare
# The users table saves accountinformation
# The cars table saves the vehicles listed by owners
# The bookings table keeps track of rental reservations
# Other tables store watched cars, message,s and notifications
# SQLite is used so the information stays saved after closing the website
def init_db():
    db = get_db()
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
        question1 TEXT NOT NULL, answer1 TEXT NOT NULL,
        question2 TEXT NOT NULL, answer2 TEXT NOT NULL,
        question3 TEXT NOT NULL, answer3 TEXT NOT NULL,
        balance REAL NOT NULL DEFAULT 1000
    );
    CREATE TABLE IF NOT EXISTS cars (
        id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL REFERENCES users(id),
        make TEXT NOT NULL, model TEXT NOT NULL, year INTEGER NOT NULL,
        mileage INTEGER NOT NULL, location TEXT NOT NULL, price REAL NOT NULL,
        description TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS blocked_dates (
        id INTEGER PRIMARY KEY AUTOINCREMENT, car_id INTEGER NOT NULL REFERENCES cars(id),
        start_at TEXT NOT NULL, end_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, car_id INTEGER NOT NULL REFERENCES cars(id),
        renter_id INTEGER NOT NULL REFERENCES users(id),
        start_at TEXT NOT NULL, end_at TEXT NOT NULL,
        total REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
    );
    CREATE TABLE IF NOT EXISTS watches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
        car_id INTEGER NOT NULL REFERENCES cars(id), max_price REAL NOT NULL,
        start_at TEXT, end_at TEXT, UNIQUE(user_id, car_id)
    );
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
        message TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, sender_id INTEGER NOT NULL REFERENCES users(id),
        recipient_id INTEGER NOT NULL REFERENCES users(id), text TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    ''')
    db.commit()
