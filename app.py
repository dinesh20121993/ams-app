import io
import os
import re
import sqlite3
from functools import wraps
import qrcode
import pandas as pd
from datetime import date, datetime
from dotenv import load_dotenv
from flask import (Flask, render_template, request, redirect, url_for,
                   jsonify, send_file, flash, session, g)
from database import init_db, get_connection
from email_service import send_registration_email

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'ams-dev-secret-key')

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
QRCODE_DIR = os.path.join(BASE_DIR, 'static', 'qrcodes')
os.makedirs(QRCODE_DIR, exist_ok=True)

with app.app_context():
    init_db()

# ── Auth ───────────────────────────────────────────────────────────────────────

@app.before_request
def load_auth():
    # Expose auth state to every template via g (avoids name collision with
    # db 'session' rows that some views pass as template variables)
    g.authenticated = session.get('authenticated', False)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('authenticated'):
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        entered   = request.form.get('password', '').strip()
        correct   = os.environ.get('TRAINER_PASSWORD', '')
        if not correct:
            error = 'Server error: TRAINER_PASSWORD is not configured.'
        elif entered == correct:
            session.clear()
            session['authenticated'] = True
            return redirect(url_for('index'))
        else:
            error = 'Incorrect password. Please try again.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ── Helpers ────────────────────────────────────────────────────────────────────

