import os
import secrets
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db, close_db, init_db
from patterns.singleton import SessionManager
from patterns.builder import CarBuilder
from patterns.observer import CarSubject, WatchObserver
from patterns.mediator import (
    UIMediator,
    BookingComponent,
    PaymentComponent,
    MessageComponent,
    NotificationComponent
)
from patterns.proxy import PaymentProxy
from patterns.chain import check_recovery_answers

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('DRIVESHARE_SECRET', secrets.token_hex(24))
app.config['DATABASE'] = os.path.join(app.instance_path, 'driveshare.db')
os.makedirs(app.instance_path, exist_ok=True)
app.teardown_appcontext(close_db)

# Get the one session manager object so the app can use it for login and logout
manager = SessionManager.get_instance()


def send_notification(db, user_id, message):
    db.execute('INSERT INTO notifications(user_id, message) VALUES (?, ?)', (user_id, message))


# Set up the Mediator so booking, payment and message parts 
# can send alerts through one place
mediator = UIMediator()
booking_ui = BookingComponent()
payment_ui = PaymentComponent()
message_ui = MessageComponent()
notification_ui = NotificationComponent(send_notification)
mediator.register('booking', booking_ui)
mediator.register('payment', payment_ui)
mediator.register('messages', message_ui)
mediator.register('notifications', notification_ui)
# Set up the car Subject so renters watching a car can get 
# updates when it changes
subject = CarSubject()


# Turn the date fields into dates and make sure the end 
# comes after the start
def parse_period(start, end):
    """Date/time from HTML datetime-local inputs; end must be later."""
    a = datetime.fromisoformat(start)
    b = datetime.fromisoformat(end)
    if b <= a:
        raise ValueError('End must be after start.')
    if a < datetime.now():
        raise ValueError('Choose a future date/time.')
    return a, b


# Check the booking and blocked dates before saying a car 
# is available
def available(db, car_id, start, end):
    # Dates overlap when the new rental starts before the old one ends and ends after it starts
    booking = db.execute('''SELECT id FROM bookings WHERE car_id=?
       AND status IN ('pending','paid') AND start_at < ? AND end_at > ?''',
       (car_id, end, start)).fetchone()
    blocked = db.execute('''SELECT id FROM blocked_dates WHERE car_id=?
       AND start_at < ? AND end_at > ?''', (car_id, end, start)).fetchone()
    return not booking and not blocked


# Check the form token on POST requests to help stop unwanted
# form submissions
@app.before_request
def prepare():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_hex(16)
    if request.method == 'POST':
        if not secrets.compare_digest(session.get('csrf', ''), request.form.get('csrf', '')):
            abort(400, 'Invalid form token. Refresh the page and try again.')


# Give every HTML page the logged-in user and form token
@app.context_processor
def context_data():
    user = None
    user_id = manager.current_user_id()
    if user_id:
        user = get_db().execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    return {'user': user, 'csrf': session.get('csrf')}


# Send someone to the login page before opening a page that 
# needs an account
def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not manager.current_user_id():
            flash('Please log in first.')
            return redirect(url_for('login'))
        return function(*args, **kwargs)
    return wrapper


# Use the Observer to check renters who saved this car and 
# send alerts when their rules match
def notify_watchers(db, car, event):
    subject.observers.clear()
    subject.attach(WatchObserver(db, send_notification, available))
    subject.notify(car, event)


# Show active cars and let renters search by location, price 
# and dates
@app.route('/')
def home():
    db = get_db()
    location = request.args.get('location', '').strip()
    start = request.args.get('start', '').strip()
    end = request.args.get('end', '').strip()
    max_price = request.args.get('max_price', '').strip()
    query = (
        'SELECT cars.*, users.name AS owner_name '
        'FROM cars JOIN users ON users.id=cars.owner_id '
        'WHERE cars.active=1'
    )
    args = []
    if location:
        query += ' AND (cars.location LIKE ? OR cars.make LIKE ? OR cars.model LIKE ?)'
        args += [f'%{location}%'] * 3
    if max_price:
        try:
            query += ' AND cars.price <= ?'
            args.append(float(max_price))
        except ValueError:
            flash('Price must be a number.')
    cars = db.execute(query + ' ORDER BY cars.id DESC', args).fetchall()
    if start and end:
        try:
            parse_period(start, end)
            cars = [car for car in cars if available(db, car['id'], start, end)]
        except ValueError as error:
            flash(str(error))
    return render_template('home.html', cars=cars)


