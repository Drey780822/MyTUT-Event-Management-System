from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
import psycopg2
from psycopg2 import Error
from datetime import datetime
import qrcode
import io
import base64
from datetime import datetime
from flask_mail import Mail, Message
from twilio.rest import Client
from functools import wraps
import os


app = Flask(__name__)
app.secret_key = "abcd1234"

# Email Configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'  # or your email provider
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('EMAIL_USER')  # Set environment variables
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASS')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('EMAIL_USER')

# Twilio Configuration (for WhatsApp)
app.config['TWILIO_ACCOUNT_SID'] = os.environ.get('TWILIO_ACCOUNT_SID')
app.config['TWILIO_AUTH_TOKEN'] = os.environ.get('TWILIO_AUTH_TOKEN')
app.config['TWILIO_WHATSAPP_NUMBER'] = os.environ.get('TWILIO_WHATSAPP_NUMBER')

# Initialize extensions
mail = Mail(app)

# Initialize Twilio client
twilio_client = Client(app.config['TWILIO_ACCOUNT_SID'], app.config['TWILIO_AUTH_TOKEN'])

# Database configuration
DB_HOST = "localhost"
DB_NAME = "MyTUTEvents_db"
DB_USER = "postgres"
DB_PASS = "1234"

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        return conn
    except Error as e:
        print(f"Error connecting to database: {e}")
        return None
 
# Admin Routes
@app.route('/admin/')
def admin_index():
    return render_template('admin/index.html')

@app.route('/all_organizers/')
def all_organizers():
    return render_template('admin/organizers.html')

@app.route('/students/')
def students():
    return render_template('admin/students.html')

@app.route('/admin/')
def organiser_dashboard():
    return render_template('admin/organiser_dashboard.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'staff_nr' not in session:
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'error')
        return render_template('admin/admin_dashboard.html', 
                             admin={}, 
                             stats={},
                             upcoming_events=[], 
                             recent_registrations=[], 
                             categories=[],
                             admin_name='Admin')
    
    try:
        cursor = conn.cursor()
        
        # Get admin info
        cursor.execute("SELECT first_name, last_name, email FROM admins WHERE staff_nr = %s", (session['staff_nr'],))
        admin = cursor.fetchone()
        if admin:
            admin_data = {
                'first_name': admin[0],
                'last_name': admin[1],
                'email': admin[2],
                'staff_nr': session['staff_nr']
            }
            admin_name = f"{admin[0]} {admin[1]}"
        else:
            admin_data = {}
            admin_name = "Admin"
        
        # Stats
        cursor.execute("SELECT COUNT(*) FROM events")
        total_events = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT student_number) FROM event_registrations")
        total_attendees = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM events WHERE event_date >= CURRENT_DATE")
        upcoming_events_count = cursor.fetchone()[0]
        
        # Average attendance (based on status)
        cursor.execute("""
            SELECT COALESCE(AVG(
                CASE 
                    WHEN total > 0 
                    THEN attended * 100.0 / total 
                    ELSE 0 
                END
            ), 0)
            FROM (
                SELECT 
                    e.event_id,
                    COUNT(er.registration_id) AS total,
                    COUNT(CASE WHEN er.status = 'Attended' THEN 1 END) AS attended
                FROM events e
                LEFT JOIN event_registrations er ON e.event_id = er.event_id
                GROUP BY e.event_id
            ) sub
        """)
        avg_attendance = cursor.fetchone()[0] or 0
        
        # Upcoming events with registration count
        cursor.execute("""
            SELECT 
                e.event_id,
                e.title,
                TO_CHAR(e.event_date, 'YYYY-MM-DD') as event_date,
                TO_CHAR(e.event_time, 'HH12:MI AM') as event_time,
                e.location,
                COUNT(er.registration_id) AS registered,
                e.max_attendees
            FROM events e
            LEFT JOIN event_registrations er ON e.event_id = er.event_id
            WHERE e.event_date >= CURRENT_DATE
            GROUP BY e.event_id
            ORDER BY e.event_date
            LIMIT 5
        """)
        upcoming_events = cursor.fetchall()
        
        # Recent registrations
        cursor.execute("""
            SELECT 
                s.first_name,
                s.last_name,
                s.student_number,
                e.title,
                TO_CHAR(er.registration_date, 'YYYY-MM-DD HH24:MI') as reg_date,
                er.status,
                er.registration_id
            FROM event_registrations er
            JOIN students s ON er.student_number = s.student_number
            JOIN events e ON er.event_id = e.event_id
            ORDER BY er.registration_date DESC
            LIMIT 10
        """)
        recent_registrations = cursor.fetchall()
        
        # Categories
        cursor.execute("""
            SELECT COALESCE(category, 'Uncategorized') as category, COUNT(*) as count 
            FROM events 
            GROUP BY category
        """)
        categories = cursor.fetchall()
        
    except Exception as e:
        print(f"Dashboard error: {e}")
        flash('Error loading dashboard data', 'error')
        admin_data = {}
        admin_name = "Admin"
        total_events = total_attendees = upcoming_events_count = avg_attendance = 0
        upcoming_events = []
        recent_registrations = []
        categories = []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    
    stats = {
        'total_events': total_events,
        'total_attendees': total_attendees,
        'upcoming_events': upcoming_events_count,
        'avg_attendance': round(avg_attendance, 1)
    }
    
    return render_template('admin/admin_dashboard.html',
                         admin=admin_data,
                         stats=stats,
                         upcoming_events=upcoming_events,
                         recent_registrations=recent_registrations,
                         categories=categories,
                         admin_name=admin_name)