def _write_qr(filepath, url):
    qr = qrcode.QRCode(
        box_size=8,
        border=3,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr.make_image(fill_color='#1a202c', back_color='white').save(filepath)

def generate_qr(session_id, base_url):
    """Generate a QR PNG for attendance marking (regenerated every load)."""
    filename = f'session_{session_id}.png'
    filepath = os.path.join(QRCODE_DIR, filename)
    _write_qr(filepath, f'{base_url}mark-attendance?session_id={session_id}')
    return f'qrcodes/{filename}'

def generate_register_qr(base_url):
    """Generate the static registration QR once; skip if already on disk."""
    filepath = os.path.join(QRCODE_DIR, 'register_qr.png')
    if not os.path.exists(filepath):
        _write_qr(filepath, f'{base_url}student-register')
    return 'qrcodes/register_qr.png'

# ── Home ───────────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    return render_template('index.html')

# ── Student Registration Form (PUBLIC – accessed via QR code) ─────────────────

@app.route('/student-register', methods=['GET'])
def student_register_form():
    return render_template('student_register.html')

@app.route('/student-register', methods=['POST'])
def student_register_submit():
    name        = request.form.get('name',        '').strip()
    mobile      = request.form.get('mobile',      '').strip()
    email       = request.form.get('email',       '').strip()
    gender      = request.form.get('gender',      '').strip()
    course_name = request.form.get('course_name', 'Python Programming').strip()
    batch_name  = request.form.get('batch_name',  '').strip()

    if not mobile.isdigit() or len(mobile) != 10:
        return _error('Invalid Mobile', 'Please enter a valid 10-digit mobile number.')

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM students WHERE mobile = ?', (mobile,))
    if cursor.fetchone():
        conn.close()
        return _error('Already Registered',
                      'This mobile number is already registered. '
                      'Please contact your trainer if you think this is a mistake.')

    cursor.execute(
        '''INSERT INTO students (name, mobile, email, gender, course_name, batch_name)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (name, mobile, email, gender, course_name, batch_name),
    )
    conn.commit()
    conn.close()

    send_registration_email({
        'name':       name,
        'email':      email,
        'mobile':     mobile,
        'batch_name': batch_name,
    })

    return redirect(url_for('registration_success', name=name, email=email))

@app.route('/registration-success')
def registration_success():
    name  = request.args.get('name',  'Student')
    email = request.args.get('email', '')
    return render_template('registration_success.html', name=name, email=email)

# ── Add Student (trainer manual entry) ────────────────────────────────────────

@app.route('/add-student', methods=['GET'])
@login_required
def add_student_form():
    return render_template('add_student.html')

@app.route('/add-student', methods=['POST'])
@login_required
def add_student_submit():
    name        = request.form.get('name',        '').strip()
    mobile      = request.form.get('mobile',      '').strip()
    email       = request.form.get('email',       '').strip()
    gender      = request.form.get('gender',      '').strip()
    course_name = request.form.get('course_name', 'Python Programming').strip()
    batch_name  = request.form.get('batch_name',  '').strip()

    form_data = dict(name=name, mobile=mobile, email=email,
                     gender=gender, course_name=course_name, batch_name=batch_name)

    if not mobile.isdigit() or len(mobile) != 10:
        return render_template('add_student.html', form=form_data,
                               error_mobile='Mobile number must be exactly 10 digits.')

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM students WHERE mobile = ?', (mobile,))
    if cursor.fetchone():
        conn.close()
        return render_template('add_student.html', form=form_data,
                               error_mobile='Mobile number already registered.')

    cursor.execute(
        '''INSERT INTO students (name, mobile, email, gender, course_name, batch_name)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (name, mobile, email, gender, course_name, batch_name),
    )
    conn.commit()
    conn.close()

    flash('Student added successfully!')
    return redirect(url_for('add_student_form'))

# ── Manual Attendance (trainer) ────────────────────────────────────────────────

def _load_sessions(cursor):
    cursor.execute(
        'SELECT id, session_name, date FROM sessions ORDER BY date DESC, start_time DESC'
    )
    return cursor.fetchall()

@app.route('/manual-attendance', methods=['GET'])
@login_required
def manual_attendance_form():
    conn   = get_connection()
    cursor = conn.cursor()
    sessions = _load_sessions(cursor)
    conn.close()
    return render_template('manual_attendance.html', sessions=sessions)

@app.route('/manual-attendance', methods=['POST'])
@login_required
def manual_attendance_submit():
    session_id = request.form.get('session_id', type=int)
    mobile     = request.form.get('mobile', '').strip()

    conn   = get_connection()
    cursor = conn.cursor()
    sessions  = _load_sessions(cursor)
    form_data = {'session_id': session_id, 'mobile': mobile}

    def rerender(**errors):
        conn.close()
        return render_template('manual_attendance.html',
                               sessions=sessions, form=form_data, **errors)

    if not session_id:
        return rerender(error_session='Please select a session.')

    if not mobile.isdigit() or len(mobile) != 10:
        return rerender(error_mobile='Mobile number must be exactly 10 digits.')

    cursor.execute('SELECT * FROM students WHERE mobile = ?', (mobile,))
    student = cursor.fetchone()
    if not student:
        return rerender(error_mobile='Student not found. Please register them first.')

    cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
    db_session = cursor.fetchone()
    if not db_session:
        return rerender(error_session='Selected session does not exist.')

    cursor.execute(
        'SELECT id FROM attendance WHERE student_mobile = ? AND session_id = ?',
        (mobile, session_id)
    )
    if cursor.fetchone():
        return rerender(
            error_mobile='Attendance already marked for this student in this session.'
        )

    cursor.execute(
        'INSERT INTO attendance (student_mobile, session_id) VALUES (?, ?)',
        (mobile, session_id)
    )
    conn.commit()
    conn.close()

    flash(f"{student['name']} marked present for {db_session['session_name']}")
    return redirect(url_for('manual_attendance_form'))

# ── Register Student QR ────────────────────────────────────────────────────────

@app.route('/register-student-qr')
@login_required
def register_student_qr():
    qr_path = generate_register_qr(request.url_root)
    return render_template('register_student_qr.html', qr_path=qr_path)

# ── Start Session ──────────────────────────────────────────────────────────────

@app.route('/start-session', methods=['GET'])
@login_required
def start_session_form():
    return render_template('start_session.html', today=date.today().isoformat())

@app.route('/start-session', methods=['POST'])
@login_required
def start_session_submit():
    session_name = request.form['session_name'].strip()
    session_date = request.form['date']
    start_time   = datetime.now()

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO sessions (session_name, date, start_time) VALUES (?, ?, ?)',
        (session_name, session_date, start_time)
    )
    conn.commit()
    session_id = cursor.lastrowid
    conn.close()

    return redirect(url_for('active_session', session_id=session_id))

# ── Active Session ─────────────────────────────────────────────────────────────

SESSION_DURATION = 600  # 10 minutes in seconds

@app.route('/active-session/<int:session_id>')
@login_required
def active_session(session_id):
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
    db_session = cursor.fetchone()
    conn.close()

    if db_session is None:
        return 'Session not found', 404

    start_time        = datetime.fromisoformat(db_session['start_time'])
    elapsed           = (datetime.now() - start_time).total_seconds()
    seconds_remaining = max(0, int(SESSION_DURATION - elapsed))
    qr_path           = generate_qr(session_id, request.url_root)

    return render_template(
        'active_session.html',
        session=db_session,
        qr_path=qr_path,
        seconds_remaining=seconds_remaining,
    )

