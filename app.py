from MySQLdb import MySQLError
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, jsonify
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash
from flask_mysqldb import MySQL
import MySQLdb.cursors
from werkzeug.security import check_password_hash, generate_password_hash
import smtplib  # For sending emails
from email.message import EmailMessage
import random
import string

import os
import uuid
from datetime import datetime
from decimal import Decimal
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.mysql import JSON
import razorpay
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "your_secret_key"
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret")  # change in prod
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://root:root@localhost/gov_services'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


# ✅ Initialize SQLAlchemy
db = SQLAlchemy(app)

# Razorpay client (use test keys first)
RAZORPAY_KEY_ID = os.getenv("rzp_test_RYA0tri2cAfoE8")
RAZORPAY_SECRET = os.getenv("FuIi5rksxQoJ294Qg9trERek")
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_SECRET))


# ✅ Database Connection
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",        # replace with your MySQL username
        password="root",  # replace with your MySQL password
        database="gov_services"
    )


# ---------- MODELS ----------
# ✅ Define your model
class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    image = db.Column(db.String(200), nullable=False)
    short_desc = db.Column(db.String(255), nullable=False)
    long_desc = db.Column(db.Text, nullable=False)
    base_price = db.Column(db.Float, nullable=False)
    documents = db.Column(db.String(500), nullable=False)  # list of {"name": "Aadhaar", "price": 20.0}

class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    app_id = db.Column(db.String(50), unique=True, index=True)  # e.g., APP-0001
    applicant_name = db.Column(db.String(200))
    email = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    total_amount = db.Column(db.Numeric(10,2))
    status = db.Column(db.String(50), default="Submitted")
    razorpay_order_id = db.Column(db.String(200), nullable=True)
    razorpay_payment_id = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ApplicationItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('application.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'))
    selected_documents = db.Column(JSON)  # list of selected doc names
    item_amount = db.Column(db.Numeric(10,2))

# ---------- UTILITIES ----------
def generate_app_id():
    # Format APP-0001 style. You can change to UUID if preferred (see docs).
    last = Application.query.order_by(Application.id.desc()).first()
    next_num = 1 if not last else last.id + 1
    return f"APP-{next_num:04d}"

def calculate_item_amount(service_obj, selected_doc_names):
    total = Decimal(service_obj.base_price)
    for doc in service_obj.documents or []:
        if doc['name'] in selected_doc_names:
            total += Decimal(str(doc.get('price', 0)))
    return total


# ---------- SAMPLE DATA LOADER (run once) ----------
@app.cli.command("initdb")
def initdb_command():
    db.create_all()
    # Add sample services if none exist
    if not Service.query.first():
        s1 = Service(
            title="PAN Card Service",
            image="pan.jpg",
            short_desc="Apply or update PAN",
            long_desc="Full PAN support",
            base_price=50,
            documents=[{"name":"Passport Photo","price":20},{"name":"Aadhaar Copy","price":10},{"name":"Address Proof","price":15}]
        )
        s2 = Service(
            title="Aadhaar Service",
            image="aadhaar.jpg",
            short_desc="Aadhaar update & registration",
            long_desc="Aadhaar support",
            base_price=40,
            documents=[{"name":"Passport Photo","price":20},{"name":"Proof of Address","price":10}]
        )
        db.session.add_all([s1,s2])
        db.session.commit()
    print("DB initialized")


@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/register')
def register():
    return render_template('register.html')



# ✅ Route: Handle Form Submission
@app.route('/register', methods=['GET', 'POST'])
def register_user():
    name = request.form['full_name']
    email = request.form['email']
    phone = request.form['phone']
    password = request.form['password']
    confirm_password = request.form['confirm-password']

    if password != confirm_password:
        flash("Passwords do not match!", "error")
        return redirect(url_for('register'))

    hashed_password = generate_password_hash(password)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (name, email, phone, password) VALUES (%s, %s, %s, %s)",
            (name, email, phone, hashed_password)
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash("Registration successful!", "success")
        return redirect(url_for('login'))
    except Error as e:
        # print("MySQL Error:", e)
        flash(f"An error occurred: {e}", "Enter unique e-mail id")
        return redirect(url_for('register'))

