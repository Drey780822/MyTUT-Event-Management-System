from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import psycopg2
from psycopg2 import Error
from datetime import datetime


app = Flask(__name__)
app.secret_key = "abcd1234"  # Change this to a secure random key in production

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
    return render_template('admin/admin_login.html')
	
@app.route('/admin/login')
def admin_login():
    return render_template('admin/admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'staff_nr' not in session:
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    if not conn:
        return render_template('admin/admin_dashboard.html', 
                             admin={}, 
                             stats={'total_events': 0, 'total_attendees': 0, 'upcoming_events': 0, 'avg_attendance': 0},
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
            
        # Get stats
        cursor.execute("SELECT COUNT(*) FROM events")
        result = cursor.fetchone()
        total_events = result[0] if result else 0
        
        cursor.execute("SELECT COUNT(DISTINCT student_id) FROM event_registrations")
        result = cursor.fetchone()
        total_attendees = result[0] if result else 0
        
        cursor.execute("SELECT COUNT(*) FROM events WHERE event_date >= CURRENT_DATE")
        result = cursor.fetchone()
        upcoming_events_count = result[0] if result else 0
        
        # Fixed attendance calculation - assuming you have attended column in event_registrations
        cursor.execute("""
            SELECT COALESCE(AVG(
                CASE 
                    WHEN COUNT(*) > 0 
                    THEN (COUNT(CASE WHEN status = 'Attended' THEN 1 END) * 100.0 / COUNT(*))
                    ELSE 0 
                END
            ), 0)
            FROM event_registrations 
            GROUP BY event_id
        """)
        result = cursor.fetchone()
        avg_attendance = result[0] if result else 0
        
        # Get upcoming events
       
        
        # Get recent registrations
        cursor.execute("""
            SELECT s.first_name, s.last_name, s.student_number, e.title, er.registration_date, er.status, er.registration_id
            FROM event_registrations er
            JOIN students s ON er.student_id = s.student_number
            JOIN events e ON er.event_id = e.event_id
            ORDER BY er.registration_date DESC
            LIMIT 10
        """)
        recent_registrations = cursor.fetchall()

        # Get category distribution
        cursor.execute("""
            SELECT COALESCE(category, 'Uncategorized') as category, COUNT(*) as count 
            FROM events 
            GROUP BY category
        """)
        categories = cursor.fetchall()
        
    except Exception as e:
        print(f"Error in admin dashboard: {e}")
        admin_data = {}
        admin_name = "Admin"
        total_events = 0
        total_attendees = 0
        upcoming_events_count = 0
        avg_attendance = 0
        upcoming_events_data = []
        recent_registrations = []
        categories = []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return render_template('admin/admin_dashboard.html', 
                         admin=admin_data,
                         stats={
                             'total_events': total_events,
                             'total_attendees': total_attendees,
                             'upcoming_events': upcoming_events_count,
                             'avg_attendance': round(avg_attendance, 1)
                         },
                         upcoming_events=upcoming_events_data,
                         recent_registrations=recent_registrations,
                         categories=categories,
                         admin_name=admin_name)

@app.route('/admin/login', methods=['POST'])
def admin_login_post():
    staff_nr = request.form.get('username')
    password = request.form.get('password')
    remember_me = request.form.get('rememberMe')

    if not staff_nr or not password:
        return jsonify({'success': False, 'message': 'Please provide both username and password'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT first_name, last_name, email, password FROM admins WHERE staff_nr = %s", (staff_nr,))
        admin = cursor.fetchone()

        if admin and admin[3] == password:
            session['staff_nr'] = staff_nr
            if remember_me: 
                session.permanent = True
            return jsonify({
                'success': True,
                'message': 'Admin login successful!',
                'redirect': url_for('admin_dashboard')
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Invalid staff ID or password'
            })
    except Exception as e:
        print(f"Error during admin login: {e}")
        return jsonify({'success': False, 'message': 'An error occurred during login'})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

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
            
@app.route('/admin_logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_index')) 

# Student Routes
@app.route('/')
def index():
    conn = get_db_connection()
    events_data = []
    past_events = []
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
              
        except Exception as e:
            print(f"Error fetching events for homepage: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    return render_template('index.html', events=events_data, past_events=past_events)
@app.route('/login_itspin')
def login_itspin():
    return render_template('login_itspin.html')

@app.route('/login_studemail')
def login_studemail():
    return render_template('login_studemail.html')

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
    
    return render_template('register_event.html', event=event_data)

@app.route('/submit_registration', methods=['POST'])
def submit_registration():
    if request.method == 'POST':
        # Get form data
        event_id = request.form.get('event_id')
        full_name = request.form.get('fullName')
        student_number = request.form.get('studentNumber')
        email = request.form.get('email')
        phone = request.form.get('phone')
        faculty = request.form.get('faculty')
        dietary_restrictions = request.form.get('dietaryRestrictions')
        special_requirements = request.form.get('specialRequirements')
        
        # Validate required fields
        if not all([event_id, full_name, student_number, email]):
            flash('Please fill in all required fields', 'error')
            return redirect(url_for('register', event_id=event_id))
        
        conn = get_db_connection()
        if not conn:
            flash('Database connection error', 'error')
            return redirect(url_for('register', event_id=event_id))
            
        try:
            cursor = conn.cursor()
            
            # Check if student already registered for this event
            cursor.execute("""
                SELECT registration_id FROM event_registrations 
                WHERE event_id = %s AND student_id = %s
            """, (event_id, student_number))
            
            if cursor.fetchone():
                flash('You have already registered for this event', 'error')
                return redirect(url_for('register', event_id=event_id))
            
            # Check if there are available seats
            cursor.execute("""
                SELECT max_attendees, 
                       (SELECT COUNT(*) FROM event_registrations WHERE event_id = %s) as current_registrations
                FROM events WHERE event_id = %s
            """, (event_id, event_id))
            
            event_capacity = cursor.fetchone()
            if event_capacity and event_capacity[1] >= event_capacity[0]:
                flash('This event is fully booked', 'error')
                return redirect(url_for('register', event_id=event_id))
            
            # Insert registration
            cursor.execute("""
                INSERT INTO event_registrations (event_id, student_id, full_name, email, phone, faculty, 
                                              dietary_restrictions, special_requirements, registration_date, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Registered')
            """, (event_id, student_number, full_name, email, phone, faculty, 
                  dietary_restrictions, special_requirements, datetime.now()))
            
            # Get event details for confirmation
            cursor.execute("""
                SELECT title, event_date, event_time, location 
                FROM events WHERE event_id = %s
            """, (event_id,))
            event_details = cursor.fetchone()
            
            conn.commit()
            
            # Store registration details in session for confirmation page
            session['registration_details'] = {
                'event_title': event_details[0],
                'event_date': event_details[1],
                'event_time': event_details[2],
                'event_location': event_details[3],
                'student_name': full_name,
                'student_number': student_number,
                'email': email,
                'confirmation_code': f"TUT-{event_id}-{student_number[-4:]}"
            }
            
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
            cursor.execute("""
                SELECT event_id, title, event_date, event_time, location, faculty, 
                       max_attendees, event_image, description,
                       (max_attendees - COALESCE((SELECT COUNT(*) FROM event_registrations WHERE event_id = events.event_id), 0)) as seats_left
                FROM events 
                WHERE event_date >= CURRENT_DATE 
                ORDER BY event_date
            """)
            events = cursor.fetchall()
            
            for event in events:
                events_data.append({
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

@app.route('/gallery')
def gallery():
    return render_template('gallery.html')

if __name__ == '__main__':
    app.run(debug=True)