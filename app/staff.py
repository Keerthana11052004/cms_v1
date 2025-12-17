from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, login_user, logout_user, current_user
from .forms import LoginForm
from .utils import decode_qr_code
from . import Curr_Proj_Name, mysql, User
from datetime import date
import sys
from .db_config import get_db_connection
from .employee import URL_Redirect_ConnClose

staff_bp = Blueprint('staff', __name__)

@staff_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    from . import mysql, User
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT message_text FROM special_messages WHERE is_active = TRUE AND DATE(created_at) = CURDATE() ORDER BY created_at DESC LIMIT 1")
    special_message = cur.fetchone()
    if form.validate_on_submit():
        import hashlib
        employee_id = form.employee_id.data
        password = form.password.data
        cur.execute("SELECT * FROM employees WHERE employee_id=%s AND role_id IN (2,3) AND is_active=1", (employee_id,))
        user = cur.fetchone()
        if user and password:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            if user['password_hash'] == password_hash or user['password_hash'] == password:
                role = 'Supervisor' if user['role_id'] == 3 else 'Staff'
                user_obj = User(user['id'], name=user['name'], email=user['email'], role=role)
                login_user(user_obj)
                flash('Login successful!', 'success')
                return URL_Redirect_ConnClose(conn, url_for('staff.dashboard'))
            else:
                flash('Invalid password.', 'danger')
        else:
            flash('Invalid employee ID or not staff.', 'danger')
    cur.close()
    conn.close()
    return render_template('staff/login.html', form=form, special_message=special_message)

@staff_bp.route('/logout')
def logout():
    print("[DEBUG] Logout function called.", file=sys.stderr)
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))

@staff_bp.route('/qr_scanner')
@login_required
def qr_scanner():
    dashboard_url = url_for('staff.dashboard')
    return render_template('staff/qr_scanner.html', dashboard_url=dashboard_url)

@staff_bp.route('/test_db')
@login_required
def test_db():
    """Test database connection and table structure"""
    from . import mysql
    import sys
    try:
        # Test connection
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Test basic connection
        cur.execute("SELECT 1")
        result = cur.fetchone()
        print(f"[DEBUG] Basic connection test result: {result}", file=sys.stderr)
        
        # Test if tables exist
        cur.execute("SHOW TABLES")
        tables = cur.fetchall()
        print(f"[DEBUG] Tables found: {tables}", file=sys.stderr)
        
        # Test bookings table structure
        cur.execute("DESCRIBE bookings")
        booking_columns = cur.fetchall()
        print(f"[DEBUG] Booking columns: {booking_columns}", file=sys.stderr)
        
        # Test employees table
        cur.execute("SELECT COUNT(*) as count FROM employees")
        emp_count = cur.fetchone()
        print(f"[DEBUG] Employee count: {emp_count}", file=sys.stderr)
        
        # Test locations table
        cur.execute("SELECT name FROM locations")
        locations = cur.fetchall()
        print(f"[DEBUG] Locations: {locations}", file=sys.stderr)
        
        # Test sample booking data
        cur.execute("SELECT COUNT(*) as count FROM bookings")
        booking_count = cur.fetchone()
        print(f"[DEBUG] Booking count: {booking_count}", file=sys.stderr)

        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'connection': 'OK',
            'tables': [table['Tables_in_food'] for table in tables],
            'booking_columns': [col['Field'] for col in booking_columns],
            'employee_count': emp_count['count'],
            'locations': [loc['name'] for loc in locations],
            'booking_count': booking_count['count']
        })
    except Exception as e:
        print(f"[DEBUG] Database test error: {str(e)}", file=sys.stderr)
        import traceback
        tb = traceback.format_exc()
        print(f"[DEBUG] Full traceback: {tb}", file=sys.stderr)
        return jsonify({'success': False, 'error': str(e), 'traceback': tb})