# ✅ Route: Handle Form Login
@app.route('/login', methods=['GET', 'POST'])
def login_user():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        conn.close()

        if user:
            if check_password_hash(user['password'], password):
                #flash(f"✅ Login Successful! Welcome, {user['name']}.", "success")
                return redirect(url_for('home'))
            else:
                flash("❌ Incorrect password!", "error")
        else:
            flash("❌ Email not found!", "error")

    return render_template('login.html')


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        conn.close()

        if user:
            # Generate temporary password or reset token
            temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            hashed_temp_password = generate_password_hash(temp_password)

            # Update password in DB (temporary)
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET password=%s WHERE email=%s", (hashed_temp_password, email))
            conn.commit()
            conn.close()

            # Send email to user (simplest SMTP example)
            try:
                msg = EmailMessage()
                msg.set_content(f"Your temporary password is: {temp_password}\nPlease login and change it immediately.")
                msg['Subject'] = 'Reset Your Password'
                msg['From'] = 'hetvi5007@gmail.com'
                msg['To'] = email

                # Replace SMTP settings with your email provider
                with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
                    smtp.starttls()
                    smtp.login('hetvi5007@gmail.com', 'Malti@213')
                    smtp.send_message(msg)

                flash("A temporary password has been sent to your email.", "success")
            except Exception as e:
                flash(f"Failed to send email: {e}", "error")

        else:
            flash("Email not found!", "error")

    return render_template('forgot_password.html')

# About Section
@app.route('/about')
def about():
    # Example: decide whether to show the login button in header
    # If user is logged in you might set session['user_id'] somewhere else after login
    show_login = 'user_id' not in session
    # You can pass page_title, meta description, or any content you want
    return render_template(
        'about.html',
        show_login=show_login,
        page_title="About Us - Krishi E-Government Services"
    )



@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/send_message', methods=['POST'])
def send_message():
    # You can handle form data here (store in DB or send email)
    name = request.form['name']
    email = request.form['email']
    subject = request.form['subject']
    message = request.form['message']
    # Example: flash message or redirect
    flash("Your message has been sent successfully!", "success")
    return redirect(url_for('home'))

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')


services_data = [
    {
        "id": 1,
        "title": "PAN Card Services",
        "short_desc": "Apply or update your PAN card quickly and securely.",
        "long_desc": "We assist users with applying for new PAN cards, correcting existing information, and tracking the application status directly through authorized channels.",
        "image": "Pan Card.jpg",
        "documents": ["Passport size photo", "Aadhaar Card", "Proof of Address", "Date of Birth Proof"]
    },
    {
        "id": 2,
        "title": "Aadhaar Card Services",
        "short_desc": "Register or update your Aadhaar details easily.",
        "long_desc": "Our Aadhaar service helps you register for a new Aadhaar, update address or phone number, and track your application status seamlessly.",
        "image": "aadhaar.jpg",
        "documents": ["Passport size photo", "Proof of Address", "Proof of Identity"]
    },
    {
        "id": 3,
        "title": "Voter ID Services",
        "short_desc": "Get your new or updated Voter ID hassle-free.",
        "long_desc": "We simplify the process of applying for a new Voter ID or updating your details with the Election Commission of India.",
        "image": "voter.jpg",
        "documents": ["Passport size photo", "Proof of Residence", "Age Proof"]
    },
    {
        "id": 4,
        "title": "Passport Services",
        "short_desc": "Apply or renew your passport easily.",
        "long_desc": "We provide complete assistance for passport applications, renewals, document verification, and appointment scheduling.",
        "image": "Passport 2.jpg",
        "documents": ["Passport size photo", "Proof of Address", "Aadhaar Card", "Old Passport (if renewal)"]
    },
    {
        "id": 5,
        "title": "Driving License Services",
        "short_desc": "Apply for or renew your driving license.",
        "long_desc": "We guide you through new license applications, renewals, and test scheduling with the RTO efficiently.",
        "image": "license.jpg",
        "documents": ["Passport size photo", "Aadhaar Card", "Proof of Residence", "Medical Certificate"]
    },
]


with app.app_context():
    db.create_all()


@app.route('/services')
def services():
    all_services = Service.query.all()
    return render_template('services.html', services=all_services)

@app.route('/service/<int:service_id>')
def service_detail(service_id):
    service = Service.query.get_or_404(service_id)
    return render_template('service_detail.html', service=service)






