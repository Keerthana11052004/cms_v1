from flask import Blueprint, render_template, redirect, url_for, request, flash, session, abort
from flask_login import login_user, logout_user, login_required, current_user
from .forms import LoginForm, BookMealForm, ProfileUpdateForm
from .utils import generate_meal_qr_code
from . import Curr_Proj_Name, mysql, User
from . import mysql, User
import hashlib
from datetime import date, datetime, time
from . import Curr_Proj_Name, mysql, User
from .db_config import get_db_connection

employee_bp = Blueprint('employee', __name__)

@employee_bp.before_request
def before_request_log():
    try:
        # This will execute before any request to this blueprint
        # You can add logging here to see if the request even reaches this point
        print(f"Employee Blueprint: Request received for {request.path}")
    except Exception as e:
        import traceback
        with open("app_errors.log", "a") as log_file:
            log_file.write(f"[{datetime.now()}] Error in employee_bp.before_request: {e}\n")
            traceback.print_exc(file=log_file)
        print(f"Error in employee_bp.before_request: {e}")
        traceback.print_exc()
        abort(500)

@employee_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT message_text FROM special_messages WHERE is_active = TRUE AND DATE(created_at) = CURDATE() ORDER BY created_at DESC LIMIT 1")
    special_message = cur.fetchone()

    # Fetch all locations for the menu modal
    cur.execute("SELECT name FROM locations ORDER BY name")
    locations = cur.fetchall()

    if form.validate_on_submit():
        employee_id = form.employee_id.data
        password = form.password.data
        cur.execute("SELECT * FROM employees WHERE employee_id=%s AND role_id=1 AND is_active=1", (employee_id,))
        user = cur.fetchone()
        if user:
            if password:  # Check if password is not None or empty
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                if user['password_hash'] == password_hash or user['password_hash'] == password:
                    user_obj = User(user['id'], name=user['name'], email=user['email'], role='Employee')
                    login_user(user_obj)
                    # Flash message will appear on dashboard
                    return URL_Redirect_ConnClose(conn, url_for('employee.dashboard'))
                else:
                    flash('Invalid password.', 'danger')
            else:
                flash('Password is required.', 'danger')
        else:
            flash('Invalid employee ID or not an employee.', 'danger')
    cur.close()
    conn.close()
    return render_template('employee/login.html', form=form, special_message=special_message, locations=locations)

@employee_bp.route('/logout')
def logout():
    from flask_login import logout_user
    logout_user()
    session['logout_message'] = 'Logged out successfully.'
    # Clear dashboard visited flag so login message appears again on next login
    session.pop('dashboard_visited', None)
    return redirect(url_for('index'))

