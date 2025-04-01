from flask import Flask, request, jsonify
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime, time

import traceback
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from flask_mail import Mail, Message
import time as std_time


from paddleocr import PaddleOCR as pdl
from werkzeug.utils import secure_filename


app = Flask(__name__)



# Database connection configuration
def get_db_connection():
    """Establish and return a database connection."""
    conn = psycopg2.connect(
        database="legal",
        user="postgres",
        host='localhost',
        password="123456",
        port=5432
    )
    return conn

#SIGNUP
@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')

    if not name or not email or not password:
        return jsonify({'error': 'Missing fields'}), 400

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO Users (name, email, password_hash)
                VALUES (%s, %s, %s) RETURNING user_id, is_judge;
                """,
                (name, email, password)  # Store the password as plain text (no hashing)
            )
            result = cur.fetchone()
            conn.commit()
            user_id, is_judge = result
            return jsonify({'user_id': user_id, 'is_judge': is_judge}), 201
    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({'error': 'User with this email already exists'}), 409

# LOGIN
"""
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'error': 'Missing fields'}), 400

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, password_hash, is_judge FROM Users WHERE email = %s", (email,))
            user = cur.fetchone()

            if user is None:
                return jsonify({'error': 'User not found'}), 404

            user_id, stored_password, is_judge = user
            if stored_password == password:
                return jsonify({'user_id': user_id, 'is_judge': is_judge}), 200
            else:
                return jsonify({'error': 'Incorrect password'}), 401
    except Exception as e:
        return jsonify({'error': 'An error occurred'}), 500
"""
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'error': 'Missing fields'}), 400

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, password_hash, is_judge FROM Users WHERE email = %s", (email,))
            user = cur.fetchone()

            if user is None:
                return jsonify({'error': 'User not found'}), 404

            user_id, stored_password, is_judge = user
            if stored_password == password:
                return jsonify({'user_id': user_id, 'is_judge': is_judge}), 200
            else:
                return jsonify({'error': 'Incorrect password'}), 401
    except Exception as e:
        return jsonify({'error': 'An error occurred'}), 500

# REFERENCE ID PASS KEY CHECK
"""
@app.route('/api/validate_case', methods=['POST'])
def validate_case():
    data = request.get_json()
    reference_id = data.get('reference_id')
    pass_key = data.get('pass_key')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        SELECT * FROM cases WHERE reference_id = %s AND passkey = %s
    , (reference_id, pass_key))

    case = cursor.fetchone()
    cursor.close()

    if case:
        return jsonify({
            "status": "success",
            "case_id": case[0],
        }), 200
    else:
        return jsonify({"status": "error", "message": "Invalid reference ID or pass key"}), 401
"""
@app.route('/api/validate_case', methods=['POST'])
def validate_case():
    data = request.get_json()
    reference_id = data.get('reference_id')
    pass_key = data.get('pass_key')
    user_id = data.get('user_id')  # Get the user_id from the request

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT case_id FROM cases
            WHERE reference_id = %s AND passkey = %s
            """, (reference_id, pass_key)
        )
        case = cur.fetchone()

        if case:
            case_id = case[0]
            cur.execute(
                """
                UPDATE cases
                SET defendant_id = %s
                WHERE case_id = %s
                """, (user_id, case_id)
            )
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'case_id': case_id}), 200
        else:
            cur.close()
            conn.close()
            return jsonify({'message': 'Invalid reference ID or pass key'}), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# SAVE TEMP SLOTS (from prosecutor)