@app.route('/cart/add', methods=['POST'])
def cart_add():
    data = request.json
    service_id = int(data['service_id'])
    selected_documents = data.get('selected_documents', [])
    service = Service.query.get_or_404(service_id)
    item_amount = float(calculate_item_amount(service, selected_documents))
    cart = session.get('cart', [])
    cart.append({
        "service_id": service_id,
        "title": service.title,
        "selected_documents": selected_documents,
        "item_amount": item_amount,
        "image": service.image
    })
    session['cart'] = cart
    session.modified = True
    return jsonify({"ok": True, "cart": cart})

@app.route('/cart')
def view_cart():
    cart = session.get('cart', [])
    return render_template('cart.html', cart=cart)

# Application form
@app.route('/apply', methods=['GET', 'POST'])
def apply():
    cart = session.get('cart', [])
    if not cart:
        flash("Your cart is empty.", "warning")
        return redirect(url_for('services'))

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        # create application and items
        total_amount = sum(Decimal(str(item['item_amount'])) for item in cart)
        app_obj = Application(
            app_id = generate_app_id(),
            applicant_name=name, email=email, phone=phone,
            total_amount=total_amount, status="Submitted"
        )
        db.session.add(app_obj)
        db.session.commit()  # get app_obj.id

        for item in cart:
            ai = ApplicationItem(
                application_id=app_obj.id,
                service_id=item['service_id'],
                selected_documents=item['selected_documents'],
                item_amount=Decimal(str(item['item_amount']))
            )
            db.session.add(ai)
        db.session.commit()

        # Create Razorpay order for total_amount (in paise)
        amount_paise = int(total_amount * 100)
        razorpay_order = razorpay_client.order.create(dict(amount=amount_paise, currency='INR', payment_capture=1))
        app_obj.razorpay_order_id = razorpay_order['id']
        db.session.commit()

        # clear cart
        session.pop('cart', None)

        # render payment page with order details
        return render_template('payment.html', service_order=app_obj, razorpay_order=razorpay_order, razorpay_key=RAZORPAY_KEY_ID)

    # GET -> show form
    return render_template('application_form.html', cart=cart)

# endpoint hit after successful payment (client redirect)
@app.route('/payment/success', methods=['POST'])
def payment_success():
    # Verify signature optionally if using client-side flow; Razorpay webhook recommended for final confirmation
    payload = request.form
    razorpay_payment_id = payload.get('razorpay_payment_id')
    razorpay_order_id = payload.get('razorpay_order_id')
    # Find application by razorpay_order_id
    app_obj = Application.query.filter_by(razorpay_order_id=razorpay_order_id).first()
    if not app_obj:
        abort(404)
    app_obj.razorpay_payment_id = razorpay_payment_id
    app_obj.status = "Processing"
    db.session.commit()
    return render_template('application_submitted.html', application=app_obj)

# Razorpay webhook example (configure webhook URL in Razorpay dashboard)
@app.route('/webhook/razorpay', methods=['POST'])
def razorpay_webhook():
    # IMPORTANT: verify signature using RAZORPAY_SECRET. See Razorpay docs.
    data = request.get_json()
    event = data.get('event')
    payload = data.get('payload', {})
    if event == "payment.captured":
        rp_payment = payload.get('payment', {}).get('entity', {})
        order_id = rp_payment.get('order_id')
        app_obj = Application.query.filter_by(razorpay_order_id=order_id).first()
        if app_obj:
            app_obj.status = "Completed"
            app_obj.razorpay_payment_id = rp_payment.get('id')
            db.session.commit()
    return jsonify({"status":"ok"}), 200

@app.route('/track', methods=['GET','POST'])
def track():
    app_info = None
    if request.method == 'POST':
        app_id = request.form.get('app_id')
        app_info = Application.query.filter_by(app_id=app_id).first()
        if not app_info:
            flash("Application not found", "danger")
    return render_template('track.html', app_info=app_info)

# simple application listing for user dashboard (optional)
@app.route('/my_applications')
def my_applications():
    # in production filter by logged-in user
    apps = Application.query.order_by(Application.created_at.desc()).all()
    return render_template('my_applications.html', apps=apps)


if __name__ == "__main__":
    app.run(debug=True)