@employee_bp.route('/dashboard')
@login_required
def dashboard():
    # Show login success message on first visit to dashboard after login
    if not session.get('dashboard_visited'):
        flash('Login successful!', 'success')
        session['dashboard_visited'] = True
    else:
        # Reset the flag if we're navigating away and back to dashboard
        if request.args.get('reset_visited'):
            session['dashboard_visited'] = False
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Initialize all variables with safe defaults
        today_bookings = []
        chart_labels = []
        breakfast_data = []
        lunch_data = []
        dinner_data = []
        locations = []
        daily_menu = []
        # Fetch all locations for the unit selector
        cur.execute("SELECT id, name FROM locations ORDER BY name")
        locations = cur.fetchall()
        
        # Get today's booking status - only the latest booking for each meal type
        from datetime import date, timedelta
        today = date.today()
        
        cur.execute("""
            SELECT b.*, m.name as meal_name, l.name as location_name
            FROM bookings b
            JOIN meals m ON b.meal_id = m.id
            JOIN locations l ON b.location_id = l.id
            WHERE b.employee_id = %s AND b.booking_date = %s
            AND b.id IN (
                SELECT MAX(id) 
                FROM bookings 
                WHERE employee_id = %s AND booking_date = %s 
                GROUP BY shift
            )
            ORDER BY b.shift
        """, (current_user.id, today, current_user.id, today))
        
        today_bookings = cur.fetchall()
        
        # Get bookings for past 7 days for chart
        seven_days_ago = today - timedelta(days=6)
        
        cur.execute("""
            SELECT
                DATE(b.booking_date) as date,
                b.shift,
                b.status,
                COUNT(*) as count
            FROM bookings b
            WHERE b.employee_id = %s
            AND b.booking_date >= %s
            AND b.booking_date <= %s
            GROUP BY DATE(b.booking_date), b.shift, b.status
            ORDER BY DATE(b.booking_date), b.shift
        """, (current_user.id, seven_days_ago, today))
        
        booking_data = cur.fetchall()
        
        # Process data for chart
        chart_data = {}
        for i in range(7):
            chart_date = seven_days_ago + timedelta(days=i)
            chart_data[chart_date.strftime('%Y-%m-%d')] = {
                'date': chart_date.strftime('%b %d'),
                'Breakfast': 0,
                'Lunch': 0,
                'Dinner': 0
            }
        
        for booking in booking_data:
            date_str = booking['date'].strftime('%Y-%m-%d')
            if date_str in chart_data:
                chart_data[date_str][booking['shift']] = booking['count']
        
        chart_labels = [data['date'] for data in chart_data.values()] if chart_data else []
        breakfast_data = [data['Breakfast'] for data in chart_data.values()] if chart_data else []
        lunch_data = [data['Lunch'] for data in chart_data.values()] if chart_data else []
        dinner_data = [data['Dinner'] for data in chart_data.values()] if chart_data else []

        # Get employee's location from their profile, with a fallback to a default
        cur.execute("SELECT location_id FROM employees WHERE id = %s", (current_user.id,))
        user_location = cur.fetchone()
        if user_location and user_location['location_id']:
            location_id = user_location['location_id']
        else:
            # Fallback to a default location if not set for the user
            cur.execute("SELECT id FROM locations ORDER BY id LIMIT 1")
            default_location = cur.fetchone()
            location_id = default_location['id'] if default_location else None

        daily_menu = []
        if location_id is not None: # Ensure location_id is not None before querying
            # Try to get today's menu
            cur.execute("""
                SELECT meal_type, items
                FROM daily_menus
                WHERE location_id = %s AND menu_date = %s
                ORDER BY FIELD(meal_type, 'Breakfast', 'Lunch', 'Dinner')
            """, (location_id, today))
            daily_menu = cur.fetchall()
        else:
            # Don't show debug message - just set empty menu
            daily_menu = []
        cur.close()
        conn.close()

        return render_template('employee/dashboard.html',
                            today_bookings=today_bookings,
                            chart_labels=chart_labels,
                            breakfast_data=breakfast_data,
                            lunch_data=lunch_data,
                            dinner_data=dinner_data,
                            locations=locations,
                            daily_menu=daily_menu)
    except Exception as e:
        print(f"Error in employee dashboard: {e}")
        import traceback
        traceback.print_exc()
        abort(500)

@employee_bp.route('/select_unit', methods=['POST'])
@login_required
def select_unit():
    unit_id = request.form.get('unit_id')
    if unit_id:
        session['selected_unit_id'] = int(unit_id)
        return {'status': 'success', 'message': 'Unit selected successfully!'}
    else:
        return {'status': 'error', 'message': 'Invalid unit selection.'}, 400

@employee_bp.route('/book', methods=['GET', 'POST'])

