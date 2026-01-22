from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import login_required, login_user, logout_user, current_user
from .forms import LoginForm
from .utils import decode_qr_code
from . import Curr_Proj_Name, mysql, User
from datetime import date
import sys
from .db_config import get_db_connection
from .employee import URL_Redirect_ConnClose
import hashlib
from datetime import date, timedelta, datetime
from .forms import AddMenuForm

staff_bp = Blueprint('staff', __name__)


@staff_bp.route('/add_menu', methods=['GET', 'POST'])
@login_required
def add_menu():
    # Allow only Staff role to add menus
    if current_user.role not in ['Staff', 'Supervisor']:
        flash('Access denied.', 'danger')
        return redirect(url_for('staff.dashboard'))

    form = AddMenuForm()
    # Set default date to tomorrow
    if request.method == 'GET':
        form.menu_date.data = date.today()
    conn = get_db_connection()
    cur = conn.cursor()

    # Populate location choices - Allow staff to see locations that have employees but no dedicated staff
    # First get the staff's assigned location
    if current_user.role in ['Staff', 'Supervisor'] and current_user.location:
        # Get all locations that have employees but may not have dedicated staff
        cur.execute("""
            SELECT DISTINCT l.id, l.name 
            FROM locations l
            INNER JOIN employees e ON l.id = e.location_id
            WHERE e.role_id = 1  -- Employee role
            ORDER BY l.name
        """)
        locations = cur.fetchall()
        form.location_id.choices = [(l['id'], l['name']) for l in locations]
        if locations:
            # Default to staff's assigned location if available in the list
            staff_location_exists = any(loc['name'] == current_user.location for loc in locations)
            if staff_location_exists:
                cur.execute("SELECT id FROM locations WHERE name = %s", (current_user.location,))
                staff_loc_result = cur.fetchone()
                if staff_loc_result:
                    form.location_id.data = staff_loc_result['id']
            elif locations:
                form.location_id.data = locations[0]['id']
    else:
        # For safety, if staff doesn't have a location assigned, deny access
        flash('Access denied: You are not assigned to a location.', 'danger')
        return redirect(url_for('staff.dashboard'))

    if form.validate_on_submit():
        location_id = form.location_id.data
        menu_date = form.menu_date.data
        meal_type = form.meal_type.data
        items = form.items.data

        # Check if a menu for this meal type, date, and location already exists
        cur.execute("SELECT id FROM daily_menus WHERE location_id = %s AND menu_date = %s AND meal_type = %s", (location_id, menu_date, meal_type))
        existing_menu = cur.fetchone()

        if existing_menu:
            flash(f'A menu for {meal_type} on {menu_date} for this location already exists.', 'warning')
            return redirect(url_for('staff.add_menu'))

        try:
            cur.execute("""
                INSERT INTO daily_menus (location_id, menu_date, meal_type, items)
                VALUES (%s, %s, %s, %s)
            """, (location_id, menu_date, meal_type, items))
            flash('Menu added successfully!', 'success')
            return redirect(url_for('staff.add_menu'))
        except Exception as e:
            flash(f'Error adding menu: {e}', 'danger')
    cur.close()
    conn.close()
    return render_template('staff/add_menu.html', form=form)


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
                # Flash message will appear on dashboard
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
    session['logout_message'] = 'Logged out successfully.'
    # Clear dashboard visited flag so login message appears again on next login
    session.pop('dashboard_visited', None)
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

