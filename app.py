from flask import Flask, render_template, request, redirect, session
import datetime
import os
import requests
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-secret-key")

# ----------------------------
# EMAIL FUNCTION (UNCHANGED)
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
# SUPABASE REST API
# ----------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")  # Example: https://<project>.supabase.co/rest/v1/complaints
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")  # Supabase anon or service key

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

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
    timestamp = datetime.datetime.now().isoformat()

    # Insert into Supabase via REST API
    data = {
        "student_id": student_id,
        "student_email": student_email,
        "issue": issue_text,
        "category": category,
        "priority": priority,
        "timestamp": timestamp,
        "status": "Pending"
    }

    response = requests.post(f"{SUPABASE_URL}", json=data, headers=HEADERS)
    if response.status_code not in (200, 201):
        return f"Database error: {response.text}", 500

    complaint_id = response.json()[0]["id"] if response.json() else "N/A"

    # Send email to admin
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

    # Fetch complaints from Supabase
    response = requests.get(f"{SUPABASE_URL}?order=id.desc", headers=HEADERS)
    complaints = response.json() if response.status_code == 200 else []

    return render_template("dashboard.html", complaints=complaints)

@app.route('/resolve/<int:complaint_id>')
def resolve_complaint(complaint_id):
    if not session.get('admin'):
        return redirect('/')

    # Update status
    patch_data = {"status": "Resolved"}
    requests.patch(f"{SUPABASE_URL}?id=eq.{complaint_id}", json=patch_data, headers=HEADERS)

    # Get student email to send resolved mail
    response = requests.get(f"{SUPABASE_URL}?id=eq.{complaint_id}", headers=HEADERS)
    student_email = response.json()[0]["student_email"] if response.json() else None
    if student_email:
        send_email(
            student_email,
            f"Complaint {complaint_id} Resolved",
            "<p>Your complaint has been resolved.</p>"
        )

    return redirect('/dashboard')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect('/')

if __name__ == "__main__":
    app.run()