@login_required
def book_meal():
    form = BookMealForm()
    today = date.today().isoformat()
    conn = None
    cur = None
    try:
        if form.validate_on_submit():
            qr_image_base64 = None
            shift = form.shift.data
            date_val = form.date.data
            recurrence = form.recurrence.data
            now = datetime.now().time()
            # Booking windows
            allowed = False
            if shift == 'Breakfast':
                allowed = time(4,0) <= now <= time(9,30)
            elif shift == 'Lunch':
                allowed = time(9,30) <= now <= time(12,30)
            elif shift == 'Dinner':
                allowed = time(14,0) <= now <= time(19,0)
            if not allowed:
                flash('Booking for {} is only allowed during its time window.'.format(shift), 'danger')
                return redirect(url_for('employee.book_meal'))
            conn = get_db_connection(False)
            cur = conn.cursor()
            cur.execute("SELECT id FROM meals WHERE name=%s", (shift,))
            meal = cur.fetchone()
            if not meal:
                flash('Invalid meal/shift selected.', 'danger')
                return URL_Redirect_ConnClose(conn, url_for('employee.book_meal'))
            meal_id = meal['id']
            employee_id = current_user.id
            # Check for existing booking for the same date and shift
            cur.execute("SELECT id, status FROM bookings WHERE employee_id=%s AND booking_date=%s AND shift=%s", (employee_id, date_val, shift))
            existing_booking = cur.fetchone()
            if existing_booking:
                if existing_booking['status'] == 'Booked':
                    flash(f'You have already booked {shift} for {date_val}.', 'warning')
                elif existing_booking['status'] == 'Consumed':
                    flash(f'Your {shift} for {date_val} has already been consumed.', 'info')
                elif existing_booking['status'] == 'Cancelled':
                    flash(f'Your {shift} for {date_val} was cancelled.', 'info')
                return URL_Redirect_ConnClose(conn, url_for('employee.book_meal'))
            # 
            cur.execute("SELECT location_id FROM employees WHERE id=%s", (employee_id,))
            emp = cur.fetchone()
            if not emp or not emp['location_id']:
                flash('Your location is not set. Contact admin.', 'danger')
                return URL_Redirect_ConnClose(conn, url_for('employee.book_meal'))
            location_id = emp['location_id']
            cur.execute("SELECT e.name, e.employee_id, l.name as location_name FROM employees e JOIN locations l ON e.location_id = l.id WHERE e.id=%s", (employee_id,))
            emp_details = cur.fetchone()
            if not emp_details:
                flash('Employee details not found.', 'danger')
                return URL_Redirect_ConnClose(conn, url_for('employee.book_meal'))
            try:
                # Step 1: Create the booking record without the QR code to get the booking_id
                cur.execute("""
                    INSERT INTO bookings (employee_id, employee_id_str, meal_id, booking_date, shift, recurrence, location_id, booking_type, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (employee_id, emp_details['employee_id'], meal_id, date_val, shift, recurrence, location_id, 'App', 'Booked'))
                
                # Get the ID of the new booking
                booking_id = cur.lastrowid
                
                # Step 2: Generate the QR code with the unique booking_id
                qr_image_base64, qr_data_string = generate_meal_qr_code(
                    booking_id=booking_id,
                    employee_id=emp_details['employee_id'],
                    date=str(date_val),
                    shift=shift
                )
                
                # Step 3: Update the booking record with the generated QR code
                cur.execute("""
                    UPDATE bookings
                    SET qr_code_data = %s
                    WHERE id = %s
                """, (qr_image_base64, booking_id))
                
                conn.commit() # XXXXX
                
                flash('Meal booked successfully! QR code generated.', 'success')
                session['last_booking_qr'] = qr_image_base64
                return URL_Redirect_ConnClose(conn, url_for('employee.book_meal'))
                
            except Exception as e:
                if conn:
                    conn.rollback()
                flash('Error booking meal: ' + str(e), 'danger')
                return URL_Redirect_ConnClose(conn, url_for('employee.book_meal'))
        
        # Check if user has already booked a meal for today
        conn = get_db_connection(False)
        cur = conn.cursor()
        cur.execute("""
            SELECT b.*, m.name as meal_name, l.name as location_name
            FROM bookings b
            JOIN meals m ON b.meal_id = m.id
            JOIN locations l ON b.location_id = l.id
            WHERE b.employee_id = %s AND b.booking_date = %s AND b.status = 'Booked'
            ORDER BY b.shift
        """, (current_user.id, date.today()))
        today_bookings = cur.fetchall()
        
        qr_image_base64 = session.pop('last_booking_qr', None)
        return render_template('employee/book.html', form=form, qr_image_base64=qr_image_base64, today=today, today_bookings=today_bookings)
    finally:
        if cur:
            cur.close()
        

@employee_bp.route('/history')
@login_required
def booking_history():
    conn = get_db_connection()
    cur = conn.cursor()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    query = '''
        SELECT b.*, m.name as meal_name, l.name as location_name, e.name as employee_name, e.employee_id
        FROM bookings b
        JOIN meals m ON b.meal_id = m.id
        JOIN locations l ON b.location_id = l.id
        JOIN employees e ON b.employee_id = e.id
        WHERE b.employee_id = %s
    '''
    params = [current_user.id]
    if start_date:
        query += ' AND b.booking_date >= %s'
        params.append(start_date)
    if end_date:
        query += ' AND b.booking_date <= %s'
        params.append(end_date)
    query += ' ORDER BY b.booking_date DESC, b.created_at DESC'
    cur.execute(query, tuple(params))
    bookings = cur.fetchall()

    cur.close()
    conn.close()
    return render_template('employee/history.html', bookings=bookings)

@employee_bp.route('/cancel_booking/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    conn = get_db_connection()
    cur = conn.cursor()
    # Check if booking exists and belongs to current user and is 'Booked'
    cur.execute("SELECT * FROM bookings WHERE id=%s AND employee_id=%s", (booking_id, current_user.id))
    booking = cur.fetchone()
    if not booking:
        flash('Booking not found or not authorized.', 'danger')
        return URL_Redirect_ConnClose(conn, url_for('employee.booking_history'))
    if booking['status'] != 'Booked':
        flash('Only booked meals can be cancelled.', 'warning')
        return URL_Redirect_ConnClose(conn, url_for('employee.booking_history'))
    # Update status to Cancelled
    cur.execute("UPDATE bookings SET status='Cancelled' WHERE id=%s", (booking_id,))
    flash('Booking cancelled successfully.', 'success')
    return URL_Redirect_ConnClose(conn, url_for('employee.booking_history'))

@employee_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = get_db_connection()
    cur = conn.cursor()
    # Get all locations and departments for dropdowns
    cur.execute("SELECT id, name FROM locations ORDER BY name")
    locations = cur.fetchall()
    cur.execute("SELECT id, name FROM departments ORDER BY name")
    departments = cur.fetchall()
    # Get current employee details
    cur.execute("""
        SELECT e.*, d.name as department_name, l.name as location_name 
        FROM employees e 
        LEFT JOIN departments d ON e.department_id = d.id 
        LEFT JOIN locations l ON e.location_id = l.id 
        WHERE e.id = %s
    """, (current_user.id,))
    employee = cur.fetchone()
    # Prepare form
    form = ProfileUpdateForm()
    form.department_id.choices = [(d['id'], d['name']) for d in departments]
    form.location_id.choices = [(l['id'], l['name']) for l in locations]
    if request.method == 'POST' and form.validate_on_submit():
        name = form.name.data
        department_id = form.department_id.data or None
        location_id = form.location_id.data or None
        password = form.password.data
        confirm_password = form.confirm_password.data
        # Password update logic
        if password:
            if password != confirm_password:
                flash('Passwords do not match.', 'danger')
            else:
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                cur.execute("UPDATE employees SET password_hash=%s WHERE id=%s", (password_hash, current_user.id))
                flash('Password updated successfully.', 'success')
        # Update name, department, location
        cur.execute(
            "UPDATE employees SET name=%s, department_id=%s, location_id=%s WHERE id=%s",
            (name, department_id, location_id, current_user.id)
        )
        flash('Profile updated successfully.', 'success')
        return URL_Redirect_ConnClose(conn, url_for('employee.profile'))
    # Pre-populate form fields on GET
    elif request.method == 'GET' and employee:
        form.name.data = employee['name']
        form.email.data = employee['email']
        form.employee_id.data = employee['employee_id']
        form.department_id.data = employee['department_id']
        form.location_id.data = employee['location_id']
    return render_template('employee/profile.html', form=form, employee=employee, locations=locations, departments=departments)

@employee_bp.route('/menu')
@login_required
def view_menu():
    conn = get_db_connection()
    cur = conn.cursor()
    today = date.today()

    # Fetch all locations for the unit selector
    cur.execute("SELECT id, name FROM locations ORDER BY name")
    locations = cur.fetchall()
    
    # Get employee's location from their profile, with a fallback to a default
    cur.execute("SELECT location_id FROM employees WHERE id = %s", (current_user.id,))
    user_location = cur.fetchone()
    if user_location and user_location['location_id']:
        location_id = user_location['location_id']
    else:
        # Fallback to a default location if not set for the user
        cur.execute("SELECT id FROM locations ORDER BY id LIMIT 1")
        default_location = cur.fetchone()
        location_id = default_location['id'] if default_location else None

    menu = []
    if location_id:
        # Try to get today's menu
        cur.execute("""
            SELECT meal_type, items
            FROM daily_menus
            WHERE location_id = %s AND menu_date = %s
            ORDER BY FIELD(meal_type, 'Breakfast', 'Lunch', 'Dinner')
        """, (location_id, today))
        menu = cur.fetchall()

    else:
        flash('Please select a unit to view the menu.', 'info')
        return URL_Redirect_ConnClose(conn, url_for('employee.dashboard'))

    return render_template('employee/view_menu.html', menu=menu, locations=locations)
@employee_bp.route('/api/menu/<int:location_id>')
def get_menu_for_location(location_id):
    conn = get_db_connection()
    cur = conn.cursor()
    today = date.today()
    cur.execute("""
        SELECT meal_type, items
        FROM daily_menus
        WHERE location_id = %s AND menu_date = %s
        ORDER BY FIELD(meal_type, 'Breakfast', 'Lunch', 'Dinner')
    """, (location_id, today))
    menu = cur.fetchall()
    
    # If no menu for today, return an empty list
    if not menu:
        return {'menu': []}
    cur.close()
    conn.close()
    return {'menu': menu}

def URL_Redirect_ConnClose(conn, url):
    try:
        if conn:
            try:
                cur = conn.cursor()
                if cur:
                    cur.close()
            except:
                pass
            conn.close()
    except Exception as e:
        print(f"Error in URL_Redirect_ConnClose: {e}")
    finally:
        return redirect(url)