@staff_bp.route('/clear_biometric_data', methods=['POST'])
@login_required
def clear_biometric_data():
    from .biometric_integration import clear_biometric_attendance
    try:
        success = clear_biometric_attendance()
        if success:
            return jsonify({'success': True, 'message': 'All attendance data cleared successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to clear attendance data'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error clearing data: {str(e)}'})


@staff_bp.route('/clear_old_punches', methods=['POST'])
@login_required
def clear_old_punches():
    from .biometric_integration import clear_old_punches_except_today
    try:
        success = clear_old_punches_except_today()
        if success:
            return jsonify({'success': True, 'message': 'Old punch data processed successfully (only today\'s punches remain)'})
        else:
            return jsonify({'success': False, 'message': 'Device does not support selective deletion. Only today\'s punches remain according to system records, but all punches are still stored on the device.'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error processing punches: {str(e)}'})


@staff_bp.route('/sync_biometric_users', methods=['POST'])
@login_required
def sync_biometric_users():
    from .biometric_integration import sync_cms_users_to_biometric
    try:
        success = sync_cms_users_to_biometric()
        if success:
            return jsonify({'success': True, 'message': 'Users synced successfully to biometric device'})
        else:
            return jsonify({'success': False, 'message': 'Failed to sync users to biometric device'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error syncing users: {str(e)}'})


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
            INSERT INTO bookings (employee_id, employee_id_str, meal_id, booking_date, shift, location_id, booking_type, status)
            SELECT e.id, e.employee_id, m.id, %s, 'Lunch', l.id, 'App', 'Booked'
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

# Biometric scan function for meal consumption
@staff_bp.route('/scan_biometric', methods=['POST'])
@login_required
def scan_biometric():
    from . import mysql
    import sys
    import traceback # Import traceback for detailed error logging
    
    # Initialize variables to prevent unbound errors
    conn = None
    cur = None
    
    try:
        print("=== SCAN_BIOMETRIC CALLED ===", file=sys.stderr)
        
        # Get biometric user ID from request
        biometric_data = request.json if request.is_json else request.form
        user_id = biometric_data.get('user_id') if biometric_data else None
        
        if not user_id:
            response_data = {'success': False, 'message': 'No biometric user ID provided'}
            print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
            return jsonify(response_data)
        
        # Find the employee in our system based on biometric ID
        conn = get_db_connection(False)
        cur = conn.cursor()
        
        # First, find the employee by matching the biometric user_id with employee_id
        cur.execute("SELECT id, name, employee_id FROM employees WHERE employee_id = %s", (str(user_id),))
        employee = cur.fetchone()
        
        if not employee:
            response_data = {'success': False, 'message': f'Employee with biometric ID {user_id} not found in system.'}
            print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
            return jsonify(response_data)
        
        employee_db_id = employee['id']
        employee_name = employee['name']
        employee_id = employee['employee_id']
        
        # Find today's booking for this employee that is still 'Booked'
        today = date.today()
        cur.execute("""
            SELECT b.*, m.name as meal_name, l.name as location_name
            FROM bookings b
            JOIN meals m ON b.meal_id = m.id
            JOIN locations l ON b.location_id = l.id
            WHERE b.employee_id = %s 
            AND b.booking_date = %s
            AND b.status = 'Booked'
            ORDER BY b.created_at DESC
        """, (employee_db_id, today))
        
        booking = cur.fetchone()
        
        if not booking:
            response_data = {
                'success': False,
                'message': f'{employee_name} (ID: {employee_id}) needs to book meals before consumption.',
                'booking': {
                    'employee_name': employee_name,
                    'employee_id': employee_id,
                    'date': today.strftime('%Y-%m-%d'),
                    'status': 'No Booking'
                }
            }
            print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
            return jsonify(response_data)
        
        # Process the booking
        status = booking['status']
        if isinstance(status, bytes):
            status = status.decode('utf-8')
        
        if status.strip() == 'Consumed':
            # Format the consumed_at time for display
            consumed_time = booking.get('consumed_at')
            if consumed_time:
                if hasattr(consumed_time, 'strftime'):
                    processed_time = consumed_time.strftime('%d/%m/%Y, %I:%M:%S %p')
                else:
                    processed_time = str(consumed_time)
            else:
                processed_time = 'Unknown'
            
            response_data = {
                'success': False,
                'message': 'ℹ️ This meal has already been consumed.',
                'booking': {
                    'employee_name': employee_name,
                    'employee_id': employee_id,
                    'unit': booking['location_name'],
                    'date': booking['booking_date'].strftime('%Y-%m-%d'),
                    'shift': booking['shift'],
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
                    'employee_name': employee_name,
                    'employee_id': employee_id,
                    'unit': booking['location_name'],
                    'date': booking['booking_date'].strftime('%Y-%m-%d'),
                    'shift': booking['shift'],
                    'status': booking['status']
                }
            }
            print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
            return jsonify(response_data)
        
        # Update booking status to consumed
        try:
            cur.execute("""
                UPDATE bookings 
                SET status = 'Consumed', consumed_at = NOW() 
                WHERE id = %s
            """, (booking['id'],))
            
            # Log the consumption
            staff_id_to_use = getattr(current_user, 'id', None) or employee_db_id
            cur.execute("""
                INSERT INTO meal_consumption_log (booking_id, employee_id, meal_id, location_id, staff_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (booking['id'], employee_db_id, booking['meal_id'], booking['location_id'], staff_id_to_use))
            
            conn.commit()
            
            response_data = {
                'success': True,
                'message': f'✅ Meal Consumed Successfully for {employee_name} (ID: {employee_id})',
                'booking': {
                    'employee_name': employee_name,
                    'employee_id': employee_id,
                    'unit': booking['location_name'],
                    'date': booking['booking_date'].strftime('%Y-%m-%d'),
                    'shift': booking['shift'],
                    'status': 'Consumed'
                }
            }
            print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
            return jsonify(response_data)
        
        except Exception as e:
            tb = traceback.format_exc()
            if conn:
                conn.rollback()
            response_data = {'success': False, 'message': f'Error processing meal: {str(e)}', 'trace': tb}
            print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
            return jsonify(response_data)
    
    except Exception as e:
        tb = traceback.format_exc()
        response_data = {
            'success': False,
            'message': f'An unexpected error occurred: {str(e)}',
            'trace': tb
        }
        print(f"[DEBUG] UNEXPECTED ERROR: {str(e)}", file=sys.stderr)
        print(f"[DEBUG] Full traceback: {tb}", file=sys.stderr)
        return jsonify(response_data), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@staff_bp.route('/scan_biometric_consumption', methods=['POST'])
@login_required
def scan_biometric_consumption():
    from . import mysql
    import sys
    import traceback
    from .biometric_integration import biometric_consumption
    from datetime import date
    
    # Initialize variables to prevent unbound errors
    conn = None
    cur = None
    
    try:
        print("=== SCAN_BIOMETRIC_CONSUMPTION CALLED ===", file=sys.stderr)
        
        # Get biometric user ID from request
        biometric_data = request.json if request.is_json else request.form
        user_id = biometric_data.get('user_id') if biometric_data else None
        
        if not user_id:
            response_data = {'success': False, 'message': 'No biometric user ID provided'}
            print(f"[DEBUG] JSON response: {response_data}", file=sys.stderr)
            return jsonify(response_data)
        
        # Check if staff has location assignment for cross-location consumption
        staff_location_id = None
        staff_id = current_user.id
        
        if current_user.location:
            # Get the location ID for staff's assigned location
            conn = get_db_connection(False)
            cur = conn.cursor()
            cur.execute("SELECT id FROM locations WHERE name = %s", (current_user.location,))
            staff_location = cur.fetchone()
            if staff_location:
                staff_location_id = staff_location['id']
        
        # Use the biometric consumption service to verify and process the meal consumption
        # Pass staff location and ID to allow cross-location consumption
        result = biometric_consumption.verify_consumption(user_id, staff_location_id=staff_location_id, staff_id=staff_id)
        print(f"[DEBUG] Consumption verification result: {result}", file=sys.stderr)
        
        # Update the result to indicate it came from biometric consumption verification
        if 'booking' in result:
            result['booking']['verification_method'] = 'biometric_consumption'
        
        return jsonify(result)
        
    except Exception as e:
        tb = traceback.format_exc()
        response_data = {
            'success': False,
            'message': f'An unexpected error occurred: {str(e)}',
            'trace': tb
        }
        print(f"[DEBUG] UNEXPECTED ERROR in consumption verification: {str(e)}", file=sys.stderr)
        print(f"[DEBUG] Full traceback: {tb}", file=sys.stderr)
        return jsonify(response_data), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


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
        print(f"[DEBUG] Current staff location: {current_user.location}", file=sys.stderr)
            
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
        
        # Check if staff can verify this booking at their location
        # If staff has a location assignment, allow verification at their location regardless of booking location
        booking_location_id = booking_to_process['location_id']
        booking_location_name = booking_to_process['location_name']
        staff_location_name = current_user.location
        
        # If staff has location assignment, use that location for verification
        # This allows cross-location consumption where an employee booked at one location
        # but consumes at another location where the staff is present
        verification_location_id = booking_location_id
        verification_location_name = booking_location_name
        
        if staff_location_name:
            # Get the location ID for staff's assigned location
            cur.execute("SELECT id FROM locations WHERE name = %s", (staff_location_name,))
            staff_location = cur.fetchone()
            if staff_location:
                verification_location_id = staff_location['id']
                verification_location_name = staff_location_name
        
        # If we reach here, it means booking_to_process is 'Booked' and ready for consumption
        booking = booking_to_process # Assign to 'booking' for the rest of the function
        # Update booking status to consumed
        try:
            cur.execute("""
                UPDATE bookings 
                SET status = 'Consumed', consumed_at = NOW() 
                WHERE id = %s
            """, (booking['id'],))
            # Log the consumption with verification location
            cur.execute("""
                INSERT INTO meal_consumption_log (booking_id, employee_id, meal_id, location_id, staff_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (booking['id'], booking['employee_id'], booking['meal_id'], verification_location_id, current_user.id))
            conn.commit() # Changed conn.commit() to conn.commit()
            response_data = {
                'success': True, 
                'message': f'✅ Meal Verified Successfully for {booking["employee_name"]} (Booking ID: {booking["id"]})',
                'booking': {
                    'employee_name': booking['employee_name'],
                    'employee_id': booking['employee_id'],
                    'unit': verification_location_name,  # Show the location where consumption happened
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
    # Show login success message on first visit to dashboard after login
    if not session.get('dashboard_visited'):
        flash('Login successful!', 'success')
        session['dashboard_visited'] = True
    else:
        # Reset the flag if we're navigating away and back to dashboard
        if request.args.get('reset_visited'):
            session['dashboard_visited'] = False
    
    from . import mysql
    from datetime import date
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if staff member has a specific location assignment
    staff_location_filter = ""
    staff_location_params = []
    
    if current_user.location:
        staff_location_filter = "WHERE l.name = %s"
        staff_location_params = [current_user.location]
    
    # Unit-wise meal data for charts (unit-specific for staff)
    query = f'''
        SELECT l.name as location_name, COUNT(b.id) as meals_booked
        FROM bookings b
        JOIN locations l ON b.location_id = l.id
        {staff_location_filter}
        GROUP BY l.name
        ORDER BY meals_booked DESC
    '''
    cur.execute(query, staff_location_params)
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
    # Apply same location filter for meal breakdown
    breakdown_query = f'''
        SELECT l.name as location_name, b.shift, COUNT(b.id) as count
        FROM bookings b
        JOIN locations l ON b.location_id = l.id
        {staff_location_filter}
        GROUP BY l.name, b.shift
        '''
    cur.execute(breakdown_query, staff_location_params)
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
    daily_summary_query = '''
        SELECT b.shift, l.name as location, 
               SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as consumed,
               SUM(CASE WHEN b.status = 'Booked' THEN 1 ELSE 0 END) as booked
        FROM bookings b
        JOIN locations l ON b.location_id = l.id
        {}
        GROUP BY b.shift, l.name
        ORDER BY b.shift, l.name
    '''
    # Combine location filter with date filter
    if staff_location_filter:
        # When staff_location_filter is "WHERE l.name = %s", we need to insert the date condition
        # Replace the WHERE with WHERE (condition) AND to add the date filter
        formatted_filter = staff_location_filter.replace("WHERE", "WHERE (") + " AND b.booking_date = %s)"
        final_daily_query = daily_summary_query.format(formatted_filter)
        cur.execute(final_daily_query, staff_location_params + [today])
    else:
        final_daily_query = daily_summary_query.format("WHERE b.booking_date = %s")
        cur.execute(final_daily_query, [today])
    summary_data = cur.fetchall()
    # Monthly summary data
    first_day = today.replace(day=1)
    if today.month == 12:
        next_month = today.replace(year=today.year+1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month+1, day=1)
    last_day = next_month
    monthly_summary_query = '''
        SELECT b.shift, l.name as location, 
               SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as consumed,
               SUM(CASE WHEN b.status = 'Booked' THEN 1 ELSE 0 END) as booked
        FROM bookings b
        JOIN locations l ON b.location_id = l.id
        {}
        GROUP BY b.shift, l.name
        ORDER BY b.shift, l.name
    '''
    # Combine location filter with date filter
    if staff_location_filter:
        # When staff_location_filter is "WHERE l.name = %s", we need to insert the date condition
        # Replace the WHERE with WHERE (condition) AND to add the date filter
        formatted_filter = staff_location_filter.replace("WHERE", "WHERE (") + " AND b.booking_date >= %s AND b.booking_date < %s)"
        final_monthly_query = monthly_summary_query.format(formatted_filter)
        cur.execute(final_monthly_query, staff_location_params + [first_day, last_day])
    else:
        final_monthly_query = monthly_summary_query.format("WHERE b.booking_date >= %s AND b.booking_date < %s")
        cur.execute(final_monthly_query, [first_day, last_day])
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
    
    # Check if staff member has a specific location assignment
    staff_location_filter = ""
    staff_location_params = []
    
    if current_user.location:
        staff_location_filter = "AND l.name = %s"
        staff_location_params = [current_user.location]
    
    summary_query = f'''
        SELECT b.shift, l.name as location, 
               SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as consumed,
               SUM(CASE WHEN b.status = 'Booked' THEN 1 ELSE 0 END) as booked
        FROM bookings b
        JOIN locations l ON b.location_id = l.id
        WHERE b.booking_date = %s {staff_location_filter}
        GROUP BY b.shift, l.name
        ORDER BY b.shift, l.name
    '''
    cur.execute(summary_query, [today] + staff_location_params)
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
    
    # Check if staff member has a specific location assignment
    staff_location_filter = ""
    staff_location_params = []
    
    if current_user.location:
        staff_location_filter = "AND l.name = %s"
        staff_location_params = [current_user.location]
    
    summary_query = f'''
        SELECT b.shift, l.name as location, 
               SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as consumed,
               SUM(CASE WHEN b.status = 'Booked' THEN 1 ELSE 0 END) as booked
        FROM bookings b
        JOIN locations l ON b.location_id = l.id
        WHERE b.booking_date = %s {staff_location_filter}
        GROUP BY b.shift, l.name
        ORDER BY b.shift, l.name
    '''
    cur.execute(summary_query, [today] + staff_location_params)
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