@app.route('/api/save_temp_slot', methods=['POST'])
def save_temp_slot():
    data = request.get_json()
    print("Received data:", data)  # Log the received data for debugging

    try:
        prosecutor_id = data['prosecutor_id']
        case_id = data['case_id']
        date = data['date']
        slots = data['slots']
    except KeyError as e:
        return jsonify({"error": f"Missing key: {str(e)}"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    for slot in slots:
        try:
            start_time = slot['start_time']
            end_time = slot['end_time']

            cursor.execute("""
                INSERT INTO temp_slots (case_id, prosecutor_id, date, start_time, end_time)
                VALUES (%s, %s, %s, %s, %s)
            """, (case_id, prosecutor_id, date, start_time, end_time))
        except KeyError as e:
            return jsonify({"error": f"Missing key in slot: {str(e)}"}), 400

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Slots saved successfully!"}), 201

# FETCH TEMP SLOTS
@app.route('/api/temp_slots', methods=['GET'])
def get_temp_slots():
    case_id = request.args.get('case_id')
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM temp_slots WHERE case_id = %s
    """, (case_id,))

    temp_slots = cursor.fetchall()
    cursor.close()
    conn.close()

    def format_time(value):
        if isinstance(value, datetime):
            return value.strftime("%H:%M:%S")
        elif isinstance(value, time):
            return value.strftime("%H:%M:%S")
        return str(value)

    temp_slots_list = [{
        'temp_slot_id': slot[0],
        'case_id': slot[1],
        'prosecutor_id': slot[2],
        'date': slot[3],
        'start_time': format_time(slot[4]),
        'end_time': format_time(slot[5]),
    } for slot in temp_slots]

    return jsonify(temp_slots_list), 200

# CONFIRM SLOT
@app.route('/api/confirm_slot', methods=['POST'])
def confirm_slot():
    data = request.get_json()
    case_id = data['case_id']
    date = data['date']
    start_time = data['start_time']
    end_time = data['end_time']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get defendant_id
        cursor.execute("""
            SELECT defendant_id FROM Cases WHERE case_id = %s
        """, (case_id,))
        result = cursor.fetchone()
        if result:
            defendant_id = result[0]
        else:
            cursor.close()
            conn.close()
            return jsonify({"message": "Case not found"}), 404

        # Get prosecutor_id
        cursor.execute("""
            SELECT prosecutor_id FROM Cases WHERE case_id = %s
        """, (case_id,))
        r = cursor.fetchone()
        if r:
            prosecutor_id = r[0]
        else:
            cursor.close()
            conn.close()
            return jsonify({"message": "Case not found"}), 404

        # Insert into Real_Slots
        cursor.execute("""
            INSERT INTO Real_Slots (case_id, date, start_time, end_time, booked_by_prosecutor_id, booked_by_defense_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (case_id, date, start_time, end_time, prosecutor_id, defendant_id))

        # Delete from Temp_Slots
        cursor.execute("""
            DELETE FROM Temp_Slots WHERE case_id = %s AND date = %s AND start_time = %s
        """, (case_id, date, start_time))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": "Slot confirmed successfully!"}), 200

    except Exception as e:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        return jsonify({"error": str(e)}), 500






app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'legalcourtroom@gmail.com'
app.config['MAIL_PASSWORD'] = 'lftv efdz akbt rdtq'
app.config['MAIL_DEFAULT_SENDER'] = 'njinesh239@gmail.com'

mail = Mail(app)








@app.route('/send-email', methods=['POST'])
def send_email():
    """Send an email to the defendant with case details."""
    try:
        data = request.json
        recipient = data.get('defendant_email')
        ref_id = data.get('reference_id')
        passkey = data.get('passkey')

        if not recipient:
            return jsonify({"error": "Recipient email is required"}), 400

        msg = Message(
            subject="Case Booking Confirmation",
            recipients=[recipient],
            body=f"We are writing to inform you that a case has been registered in your name. Below are the details of the case and the necessary credentials for you to access it.\n\nReference ID: {ref_id}\nPasskey: {passkey}.\nPlease keep these details safe and use the passkey to log in and access the petition and related documents.\n\nBest regards,\nVirtual Courtroom"
        )

        mail.send(msg)
        return jsonify({"message": "Email sent successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/store-case', methods=['POST'])
def store_case():
    """Store case details in the PostgreSQL database."""
    data = request.get_json()
    case_name = data.get('case_name')
    reference_id = data.get('reference_id')
    passkey = data.get('passkey')
    prosecutor_id = data.get('user_id')
    
    print(data)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO cases (case_name, reference_id, passkey, prosecutor_id)
            VALUES (%s, %s, %s, %s)
            RETURNING case_id
            """, (case_name, reference_id, passkey, prosecutor_id)
        )
        case_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'message': 'Case details stored successfully', 'case_id': case_id}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500





'''njs code copy
@app.route('/api/validate_case', methods=['POST'])
def validate_case():
    """Validate the case using reference ID and passkey."""
    data = request.get_json()
    reference_id = data.get('reference_id')
    pass_key = data.get('pass_key')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT * FROM cases WHERE reference_id = %s AND passkey = %s
        """, (reference_id, pass_key))

        case = cursor.fetchone()
        cursor.close()
        conn.close()

        if case:
            return jsonify({
                "status": "success",
                "case_id": case['case_id'],
                
            }), 200
        else:
            return jsonify({"status": "error", "message": "Invalid reference ID or pass key"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500

'''









"""
@app.route('/upload', methods=['POST'])
def upload_to_drive():
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    file_path = os.path.join('temp', file.filename)

    # Ensure the 'temp' directory exists
    os.makedirs('temp', exist_ok=True)

    try:
        file.save(file_path)

        # Upload file to Google Drive
        media = MediaFileUpload(file_path, mimetype='application/pdf')
        file_metadata = {'name': file.filename, 'parents': ['1bh35rYdDPH_0WZBhj_SCioRyXe9tojTw']}

        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()

        # Set permissions (public read access as an example)
        drive_service.permissions().create(
            fileId=uploaded_file['id'],
            body={'role': 'reader', 'type': 'anyone'}
        ).execute()
        file_link = f"https://drive.google.com/file/d/{uploaded_file['id']}/view?usp=sharing"
        # Cleanup and return file ID
        std_time.sleep(1)
        

        return jsonify({
            'file_id': uploaded_file.get('id'),
            'file_link': file_link
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
  
"""












@app.route('/savefileid', methods=['POST'])
def save_file_id():
    """Save the file ID associated with a case."""
    data = request.get_json()
    file_id = data.get('file_id')
    case_id = data.get('case_id')  # Use case_id instead of reference_id

    if not file_id or not case_id:
        return jsonify({'error': 'File ID and Case ID are required'}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            UPDATE cases
            SET file_id = %s
            WHERE case_id = %s
        """, (file_id, case_id))

        conn.commit()

        if cur.rowcount == 0:
            return jsonify({'error': 'Case not found for the given case ID'}), 404

        return jsonify({'message': 'File ID saved successfully'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()



@app.route('/get_file_id', methods=['POST'])
def get_file_id():
    """Retrieve the file ID corresponding to a case ID."""
    data = request.json
    case_id = data.get('case_id')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT file_id FROM cases WHERE case_id = %s', (case_id,))
    file_id = cur.fetchone()
    conn.close()

    if file_id:
        return jsonify({'file_id': file_id[0]}), 200
    else:
        return jsonify({'error': 'File ID not found for the given case ID'}), 404









# Configurations
UPLOAD_FOLDER = 'uploads/'
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ocr = pdl(use_angle_cls=True, lang='en')

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Google Drive API credentials and service setup
SCOPES = ['https://www.googleapis.com/auth/drive.file']
credentials = service_account.Credentials.from_service_account_file(
    'F:/vc/legalcourtroom/lib/service_account.json', scopes=SCOPES
)
drive_service = build('drive', 'v3', credentials=credentials)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_google_drive(file_path, filename):
    media = MediaFileUpload(file_path, mimetype='application/pdf')
    file_metadata = {'name': filename, 'parents': ['1bh35rYdDPH_0WZBhj_SCioRyXe9tojTw']}

    uploaded_file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()

    drive_service.permissions().create(
        fileId=uploaded_file['id'],
        body={'role': 'reader', 'type': 'anyone'}
    ).execute()

    return uploaded_file.get('id')

@app.route('/upload-and-process-ocr', methods=['POST'])
def upload_and_process_ocr():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Perform OCR on the uploaded file
        result = ocr.ocr(file_path, cls=True)
        texts = [line[-1][0] for line in result[0]]

        # Save the OCR-ed text to a file
        text_file_path = file_path.replace('.pdf', '.txt')
        with open(text_file_path, 'w', encoding='utf-8') as text_file:
            for text in texts:
                text_file.write(text + '\n')

        # Upload the PDF file to Google Drive
        try:
            file_id = upload_to_google_drive(file_path, filename)
            file_link = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"

            return jsonify({
                'message': 'File uploaded to Google Drive and OCR processed',
                'file_id': file_id,  # 🔥 Added this to the response
                'file_link': file_link,
                'text_file_path': text_file_path
            }), 200

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    else:
        return jsonify({'error': 'Invalid file format'}), 400



@app.route('/sendemail1', methods=['POST'])
def send_email1():
    """Send an email when the slot is confirmed."""
    try:
        data = request.json
        receiver_email = data.get('email')  # Email passed from frontend
        case_id = data.get('case_id')  # Case ID
        date = data.get('date')  # Selected date
        start_time = data.get('start_time')  # Start time of the slot
        end_time = data.get('end_time')  # End time of the slot

        # Validate if the required data exists
        if not receiver_email or not case_id or not date or not start_time or not end_time:
            return jsonify({"error": "Missing required fields"}), 400

        # Construct email body with the selected slot details
        email_body = f"""
        Dear Prosecutor,

        We are writing to inform you that your time slot for the case with Case ID: {case_id} has been confirmed. Below are the details of the scheduled slot:

        Date: {date}
        Time: {start_time} to {end_time}

        Please make a note of this information, and ensure to be available for the scheduled slot.

        Best regards,
        Virtual Courtroom
        """

        # Send email
        msg = Message(
            subject="Slot Confirmation for Your Case",
            recipients=[receiver_email],  # Receiver email passed from frontend
            body=email_body,
            sender='legalcourtroom@gmail.com'
        )

        mail.send(msg)
        return jsonify({"message": "Email sent successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True,host="0.0.0.0",port=5000)
