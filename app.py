from flask import Flask, render_template, request, redirect, session
import datetime
import os
import psycopg2
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)

# ----------------------------
# SECURITY CONFIG
# ----------------------------
app.secret_key = os.environ.get("SECRET_KEY", "fallback-secret-key")


# ----------------------------
# EMAIL FUNCTION (SAFE)
# ----------------------------
def send_email(to_email, subject, body):
    try:
        sender_email = os.environ.get("EMAIL_USER")
        app_password = os.environ.get("EMAIL_PASS")

        if not sender_email or not app_password or not to_email:
            return

        msg = MIMEText(body, "html")
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = to_email

        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        server.starttls()
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()

    except Exception as e:
        print("Email error:", e)


# ----------------------------
# DATABASE (BULLETPROOF)
# ----------------------------
def get_connection():
    try:
        return psycopg2.connect(
            os.environ.get("DATABASE_URL"),
            sslmode="require",
            connect_timeout=5
        )
    except Exception as e:
        print("Database error:", e)
        return None


# ----------------------------
# AI CLASSIFICATION
# ----------------------------
def analyze_issue(text):
    text = (text or "").lower()

    if any(word in text for word in ["ragging", "harassment", "threat"]):
        return "CRITICAL - Security Cell", "Priority 1"
    elif any(word in text for word in ["fan", "water", "washroom", "bench", "light"]):
        return "Infrastructure", "Priority 2"
    elif any(word in text for word in ["exam", "marks", "fee", "syllabus", "hall ticket"]):
        return "Academic Affairs", "Priority 3"
    else:
        return "General Administration", "Priority 4"


# ----------------------------
# ROUTES
# ----------------------------
@app.route('/')
def home():
    return render_template('index.html')


@app.route('/submit', methods=['POST'])
def submit():
    student_id = request.form.get('student_id') or "Anonymous"
    student_email = request.form.get('student_email')
    issue_text = request.form.get('issue', '').strip()

    if not issue_text:
        return "Issue cannot be empty", 400

    category, priority = analyze_issue(issue_text)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = get_connection()
    if not conn:
        return "Database temporarily unavailable. Please try again later."

    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO complaints
            (student_id, student_email, issue, category, priority, timestamp, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (student_id, student_email, issue_text, category, priority, timestamp, "Pending"))

        complaint_id = cursor.fetchone()[0]
        conn.commit()

    except Exception as e:
        print("Insert error:", e)
        return "Something went wrong while submitting your complaint."

    finally:
        conn.close()

    send_email(
        os.environ.get("ADMIN_EMAIL"),
        f"New Complaint Registered (ID {complaint_id})",
        f"<p><strong>Issue:</strong><br>{issue_text}</p>"
    )

    return redirect('/')


@app.route('/admin_login', methods=['POST'])
def admin_login():
    if (
        request.form.get('username') == os.environ.get("ADMIN_USER") and
        request.form.get('password') == os.environ.get("ADMIN_PASS")
    ):
        session['admin'] = True
        return redirect('/dashboard')

    return "Invalid login", 401


@app.route('/dashboard')
def dashboard():
    if not session.get('admin'):
        return redirect('/')

    conn = get_connection()
    if not conn:
        return "Database temporarily unavailable. Please refresh."

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM complaints ORDER BY id DESC")
        complaints = cursor.fetchall()
    except Exception as e:
        print("Dashboard error:", e)
        return "Unable to load complaints."
    finally:
        conn.close()

    return render_template("dashboard.html", complaints=complaints)


@app.route('/resolve/<int:complaint_id>')
def resolve_complaint(complaint_id):
    if not session.get('admin'):
        return redirect('/')

    conn = get_connection()
    if not conn:
        return "Database temporarily unavailable."

    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE complaints SET status='Resolved' WHERE id=%s", (complaint_id,))
        cursor.execute("SELECT student_email FROM complaints WHERE id=%s", (complaint_id,))
        result = cursor.fetchone()
        conn.commit()
    except Exception as e:
        print("Resolve error:", e)
        return "Could not resolve complaint."
    finally:
        conn.close()

    if result and result[0]:
        send_email(
            result[0],
            f"Complaint {complaint_id} Resolved",
            "<p>Your complaint has been resolved.</p>"
        )

    return redirect('/dashboard')


@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect('/')