# Decorator to check login and user type
def login_required(required_type=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('admin_login'))  # you need a GET login page route
            if required_type and session.get('user_type') != required_type:
                flash('Unauthorized access', 'error')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        # Process login
        user_type = request.form.get('user_type')
        username = request.form.get('username')
        password = request.form.get('password')
        remember_me = request.form.get('rememberMe')

        if not user_type or not username or not password:
            return jsonify({'success': False, 'message': 'All fields are required'})

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'})

        try:
            cursor = conn.cursor()
            if user_type == 'admin':
                cursor.execute(
                    "SELECT first_name, last_name, email, password FROM admins WHERE staff_nr = %s",
                    (username,)
                )
                admin = cursor.fetchone()
                if admin and admin[3] == password:  # Use hashing in production
                    session['staff_nr'] = username
                    session['user_id'] = username
                    session['user_type'] = 'admin'
                    session['user_name'] = f"{admin[0]} {admin[1]}"
                    if remember_me:
                        session.permanent = True
                    return jsonify({
                        'success': True,
                        'redirect': url_for('admin_dashboard')
                    })
                else:
                    return jsonify({'success': False, 'message': 'Invalid staff ID or password'})

            elif user_type == 'organizer':
                cursor.execute(
                    "SELECT organizer_id, name, email, password FROM organizers WHERE email = %s",
                    (username,)
                )
                organizer = cursor.fetchone()
                if organizer and organizer[3] == password:
                    session['user_id'] = organizer[0]
                    session['user_type'] = 'organizer'
                    session['user_name'] = organizer[1]
                    if remember_me:
                        session.permanent = True
                    return jsonify({
                        'success': True,
                        'redirect': url_for('organizer_dashboard')
                    })
                else:
                    return jsonify({'success': False, 'message': 'Invalid email or password'})
            else:
                return jsonify({'success': False, 'message': 'Invalid user type'})
        except Exception as e:
            print(f"Login error: {e}")
            return jsonify({'success': False, 'message': 'An error occurred during login'})
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    else:
        # GET request – show login page
        return render_template('admin/admin_login.html')

# Admin Dashboard
# @app.route('/admin/dashboard')
# @login_required(required_type='admin')
# def admin_dashboard():
#     conn = get_db_connection()
#     if not conn:
#         flash('Database error', 'error')
#         return render_template('admin/admin_dashboard.html', stats={}, events=[], users=[], registrations=[])

#     try:
#         cursor = conn.cursor()
#         # Stats
#         cursor.execute("SELECT COUNT(*) FROM events")
#         total_events = cursor.fetchone()[0]
#         cursor.execute("SELECT COUNT(*) FROM event_registrations")
#         total_registrations = cursor.fetchone()[0]
#         cursor.execute("SELECT COUNT(*) FROM students")
#         total_students = cursor.fetchone()[0]
#         cursor.execute("SELECT COUNT(*) FROM organizers")
#         total_organizers = cursor.fetchone()[0]

#         # Recent events
#         cursor.execute("""
#             SELECT event_id, title, TO_CHAR(event_date, 'YYYY-MM-DD'), max_attendees,
#                    (SELECT COUNT(*) FROM event_registrations WHERE event_id = events.event_id) as registered
#             FROM events ORDER BY event_date DESC LIMIT 5
#         """)
#         recent_events = cursor.fetchall()

#         # Recent registrations
#         cursor.execute("""
#             SELECT s.first_name, s.last_name, s.student_number, e.title, er.registration_date, er.status
#             FROM event_registrations er
#             JOIN students s ON er.student_number = s.student_number
#             JOIN events e ON er.event_id = e.event_id
#             ORDER BY er.registration_date DESC LIMIT 10
#         """)
#         recent_registrations = cursor.fetchall()

#         # Organizers list
#         cursor.execute("SELECT organizer_id, name, email, status FROM organizers ORDER BY name")
#         organizers = cursor.fetchall()

#         stats = {
#             'total_events': total_events,
#             'total_registrations': total_registrations,
#             'total_students': total_students,
#             'total_organizers': total_organizers
#         }
#     except Exception as e:
#         print(f"Admin dashboard error: {e}")
#         stats = {}
#         recent_events = []
#         recent_registrations = []
#         organizers = []
#     finally:
#         if cursor:
#             cursor.close()
#         if conn:
#             conn.close()

#     return render_template('admin/admin_dashboard.html',
#                            admin_name=session.get('user_name', 'Admin'),
#                            stats=stats,
#                            recent_events=recent_events,
#                            recent_registrations=recent_registrations,
#                            organizers=organizers)