# ── Attendance Feed (JSON) ─────────────────────────────────────────────────────

@app.route('/attendance-feed/<int:session_id>')
@login_required
def attendance_feed(session_id):
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COALESCE(s.name, a.student_mobile) AS name,
               a.student_mobile                   AS mobile,
               a.timestamp
        FROM   attendance a
        LEFT JOIN students s ON s.mobile = a.student_mobile
        WHERE  a.session_id = ?
        ORDER  BY a.timestamp ASC
    ''', (session_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(rows)

# ── Mark Attendance (PUBLIC – accessed via QR code) ───────────────────────────

def _error(title, message):
    return render_template('attendance_success.html',
                           status='error', title=title, message=message)

def _get_live_session(session_id):
    """Return session row if it exists and is still within SESSION_DURATION, else None."""
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
    db_session = cursor.fetchone()
    conn.close()
    if db_session is None:
        return None, 'Session not found'
    elapsed = (datetime.now() - datetime.fromisoformat(db_session['start_time'])).total_seconds()
    if elapsed > SESSION_DURATION:
        return None, 'Session has expired'
    return db_session, None

@app.route('/mark-attendance', methods=['GET'])
def mark_attendance_form():
    session_id = request.args.get('session_id', type=int)
    if not session_id:
        return _error('Invalid Link', 'This QR code link is invalid.')

    db_session, err = _get_live_session(session_id)
    if err:
        return _error('Session Expired' if 'expired' in err else 'Not Found', err)

    return render_template('mark_attendance.html', session=db_session)

@app.route('/mark-attendance', methods=['POST'])
def mark_attendance_submit():
    session_id = request.form.get('session_id', type=int)
    mobile     = request.form.get('mobile', '').strip()

    if not mobile.isdigit() or len(mobile) != 10:
        return _error('Invalid Mobile', 'Please enter a valid 10-digit mobile number.')

    db_session, err = _get_live_session(session_id)
    if err:
        return _error('Session Expired' if 'expired' in err else 'Not Found', err)

    conn   = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM students WHERE mobile = ?', (mobile,))
    student = cursor.fetchone()
    if student is None:
        conn.close()
        return _error('Not Registered',
                      'This mobile number is not registered. Please contact your trainer.')

    try:
        cursor.execute(
            'INSERT INTO attendance (student_mobile, session_id) VALUES (?, ?)',
            (mobile, session_id)
        )
        conn.commit()
        conn.close()
        return render_template(
            'attendance_success.html',
            status='success',
            title='Attendance Marked',
            message=f"{student['name']} has attended {db_session['session_name']}",
        )
    except sqlite3.IntegrityError:
        conn.close()
        return _error('Already Marked',
                      'Your attendance has already been marked for this session.')

# ── View Attendance ────────────────────────────────────────────────────────────

@app.route('/view-attendance')
@login_required
def view_attendance():
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.id,
               s.session_name,
               s.date,
               s.start_time,
               COUNT(a.id) AS attendee_count
        FROM   sessions s
        LEFT JOIN attendance a ON a.session_id = s.id
        GROUP  BY s.id
        ORDER  BY s.date DESC, s.start_time DESC
    ''')
    sessions = cursor.fetchall()
    conn.close()
    return render_template('view_attendance.html', sessions=sessions)

@app.route('/view-attendance/<int:session_id>')
@login_required
def session_detail(session_id):
    conn   = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
    db_session = cursor.fetchone()
    if db_session is None:
        conn.close()
        return 'Session not found', 404

    cursor.execute('''
        SELECT st.name,
               st.mobile,
               st.email,
               st.batch_name,
               a.timestamp
        FROM   attendance a
        JOIN   students st ON st.mobile = a.student_mobile
        WHERE  a.session_id = ?
        ORDER  BY a.timestamp ASC
    ''', (session_id,))
    records = cursor.fetchall()

    cursor.execute('''
        SELECT name, mobile, batch_name
        FROM   students
        WHERE  mobile NOT IN (
            SELECT student_mobile FROM attendance WHERE session_id = ?
        )
        ORDER  BY name ASC
    ''', (session_id,))
    absent = cursor.fetchall()
    conn.close()

    return render_template('session_detail.html',
                           session=db_session, records=records, absent=absent)

# ── Download Excel ─────────────────────────────────────────────────────────────

