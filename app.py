from MySQLdb import MySQLError
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, jsonify
from mysql.connector import Error
from werkzeug.security import generate_password_hash
from flask_mysqldb import MySQL
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
from decimal import Decimal
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.mysql import JSON
from email.message import EmailMessage
import mysql.connector, random, string, json, os, uuid, smtplib, MySQLdb.cursors, razorpay, warnings
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

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
razorpay_client = razorpay.Client(auth=("rzp_test_RYA0tri2cAfoE8", "FuIi5rksxQoJ294Qg9trERek"))

# ✅ Database Connection
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",        # replace with your MySQL username
        password="root",  # replace with your MySQL password
        database="gov_services"
    )

# --- STEP 1: Connect to MySQL ---
try:
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",  # update if different
        database="gov_services"   # update if different
    )
    cursor = conn.cursor()
    print("✅ Database connected successfully.")
except mysql.connector.Error as err:
    print("❌ MySQL connection error:", err)

# --- STEP 2: Load JSON file safely ---
json_path = r"C:\Users\Hetvi\OneDrive\Desktop\Final Year Project\E-Gov\data.json"  # update your path

if not os.path.exists(json_path):
    print(f"❌ JSON file not found: {json_path}")
    exit()

try:
    with open(json_path, "r", encoding="utf-8") as file:
        data = json.load(file)
        if not data:
            print("❌ JSON file is empty or invalid.")
            exit()
except json.JSONDecodeError as e:
    print(f"❌ Invalid JSON format: {e}")
    exit()
print("✅ JSON loaded successfully.")

with app.app_context():
    db.create_all()

# ---------- MODELS ----------
# ✅ Define your model
class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255))
    image = db.Column(db.String(255))
    short_desc = db.Column(db.Text)
    long_desc = db.Column(db.Text)
    base_price = db.Column(db.Float)
    documents = db.Column(db.Text)  # ✅ store as TEXT  # list of {"name": "Aadhaar", "price": 20.0}

class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    app_id = db.Column(db.String(50), unique=True, index=True)  # e.g., APP-0001
    name = db.Column(db.String(200))
    email = db.Column(db.String(200))
    mobile = db.Column(db.String(50))
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
    prefix = "APP"
    suffix = ''.join(random.choices(string.digits, k=6))
    return f"{prefix}{suffix}"

def calculate_item_amount(service_obj, selected_doc_names):
    import json
    total = Decimal(service_obj.base_price or 0)
    docs = service_obj.documents

    # ✅ Convert JSON text to Python list
    try:
        docs = json.loads(docs) if docs else []
    except Exception:
        docs = []

    for doc in docs:
        if isinstance(doc, dict) and doc.get('name') in selected_doc_names:
            total += Decimal(str(doc.get('price', 0)))
    return total



@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register')
def register():
    return render_template('register.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')


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

# ✅ Route: Forget Password
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

# ✅ Route: About Section
@app.route('/about')
def about():
    # Example: decide whether to show the login button in header
    # If user is logged in you might set session['user_id'] somewhere else after login
    show_login = 'user_id' not in session
    return render_template(
        'about.html',
        show_login=show_login,
        page_title="About Us - Krishi E-Government Services"
    )


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



# ✅ Route to display all services
@app.route('/services')
def services():
    conn = get_db_connection()
    if conn is None:
        flash("Database connection failed!", "danger")
        return render_template('services.html', services=[])
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, title, short_desc, base_price, documents, image FROM service")
        services = cursor.fetchall()
        if not services:
            print("⚠️ No services found in database.")
            flash("No services available at the moment.", "warning")
            services = []
        return render_template('services.html', services=services)
    except Error as err:
        print(f"❌ MySQL error: {err}")
        flash("An error occurred while fetching services.", "danger")
        return render_template('services.html', services=[])
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
            print("🔒 Database connection closed.")