# Ask for an email, password, and three security questions
# when someone creates an account
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        f = request.form
        fields = [
            'name', 'email', 'password',
            'question1', 'answer1',
            'question2', 'answer2',
            'question3', 'answer3'
        ]
        if any(not f.get(key, '').strip() for key in fields):
            flash('Fill in every field.')
        elif len(f['password']) < 8:
            flash('Password must have at least 8 characters.')
        elif len({f['question1'], f['question2'], f['question3']}) != 3:
            flash('Choose three different security questions.')
        else:
            try:
                db = get_db()
                # Save hashed passwords and answers instead of 
                # keeping the original words in the database
                db.execute(
                    """INSERT INTO users(
                        name, email, password,
                        question1, answer1, question2, answer2,
                        question3, answer3
                    ) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        f['name'].strip(),
                        f['email'].strip().lower(),
                        generate_password_hash(f['password']),
                        f['question1'],
                        generate_password_hash(f['answer1'].strip().lower()),
                        f['question2'],
                        generate_password_hash(f['answer2'].strip().lower()),
                        f['question3'],
                        generate_password_hash(f['answer3'].strip().lower())
                    )
                )
                db.commit()
                flash('Account created! Log in now. Your demo balance starts at $1000.')
                return redirect(url_for('login'))
            except Exception as error:
                if 'UNIQUE' in str(error):
                    flash('That email is already registered.')
                else:
                    raise
    questions = [
        'What is your favorite color?',
        'What city were you born in?',
        'What is your favorite food?',
        'What was your first pet name?',
        'What is your favorite school subject?',
        'What is your favorite movie?'
    ]
    return render_template('register.html', questions=questions)


# Find the account, check the password, and use the Singleton
# to start the login session
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = get_db().execute(
            'SELECT * FROM users WHERE email=?',
            (email,)
        ).fetchone()
        if user and check_password_hash(user['password'], request.form.get('password', '')):
            manager.login(user['id'])
            session['csrf'] = secrets.token_hex(16)
            return redirect(url_for('home'))
        flash('Email or password is incorrect.')
    return render_template('login.html')


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    manager.logout()
    flash('You logged out.')
    return redirect(url_for('home'))


# Send the three answers through the Chain of Responsibility 
# before allowing a password change
@app.route('/recover', methods=['GET','POST'])
def recover():
    user = None
    email = request.values.get('email','').strip().lower()
    if email:
        user = get_db().execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    if request.method == 'POST':
        if not user:
            flash('Account not found.')
        elif len(request.form.get('password','')) < 8:
            flash('New password must have at least 8 characters.')
        else:
            answers = [request.form.get(f'answer{i}', '') for i in (1,2,3)]
            if check_recovery_answers(user, answers):
                db = get_db()
                new_password = generate_password_hash(request.form['password'])
                db.execute(
                    'UPDATE users SET password=? WHERE id=?',
                    (new_password, user['id'])
                )
                db.commit()
                flash('Password changed. You can log in.')
                return redirect(url_for('login'))
            flash('The security answers do not match.')
    return render_template('recover.html', target=user, email=email)


# Use the Builder methods to put together a new car listing
@app.route('/car/new', methods=['GET','POST'])
@login_required
def new_car():
    if request.method == 'POST':
        try:
            f = request.form
            make, model, location = (f.get(x, '').strip() for x in ('make','model','location'))
            year, mileage, price = int(f['year']), int(f['mileage']), float(f['price'])
            if (
                not make or not model or not location
                or not (1900 <= year <= datetime.now().year + 1)
                or mileage < 0 or price <= 0
            ):
                raise ValueError('Enter valid car details and a positive daily price.')
            listing = (CarBuilder(manager.current_user_id(), make, model, year)
                       .set_mileage(mileage).set_location(location).set_price(price)
                       .set_description(f.get('description','').strip()).build())
            db = get_db()
            db.execute('''INSERT INTO cars(owner_id,make,model,year,mileage,location,price,description)
               VALUES (:owner_id,:make,:model,:year,:mileage,:location,:price,:description)''', listing)
            db.commit()
            flash('Car listed!')
            return redirect(url_for('my_cars'))
        except (ValueError, KeyError) as error:
            flash(f'Please check the listing fields. {error}')
    return render_template('car_form.html', car=None)


@app.route('/my-cars')
@login_required
def my_cars():
    db = get_db()
    cars = db.execute(
        'SELECT * FROM cars WHERE owner_id=? ORDER BY id DESC',
        (manager.current_user_id(),)
    ).fetchall()
    blocks = db.execute('''SELECT blocked_dates.* FROM blocked_dates JOIN cars ON cars.id=blocked_dates.car_id
        WHERE cars.owner_id=? ORDER BY blocked_dates.start_at''', (manager.current_user_id(),)).fetchall()
    return render_template('my_cars.html', cars=cars, blocks=blocks)


@app.route('/car/<int:car_id>')
def car_details(car_id):
    db = get_db()
    car = db.execute(
        'SELECT cars.*, users.name owner_name '
        'FROM cars JOIN users ON users.id=cars.owner_id '
        'WHERE cars.id=?',
        (car_id,)
    ).fetchone()
    if not car or not car['active']:
        abort(404)
    return render_template('car.html', car=car)


# Let owners update their own car and tell watchers if the price changes
@app.route('/car/<int:car_id>/edit', methods=['GET','POST'])
@login_required
def edit_car(car_id):
    db = get_db()
    car = db.execute(
        'SELECT * FROM cars WHERE id=? AND owner_id=?',
        (car_id, manager.current_user_id())
    ).fetchone()
    if not car:
        abort(403)
    if request.method == 'POST':
        try:
            f = request.form
            price, mileage = float(f['price']), int(f['mileage'])
            if price <= 0 or mileage < 0 or not f.get('location', '').strip():
                raise ValueError('Invalid listing details.')
            price_changed = price != car['price']
            db.execute('UPDATE cars SET mileage=?,price=?,location=?,description=? WHERE id=?',
                       (mileage, price, f['location'].strip(), f.get('description','').strip(), car_id))
            updated = db.execute('SELECT * FROM cars WHERE id=?', (car_id,)).fetchone()
            if price_changed:
                notify_watchers(db, updated, 'price')
            db.commit()
            flash('Listing updated.')
            return redirect(url_for('my_cars'))
        except (ValueError, KeyError) as error:
            flash(f'Check the fields: {error}')
    return render_template('car_form.html', car=car)


# Let the owner show or hide a car and check for availability
# alerts
@app.route('/car/<int:car_id>/toggle', methods=['POST'])
@login_required
def toggle_car(car_id):
    db = get_db()
    car = db.execute(
        'SELECT * FROM cars WHERE id=? AND owner_id=?',
        (car_id, manager.current_user_id())
    ).fetchone()
    if not car:
        abort(403)
    db.execute('UPDATE cars SET active=? WHERE id=?', (0 if car['active'] else 1, car_id))
    updated = db.execute('SELECT * FROM cars WHERE id=?', (car_id,)).fetchone()
    if updated['active']:
        notify_watchers(db, updated, 'availability')
    db.commit()
    flash('Car listing status updated.')
    return redirect(url_for('my_cars'))


# Let the owner block times when the car cannot be rented
@app.route('/car/<int:car_id>/block', methods=['POST'])
@login_required
def block_dates(car_id):
    db = get_db()
    car = db.execute(
        'SELECT * FROM cars WHERE id=? AND owner_id=?',
        (car_id, manager.current_user_id())
    ).fetchone()
    if not car:
        abort(403)
    try:
        start, end = request.form['start'], request.form['end']
        parse_period(start, end)
        if not available(db, car_id, start, end):
            raise ValueError('Those dates overlap an existing booking or block.')
        db.execute('INSERT INTO blocked_dates(car_id,start_at,end_at) VALUES (?,?,?)', (car_id,start,end))
        db.commit()
        flash('Dates blocked on your calendar.')
    except (ValueError, KeyError) as error:
        flash(str(error))
    return redirect(url_for('my_cars'))


# Remove an owner block and tell watchers the dates may 
# be free again
@app.route('/block/<int:block_id>/remove', methods=['POST'])
@login_required
def remove_block(block_id):
    db = get_db()
    row = db.execute('''SELECT blocked_dates.*, cars.owner_id FROM blocked_dates
       JOIN cars ON cars.id=blocked_dates.car_id WHERE blocked_dates.id=?''', (block_id,)).fetchone()
    if not row or row['owner_id'] != manager.current_user_id():
        abort(403)
    db.execute('DELETE FROM blocked_dates WHERE id=?', (block_id,))
    car = db.execute('SELECT * FROM cars WHERE id=?', (row['car_id'],)).fetchone()
    if car['active']:
        notify_watchers(db, car, 'availability')
    db.commit()
    flash('Dates are available again.')
    return redirect(url_for('my_cars'))


# Check the selected car and dates before saving a new rental
# booking
@app.route('/car/<int:car_id>/book', methods=['POST'])
@login_required
def book_car(car_id):
    db = get_db()
    try:
        start, end = request.form['start'], request.form['end']
        a,b = parse_period(start,end)
        # Keep the date check and booking save together so two 
        # renters cannot book the same time
        db.execute('BEGIN IMMEDIATE')
        car = db.execute('SELECT * FROM cars WHERE id=? AND active=1', (car_id,)).fetchone()
        if not car:
            raise ValueError('Car not available.')
        if car['owner_id'] == manager.current_user_id():
            raise ValueError('You cannot rent your own car.')
        if not available(db, car_id, start, end):
            raise ValueError('Those dates are already reserved.')
        days = max(1, (b-a).total_seconds() / 86400)
        total = round(days * car['price'], 2)
        cursor = db.execute('''INSERT INTO bookings(car_id,renter_id,start_at,end_at,total)
             VALUES (?,?,?,?,?)''', (car_id, manager.current_user_id(), start,end,total))
        booking = db.execute('SELECT * FROM bookings WHERE id=?', (cursor.lastrowid,)).fetchone()
        booking_ui.booking_created(db, booking, car)
        db.commit()
        flash(f'Booking created. Demo payment due: ${total:.2f}.')
        return redirect(url_for('bookings'))
    except (ValueError, KeyError) as error:
        db.rollback()
        flash(str(error))
        return redirect(url_for('car_details', car_id=car_id))


# Use the Proxy to check the renter, amount
# and balance before changing demo money
@app.route('/booking/<int:booking_id>/pay', methods=['POST'])
@login_required
def pay(booking_id):
    db = get_db()
    try:
        db.execute('BEGIN IMMEDIATE')
        booking = db.execute('SELECT * FROM bookings WHERE id=?', (booking_id,)).fetchone()
        if not booking:
            abort(404)
        car = db.execute('SELECT * FROM cars WHERE id=?', (booking['car_id'],)).fetchone()
        PaymentProxy().pay(db, booking, car, manager.current_user_id())
        payment_ui.payment_completed(db, booking, car)
        db.commit()
        flash('Payment complete! This is a demo; no real money was charged.')
    except ValueError as error:
        db.rollback()
        flash(str(error))
    return redirect(url_for('bookings'))


# Cancel an unpaid booking and let the owner know
@app.route('/booking/<int:booking_id>/cancel', methods=['POST'])
@login_required
def cancel(booking_id):
    db = get_db()
    booking = db.execute('SELECT * FROM bookings WHERE id=?', (booking_id,)).fetchone()
    if not booking or booking['renter_id'] != manager.current_user_id():
        abort(403)
    if booking['status'] != 'pending':
        flash('Only unpaid bookings can be cancelled in this demo.')
        return redirect(url_for('bookings'))
    db.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
    car = db.execute('SELECT * FROM cars WHERE id=?', (booking['car_id'],)).fetchone()
    notify_watchers(db, car, 'availability')
    send_notification(db, car['owner_id'], 'A renter cancelled an unpaid booking.')
    db.commit()
    flash('Booking cancelled.')
    return redirect(url_for('bookings'))


# Save the renter's price limit and dates so the Observer can 
# check them later
@app.route('/car/<int:car_id>/watch', methods=['POST'])
@login_required
def watch(car_id):
    db = get_db()
    car = db.execute('SELECT * FROM cars WHERE id=?', (car_id,)).fetchone()
    if not car or car['owner_id'] == manager.current_user_id():
        abort(403)
    try:
        maximum = float(request.form['max_price'])
        start, end = request.form.get('start',''), request.form.get('end','')
        if maximum <= 0 or bool(start) != bool(end):
            raise ValueError('Enter a valid price and either both dates or neither.')
        if start:
            parse_period(start,end)
        db.execute('''INSERT INTO watches(user_id,car_id,max_price,start_at,end_at) VALUES (?,?,?,?,?)
           ON CONFLICT(user_id,car_id) DO UPDATE SET max_price=excluded.max_price,
           start_at=excluded.start_at,end_at=excluded.end_at''',
           (manager.current_user_id(),car_id,maximum,start or None,end or None))
        db.commit()
        flash('Added to your watchlist! You will see alerts in Notifications.')
    except (ValueError, KeyError) as error:
        flash(str(error))
    return redirect(url_for('car_details', car_id=car_id))


@app.route('/watches')
@login_required
def watches():
    db = get_db()
    data = db.execute('''SELECT watches.*, cars.make, cars.model, cars.price FROM watches
      JOIN cars ON cars.id=watches.car_id WHERE watches.user_id=?''', (manager.current_user_id(),)).fetchall()
    return render_template('watches.html', watches=data)


@app.route('/watch/<int:watch_id>/remove', methods=['POST'])
@login_required
def unwatch(watch_id):
    db = get_db()
    db.execute('DELETE FROM watches WHERE id=? AND user_id=?', (watch_id,manager.current_user_id()))
    db.commit()
    return redirect(url_for('watches'))


@app.route('/notifications')
@login_required
def notifications():
    data = get_db().execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC',
        (manager.current_user_id(),)).fetchall()
    return render_template('notifications.html', notifications=data)


# Save a message for another user and use the mediator to 
# send an alert
@app.route('/messages', methods=['GET', 'POST'])
@login_required
def messages():
    db = get_db()
    if request.method == 'POST':
        recipient = request.form.get('recipient','').strip().lower()
        text = request.form.get('text','').strip()
        receiver = db.execute('SELECT * FROM users WHERE email=?', (recipient,)).fetchone()
        if not receiver or receiver['id'] == manager.current_user_id() or not text:
            flash('Enter another registered user email and a message.')
        else:
            sender = db.execute('SELECT name FROM users WHERE id=?', (manager.current_user_id(),)).fetchone()
            db.execute('INSERT INTO messages(sender_id,recipient_id,text) VALUES (?,?,?)',
               (manager.current_user_id(),receiver['id'],text))
            message_ui.message_sent(db, receiver['id'], sender['name'])
            db.commit()
            flash('Message sent.')
        return redirect(url_for('messages'))
    data = db.execute('''SELECT messages.*, a.name sender_name, b.name recipient_name FROM messages
       JOIN users a ON a.id=messages.sender_id JOIN users b ON b.id=messages.recipient_id
       WHERE sender_id=? OR recipient_id=? ORDER BY messages.id DESC''',
       (manager.current_user_id(),manager.current_user_id())).fetchall()
    return render_template('messages.html', messages=data)


# Show upcoming and active bookings so renters can pay or cancel pending bookings
@app.route('/bookings')
@login_required
def bookings():
    db = get_db()
    bookings = db.execute('''SELECT bookings.*, cars.make, cars.model, cars.owner_id,
       renter.name AS renter_name FROM bookings JOIN cars ON bookings.car_id=cars.id
       JOIN users renter ON renter.id=bookings.renter_id
       WHERE (bookings.renter_id=? OR cars.owner_id=?)
       AND bookings.status IN ('pending', 'paid')
       AND date(bookings.end_at) >= date('now')
       ORDER BY bookings.id DESC''',
       (manager.current_user_id(), manager.current_user_id())).fetchall()
    return render_template('bookings.html', bookings=bookings)


with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True)