# Organizer Dashboard
@app.route('/organizer/dashboard')
@login_required(required_type='organizer')
def organizer_dashboard():
    organizer_id = session['user_id']
    conn = get_db_connection()
    if not conn:
        flash('Database error', 'error')
        return render_template('organizer/organizer_dashboard.html', events=[], stats={})

    try:
        cursor = conn.cursor()
        # Organizer's events
        cursor.execute("""
            SELECT event_id, title, TO_CHAR(event_date, 'YYYY-MM-DD'), max_attendees,
                   (SELECT COUNT(*) FROM event_registrations WHERE event_id = events.event_id) as registered
            FROM events WHERE created_by = %s ORDER BY event_date DESC
        """, (organizer_id,))
        events = cursor.fetchall()

        # Stats for this organizer
        cursor.execute("SELECT COUNT(*) FROM events WHERE created_by = %s", (organizer_id,))
        my_events = cursor.fetchone()[0]
        cursor.execute("""
            SELECT COUNT(*) FROM event_registrations er
            JOIN events e ON er.event_id = e.event_id
            WHERE e.created_by = %s
        """, (organizer_id,))
        total_registrations = cursor.fetchone()[0]
        cursor.execute("""
            SELECT COUNT(DISTINCT student_number) FROM event_registrations er
            JOIN events e ON er.event_id = e.event_id
            WHERE e.created_by = %s
        """, (organizer_id,))
        unique_students = cursor.fetchone()[0]

        stats = {
            'my_events': my_events,
            'total_registrations': total_registrations,
            'unique_students': unique_students
        }

        # Recent registrations for organizer's events
        cursor.execute("""
            SELECT s.first_name, s.last_name, s.student_number, e.title, er.registration_date, er.status, er.registration_id
            FROM event_registrations er
            JOIN students s ON er.student_number = s.student_number
            JOIN events e ON er.event_id = e.event_id
            WHERE e.created_by = %s
            ORDER BY er.registration_date DESC LIMIT 10
        """, (organizer_id,))
        recent_registrations = cursor.fetchall()
    except Exception as e:
        print(f"Organizer dashboard error: {e}")
        events = []
        stats = {}
        recent_registrations = []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return render_template('organizer/organizer_dashboard.html',
                           organizer_name=session.get('user_name', 'Organizer'),
                           events=events,
                           stats=stats,
                           recent_registrations=recent_registrations)

# Logout
@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_index'))