@app.route('/download-excel/<int:session_id>')
@login_required
def download_excel(session_id):
    conn   = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
    db_session = cursor.fetchone()
    if db_session is None:
        conn.close()
        return 'Session not found', 404

    cursor.execute('''
        SELECT st.name        AS "Name",
               st.mobile      AS "Mobile",
               st.email       AS "Email",
               s.session_name AS "Session Name",
               s.date         AS "Date",
               st.batch_name  AS "Batch Name",
               a.timestamp    AS "Timestamp"
        FROM   attendance a
        JOIN   students  st ON st.mobile     = a.student_mobile
        JOIN   sessions  s  ON s.id          = a.session_id
        WHERE  a.session_id = ?
        ORDER  BY a.timestamp ASC
    ''', (session_id,))
    rows = cursor.fetchall()
    conn.close()

    df = pd.DataFrame(
        [dict(r) for r in rows],
        columns=['Name', 'Mobile', 'Email', 'Session Name', 'Date', 'Batch Name', 'Timestamp'],
    )

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Attendance')

        ws = writer.sheets['Attendance']
        for col in ws.columns:
            max_len = max((len(str(cell.value)) for cell in col if cell.value), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 50)

    buf.seek(0)
    safe_name = re.sub(r'[^\w\-]', '_', db_session['session_name'])
    filename  = f"attendance_{safe_name}_{db_session['date']}.xlsx"

    return send_file(
        buf,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename,
    )

# ── View / Delete / Edit Students ─────────────────────────────────────────────

@app.route('/view-students')
@login_required
def view_students():
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM students ORDER BY name ASC')
    students = cursor.fetchall()
    conn.close()
    return render_template('view_students.html', students=students)

@app.route('/delete-student/<int:student_id>', methods=['POST'])
@login_required
def delete_student(student_id):
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT name, mobile FROM students WHERE id = ?', (student_id,))
    student = cursor.fetchone()
    if student:
        cursor.execute('DELETE FROM attendance WHERE student_mobile = ?', (student['mobile'],))
        cursor.execute('DELETE FROM students    WHERE id = ?',            (student_id,))
        conn.commit()
        flash(f"\"{student['name']}\" deleted.")
    conn.close()
    return redirect(url_for('view_students'))

@app.route('/edit-student/<int:student_id>', methods=['GET'])
@login_required
def edit_student_form(student_id):
    conn    = get_connection()
    cursor  = conn.cursor()
    cursor.execute('SELECT * FROM students WHERE id = ?', (student_id,))
    student = cursor.fetchone()
    conn.close()
    if student is None:
        return 'Student not found', 404
    return render_template('edit_student.html', student=student)

@app.route('/edit-student/<int:student_id>', methods=['POST'])
@login_required
def edit_student_submit(student_id):
    conn   = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM students WHERE id = ?', (student_id,))
    current = cursor.fetchone()
    if current is None:
        conn.close()
        return 'Student not found', 404

    name        = request.form.get('name',        '').strip()
    mobile      = request.form.get('mobile',      '').strip()
    email       = request.form.get('email',       '').strip()
    gender      = request.form.get('gender',      '').strip()
    course_name = request.form.get('course_name', '').strip()
    batch_name  = request.form.get('batch_name',  '').strip()

    form_data = dict(id=student_id, name=name, mobile=mobile, email=email,
                     gender=gender, course_name=course_name, batch_name=batch_name)

    if not mobile.isdigit() or len(mobile) != 10:
        conn.close()
        return render_template('edit_student.html',
                               student=form_data,
                               error_mobile='Mobile number must be exactly 10 digits.')

    cursor.execute('SELECT id FROM students WHERE mobile = ? AND id != ?',
                   (mobile, student_id))
    if cursor.fetchone():
        conn.close()
        return render_template('edit_student.html',
                               student=form_data,
                               error_mobile='Mobile number already registered to another student.')

    old_mobile = current['mobile']
    if mobile != old_mobile:
        cursor.execute('UPDATE attendance SET student_mobile = ? WHERE student_mobile = ?',
                       (mobile, old_mobile))

    cursor.execute('''
        UPDATE students
        SET name=?, mobile=?, email=?, gender=?, course_name=?, batch_name=?
        WHERE id=?
    ''', (name, mobile, email, gender, course_name, batch_name, student_id))
    conn.commit()
    conn.close()

    flash('Student updated successfully!')
    return redirect(url_for('view_students'))

if __name__ == '__main__':
    app.run(debug=True)