@staff_bp.route('/simple_test')
@login_required
def simple_test():
    """Simple database test without complex queries"""
    from . import mysql
    import sys
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 as test")
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Simple test successful',
            'result': result
        })
    except Exception as e:
        print(f"[DEBUG] Simple test error: {str(e)}", file=sys.stderr)
        return jsonify({'success': False, 'error': str(e)})

@staff_bp.route('/create_test_booking')
@login_required
def create_test_booking():
    """Create a test booking for QR scanner testing"""
    from . import mysql
    import sys
    from datetime import date, timedelta
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get today's date
        today = date.today()
        
        # Check if test booking already exists
        cur.execute("""
            SELECT b.*, e.employee_id, l.name as location_name
            FROM bookings b
            JOIN employees e ON b.employee_id = e.id
            JOIN locations l ON b.location_id = l.id
            WHERE (e.employee_id = 'EMP001' OR b.employee_id_str = 'EMP001') AND b.booking_date = %s AND b.shift = 'Lunch'
        """, (today,))
        
        existing_booking = cur.fetchone()
        
        if existing_booking:
            response_data = {
                'success': True,
                'message': 'Test booking already exists',
                'booking': {
                    'employee_name': 'John Doe',
                    'employee_id': 'EMP001',
                    'unit': existing_booking['location_name'],
                    'date': existing_booking['booking_date'].strftime('%Y-%m-%d'),
                    'shift': existing_booking['shift'],
                    'status': existing_booking['status']
                }
            }
            print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
            cur.close()
            conn.close()
            return jsonify(response_data)
        
        # Create test booking
        cur.execute("""
            INSERT INTO bookings (employee_id, employee_id_str, meal_id, booking_date, shift, location_id, status)
            SELECT e.id, e.employee_id, m.id, %s, 'Lunch', l.id, 'Booked'
            FROM employees e, meals m, locations l
            WHERE e.employee_id = 'EMP001' AND m.name = 'Lunch' AND l.name = 'Unit 1'
        """, (today,))
        
        response_data = {
            'success': True,
            'message': 'Test booking created successfully',
            'booking': {
                'employee_name': 'John Doe',
                'employee_id': 'EMP001',
                'unit': 'Unit 1',
                'date': today.strftime('%Y-%m-%d'),
                'shift': 'Lunch',
                'status': 'Booked'
            }
        }
        print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
        return jsonify(response_data)
        
    except Exception as e:
        print(f"[DEBUG] Create test booking error: {str(e)}", file=sys.stderr)
        import traceback
        tb = traceback.format_exc()
        print(f"[DEBUG] Full traceback: {tb}", file=sys.stderr)
        return jsonify({'success': False, 'error': str(e), 'traceback': tb})