@app.route("/service/<int:id>")
def service_detail(id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM service WHERE id = %s", (id,))
        service = cursor.fetchone()
        if not service:
            return "Service not found", 404

        # ✅ Convert comma-separated document names into a list
        if service.get("documents"):
            service["documents"] = [doc.strip() for doc in service["documents"].split(",") if doc.strip()]
        else:
            service["documents"] = []

        return render_template("service_detail.html", service=service)
    
    except mysql.connector.Error as err:
        flash(f"MySQL Error: {err}", "danger")
        return redirect(url_for("services"))
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


# ✅ Correct "Apply" button redirection target
# ✅ Show service form and handle submission after payment
import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/images'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/application_form/<int:id>", methods=["GET", "POST"])
def application_form(id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM service WHERE id = %s", (id,))
    service = cur.fetchone()
    cur.close()
    conn.close()

    if not service:
        return "Service not found", 404

    # Split document list
    if service.get("documents"):
        service["documents"] = [doc.strip() for doc in service["documents"].split(",") if doc.strip()]
    else:
        service["documents"] = []

    if request.method == "POST":
        # Temporarily store form details in session
        session["form_data"] = {
            "service_id": id,
            "name": request.form["name"],
            "email": request.form["email"],
            "mobile": request.form["phone"],
        }
        return redirect(url_for("payment", id=id))

    return render_template("application_form.html", service=service)





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
def generate_app_id():
    prefix = "APP"
    suffix = ''.join(random.choices(string.digits, k=6))
    return f"{prefix}{suffix}"
@app.route('/apply', methods=['POST'])
def apply():
    if 'user_id' not in session:
        flash("Please login first.", "warning")
        return redirect(url_for('login'))

    user_id = session['user_id']
    name = request.form['name']
    email = request.form['email']
    mobile = request.form['mobile']
    service_id = request.form['service_id']

    try:
        cur = mysql.connection.cursor(dictionary=True)
        
        # ✅ Fetch service_name and base_price correctly
        cur.execute("SELECT title AS service_name, base_price AS total_amount FROM services WHERE id = %s", (service_id,))
        service = cur.fetchone()

        if not service:
            flash("Service not found.", "danger")
            return redirect(url_for('services'))

        # ✅ Use correct dictionary keys
        service_name = service['service_name']
        total_amount = service['base_price']

        # ✅ Generate unique Application ID
        app_id = "APP" + ''.join(random.choices(string.digits, k=6))

        # ✅ Insert everything properly
        cur.execute("""
            INSERT INTO application (app_id, user_id, name, email, mobile, service_id, service_name, total_amount)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (app_id, user_id, name, email, mobile, service_id, service_name, total_amount))

        mysql.connection.commit()
        cur.close()

        flash("Application submitted successfully!", "success")
        return redirect(url_for('my_applications'))

    except Error as e:
        print("❌ MySQL error:", e)
        flash("An error occurred while submitting your application.", "danger")
        return redirect(url_for('services'))






@app.route("/submit_application/<int:id>", methods=["POST"])
def submit_application(id):
    try:
        # Get form data
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]

        # Connect to DB
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="root",
            database="gov_services"
        )
        cursor = conn.cursor()

        # Insert data
        cursor.execute("""
            INSERT INTO application (service_id, name, email, phone, status)
            VALUES (%s, %s, %s, %s, %s)
        """, (id, name, email, phone, "Pending"))

        conn.commit()
        cursor.close()
        conn.close()

        flash("✅ Application submitted successfully!", "success")
        return redirect(url_for("my_applications"))

    except mysql.connector.Error as err:
        print(f"MySQL error: {err}")
        flash("❌ Database error, please try again later.", "danger")
        return redirect(url_for("application_form", id=id))

    except Exception as e:
        print(f"Error: {e}")
        flash("❌ Unexpected error occurred.", "danger")
        return redirect(url_for("application_form", id=id))



@app.route("/apply_service/<int:id>")
def apply_service(id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM services WHERE id = %s", (id,))
        service = cursor.fetchone()
        cursor.close()
        conn.close()

        if not service:
            flash("Service not found.", "danger")
            return redirect(url_for("services"))

        return render_template("apply_service.html", service=service)

    except Error as e:
        flash(f"MySQL Error: {e}", "danger")
        return redirect(url_for("services"))



@app.route("/payment/<int:id>", methods=["GET", "POST"])
def payment(id):
    # Fetch service details
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM service WHERE id = %s", (id,))
    service = cur.fetchone()
    cur.close()
    conn.close()

    if not service:
        return "Service not found", 404

    # Get form data from session
    form_data = session.get("form_data")

    # ✅ If someone visits this page directly without submitting form first
    if not form_data:
        flash("Please fill out the application form first.", "warning")
        return redirect(url_for("application_form", id=id))

    # 🧾 When submit button is clicked (after payment done)
    if request.method == "POST":
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO application (service_id, name, email, mobile, payment_status)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            form_data["service_id"],
            form_data["name"],
            form_data["email"],
            form_data["mobile"],
            "Completed"
        ))
        conn.commit()
        cur.close()
        conn.close()

        # Remove data from session
        session.pop("form_data", None)

        flash("✅ Application submitted successfully!", "success")
        return redirect(url_for("my_applications"))

    # 🧭 Render payment page
    return render_template("payment.html", service=service)




@app.route("/my_applications")
def my_applications():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM application ORDER BY id DESC")
    applications = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("my_applications.html", applications=applications)



@app.route("/create_order", methods=["POST"])
def create_order():
    import razorpay
    data = request.get_json()
    amount = data.get("amount")  # amount in paise

    client = razorpay.Client(auth=("rzp_test_RYA0tri2cAfoE8", "FuIi5rksxQoJ294Qg9trERek"))

    order = client.order.create({
        "amount": amount,
        "currency": "INR",
        "payment_capture": "1"
    })

    return jsonify(order)





    

@app.route("/payment_success")
def payment_success():
    payment_id = request.args.get("payment_id")
    flash(f"Payment successful! Payment ID: {payment_id}", "success")
    return redirect(url_for("home"))



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




if __name__ == "__main__":
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="root",
            database="gov_services"
        )
        cursor = conn.cursor()

        # ✅ Check if the service table already has rows
        cursor.execute("SELECT COUNT(*) FROM service")
        count = cursor.fetchone()[0]

        if count == 0:
            print("🟡 No existing data found. Inserting sample JSON records...")
            for record in data:
                title = record.get("title")
                short_desc = record.get("short_desc")
                documents = json.dumps(record.get("documents", []))
                base_price = record.get("base_price", 0)

                cursor.execute("""
                    INSERT INTO service (title, short_desc, documents, base_price)
                    VALUES (%s, %s, %s, %s)
                """, (title, short_desc, documents, base_price))

            conn.commit()
            print("✅ Sample JSON data inserted successfully into MySQL.")
        else:
            print(f"⚠️ Skipping JSON insertion — {count} services already exist in DB.")

    except mysql.connector.Error as err:
        print(f"❌ MySQL error: {err}")
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
            print("🔒 Database connection closed.")
    
    app.run(debug=True)