@app.route('/admin/event/create', methods=['POST'])
def create_event():
    if 'staff_nr' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'})

    title = request.form.get('title')
    description = request.form.get('description')
    event_date = request.form.get('event_date')
    max_attendees = request.form.get('max_attendees')
    category = request.form.get('category')

    if not all([title, description, event_date, max_attendees, category]):
        return jsonify({'success': False, 'message': 'All fields are required'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
        
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO events (title, description, event_date, max_attendees, category, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING event_id
        """, (title, description, event_date, max_attendees, category, session['staff_nr']))
        event_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({'success': True, 'message': 'Event created successfully'})
    except Exception as e:
        conn.rollback()
        print(f"Error creating event: {e}")
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
# ---------- Organizers CRUD ----------
@app.route('/admin/organizers', methods=['GET'])
@login_required(required_type='admin')
def get_organizers():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT organizer_id, name, email, phone, department, events_organized, status FROM organizers ORDER BY name")
        rows = cursor.fetchall()
        organizers = []
        for row in rows:
            organizers.append({
                'organizer_id': row[0],
                'name': row[1],
                'email': row[2],
                'phone': row[3],
                'department': row[4],
                'events_organized': row[5],
                'status': row[6]
            })
        return jsonify(organizers)
    except Exception as e:
        print(e)
        return jsonify([])
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/admin/organizers/<int:id>', methods=['GET'])
@login_required(required_type='admin')
def get_organizer(id):
    conn = get_db_connection()
    if not conn:
        return jsonify({})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT organizer_id, name, email, phone, department, events_organized, status FROM organizers WHERE organizer_id = %s", (id,))
        row = cursor.fetchone()
        if row:
            return jsonify({
                'organizer_id': row[0],
                'name': row[1],
                'email': row[2],
                'phone': row[3],
                'department': row[4],
                'events_organized': row[5],
                'status': row[6]
            })
        return jsonify({})
    except Exception as e:
        print(e)
        return jsonify({})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/admin/organizers', methods=['POST'])
@login_required(required_type='admin')
def create_organizer():
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    department = request.form.get('department')
    password = request.form.get('password')
    status = request.form.get('status', 'active')

    if not name or not email or not password:
        return jsonify({'success': False, 'message': 'Name, email and password are required'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO organizers (name, email, phone, department, password, status, events_organized)
            VALUES (%s, %s, %s, %s, %s, %s, 0)
        """, (name, email, phone, department, password, status))
        conn.commit()
        return jsonify({'success': True, 'message': 'Organizer created'})
    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/admin/organizers/<int:id>', methods=['PUT'])
@login_required(required_type='admin')
def update_organizer(id):
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    department = request.form.get('department')
    password = request.form.get('password')
    status = request.form.get('status')

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    try:
        cursor = conn.cursor()
        if password:
            cursor.execute("""
                UPDATE organizers SET name=%s, email=%s, phone=%s, department=%s, password=%s, status=%s
                WHERE organizer_id=%s
            """, (name, email, phone, department, password, status, id))
        else:
            cursor.execute("""
                UPDATE organizers SET name=%s, email=%s, phone=%s, department=%s, status=%s
                WHERE organizer_id=%s
            """, (name, email, phone, department, status, id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Organizer updated'})
    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/admin/organizers/<int:id>', methods=['DELETE'])
@login_required(required_type='admin')
def delete_organizer(id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM organizers WHERE organizer_id = %s", (id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Organizer deleted'})
    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# ---------- Students CRUD ----------
@app.route('/admin/students', methods=['GET'])
@login_required(required_type='admin')
def get_students():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number, first_name, last_name, email, phone, faculty, is_active FROM students ORDER BY last_name")
        rows = cursor.fetchall()
        students = []
        for row in rows:
            students.append({
                'student_number': row[0],
                'first_name': row[1],
                'last_name': row[2],
                'email': row[3],
                'phone': row[4],
                'faculty': row[5],
                'is_active': row[6]
            })
        return jsonify(students)
    except Exception as e:
        print(e)
        return jsonify([])
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/admin/students/<string:id>', methods=['GET'])
@login_required(required_type='admin')
def get_student(id):
    conn = get_db_connection()
    if not conn:
        return jsonify({})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number, first_name, last_name, email, phone, faculty, is_active FROM students WHERE student_number = %s", (id,))
        row = cursor.fetchone()
        if row:
            return jsonify({
                'student_number': row[0],
                'first_name': row[1],
                'last_name': row[2],
                'email': row[3],
                'phone': row[4],
                'faculty': row[5],
                'is_active': row[6]
            })
        return jsonify({})
    except Exception as e:
        print(e)
        return jsonify({})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/admin/students', methods=['POST'])
@login_required(required_type='admin')
def create_student():
    student_number = request.form.get('student_number')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    faculty = request.form.get('faculty')
    pin = request.form.get('pin')
    is_active = request.form.get('is_active') == 'true'

    if not student_number or not first_name or not last_name or not email or not pin:
        return jsonify({'success': False, 'message': 'Required fields missing'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO students (student_number, first_name, last_name, email, phone, faculty, pin, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (student_number, first_name, last_name, email, phone, faculty, pin, is_active))
        conn.commit()
        return jsonify({'success': True, 'message': 'Student created'})
    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/admin/students/<string:id>', methods=['PUT'])
@login_required(required_type='admin')
def update_student(id):
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    faculty = request.form.get('faculty')
    pin = request.form.get('pin')
    is_active = request.form.get('is_active') == 'true'

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    try:
        cursor = conn.cursor()
        if pin:
            cursor.execute("""
                UPDATE students SET first_name=%s, last_name=%s, email=%s, phone=%s, faculty=%s, pin=%s, is_active=%s
                WHERE student_number=%s
            """, (first_name, last_name, email, phone, faculty, pin, is_active, id))
        else:
            cursor.execute("""
                UPDATE students SET first_name=%s, last_name=%s, email=%s, phone=%s, faculty=%s, is_active=%s
                WHERE student_number=%s
            """, (first_name, last_name, email, phone, faculty, is_active, id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Student updated'})
    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/admin/students/<string:id>', methods=['DELETE'])
@login_required(required_type='admin')
def delete_student(id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM students WHERE student_number = %s", (id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Student deleted'})
    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()# ---------- Organizer Routes ----------
@app.route('/organizer/stats')
@login_required(required_type='organizer')
def organizer_stats():
    org_id = session['user_id']
    conn = get_db_connection()
    if not conn:
        return jsonify({})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM events WHERE created_by = %s", (org_id,))
        my_events = cursor.fetchone()[0]
        cursor.execute("""
            SELECT COUNT(*) FROM event_registrations er
            JOIN events e ON er.event_id = e.event_id
            WHERE e.created_by = %s
        """, (org_id,))
        total_regs = cursor.fetchone()[0]
        cursor.execute("""
            SELECT COUNT(*) FROM events
            WHERE created_by = %s AND event_date >= CURRENT_DATE
        """, (org_id,))
        upcoming = cursor.fetchone()[0]
        return jsonify({'my_events': my_events, 'total_registrations': total_regs, 'upcoming_events': upcoming})
    except Exception as e:
        print(e)
        return jsonify({})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/organizer/events')
@login_required(required_type='organizer')
def get_organizer_events():
    org_id = session['user_id']
    limit = request.args.get('limit', type=int)
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    try:
        cursor = conn.cursor()
        query = """
            SELECT e.event_id, e.title, TO_CHAR(e.event_date, 'YYYY-MM-DD HH24:MI') as event_date,
                   e.location, e.max_attendees,
                   (SELECT COUNT(*) FROM event_registrations WHERE event_id = e.event_id) as registered
            FROM events e
            WHERE e.created_by = %s
            ORDER BY e.event_date DESC
        """
        if limit:
            query += " LIMIT %s"
            cursor.execute(query, (org_id, limit))
        else:
            cursor.execute(query, (org_id,))
        rows = cursor.fetchall()
        events = []
        for row in rows:
            events.append({
                'event_id': row[0],
                'title': row[1],
                'event_date': row[2],
                'location': row[3],
                'max_attendees': row[4],
                'registered': row[5]
            })
        return jsonify(events)
    except Exception as e:
        print(e)
        return jsonify([])
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/organizer/events/<int:id>', methods=['GET'])
@login_required(required_type='organizer')
def get_organizer_event(id):
    org_id = session['user_id']
    conn = get_db_connection()
    if not conn:
        return jsonify({})
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT event_id, title, description, event_date, location, max_attendees, category, faculty
            FROM events WHERE event_id = %s AND created_by = %s
        """, (id, org_id))
        row = cursor.fetchone()
        if row:
            return jsonify({
                'event_id': row[0],
                'title': row[1],
                'description': row[2],
                'event_date': row[3].isoformat() if row[3] else None,
                'location': row[4],
                'max_attendees': row[5],
                'category': row[6],
                'faculty': row[7]
            })
        return jsonify({})
    except Exception as e:
        print(e)
        return jsonify({})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/organizer/events', methods=['POST'])
@login_required(required_type='organizer')
def organizer_create_event():
    org_id = session['user_id']
    title = request.form.get('title')
    description = request.form.get('description')
    event_date = request.form.get('event_date')
    location = request.form.get('location')
    max_attendees = request.form.get('max_attendees')
    category = request.form.get('category')
    faculty = request.form.get('faculty')

    if not all([title, event_date, location, max_attendees]):
        return jsonify({'success': False, 'message': 'Missing required fields'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO events (title, description, event_date, location, max_attendees, category, faculty, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (title, description, event_date, location, max_attendees, category, faculty, org_id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Event created'})
    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/organizer/events/<int:id>', methods=['PUT'])
@login_required(required_type='organizer')
def organizer_update_event(id):
    org_id = session['user_id']
    title = request.form.get('title')
    description = request.form.get('description')
    event_date = request.form.get('event_date')
    location = request.form.get('location')
    max_attendees = request.form.get('max_attendees')
    category = request.form.get('category')
    faculty = request.form.get('faculty')

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE events SET title=%s, description=%s, event_date=%s, location=%s,
                max_attendees=%s, category=%s, faculty=%s
            WHERE event_id=%s AND created_by=%s
        """, (title, description, event_date, location, max_attendees, category, faculty, id, org_id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Event updated'})
    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/organizer/events/<int:id>', methods=['DELETE'])
@login_required(required_type='organizer')
def organizer_delete_event(id):
    org_id = session['user_id']
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    try:
        cursor = conn.cursor()
        # First delete registrations for this event
        cursor.execute("DELETE FROM event_registrations WHERE event_id = %s", (id,))
        cursor.execute("DELETE FROM events WHERE event_id = %s AND created_by = %s", (id, org_id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Event deleted'})
    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/organizer/registrations')
@login_required(required_type='organizer')
def get_organizer_registrations():
    org_id = session['user_id']
    event_id = request.args.get('event_id')
    status = request.args.get('status')
    limit = request.args.get('limit', type=int)

    conn = get_db_connection()
    if not conn:
        return jsonify([])
    try:
        cursor = conn.cursor()
        query = """
            SELECT er.registration_id, s.first_name, s.last_name, s.student_number,
                   e.title, er.registration_date, er.status
            FROM event_registrations er
            JOIN students s ON er.student_number = s.student_number
            JOIN events e ON er.event_id = e.event_id
            WHERE e.created_by = %s
        """
        params = [org_id]
        if event_id:
            query += " AND er.event_id = %s"
            params.append(event_id)
        if status:
            query += " AND er.status = %s"
            params.append(status)
        query += " ORDER BY er.registration_date DESC"
        if limit:
            query += " LIMIT %s"
            params.append(limit)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        regs = []
        for row in rows:
            regs.append({
                'registration_id': row[0],
                'student_name': f"{row[1]} {row[2]}",
                'student_number': row[3],
                'event_title': row[4],
                'registration_date': row[5].strftime('%Y-%m-%d %H:%M') if row[5] else '',
                'status': row[6]
            })
        return jsonify(regs)
    except Exception as e:
        print(e)
        return jsonify([])
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/organizer/registrations/<int:reg_id>', methods=['PUT'])
@login_required(required_type='organizer')
def update_registration_status(reg_id):
    data = request.get_json()
    status = data.get('status')
    if status not in ['Pending', 'Approved', 'Rejected', 'Attended']:
        return jsonify({'success': False, 'message': 'Invalid status'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    try:
        cursor = conn.cursor()
        # Ensure the registration belongs to an event owned by this organizer
        cursor.execute("""
            UPDATE event_registrations SET status=%s
            WHERE registration_id=%s AND event_id IN (SELECT event_id FROM events WHERE created_by=%s)
        """, (status, reg_id, session['user_id']))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': 'Not authorized or not found'})
        return jsonify({'success': True, 'message': f'Registration {status}'})
    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/organizer/checkin', methods=['POST'])
@login_required(required_type='organizer')
def checkin_attendee():
    event_id = request.form.get('event_id')
    student_number = request.form.get('student_number')

    if not event_id or not student_number:
        return jsonify({'success': False, 'message': 'Missing event or student number'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    try:
        cursor = conn.cursor()
        # Verify event belongs to this organizer
        cursor.execute("SELECT event_id FROM events WHERE event_id=%s AND created_by=%s", (event_id, session['user_id']))
        if not cursor.fetchone():
            return jsonify({'success': False, 'message': 'Event not found or unauthorized'})

        # Update registration status to 'Attended'
        cursor.execute("""
            UPDATE event_registrations SET status='Attended'
            WHERE event_id=%s AND student_number=%s
            RETURNING registration_id
        """, (event_id, student_number))
        updated = cursor.fetchone()
        if not updated:
            return jsonify({'success': False, 'message': 'Registration not found'})

        conn.commit()
        # Optionally get student name for response
        cursor.execute("SELECT first_name, last_name FROM students WHERE student_number=%s", (student_number,))
        student = cursor.fetchone()
        student_name = f"{student[0]} {student[1]}" if student else student_number
        return jsonify({'success': True, 'message': 'Check-in successful', 'student_name': student_name, 'event_title': 'Event'})
    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/organizer/profile', methods=['GET'])
@login_required(required_type='organizer')
def get_organizer_profile():
    org_id = session['user_id']
    conn = get_db_connection()
    if not conn:
        return jsonify({})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name, email, phone, department FROM organizers WHERE organizer_id=%s", (org_id,))
        row = cursor.fetchone()
        if row:
            return jsonify({'name': row[0], 'email': row[1], 'phone': row[2], 'department': row[3]})
        return jsonify({})
    except Exception as e:
        print(e)
        return jsonify({})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/organizer/profile', methods=['PUT'])
@login_required(required_type='organizer')
def update_organizer_profile():
    org_id = session['user_id']
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    department = request.form.get('department')
    password = request.form.get('password')

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    try:
        cursor = conn.cursor()
        if password:
            cursor.execute("""
                UPDATE organizers SET name=%s, email=%s, phone=%s, department=%s, password=%s
                WHERE organizer_id=%s
            """, (name, email, phone, department, password, org_id))
        else:
            cursor.execute("""
                UPDATE organizers SET name=%s, email=%s, phone=%s, department=%s
                WHERE organizer_id=%s
            """, (name, email, phone, department, org_id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Profile updated'})
    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/admin/event/delete/<int:event_id>', methods=['POST'])
def delete_event(event_id):
    if 'staff_nr' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
        
    try:
        cursor = conn.cursor()
        # First delete related registrations
        cursor.execute("DELETE FROM event_registrations WHERE event_id = %s", (event_id,))
        # Then delete the event
        cursor.execute("DELETE FROM events WHERE event_id = %s", (event_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Event deleted successfully'})
    except Exception as e:
        conn.rollback()
        print(f"Error deleting event: {e}")
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/admin/registration/approve/<int:registration_id>', methods=['POST'])
def approve_registration(registration_id):
    if 'staff_nr' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
        
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE event_registrations SET status = 'Approved' WHERE registration_id = %s", (registration_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Registration approved'})
    except Exception as e:
        conn.rollback()
        print(f"Error approving registration: {e}")
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/admin/registration/reject/<int:registration_id>', methods=['POST'])
def reject_registration(registration_id):
    if 'staff_nr' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
        
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE event_registrations SET status = 'Rejected' WHERE registration_id = %s", (registration_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Registration rejected'})
    except Exception as e:
        conn.rollback()
        print(f"Error rejecting registration: {e}")
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            


# Student Routes
@app.route('/')
def index():
    conn = get_db_connection()
    events_data = []
    past_events = []
    organizers_data = []
    if conn:
        try:
            cursor = conn.cursor()
            # Fetch upcoming events for the homepage
            cursor.execute("""
                SELECT 
                    events.event_id,
                    events.title, 
                    TO_CHAR(events.event_date, 'FMDay, FMMonth DD, YYYY') AS formatted_date,
                    TO_CHAR(events.event_time, 'HH12:MI AM') AS formatted_time, 
                    events.location,
                    events.faculty,
                    events.max_attendees,
                    events.event_image,
                    events.description,
                    (events.max_attendees - COALESCE(COUNT(event_registrations.registration_id), 0)) AS seats_left
                FROM events
                LEFT JOIN event_registrations 
                    ON events.event_id = event_registrations.event_id
                WHERE events.event_date >= CURRENT_DATE
                GROUP BY 
                    events.event_id,
                    events.title, 
                    events.event_date, 
                    events.event_time, 
                    events.location,
                    events.faculty,
                    events.max_attendees,
                    events.event_image,
                    events.description
                ORDER BY events.event_date
                LIMIT 3;
            """)
            events = cursor.fetchall()
            
            for event in events:
                events_data.append({
                    'event_id': event[0],
                    'title': event[1],
                    'event_date': event[2],   # formatted (e.g., Thursday, May 15, 2025)
                    'event_time': event[3],   # formatted (e.g., 09:00 AM)
                    'location': event[4],
                    'faculty': event[5],
                    'max_attendees': event[6],
                    'event_image': event[7],
                    'description': event[8],
                    'seats_left': event[9]
                })
        # Fetch past events for the homepage
            cursor.execute("""
                SELECT 
                    events.event_id,
                    events.title, 
                    TO_CHAR(events.event_date, 'FMDay, FMMonth DD, YYYY') AS formatted_date,
                    TO_CHAR(events.event_time, 'HH12:MI AM') AS formatted_time, 
                    events.location,
                    events.faculty,
                    events.max_attendees,
                    events.event_image,
                    events.description,
                    COALESCE(COUNT(event_registrations.registration_id), 0) AS total_attendees
                FROM events
                LEFT JOIN event_registrations 
                    ON events.event_id = event_registrations.event_id
                WHERE events.event_date < CURRENT_DATE
                GROUP BY 
                    events.event_id,
                    events.title, 
                    events.event_date, 
                    events.event_time, 
                    events.location,
                    events.faculty,
                    events.max_attendees,
                    events.event_image,
                    events.description
                ORDER BY events.event_date DESC
                LIMIT 3;
            """)
            past_events_data = cursor.fetchall()
            
            for event in past_events_data:
                past_events.append({
                    'event_id': event[0],
                    'title': event[1],
                    'event_date': event[2],
                    'event_time': event[3],
                    'location': event[4],
                    'faculty': event[5],
                    'max_attendees': event[6],
                    'event_image': event[7],
                    'description': event[8],
                    'total_attendees': event[9]
                })
                # Fetch organizers # Fetch organizers
            cursor.execute("""
                SELECT 
        organizer_id,
        name,
        email,
        phone,
        department,
        events_organized,
        status
    FROM organizers
    WHERE status = 'active'
    ORDER BY events_organized DESC
    LIMIT 3;
            """)
            organizers = cursor.fetchall()
            
            for org in organizers:
                organizers_data.append({
                    'organizer_id': org[0],
                    'name': org[1],
                    'email': org[2],
                    'phone': org[3],
                    'department': org[4],
                    'events_organized': org[5],
                    'status': org[6]
                })
              
        except Exception as e:
            print(f"Error fetching data for homepage: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
                
    return render_template('index.html', 
                         events=events_data, 
                         past_events=past_events,
                         organizers=organizers_data)
@app.route('/login_itspin')
def login_itspin():
    return render_template('login_itspin.html')

@app.route('/login_studemail')
def login_studemail():
    return render_template('login_studemail.html')

@app.route('/register_student')
def register_student():
    return redirect("https://tut.ac.za/study-at-tut/undergraduate/")

@app.route('/register/<int:event_id>')
def register(event_id):
    conn = get_db_connection()
    event_data = None
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT event_id, title, event_date, event_time, location, faculty, 
                       max_attendees, event_image, description,
                       (max_attendees - COALESCE((SELECT COUNT(*) FROM event_registrations WHERE event_id = events.event_id), 0)) as seats_left
                FROM events 
                WHERE event_id = %s
            """, (event_id,))
            event = cursor.fetchone()
            
            if event:
                event_data = {
                    'event_id': event[0],
                    'title': event[1],
                    'event_date': event[2],
                    'event_time': event[3],
                    'location': event[4],
                    'faculty': event[5],
                    'max_attendees': event[6],
                    'event_image': event[7],
                    'description': event[8],
                    'seats_left': event[9]
                }
              
        except Exception as e:
            print(f"Error fetching event for registration: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    if not event_data:
        flash('Event not found', 'error')
        return redirect(url_for('upcoming_events'))
    
    # Check if event has available seats
    if event_data['seats_left'] <= 0:
        flash('This event is fully booked. No seats available.', 'error')
        return redirect(url_for('index'))
    
    return render_template('register_event.html', event=event_data)

def authenticate_student(student_number, email):
    """Authenticate student credentials"""
    conn = get_db_connection()
    if not conn:
        return False, "Database connection error"
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT student_number, email 
            FROM students 
            WHERE student_number = %s AND email = %s AND is_active = TRUE
        """, (student_number, email))
        
        student = cursor.fetchone()
        if student:
            return True, {
                'id': student[0],
                'email': student[1]
            }
        else:
            return False, "Invalid student credentials or student not found"
            
    except Exception as e:
        return False, f"Authentication error: {str(e)}"
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def check_existing_registration(event_id, student_number):
    """Check if student is already registered for the event"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT event_id,student_number
            FROM event_registrations 
            WHERE event_id = %s AND student_number = %s
        """, (event_id, student_number))
        
        return cursor.fetchone() is not None
        
    except Exception as e:
        print(f"Error checking registration: {e}")
        return True
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def check_event_availability(event_id):
    """Check if event has available seats"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT max_attendees, 
                   (SELECT COUNT(*) FROM event_registrations WHERE event_id = %s) as registered_count
            FROM events 
            WHERE event_id = %s
        """, (event_id, event_id))
        
        result = cursor.fetchone()
        if result:
            max_attendees = result[0]
            registered_count = result[1]
            return registered_count < max_attendees
        return False
        
    except Exception as e:
        print(f"Error checking event availability: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
@app.route('/submit_registration', methods=['POST'])
def submit_registration():
    if request.method == 'POST':
        # Get form data
        event_id = request.form.get('event_id')
        first_name = request.form.get('fullName')
        student_number = request.form.get('studentNumber')
        email = request.form.get('email')
        phone = request.form.get('phone')
        faculty = request.form.get('faculty')
        dietary_restrictions = request.form.get('dietaryRestrictions')
        special_requirements = request.form.get('specialRequirements')
        
        # Validate required fields
        if not all([event_id, first_name, student_number, email]):
            flash('Please fill in all required fields', 'error')
            return redirect(url_for('register', event_id=event_id))
        
        # Step 1: Authenticate student
        auth_success, auth_result = authenticate_student(student_number, email)
        if not auth_success:
            flash(f'Student authentication failed: {auth_result}', 'error')
            return redirect(url_for('register', event_id=event_id))
        
        # Step 2: Check if student is already registered
        if check_existing_registration(event_id, student_number):
            flash('You have already registered for this event', 'error')
            return redirect(url_for('register', event_id=event_id))
        
        # Step 3: Check event availability
        if not check_event_availability(event_id):
            flash('This event is fully booked. No seats available.', 'error')
            return redirect(url_for('register', event_id=event_id))
        
        conn = get_db_connection()
        if not conn:
            flash('Database connection error', 'error')
            return redirect(url_for('register', event_id=event_id))
            
        try:
            cursor = conn.cursor()
            
            # Generate QR code data
            qr_data = f"TUT-EVENT-{event_id}-{student_number}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # Insert registration
            cursor.execute("""
                INSERT INTO event_registrations (event_id, student_number, full_name, email, phone, faculty, 
                                              dietary_restrictions, special_requirements, registration_date, status, qr_code_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Registered', %s)
            """, (event_id, student_number, first_name, email, phone, faculty, 
                  dietary_restrictions, special_requirements, datetime.now(), qr_data))
            
            # Get event details for confirmation
            cursor.execute("""
                SELECT title, event_date, event_time, location, faculty
                FROM events WHERE event_id = %s
            """, (event_id,))
            event_details = cursor.fetchone()
            
            conn.commit()
            
            # Generate QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(qr_data)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert QR code to base64 for embedding in HTML
            buffer = io.BytesIO()
            qr_img.save(buffer, format='PNG')
            qr_base64 = base64.b64encode(buffer.getvalue()).decode()
            
              # Helper function to format date/time for JSON serialization
            def format_for_json(obj):
                if hasattr(obj, 'strftime'):
                    if hasattr(obj, 'hour'):  # time object
                        return obj.strftime('%I:%M %p')
                    else:  # date object
                        return obj.strftime('%A, %B %d, %Y')
                return str(obj) if obj is not None else ""
            
            # Store registration details in session for confirmation page
            session['registration_details'] = {
                'event_title': event_details[0],
                'event_date': format_date(event_details[1]),  # Format date properly
                'event_time': format_time(event_details[2]),  # Format time properly
                'event_location': event_details[3],
                'event_faculty': event_details[4],
                'student_name': first_name,
                'student_number': student_number,
                'email': email,
                'phone': phone,
                'faculty': faculty,
                'dietary_restrictions': dietary_restrictions,
                'special_requirements': special_requirements,
                'confirmation_code': f"TUT-{event_id}-{student_number[-4:]}",
                'qr_code': qr_base64,
                'qr_data': qr_data
            }
            
            # Send notifications (you'll need to implement these)
            send_email_confirmation(session['registration_details'])
            send_whatsapp_notification(session['registration_details'])
            
            return redirect(url_for('registration_confirmation'))
            
        except Exception as e:
            conn.rollback()
            print(f"Error during registration: {e}")
            flash('An error occurred during registration', 'error')
            return redirect(url_for('register', event_id=event_id))
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

def format_date(date_obj):
    """Format date object for JSON serialization"""
    if hasattr(date_obj, 'strftime'):
        return date_obj.strftime('%A, %B %d, %Y')
    return str(date_obj)

def format_time(time_obj):
    """Format time object for JSON serialization"""
    if hasattr(time_obj, 'strftime'):
        return time_obj.strftime('%I:%M %p')
    return str(time_obj)            
def send_email_confirmation(registration_details):
    """Send email confirmation to student"""
    try:
        # Implement your email sending logic here
        # You can use Flask-Mail, SMTPLib, or any email service
        print(f"Email sent to {registration_details['email']} for event {registration_details['event_title']}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_whatsapp_notification(registration_details):
    """Send WhatsApp notification to student"""
    try:
        # Implement your WhatsApp API integration here
        # You can use Twilio, WhatsApp Business API, etc.
        print(f"WhatsApp notification sent to {registration_details['phone']} for event {registration_details['event_title']}")
        return True
    except Exception as e:
        print(f"Error sending WhatsApp message: {e}")
        return False
                    
@app.route('/registration_confirmation')
def registration_confirmation():
    registration_details = session.get('registration_details')
    if not registration_details:
        flash('No registration found', 'error')
        return redirect(url_for('index'))
    
    return render_template('registration_confirmation.html', registration=registration_details)

@app.route('/dashboard')
def dashboard():
    if 'student_number' not in session:
        return redirect(url_for('login_itspin'))

    conn = get_db_connection()
    if not conn:
        return render_template('dashboard.html', student={})
        
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT first_name, last_name, email FROM students WHERE student_number = %s", (session['student_number'],))
        student = cursor.fetchone()
        if student:
            student_data = {
                'first_name': student[0],
                'last_name': student[1],
                'email': student[2],
                'student_number': session['student_number']
            }
        else:
            student_data = {}
    except Exception as e:
        print(f"Error in dashboard: {e}")
        student_data = {}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return render_template('dashboard.html', student=student_data)

@app.route('/login', methods=['POST'])
def login():
    student_number = request.form.get('studentNumber')
    pin = request.form.get('password')
    remember_me = request.form.get('rememberMe')

    if not student_number or not pin:
        return jsonify({'success': False, 'message': 'Please provide both student number and PIN'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number, pin FROM students WHERE student_number = %s", (student_number,))
        student = cursor.fetchone()

        if student and student[1] == pin:
            session['student_number'] = student[0]
            if remember_me:
                session.permanent = True
            return jsonify({
                'success': True,
                'message': 'Login successful!',
                'redirect': url_for('dashboard')
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Invalid student number or PIN'
            })
    except Exception as e:
        print(f"Error during login: {e}")
        return jsonify({'success': False, 'message': 'An error occurred during login'})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact_us')
def contact_us():
    return render_template('contact_us.html')

@app.route('/upcoming_events')
def upcoming_events():
    conn = get_db_connection()
    events_data = []
    if conn:
        try:
            cursor = conn.cursor()
            # Include category and compute seats_left
            cursor.execute("""
                SELECT 
                    event_id, 
                    title, 
                    event_date, 
                    event_time, 
                    location, 
                    faculty, 
                    max_attendees, 
                    event_image, 
                    description, 
                    category,
                    (max_attendees - COALESCE((
                        SELECT COUNT(*) 
                        FROM event_registrations 
                        WHERE event_id = events.event_id
                    ), 0)) AS seats_left
                FROM events 
                WHERE event_date >= CURRENT_DATE 
                ORDER BY event_date
            """)
            events = cursor.fetchall()
            
            for event in events:
                # Format date as YYYY-MM-DD for JavaScript
                formatted_date = event[2].strftime('%Y-%m-%d') if event[2] else ''
                # Format time as HH:MM AM/PM
                formatted_time = event[3].strftime('%I:%M %p') if event[3] else ''
                
                events_data.append({
                    'id': event[0],
                    'title': event[1],
                    'event_date': formatted_date,
                    'event_time': formatted_time,
                    'location': event[4],
                    'faculty': event[5],
                    'max_attendees': event[6],
                    'event_image': event[7],          # filename only
                    'description': event[8],
                    'category': event[9].lower() if event[9] else 'other',  # lowercase for filters
                    'seats_left': event[10]
                })
        except Exception as e:
            print(f"Error fetching upcoming events: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    return render_template('upcoming_events.html', events=events_data)

@app.route('/past_events')
def past_events():
    return render_template('past_events.html')
@app.route('/organizers')
def organizers():
    conn = get_db_connection()
    organizers_data = []
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    organizer_id,
                    name,
                    email,
                    phone,
                    department,
                    events_organized,
                    status
                FROM organizers
                WHERE status = 'active'
                ORDER BY events_organized DESC
            """)
            organizers = cursor.fetchall()
            
            for org in organizers:
                organizers_data.append({
                    'organizer_id': org[0],
                    'name': org[1],
                    'email': org[2],
                    'phone': org[3],
                    'department': org[4],
                    'events_organized': org[5],
                    'status': org[6]
                })
        except Exception as e:
            print(f"Error fetching organizers: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    return render_template('organizers.html', organizers=organizers_data)
@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/gallery')
def gallery():
    return render_template('gallery.html')

if __name__ == '__main__':
    app.run(debug=True)
