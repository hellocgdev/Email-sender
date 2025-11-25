import os
import time
import threading
import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage 
from email import encoders
from email.utils import formataddr
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# --- CONFIGURATION ---
# ⚠️ UPDATE THESE WITH YOUR REAL CREDENTIALS
SMTP_SERVER = 'b.trytalrn.com'
SMTP_PORT = 465
SMTP_USER = 'hire@b.trytalrn.com'
SMTP_PASS = 'fMVl36h1g}KqAfR2'
SMTP_LIMIT = 150
SMTP_WINDOW = 3600  # seconds (1 hour)
QUEUE_FILE = 'mail_queue.json'
STATS_FILE = 'send_stats.json'
SENDER_NAME = "Talrn"

# --- APP SETUP ---
app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

send_stats = []
email_queue = []
queue_lock = threading.Lock()
scheduler_running = True

# --- HELPER: Get File Path in Current Folder ---
def get_local_path(filename):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, filename)

# --- HELPER: Send Email ---
def send_email_safely(recipient, subject, email_body, is_html, attachment=None, reply_to=None):
    try:
        msg = MIMEMultipart('related')
        msg['Subject'] = subject
        msg['From'] = formataddr((SENDER_NAME, SMTP_USER))
        msg['To'] = recipient

        # NEW: ADD REPLY-TO HEADER
        if reply_to:
            msg.add_header('Reply-To', reply_to)

        msg_alternative = MIMEMultipart('alternative')
        msg.attach(msg_alternative)

        if is_html:
            part_html = MIMEText(email_body, 'html', 'utf-8')
            msg_alternative.attach(part_html)
        else:
            part_text = MIMEText(email_body, 'plain', 'utf-8')
            msg_alternative.attach(part_text)

        # ATTACH LOGO
        logo_path = get_local_path("newlogo.png")
        if os.path.exists(logo_path):
            try:
                with open(logo_path, 'rb') as f:
                    img_data = f.read()
                msg_image = MIMEImage(img_data)
                msg_image.add_header('Content-ID', '<talrn_logo>')
                msg_image.add_header('Content-Disposition', 'inline', filename='newlogo.png')
                msg.attach(msg_image)
                logger.info(f"Attached inline logo from {logo_path}")
            except Exception as e:
                logger.warning(f"Failed to attach inline logo: {e}")
        
        if attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment['content'])
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f"attachment; filename= {attachment['filename']}")
            msg.attach(part)

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as smtp:
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(msg)

        logger.info(f"✅ Sent to: {recipient}")
        send_stats.append({'timestamp': time.time(), 'recipient': recipient, 'subject': subject, 'status': 'Success'})
        return True

    except Exception as e:
        logger.error(f"❌ Failed for {recipient}: {str(e)}")
        send_stats.append({'timestamp': time.time(), 'recipient': recipient, 'subject': subject, 'status': 'Failed', 'error': str(e)})
        return False

def email_scheduler():
    global scheduler_running
    while scheduler_running:
        with queue_lock:
            if email_queue:
                task = email_queue.pop(0)
                # Pass the 'reply_to' parameter from the task to the sender function
                send_email_safely(
                    task['recipient'], 
                    task['subject'], 
                    task['body'], 
                    task['is_html'], 
                    task.get('attachment'),
                    task.get('reply_to') # <--- PASSING IT HERE
                )
        time.sleep(2)

# --- ROUTES ---

@app.route('/')
def index():
    path = get_local_path('ai_email_sender_frontend.html')
    if os.path.exists(path):
        return send_file(path)
    else:
        return f"<h1>Error: Frontend file not found at {path}</h1>"

@app.route('/send-email', methods=['POST'])
def api_send_email():
    data = request.json
    recipients = data.get('recipients', '').split(',')
    subject = data.get('subject', 'Talrn Invitation')
    body = data.get('email_body', '')
    is_html = data.get('is_html', False)
    reply_to = data.get('reply_to', None) # Get Reply-To from Frontend

    with queue_lock:
        for email in recipients:
            email = email.strip()
            if email:
                email_queue.append({
                    'recipient': email, 
                    'subject': subject, 
                    'body': body, 
                    'is_html': is_html,
                    'reply_to': reply_to # Store it in the queue
                })
    
    success_msg = f"Successfully queued {len(recipients)} emails."
    return jsonify({
        "status": "Queued", 
        "message": success_msg,
        "msg": success_msg,
        "count": len(recipients)
    })

@app.route('/stats', methods=['GET'])
def get_stats():
    return jsonify(send_stats)

if __name__ == '__main__':
    t = threading.Thread(target=email_scheduler)
    t.daemon = True
    t.start()
    print("🚀 Server running on http://localhost:5000")
    app.run(port=5000, debug=True)
