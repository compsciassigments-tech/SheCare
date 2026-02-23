from flask import Flask, render_template, request, redirect, session
import datetime
import os
import sqlite3

# ----------------------------
# SENDGRID IMPORTS
# ----------------------------
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-secret-key")

# ----------------------------
# EMAIL FUNCTION (SENDGRID)
# ----------------------------
def send_email(to_email, subject, body):
    if not to_email:
        return

    sender_email = os.environ.get("EMAIL_USER")  # verified sender in SendGrid
    sendgrid_api_key = os.environ.get("SENDGRID_API_KEY")

    if not sender_email or not sendgrid_api_key:
        print("SendGrid credentials missing")
        return

    try:
        message = Mail(
            from_email=sender_email,
            to_emails=to_email,
            subject=subject,
            html_content=body
        )
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        print(f"Email sent to {to_email}, status {response.status_code}")
    except Exception as e:
        print("Email error:", e)

# ----------------------------
# DATABASE
# ----------------------------
DB_FILE = "complaints.db"

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT,
                student_email TEXT,
                issue TEXT,
                category TEXT,
                priority TEXT,
                timestamp TEXT,
                status TEXT
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print("DB init error:", e)

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

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO complaints (student_id, student_email, issue, category, priority, timestamp, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (student_id, student_email, issue_text, category, priority, timestamp, "Pending"))
        complaint_id = cursor.lastrowid
        conn.commit()
        conn.close()
    except Exception as e:
        return f"Database error: {e}", 500

    # Email to admin
    admin_email = os.environ.get("ADMIN_EMAIL")
    send_email(
        admin_email,
        f"New Complaint Registered (ID {complaint_id})",
        f"<p><strong>Issue:</strong><br>{issue_text}</p>"
    )

    return redirect('/')

@app.route('/admin_login', methods=['POST'])
def admin_login():
    username = request.form.get('username')
    password = request.form.get('password')

    if username == os.environ.get("ADMIN_USER") and password == os.environ.get("ADMIN_PASS"):
        session['admin'] = True
        return redirect('/dashboard')

    return "Invalid Login", 401

@app.route('/dashboard')
def dashboard():
    if not session.get('admin'):
        return redirect('/')

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM complaints ORDER BY id DESC")
    complaints = cursor.fetchall()
    conn.close()

    return render_template("dashboard.html", complaints=complaints)

@app.route('/resolve/<int:complaint_id>')
def resolve_complaint(complaint_id):
    if not session.get('admin'):
        return redirect('/')

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE complaints SET status='Resolved' WHERE id=?", (complaint_id,))
    cursor.execute("SELECT student_email, issue FROM complaints WHERE id=?", (complaint_id,))
    result = cursor.fetchone()
    conn.commit()
    conn.close()

    if result and result[0]:
        # Include original complaint in the email
        send_email(
            result[0],
            f"Complaint {complaint_id} Resolved",
            f"<p>Your complaint has been resolved.</p><p><strong>Issue:</strong> {result[1]}</p>"
        )

    return redirect('/dashboard')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect('/')

# ----------------------------
# STARTUP
# ----------------------------
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