@staff_bp.route('/scan_qr', methods=['POST'])
@login_required
def scan_qr():
    from . import mysql
    import sys
    import traceback # Import traceback for detailed error logging
    
    # Initialize variables to prevent unbound errors
    conn = None
    cur = None

    try:
        print("=== SCAN_QR CALLED ===", file=sys.stderr)
        print("request.method:", request.method, file=sys.stderr)
        print("request.is_json:", request.method, file=sys.stderr)
        print("request.headers:", dict(request.headers), file=sys.stderr)
        print("request.data:", request.data, file=sys.stderr)
        print("request.form:", request.form, file=sys.stderr)
        print("request.json:", request.json if request.is_json else "Not JSON", file=sys.stderr)
        
        # Accept both JSON and form data
        qr_data = None
        if request.is_json and request.json:
            qr_data = request.json.get('qr_data')
        else:
            qr_data = request.form.get('qr_data')
        
        print("qr_data:", qr_data, file=sys.stderr)
        
        if not qr_data:
            response_data = {'success': False, 'message': 'No QR data provided'}
            print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
            return jsonify(response_data)
        
        # Decode QR data
        from .utils import decode_qr_code # Corrected import path
        decoded_data = decode_qr_code(qr_data)
        if not decoded_data:
            response_data = {'success': False, 'message': 'Invalid QR code format'}
            print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
            return jsonify(response_data)
        
        # Find the booking (allow only if not already consumed)
        conn = get_db_connection(False)
        cur = conn.cursor()
        # Normalize input for robust matching
        booking_id = decoded_data.get('booking_id')
        
        if not booking_id:
            response_data = {'success': False, 'message': 'Invalid QR code: booking_id is missing.'}
            print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
            return jsonify(response_data)
        
        try:
            # Fetch the specific booking using the unique booking_id
            cur.execute("""
                SELECT b.*, e.name as employee_name, e.employee_id, l.name as location_name
                FROM bookings b
                JOIN employees e ON b.employee_id = e.id
                JOIN locations l ON b.location_id = l.id
                WHERE b.id = %s
            """, (booking_id,))
            booking_to_process = cur.fetchone()
            
            if not booking_to_process:
                response_data = {'success': False, 'message': f'Booking with ID {booking_id} not found.'}
                print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
                return jsonify(response_data)
                
        except Exception as e:
            response_data = {'success': False, 'message': f'Database error: {str(e)}'}
            print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
            return jsonify(response_data)

        # Process the booking
        status = booking_to_process['status']
        if isinstance(status, bytes):
            status = status.decode('utf-8')
        
        print(f"[DEBUG] Booking ID: {booking_id}", file=sys.stderr)
        print(f"[DEBUG] Booking status: '{status}'", file=sys.stderr)
        print(f"[DEBUG] Status type: {type(status)}", file=sys.stderr)
        print(f"[DEBUG] Status stripped: '{status.strip()}'", file=sys.stderr)
        print(f"[DEBUG] Full booking data: {booking_to_process}", file=sys.stderr)
            
        if status.strip() == 'Consumed':
            # Format the consumed_at time for display
            consumed_time = booking_to_process.get('consumed_at')
            if consumed_time:
                if hasattr(consumed_time, 'strftime'):
                    processed_time = consumed_time.strftime('%d/%m/%Y, %I:%M:%S %p')
                else:
                    processed_time = str(consumed_time)
            else:
                processed_time = 'Unknown'
                
            response_data = {
                'success': False,  # Changed to False for already consumed
                'message': 'ℹ️ This meal has already been consumed.',
                'booking': {
                    'employee_name': booking_to_process['employee_name'],
                    'employee_id': booking_to_process['employee_id'],
                    'unit': booking_to_process['location_name'],
                    'date': booking_to_process['booking_date'].strftime('%Y-%m-%d'),
                    'shift': booking_to_process['shift'],
                    'status': status,
                    'processed_at': processed_time
                }
            }
            print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
            return jsonify(response_data)
        elif status.strip() != 'Booked':
            response_data = {
                'success': False,
                'message': 'Booking is not in a valid state for consumption.',
                'booking': {
                    'employee_name': booking_to_process['employee_name'],
                    'employee_id': booking_to_process['employee_id'],
                    'unit': booking_to_process['location_name'],
                    'date': booking_to_process['booking_date'].strftime('%Y-%m-%d'),
                    'shift': booking_to_process['shift'],
                    'status': booking_to_process['status']
                }
            }
            print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)

            cur.close()
            conn.close()
            return jsonify(response_data)
        
        # If we reach here, it means booking_to_process is 'Booked' and ready for consumption
        booking = booking_to_process # Assign to 'booking' for the rest of the function
        # Update booking status to consumed
        try:
            cur.execute("""
                UPDATE bookings 
                SET status = 'Consumed', consumed_at = NOW() 
                WHERE id = %s
            """, (booking['id'],))
            # Log the consumption
            cur.execute("""
                INSERT INTO meal_consumption_log (booking_id, employee_id, meal_id, location_id, staff_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (booking['id'], booking['employee_id'], booking['meal_id'], booking['location_id'], current_user.id))
            conn.commit() # Changed conn.commit() to conn.commit()
            response_data = {
                'success': True, 
                'message': f'✅ Meal Verified Successfully for {booking["employee_name"]} (Booking ID: {booking["id"]})',
                'booking': {
                    'employee_name': booking['employee_name'],
                    'employee_id': booking['employee_id'],
                    'unit': booking['location_name'],
                    'date': booking['booking_date'].strftime('%Y-%m-%d'),
                    'shift': booking['shift'],
                    'status': 'Consumed' # Explicitly set status for new consumption
                }
            }
            print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
            return jsonify(response_data)
        except Exception as e:
            tb = traceback.format_exc()
            if conn: # Ensure conn exists before attempting rollback
                conn.rollback() # Changed cur.rollback() to conn.rollback()
            response_data = {'success': False, 'message': f'Error processing meal: {str(e)}', 'trace': tb}
            print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
            return jsonify(response_data)
    except Exception as e:
        # Catch any unexpected errors and return a JSON response
        tb = traceback.format_exc()
        response_data = {
            'success': False,
            'message': f'An unexpected error occurred: {str(e)}',
            'trace': tb
        }
        print(f"[DEBUG] UNEXPECTED ERROR: {str(e)}", file=sys.stderr)
        print(f"[DEBUG] Full traceback: {tb}", file=sys.stderr)
        return jsonify(response_data), 500 # Return 500 status code for server errors
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@staff_bp.route('/dashboard')
@login_required
def dashboard():
    from . import mysql
    from datetime import date
    conn = get_db_connection()
    cur = conn.cursor()
    # Unit-wise meal data for charts (existing code)
    cur.execute('''
        SELECT l.name as location_name, COUNT(b.id) as meals_booked
        FROM bookings b
        JOIN locations l ON b.location_id = l.id
        GROUP BY l.name
        ORDER BY meals_booked DESC
    ''')
    unit_data = cur.fetchall()
    desired_order = ['Unit 1', 'Unit 2', 'Unit 3', 'Unit 4', 'Unit 5', 'Pallavaram']
    unit_map = {row['location_name']: row['meals_booked'] for row in unit_data}
    pie_labels = []
    pie_values = []
    for unit in desired_order:
        if unit in unit_map:
            pie_labels.append(unit)
            pie_values.append(unit_map[unit])
    for unit, count in unit_map.items():
        if unit not in desired_order:
            pie_labels.append(unit)
            pie_values.append(count)
    cur.execute('''
        SELECT l.name as location_name, b.shift, COUNT(b.id) as count
        FROM bookings b
        JOIN locations l ON b.location_id = l.id
        GROUP BY l.name, b.shift
        ''')
    breakdown_rows = cur.fetchall()
    meal_breakdown = {}
    for row in breakdown_rows:
        unit = row['location_name']
        shift = row['shift']
        count = row['count']
        if unit not in meal_breakdown:
            meal_breakdown[unit] = {'Breakfast': 0, 'Lunch': 0, 'Dinner': 0}
        meal_breakdown[unit][shift] = count
    # Daily summary data
    today = date.today()
    cur.execute('''
        SELECT b.shift, l.name as location, 
               SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as consumed,
               SUM(CASE WHEN b.status = 'Booked' THEN 1 ELSE 0 END) as booked
        FROM bookings b
        JOIN locations l ON b.location_id = l.id
        WHERE b.booking_date = %s
        GROUP BY b.shift, l.name
        ORDER BY b.shift, l.name
    ''', (today,))
    summary_data = cur.fetchall()
    # Monthly summary data
    first_day = today.replace(day=1)
    if today.month == 12:
        next_month = today.replace(year=today.year+1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month+1, day=1)
    last_day = next_month
    cur.execute('''
        SELECT b.shift, l.name as location, 
               SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as consumed,
               SUM(CASE WHEN b.status = 'Booked' THEN 1 ELSE 0 END) as booked
        FROM bookings b
        JOIN locations l ON b.location_id = l.id
        WHERE b.booking_date >= %s AND b.booking_date < %s
        GROUP BY b.shift, l.name
        ORDER BY b.shift, l.name
    ''', (first_day, last_day))
    monthly_summary_data = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('staff/dashboard.html', pie_labels=pie_labels, pie_values=pie_values, meal_breakdown=meal_breakdown, summary_data=summary_data, monthly_summary_data=monthly_summary_data)

@staff_bp.route('/summary')
@login_required
def summary():
    from . import mysql
    today = date.today()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT b.shift, l.name as location, 
               SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as consumed,
               SUM(CASE WHEN b.status = 'Booked' THEN 1 ELSE 0 END) as booked
        FROM bookings b
        JOIN locations l ON b.location_id = l.id
        WHERE b.booking_date = %s
        GROUP BY b.shift, l.name
        ORDER BY b.shift, l.name
    ''', (today,))
    summary_data = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('staff/summary.html', summary_data=summary_data)

@staff_bp.route('/summary/export')
@login_required
def export_summary_csv():
    from . import mysql
    import csv
    from io import StringIO
    from flask import Response
    today = date.today()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT b.shift, l.name as location, 
               SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as consumed,
               SUM(CASE WHEN b.status = 'Booked' THEN 1 ELSE 0 END) as booked
        FROM bookings b
        JOIN locations l ON b.location_id = l.id
        WHERE b.booking_date = %s
        GROUP BY b.shift, l.name
        ORDER BY b.shift, l.name
    ''', (today,))
    summary_data = cur.fetchall()
    # Prepare CSV
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Shift', 'Location', 'Consumed', 'Booked'])
    for row in summary_data:
        writer.writerow([row['shift'], row['location'], row['consumed'], row['booked']])
    output = si.getvalue()
    si.close()
    # Send as downloadable file
    cur.close()
    conn.close()
    return Response(
        output,
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment;filename=staff_daily_summary_{today}.csv'
        }
    )

@staff_bp.route('/monthly_summary')
@login_required
def monthly_summary():
    from datetime import date
    conn = get_db_connection()
    cur = conn.cursor()
    today = date.today()
    # Get the first and last day of the current month
    first_day = today.replace(day=1)
    if today.month == 12:
        next_month = today.replace(year=today.year+1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month+1, day=1)
    last_day = next_month
    cur.execute('''
        SELECT b.shift, l.name as location, 
               SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as consumed,
               SUM(CASE WHEN b.status = 'Booked' THEN 1 ELSE 0 END) as booked
        FROM bookings b
        JOIN locations l ON b.location_id = l.id
        WHERE b.booking_date >= %s AND b.booking_date < %s
        GROUP BY b.shift, l.name
        ORDER BY b.shift, l.name
    ''', (first_day, last_day))
    summary_data = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('staff/monthly_summary.html', summary_data=summary_data)

@staff_bp.route('/monthly_summary/export')
@login_required
def export_monthly_summary_csv():
    import csv
    from io import StringIO
    from flask import Response
    from datetime import date
    today = date.today()
    # Get the first and last day of the current month
    first_day = today.replace(day=1)
    if today.month == 12:
        next_month = today.replace(year=today.year+1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month+1, day=1)
    last_day = next_month
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT b.shift, l.name as location, 
               SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as consumed,
               SUM(CASE WHEN b.status = 'Booked' THEN 1 ELSE 0 END) as booked
        FROM bookings b
        JOIN locations l ON b.location_id = l.id
        WHERE b.booking_date >= %s AND b.booking_date < %s
        GROUP BY b.shift, l.name
        ORDER BY b.shift, l.name
    ''', (first_day, last_day))
    summary_data = cur.fetchall()
    # Prepare CSV
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Shift', 'Location', 'Consumed', 'Booked'])
    for row in summary_data:
        writer.writerow([row['shift'], row['location'], row['consumed'], row['booked']])
    output = si.getvalue()
    si.close()
    # Send as downloadable file
    cur.close()
    conn.close()
    return Response(
        output,
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment;filename=staff_monthly_summary_{today.strftime('%Y_%m')}.csv'
        }
    )

@staff_bp.route('/roles', methods=['GET', 'POST'])
@login_required
def manage_roles():
    # TODO: Role management for supervisors
    return render_template('staff/roles.html')
