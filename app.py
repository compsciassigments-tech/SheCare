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
    if not to_email:
        return

    sender_email = os.environ.get("EMAIL_USER")
    app_password = os.environ.get("EMAIL_PASS")

    if not sender_email or not app_password:
        print("Email credentials missing")
        return

    try:
        msg = MIMEText(body, "html")
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = to_email

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print("Email error:", e)


# ----------------------------
# DATABASE
# ----------------------------
def get_connection():
    DATABASE_URL = os.environ.get("DATABASE_URL")
    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
        connect_timeout=5
    )


def init_db():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id SERIAL PRIMARY KEY,
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
# AI CLASSIFICATION (SAFE)
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
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """, (student_id, student_email, issue_text, category, priority, timestamp, "Pending"))

        complaint_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
    except Exception as e:
        return f"Database error: {e}", 500

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

    cursor.execute("UPDATE complaints SET status='Resolved' WHERE id=%s", (complaint_id,))
    cursor.execute("SELECT student_email FROM complaints WHERE id=%s", (complaint_id,))
    result = cursor.fetchone()

    conn.commit()
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


# ----------------------------
# STARTUP
# ----------------------------
init_db()

if __name__ == "__main__":
    app.run()



