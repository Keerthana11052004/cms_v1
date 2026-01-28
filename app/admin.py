import os
from flask import Blueprint, render_template, redirect, url_for, request, flash, send_file, make_response, current_app, send_from_directory, abort, session, jsonify
from flask_login import login_required, login_user, logout_user, current_user
from . import Curr_Proj_Name, mysql, User
import hashlib
from .forms import LoginForm, AddUserForm, EditUserForm, VendorForm, OutsiderMealVendorForm, AddMenuForm
import csv
import io
import pandas as pd
from MySQLdb import IntegrityError
from datetime import date, timedelta, datetime
from flask_wtf.csrf import generate_csrf
from werkzeug.utils import secure_filename
from .db_config import get_db_connection

admin_bp = Blueprint('admin', __name__)

# Register the blueprint with url_prefix in app/__init__.py, so no prefix here

# These will be initialized after the app context is available
UPLOAD_FOLDER = None
ALLOWED_EXTENSIONS = None

def init_admin_config(app):
    global UPLOAD_FOLDER, ALLOWED_EXTENSIONS
    UPLOAD_FOLDER = app.config['UPLOAD_FOLDER']
    ALLOWED_EXTENSIONS = app.config['ALLOWED_EXTENSIONS']

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT message_text FROM special_messages WHERE is_active = TRUE AND DATE(created_at) = CURDATE() ORDER BY created_at DESC LIMIT 1")
    special_message = cur.fetchone()
    if form.validate_on_submit():
        employee_id = form.employee_id.data
        password = form.password.data
        cur.execute("SELECT * FROM employees WHERE employee_id=%s AND role_id IN (3,6) AND is_active=1", (employee_id,))
        user = cur.fetchone()
        if user and password:
            import hashlib
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            if user['password_hash'] == password_hash or user['password_hash'] == password:
                # Set role based on role_id
                role = 'Master Admin' if user['role_id'] == 6 else 'Unit-wise Admin'
                # Get location name
                location = None
                if user['location_id']:
                    cur.execute("SELECT name FROM locations WHERE id = %s", (user['location_id'],))
                    location_row = cur.fetchone()
                    if location_row:
                        location = location_row['name']
                user_obj = User(user['id'], name=user['name'], email=user['email'], role=role, 
                              location=location, employee_id=user['employee_id'])
                login_user(user_obj)
                # Flash message will appear on dashboard
                return redirect(url_for('admin.dashboard'))
            else:
                flash('Invalid password.', 'danger')
        else:
            flash('Invalid employee ID or not an admin/accounts.', 'danger')
    cur.close()
    conn.close()
    return render_template('admin/login.html', form=form, special_message=special_message)

@admin_bp.route('/logout')
def logout():
    logout_user()
    session['logout_message'] = 'Logged out successfully.'
    # Clear dashboard visited flag so login message appears again on next login
    session.pop('dashboard_visited', None)
    return redirect(url_for('index'))

@admin_bp.route('/dashboard')
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
    today = date.today()
    first_day = today.replace(day=1)
    if today.month == 12:
        next_month = today.replace(year=today.year+1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month+1, day=1)
    last_day = next_month

    # Base query for bookings
    # Base query parts
    base_query_template = "FROM bookings WHERE booking_date >= %s AND booking_date < %s"
    base_query_shift_template = "FROM bookings WHERE status='Booked' AND booking_date >= %s AND booking_date < %s"
    base_query_trends_template = "FROM bookings WHERE booking_date >= CURDATE() - INTERVAL 6 DAY"

    # Parameters for each query
    params_total = [first_day, last_day]
    params_shift = [first_day, last_day]
    params_trends = []

    # Unit-wise access control
    location_filter_clause = ""
    if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
        # For master admin 'a001', show all unit data
        pass
    elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
        cur.execute("SELECT id FROM locations WHERE name = %s", (current_user.location,))
        location_id_row = cur.fetchone()
        if location_id_row:
            location_id = location_id_row['id']
            location_filter_clause = " AND location_id = %s"
            params_total.append(location_id)
            params_shift.append(location_id)
            params_trends.append(location_id)

    # Construct final queries
    total_bookings_query = "SELECT COUNT(*) AS total " + base_query_template + location_filter_clause
    consumed_query = "SELECT COUNT(*) AS consumed " + base_query_template + " AND status='Consumed'" + location_filter_clause
    booked_query = "SELECT COUNT(*) AS booked " + base_query_template + " AND status='Booked'" + location_filter_clause
    
    final_shift_query = "SELECT shift, COUNT(*) as count " + base_query_shift_template + location_filter_clause + " GROUP BY shift"
    final_trends_query = "SELECT booking_date, COUNT(*) as count " + base_query_trends_template + location_filter_clause + " GROUP BY booking_date ORDER BY booking_date"

    # Total bookings for current month
    cur.execute(total_bookings_query, tuple(params_total))
    total_bookings = cur.fetchone()['total']

    # Consumed meals for current month
    cur.execute(consumed_query, tuple(params_total))
    consumed_meals = cur.fetchone()['consumed']

    # Booked meals (not yet consumed) for current month
    cur.execute(booked_query, tuple(params_total))
    booked_meals = cur.fetchone()['booked']

    # Booked meals (not yet consumed) - separate by shift for current month
    cur.execute(final_shift_query, tuple(params_shift))
    booked_by_shift = {row['shift']: row['count'] for row in cur.fetchall()}
    booked_breakfast = booked_by_shift.get('Breakfast', 0)
    booked_lunch = booked_by_shift.get('Lunch', 0)
    booked_dinner = booked_by_shift.get('Dinner', 0)
    total_booked_meals_monthwise = booked_breakfast + booked_lunch + booked_dinner

    # Consumed meals - separate by shift for current month
    consumed_shift_query = "SELECT shift, COUNT(*) as count " + base_query_template + " AND status='Consumed'" + location_filter_clause + " GROUP BY shift"
    cur.execute(consumed_shift_query, tuple(params_shift))
    consumed_by_shift = {row['shift']: row['count'] for row in cur.fetchall()}
    consumed_breakfast = consumed_by_shift.get('Breakfast', 0)
    consumed_lunch = consumed_by_shift.get('Lunch', 0)
    consumed_dinner = consumed_by_shift.get('Dinner', 0)
    total_consumed_meals_monthwise = consumed_breakfast + consumed_lunch + consumed_dinner

    # Trends (last 7 days bookings)
    cur.execute(final_trends_query, tuple(params_trends))
    trends = cur.fetchall()

    # Query for month-wise booked and consumed meals for the last 12 months
    monthwise_query = """
        SELECT
            DATE_FORMAT(booking_date, '%%Y-%%m') AS month,
            shift,
            SUM(CASE WHEN status = 'Booked' THEN 1 ELSE 0 END) AS booked_count,
            SUM(CASE WHEN status = 'Consumed' THEN 1 ELSE 0 END) AS consumed_count
        FROM bookings
        WHERE booking_date >= CURDATE() - INTERVAL 12 MONTH
    """
    monthwise_params = []
    # Unit-wise access control
    if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
        pass  # Master admin sees all data
    elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
        cur.execute("SELECT id FROM locations WHERE name = %s", (current_user.location,))
        location_id_row = cur.fetchone()
        if location_id_row:
            location_id = location_id_row['id']
            monthwise_query += " AND location_id = %s"
            monthwise_params.append(location_id)

    monthwise_query += " GROUP BY month, shift ORDER BY month, shift"
    cur.execute(monthwise_query, tuple(monthwise_params))
    monthwise_data_raw = cur.fetchall()

    # Process monthwise data for Chart.js
    monthwise_data = {}
    for row in monthwise_data_raw:
        month = row['month']
        shift = row['shift']
        if month not in monthwise_data:
            monthwise_data[month] = {'Breakfast': {'booked': 0, 'consumed': 0},
                                     'Lunch': {'booked': 0, 'consumed': 0},
                                     'Dinner': {'booked': 0, 'consumed': 0}}
        monthwise_data[month][shift]['booked'] = row['booked_count']
        monthwise_data[month][shift]['consumed'] = row['consumed_count']

    cur.close()
    conn.close()

    month_label = today.strftime('%B %Y')
    return render_template('admin/dashboard.html',
        total_bookings=total_bookings,
        consumed_meals=consumed_meals,
        booked_meals=booked_meals,
        booked_breakfast=booked_breakfast,
        booked_lunch=booked_lunch,
        booked_dinner=booked_dinner,
        consumed_breakfast=consumed_breakfast,
        consumed_lunch=consumed_lunch,
        consumed_dinner=consumed_dinner,
        total_booked_meals_monthwise=total_booked_meals_monthwise,
        total_consumed_meals_monthwise=total_consumed_meals_monthwise,
        trends=trends,
        month_label=month_label,
        monthwise_data=monthwise_data, # Pass the new data
        csrf_token=generate_csrf()
    )

@admin_bp.route('/monthly_all_units_report')
@login_required
def monthly_all_units_report():
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        flash('Access denied: Only Admin users can view this report.', 'danger')
        return redirect(url_for('admin.dashboard'))

    # Only master admin (a001) can see all units report
    if current_user.employee_id != 'a001':
        flash('Access denied: Only Master Admin can view all units report.', 'danger')
        return redirect(url_for('admin.monthly_unit_report'))

    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # If no dates provided, default to current month
    if not start_date and not end_date:
        today = date.today()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        if today.month == 12:
            end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        end_date = end_date.strftime('%Y-%m-%d')

    query = '''
        SELECT
            l.name as location,
            COUNT(b.id) as total_bookings,
            SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as consumed_meals,
            SUM(CASE WHEN b.status = 'Booked' THEN 1 ELSE 0 END) as booked_meals
        FROM locations l
        LEFT JOIN employees e ON e.location_id = l.id
        LEFT JOIN bookings b ON b.employee_id = e.id
    '''
    params = []
    where_conditions = []

    if start_date:
        where_conditions.append('b.booking_date >= %s')
        params.append(start_date)
    
    if end_date:
        where_conditions.append('b.booking_date <= %s')
        params.append(end_date)
    
    if where_conditions:
        query += ' WHERE ' + ' AND '.join(where_conditions)
    
    query += '''
        GROUP BY l.id, l.name
        ORDER BY l.name
    '''
    
    cur.execute(query, tuple(params))
    monthly_reports = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('admin/monthly_all_units_report.html',
                           monthly_reports=monthly_reports,
                           start_date=start_date,
                           end_date=end_date)

@admin_bp.route('/monthly_unit_report')
@login_required
def monthly_unit_report():
    if current_user.role not in ['Master Admin', 'Unit-wise Admin'] or (current_user.employee_id != 'a001' and not current_user.location):
        flash('Access denied: Admin access required.', 'danger')
        return redirect(url_for('admin.dashboard'))

    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # If no dates provided, default to current month
    if not start_date and not end_date:
        today = date.today()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        if today.month == 12:
            end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        end_date = end_date.strftime('%Y-%m-%d')

    query = '''
        SELECT
            l.name as location,
            COUNT(b.id) as total_bookings,
            SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as consumed_meals,
            SUM(CASE WHEN b.status = 'Booked' THEN 1 ELSE 0 END) as booked_meals
        FROM locations l
        LEFT JOIN employees e ON e.location_id = l.id
        LEFT JOIN bookings b ON b.employee_id = e.id
        WHERE l.name = %s
    '''
    params = [current_user.location]
    where_conditions = []

    if start_date:
        where_conditions.append('b.booking_date >= %s')
        params.append(start_date)
    
    if end_date:
        where_conditions.append('b.booking_date <= %s')
        params.append(end_date)
    
    if where_conditions:
        query += ' AND ' + ' AND '.join(where_conditions)
    
    query += '''
        GROUP BY l.id, l.name
        ORDER BY l.name
    '''
    
    cur.execute(query, tuple(params))
    monthly_reports = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('admin/monthly_unit_report.html',
                           monthly_reports=monthly_reports,
                           start_date=start_date,
                           end_date=end_date,
                           unit_name=current_user.location)

@admin_bp.route('/daily_unit_report')
@login_required
def daily_unit_report():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get filter parameter
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # If no dates provided, default to current month
    if not start_date and not end_date:
        today = date.today()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        if today.month == 12:
            end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        end_date = end_date.strftime('%Y-%m-%d')

    query = '''
        SELECT
            l.name as location,
            COUNT(b.id) as total_bookings,
            SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as consumed_meals,
            SUM(CASE WHEN b.status = 'Booked' THEN 1 ELSE 0 END) as booked_meals
        FROM locations l
        LEFT JOIN employees e ON e.location_id = l.id
        LEFT JOIN bookings b ON b.employee_id = e.id
    '''
    params = []
    where_conditions = []

    if start_date:
        where_conditions.append('b.booking_date >= %s')
        params.append(start_date)
    
    if end_date:
        where_conditions.append('b.booking_date <= %s')
        params.append(end_date)

    # Unit-wise access control
    if current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
        where_conditions.append('l.name = %s')
        params.append(current_user.location)

    if where_conditions:
        query += ' WHERE ' + ' AND '.join(where_conditions)

    query += '''
        GROUP BY l.id, l.name
        ORDER BY l.name
    '''
    
    cur.execute(query, tuple(params))
    daily_reports = cur.fetchall()

    unit_name = current_user.location if current_user.location else "All Units"
    report_date_str = request.args.get('report_date')

    # If no date provided, default to today
    if not report_date_str:
        report_date = date.today()
    else:
        try:
            report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format. Please use YYYY-MM-DD.', 'danger')
            return redirect(url_for('admin.daily_unit_report'))

    query = '''
        SELECT
            l.name as location,
            COUNT(b.id) as total_bookings,
            SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as consumed_meals,
            SUM(CASE WHEN b.status = 'Booked' THEN 1 ELSE 0 END) as booked_meals
        FROM locations l
        LEFT JOIN employees e ON e.location_id = l.id
        LEFT JOIN bookings b ON b.employee_id = e.id
    '''
    
    params = []
    where_conditions = ['b.booking_date = %s']
    params.append(report_date)

    # All admin users can see all units
    # if current_user.role == 'Master Admin' and current_user.employee_id != 'a001' and current_user.location:
    #     where_conditions.append('l.name = %s')
    #     params.append(current_user.location)

    if where_conditions:
        query += ' WHERE ' + ' AND '.join(where_conditions)

    query += '''
        GROUP BY l.id, l.name
        ORDER BY l.name
    '''
    
    cur.execute(query, tuple(params))
    daily_reports = cur.fetchall()

    unit_name = "All Units"
    cur.close()
    conn.close()

    return render_template('admin/daily_unit_report.html',
                           daily_reports=daily_reports,
                           report_date=report_date.strftime('%Y-%m-%d'),
                           unit_name=unit_name)

@admin_bp.route('/api/booked_meals_by_shift')
@login_required
def api_booked_meals_by_shift():
    conn = get_db_connection()
    cur = conn.cursor()
    query = """
        SELECT
            shift,
            SUM(CASE WHEN status = 'Booked' THEN 1 ELSE 0 END) as booked_count,
            SUM(CASE WHEN status = 'Consumed' THEN 1 ELSE 0 END) as consumed_count
        FROM bookings
        WHERE 1=1
    """
    params = []
    # Unit-wise access control
    if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
        # For master admin 'a001', show all unit data
        pass
    elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
        cur.execute("SELECT id FROM locations WHERE name = %s", (current_user.location,))
        location_id = cur.fetchone()
        if location_id:
            params.append(location_id['id'])
            query += " AND location_id = %s"
    # All admin users can see all unit data
    # if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
    #     # For admin user 'a001', show all unit data
    #     pass
    # elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
    #     cur.execute("SELECT id FROM locations WHERE name = %s", (current_user.location,))
    #     location_id = cur.fetchone()
    #     if location_id:
    #         params.append(location_id['id'])
    #         query += " AND location_id = %s"
    query += " GROUP BY shift"
    cur.execute(query, tuple(params))
    data_by_shift = {row['shift']: {'booked': row['booked_count'], 'consumed': row['consumed_count']} for row in cur.fetchall()}
    
    total_booked = sum(item.get('booked', 0) for item in data_by_shift.values())
    total_consumed = sum(item.get('consumed', 0) for item in data_by_shift.values())

    cur.close()
    conn.close()

    return {
        'Breakfast': {'booked': data_by_shift.get('Breakfast', {}).get('booked', 0), 'consumed': data_by_shift.get('Breakfast', {}).get('consumed', 0)},
        'Lunch': {'booked': data_by_shift.get('Lunch', {}).get('booked', 0), 'consumed': data_by_shift.get('Lunch', {}).get('consumed', 0)},
        'Dinner': {'booked': data_by_shift.get('Dinner', {}).get('booked', 0), 'consumed': data_by_shift.get('Dinner', {}).get('consumed', 0)},
        'Total': {'booked': total_booked, 'consumed': total_consumed}
    }

@admin_bp.route('/employee_reports')
@login_required
def employee_reports():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 12  # Number of items per page (between 10-15)
    offset = (page - 1) * per_page
    
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Build the query with optional date filters
    query = '''
        SELECT e.name as employee, d.name as department, l.name as location, e.id as employee_id,
               COUNT(b.id) as meals_booked,
               SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as meals_consumed
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN locations l ON e.location_id = l.id
        LEFT JOIN bookings b ON e.id = b.employee_id
    '''
    
    count_query = '''
        SELECT COUNT(DISTINCT e.id) as count
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN locations l ON e.location_id = l.id
        LEFT JOIN bookings b ON e.id = b.employee_id
    '''
    
    params = []
    count_params = []
    where_conditions = []
    count_where_conditions = []

    # All admin users can see all unit data
    if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
        # For admin user 'a001', show all unit data
        pass
    elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
        cur.execute("SELECT id FROM locations WHERE name = %s", (current_user.location,))
        location_id = cur.fetchone()
        if location_id:
            where_conditions.append('e.location_id = %s')
            params.append(location_id['id'])
            count_where_conditions.append('e.location_id = %s')
            count_params.append(location_id['id'])
        else:
            # If location not found, return empty results
            return render_template('admin/employee_reports.html',
                                 employees=[],
                                 start_date=start_date,
                                 end_date=end_date,
                                 pagination=None)
    
    if start_date:
        where_conditions.append('b.booking_date >= %s')
        params.append(start_date)
        count_where_conditions.append('b.booking_date >= %s')
        count_params.append(start_date)
    
    if end_date:
        where_conditions.append('b.booking_date <= %s')
        params.append(end_date)
        count_where_conditions.append('b.booking_date <= %s')
        count_params.append(end_date)
    
    if where_conditions:
        query += ' WHERE ' + ' AND '.join(where_conditions)
    
    if count_where_conditions:
        count_query += ' WHERE ' + ' AND '.join(count_where_conditions)
    
    # Get total count for pagination
    cur.execute(count_query, tuple(count_params))
    total_count = cur.fetchone()['count']
    
    query += '''
        GROUP BY e.id, e.name, d.name, l.name
        ORDER BY e.name
        LIMIT %s OFFSET %s
    '''
    
    params.extend([per_page, offset])
    cur.execute(query, tuple(params))
    employees = cur.fetchall()
    
    # Calculate pagination info
    total_pages = (total_count + per_page - 1) // per_page
    
    # Create a pagination object with iter_pages method
    class Pagination:
        def __init__(self, page, pages, per_page, total, has_prev, has_next, prev_num, next_num):
            self.page = page
            self.pages = pages
            self.per_page = per_page
            self.total = total
            self.has_prev = has_prev
            self.has_next = has_next
            self.prev_num = prev_num
            self.next_num = next_num
        
        def iter_pages(self, left_edge=2, left_current=2, right_current=4, right_edge=2):
            # Generator to yield page numbers for pagination links
            last = 0
            for num in range(1, self.pages + 1):
                # Show first few pages
                if num <= left_edge or (num >= self.page - left_current and num <= self.page + right_current) or num > self.pages - right_edge:
                    if last + 1 != num:
                        yield None  # Ellipsis
                    yield num
                    last = num
    
    pagination = Pagination(
        page=page,
        pages=total_pages,
        per_page=per_page,
        total=total_count,
        has_prev=page > 1,
        has_next=page < total_pages,
        prev_num=page - 1 if page > 1 else None,
        next_num=page + 1 if page < total_pages else None
    )
    
    cur.close()
    conn.close()

    return render_template('admin/employee_reports.html', 
                         employees=employees, 
                         start_date=start_date, 
                         end_date=end_date,
                         pagination=pagination)

@admin_bp.route('/dept_location_reports')
@login_required
def dept_location_reports():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 12  # Number of items per page (between 10-15)
    offset = (page - 1) * per_page
    
    # Get filter parameters
    department_filter = request.args.get('department')
    location_filter = request.args.get('location')
    
    # Build the query to get department/location reports
    query = '''
        SELECT 
            d.name as department,
            l.name as location,
            COUNT(b.id) as meals_booked,
            SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as meals_consumed
        FROM departments d
        CROSS JOIN locations l
        LEFT JOIN employees e ON e.department_id = d.id AND e.location_id = l.id
        LEFT JOIN bookings b ON e.id = b.employee_id
    '''
    
    # Build the count query separately
    count_query = '''
        SELECT COUNT(*) as count
        FROM (
            SELECT d.id as dept_id, l.id as loc_id
            FROM departments d
            CROSS JOIN locations l
            LEFT JOIN employees e ON e.department_id = d.id AND e.location_id = l.id
            LEFT JOIN bookings b ON e.id = b.employee_id
    '''
    
    params = []
    count_params = []
    where_conditions = []
    count_where_conditions = []

    # All admin users can see all unit data
    # if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
    #     # For admin user 'a001', show all unit data
    #     pass
    # elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
    #     cur.execute("SELECT id FROM locations WHERE name = %s", (current_user.location,))
    #     location_id = cur.fetchone()
    #     if location_id:
    #         where_conditions.append('l.id = %s')
    #         params.append(location_id['id'])
    #         count_where_conditions.append('l.id = %s')
    #         count_params.append(location_id['id'])
    #     else:
    #         # If location not found, return empty results
    #         return render_template('admin/dept_location_reports.html',
    #                              reports=[],
    #                              departments=[],
    #                              locations=[],
    #                              selected_department=department_filter,
    #                              selected_location=location_filter,
    #                              pagination=None)
    
    if department_filter:
        where_conditions.append('d.name = %s')
        params.append(department_filter)
        count_where_conditions.append('d.name = %s')
        count_params.append(department_filter)
    
    if location_filter:
        where_conditions.append('l.name = %s')
        params.append(location_filter)
        count_where_conditions.append('l.name = %s')
        count_params.append(location_filter)
    
    if where_conditions:
        query += ' WHERE ' + ' AND '.join(where_conditions)
    
    if count_where_conditions:
        count_query += ' WHERE ' + ' AND '.join(count_where_conditions)
    
    # Complete the count query
    count_query += ' GROUP BY d.id, l.id ) as counted_table'
    
    query += '''
        GROUP BY d.id, l.id, d.name, l.name
        ORDER BY d.name, l.name
    '''
    
    # Get total count for pagination
    cur.execute(count_query, tuple(count_params))
    total_count = cur.fetchone()['count']
    
    # Add limit and offset for pagination
    query += ' LIMIT %s OFFSET %s'
    params.extend([per_page, offset])
    
    cur.execute(query, tuple(params))
    reports = cur.fetchall()
    
    # Get departments and locations for filter dropdowns
    cur.execute('SELECT name FROM departments ORDER BY name')
    departments = [row['name'] for row in cur.fetchall()]
    
    cur.execute('SELECT name FROM locations ORDER BY name')
    locations = [row['name'] for row in cur.fetchall()]
    
    # Calculate pagination info
    total_pages = (total_count + per_page - 1) // per_page
    
    # Create a pagination object with iter_pages method
    class Pagination:
        def __init__(self, page, pages, per_page, total, has_prev, has_next, prev_num, next_num):
            self.page = page
            self.pages = pages
            self.per_page = per_page
            self.total = total
            self.has_prev = has_prev
            self.has_next = has_next
            self.prev_num = prev_num
            self.next_num = next_num
        
        def iter_pages(self, left_edge=2, left_current=2, right_current=4, right_edge=2):
            # Generator to yield page numbers for pagination links
            last = 0
            for num in range(1, self.pages + 1):
                # Show first few pages
                if num <= left_edge or (num >= self.page - left_current and num <= self.page + right_current) or num > self.pages - right_edge:
                    if last + 1 != num:
                        yield None  # Ellipsis
                    yield num
                    last = num
    
    pagination = Pagination(
        page=page,
        pages=total_pages,
        per_page=per_page,
        total=total_count,
        has_prev=page > 1,
        has_next=page < total_pages,
        prev_num=page - 1 if page > 1 else None,
        next_num=page + 1 if page < total_pages else None
    )
    
    cur.close()
    conn.close()

    return render_template('admin/dept_location_reports.html', 
                         reports=reports,
                         departments=departments,
                         locations=locations,
                         selected_department=department_filter,
                         selected_location=location_filter,
                         pagination=pagination)

@admin_bp.route('/cost_subsidy')
@login_required
def cost_subsidy():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of items per page
    offset = (page - 1) * per_page
    
    cur.execute('SELECT d.name FROM employees e JOIN departments d ON e.department_id = d.id WHERE e.id = %s', (current_user.id,))
    dept = cur.fetchone()
    # Allow 'a001' to access Cost & Subsidy regardless of department
    if not (current_user.employee_id == 'a001' or current_user.role == 'Master Admin'):
        flash('Access denied: Only Master Admin can access Cost & Subsidy Analysis.', 'danger')
        return redirect(url_for('admin.dashboard'))

    employee_filter = request.args.get('employee', '').strip()
    department_filter = request.args.get('department', '').strip()
    location_filter = request.args.get('unit', '').strip()  # 'unit' in form, but use locations
    month_filter = request.args.get('month', '').strip()

    # Get all departments and locations for dropdowns
    cur.execute('SELECT name FROM departments ORDER BY name')
    departments = cur.fetchall()
    
    cur.execute('SELECT name FROM locations ORDER BY name')
    locations = cur.fetchall()

    # Get all available months for the filter dropdown (only from this year and past 5 years)
    current_year = datetime.now().year
    earliest_year = current_year - 4  # Last 5 years including current year
    cur.execute(f"""
        SELECT DISTINCT 
            DATE_FORMAT(booking_date, '%%Y-%%m') AS month_year,
            DATE_FORMAT(booking_date, '%%M %%Y') AS display_month
        FROM bookings 
        WHERE YEAR(booking_date) BETWEEN {earliest_year} AND {current_year}
        ORDER BY month_year DESC
    """)
    available_months_data = cur.fetchall()
    # Create lists for dropdown - value is YYYY-MM, display is Month Year
    available_months = [row['month_year'] for row in available_months_data]
    month_display_names = {row['month_year']: row['display_month'] for row in available_months_data}

    # Default to current month if no month filter is provided
    if not month_filter and available_months:
        month_filter = datetime.now().strftime('%Y-%m')
    elif not month_filter and not available_months:
        month_filter = datetime.now().strftime('%Y-%m') # Fallback if no bookings exist

    query = '''
        SELECT e.id, e.name AS employee, d.name AS department, l.name AS location,
               COUNT(b.id) AS meals_booked,
               SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) AS meals_consumed
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN locations l ON e.location_id = l.id
        LEFT JOIN bookings b ON e.id = b.employee_id
    '''
    count_query = '''
        SELECT COUNT(DISTINCT e.id) as count
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN locations l ON e.location_id = l.id
        LEFT JOIN bookings b ON e.id = b.employee_id
    '''
    params = []
    count_params = []
    where_clauses = []

    if employee_filter:
        where_clauses.append('e.name LIKE %s')
        params.append(f"%{employee_filter}%")
        count_params.append(f"%{employee_filter}%")
    if department_filter:
        where_clauses.append('d.name = %s')
        params.append(department_filter)
        count_params.append(department_filter)
    if location_filter:
        where_clauses.append('l.name = %s')
        params.append(location_filter)
        count_params.append(location_filter)
    if month_filter:
        where_clauses.append("DATE_FORMAT(b.booking_date, '%%Y-%%m') = %s")
        params.append(month_filter)
        count_params.append(month_filter)

    if where_clauses:
        query += ' WHERE ' + ' AND '.join(where_clauses)
        count_query += ' WHERE ' + ' AND '.join(where_clauses)
    
    # Get total count for pagination
    cur.execute(count_query, count_params)
    total_count = cur.fetchone()['count']
    
    # Add ordering, grouping and limit for pagination
    query += ' GROUP BY e.id, e.name, d.name, l.name ORDER BY e.name LIMIT %s OFFSET %s'
    params.extend([per_page, offset])
    
    cur.execute(query, params)
    rows = cur.fetchall()
    
    # Calculate pagination info
    total_pages = (total_count + per_page - 1) // per_page
    pagination = {
        'page': page,
        'pages': total_pages,
        'per_page': per_page,
        'total': total_count,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1 if page > 1 else None,
        'next_num': page + 1 if page < total_pages else None
    }
    
    meal_price = 20
    cost_subsidy_data = []
    for row in rows:
        meals_booked = row['meals_booked'] or 0
        meals_consumed = row['meals_consumed'] or 0
        total_cost_booked = meals_booked * meal_price
        total_cost_consumed = meals_consumed * meal_price # Assuming subsidy is based on consumed meals

        cost_subsidy_data.append({
            'employee': row['employee'],
            'department': row['department'] or 'N/A',
            'unit': row['location'] or 'N/A',
            'meals_booked': meals_booked,
            'meals_consumed': meals_consumed,
            'total_cost_booked': total_cost_booked,
            'total_cost_consumed': total_cost_consumed
        })
    cur.close()
    conn.close()
    return render_template('admin/cost_subsidy.html',
                           cost_subsidy_data=cost_subsidy_data,
                           departments=departments,
                           units=locations,
                           available_months=available_months,
                           month_display_names=month_display_names,
                           selected_month=month_filter,
                           pagination=pagination)

@admin_bp.route('/export_cost_subsidy')
@login_required
def export_cost_subsidy():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT d.name FROM employees e JOIN departments d ON e.department_id = d.id WHERE e.id = %s', (current_user.id,))
    dept = cur.fetchone()
    # Allow 'a001' to export Cost & Subsidy regardless of department
    if not (current_user.employee_id == 'a001' or current_user.role == 'Master Admin'):
        flash('Access denied: Only Master Admin can access Cost & Subsidy Analysis.', 'danger')
        return redirect(url_for('admin.dashboard'))

    employee_filter = request.args.get('employee', '').strip()
    department_filter = request.args.get('department', '').strip()
    location_filter = request.args.get('unit', '').strip()
    
    query = '''
        SELECT e.id, e.name AS employee, d.name AS department, l.name AS location, COUNT(b.id) AS total_meals
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN locations l ON e.location_id = l.id
        LEFT JOIN bookings b ON e.id = b.employee_id AND b.status = 'Consumed'
    '''
    params = []
    where_clauses = []
    if employee_filter:
        where_clauses.append('e.name LIKE %s')
        params.append(f"%{employee_filter}%")
    if department_filter:
        where_clauses.append('d.name = %s')
        params.append(department_filter)
    if location_filter:
        where_clauses.append('l.name = %s')
        params.append(location_filter)
    if where_clauses:
        query += ' WHERE ' + ' AND '.join(where_clauses)
    query += ' GROUP BY e.id, e.name, d.name, l.name ORDER BY e.name'
    cur.execute(query, params)
    rows = cur.fetchall()
    meal_price = 20
    import csv, io
    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(['Employee', 'Department', 'Unit', 'Total Cost', 'Company Subsidy', 'Employee Contribution'])
    for row in rows:
        total_meals = row['total_meals'] or 0
        total_cost = total_meals * meal_price
        company_subsidy = 0
        employee_contribution = total_cost
        writer.writerow([
            row['employee'],
            row['department'] or 'N/A',
            row['location'] or 'N/A',
            total_cost,
            company_subsidy,
            employee_contribution
        ])
    output = si.getvalue()
    from flask import make_response
    response = make_response(output)
    response.headers['Content-Disposition'] = 'attachment; filename=cost_subsidy.csv'
    response.headers['Content-type'] = 'text/csv'
    cur.close()
    conn.close()
    return response



@admin_bp.route('/vendor_report_unit_wise')
@login_required
def vendor_report_unit_wise():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of items per page
    offset = (page - 1) * per_page
    
    query = "SELECT visitor_name as vendor_name, unit, purpose, count FROM outsider_meals"
    count_query = "SELECT COUNT(*) as count FROM outsider_meals"
    params = []
    count_params = []
    where_conditions = []

    # Unit-wise access control
    if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
        # For admin user 'a001', show all unit data
        pass
    elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
        where_conditions.append('unit = %s')
        params.append(current_user.location)
        count_params.append(current_user.location)
    
    if where_conditions:
        query += ' WHERE ' + ' AND '.join(where_conditions)
        count_query += ' WHERE ' + ' AND '.join(where_conditions)
    
    # Get total count for pagination
    cur.execute(count_query, tuple(count_params))
    total_count = cur.fetchone()['count']
    
    # Add ordering and limit for pagination
    query += " ORDER BY visitor_name LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
    
    cur.execute(query, tuple(params))
    vendor_reports = cur.fetchall()
    
    # Calculate pagination info
    total_pages = (total_count + per_page - 1) // per_page
    pagination = {
        'page': page,
        'pages': total_pages,
        'per_page': per_page,
        'total': total_count,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1 if page > 1 else None,
        'next_num': page + 1 if page < total_pages else None
    }
    
    cur.execute('SELECT name FROM locations ORDER BY name')
    units = [row['name'] for row in cur.fetchall()]
    cur.execute('SELECT DISTINCT purpose FROM outsider_meals WHERE purpose IS NOT NULL AND purpose != "" ORDER BY purpose')
    purposes = [row['purpose'] for row in cur.fetchall()]
    
    # Add default purpose choices if none exist in database
    default_purposes = ['Breakfast', 'Lunch', 'Dinner', 'Snacks', 'Beverages', 'Other']
    all_purposes = list(set(purposes + default_purposes))  # Combine and remove duplicates
    all_purposes.sort()  # Sort alphabetically
    
    form = OutsiderMealVendorForm()
    form.unit.choices = [(unit, unit) for unit in units]
    form.purpose.choices = [(purpose, purpose) for purpose in all_purposes]
    cur.close()
    conn.close()
    return render_template('admin/vendor_report_unit_wise.html',
                         vendor_reports=vendor_reports,
                         units=units,
                         purposes=all_purposes,
                         selected_unit=None,
                         selected_purpose=None,
                         form=form,
                         pagination=pagination)

@admin_bp.route('/vendor_report')
@login_required
def vendor_report():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of items per page
    offset = (page - 1) * per_page
    
    purpose_filter = request.args.get('purpose')
    unit_filter = request.args.get('unit')

    query = "SELECT name as vendor_name, unit, food_licence_path, agreement_date FROM vendors WHERE (food_licence_path IS NOT NULL OR agreement_date IS NOT NULL)"
    count_query = "SELECT COUNT(*) as count FROM vendors WHERE (food_licence_path IS NOT NULL OR agreement_date IS NOT NULL)"
    params = []
    count_params = []
    where_conditions = []

    # Unit-wise access control
    if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
        # For master admin 'a001', show all unit data
        pass
    elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
        where_conditions.append('unit = %s')
        params.append(current_user.location)
        count_params.append(current_user.location)
        # If a unit admin, and a unit filter is provided, ensure it matches their unit
        if unit_filter and unit_filter != current_user.location:
            flash('Access denied: You can only view reports for your assigned unit.', 'danger')
            return redirect(url_for('admin.dashboard'))
        unit_filter = current_user.location # Ensure the filter is set to their unit

    if purpose_filter:
        where_conditions.append('purpose = %s')
        params.append(purpose_filter)
        count_params.append(purpose_filter)
    
    # Unit-wise access control - apply unit filter only if not already applied by unit admin logic
    if unit_filter and not (current_user.role == 'Master Admin' and current_user.location and unit_filter == current_user.location):
        where_conditions.append('unit = %s')
        params.append(unit_filter)
        count_params.append(unit_filter)

    if where_conditions:
        query += ' AND ' + ' AND '.join(where_conditions)
        count_query += ' AND ' + ' AND '.join(where_conditions)
    
    # Get total count for pagination
    cur.execute(count_query, tuple(count_params))
    total_count = cur.fetchone()['count']
    
    # Add ordering and limit for pagination
    query += " ORDER BY name LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
    
    cur.execute(query, tuple(params))
    vendor_reports_raw = cur.fetchall()
    
    # Calculate pagination info
    total_pages = (total_count + per_page - 1) // per_page
    pagination = {
        'page': page,
        'pages': total_pages,
        'per_page': per_page,
        'total': total_count,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1 if page > 1 else None,
        'next_num': page + 1 if page < total_pages else None
    }
    
    vendor_reports = []
    for report in vendor_reports_raw:
        agreement_date = report['agreement_date']
        remaining_days = None
        if agreement_date:
            remaining_days = (agreement_date + timedelta(days=30) - date.today()).days
        
        vendor_reports.append({
            'vendor_name': report['vendor_name'],
            'unit': report['unit'],
            'food_licence_path': report['food_licence_path'],
            'agreement_date': agreement_date,
            'remaining_days': remaining_days
        })

    cur.execute('SELECT name FROM locations ORDER BY name')
    units = [row['name'] for row in cur.fetchall()]
    cur.execute('SELECT DISTINCT purpose FROM vendors WHERE purpose IS NOT NULL AND purpose != "" ORDER BY purpose')
    purposes = [row['purpose'] for row in cur.fetchall()]
    cur.close()
    conn.close()

    return render_template('admin/vendor_report.html',
                         vendor_reports=vendor_reports,
                         units=units,
                         purposes=purposes,
                         selected_unit=unit_filter,
                         selected_purpose=purpose_filter,
                         csrf_token=generate_csrf(),
                         pagination=pagination)

# Route for adding/editing outsider meal data
@admin_bp.route('/add_outsider_meal', methods=['GET', 'POST'])
@login_required
def add_outsider_meal():
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    form = OutsiderMealVendorForm()
    populate_outsider_meal_form_choices(form)
    
    if form.validate_on_submit():
        visitor_name = form.name.data
        unit = form.unit.data
        purpose = form.purpose.data
        count = 1  # Default count
        
        conn = None
        cur = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Check if outsider meal already exists
            cur.execute('SELECT id FROM outsider_meals WHERE visitor_name = %s', (visitor_name,))
            existing_outsider_meal = cur.fetchone()
            if existing_outsider_meal:
                flash('An outsider meal with this name already exists. Please use a unique name.', 'danger')
            else:
                cur.execute('''
                    INSERT INTO outsider_meals (visitor_name, unit, purpose, count)
                    VALUES (%s, %s, %s, %s)
                ''', (visitor_name, unit, purpose, count))
                conn.commit()
                flash('Outsider meal added successfully!', 'success')
                return redirect(url_for('admin.vendor_report_unit_wise'))
        except IntegrityError as e:
            if e.args[0] == 1062:
                flash('An outsider meal with this name already exists. Please use a unique name.', 'danger')
            else:
                flash('Database error: ' + str(e), 'danger')
            if conn:
                conn.rollback()
        except Exception as e:
            flash(f'Error processing outsider meal: {e}', 'danger')
            if conn:
                conn.rollback()
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()
    
    populate_outsider_meal_form_choices(form)
    return render_template('admin/add_outsider_meal.html', form=form, csrf_token=generate_csrf())


def populate_outsider_meal_form_choices(form):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get units
    cur.execute('SELECT name FROM locations ORDER BY name')
    units = [row['name'] for row in cur.fetchall()]
    form.unit.choices = [(unit, unit) for unit in units]
    
    # Get default purposes
    default_purposes = ['Breakfast', 'Lunch', 'Dinner', 'Snacks', 'Beverages', 'Other']
    cur.execute('SELECT DISTINCT purpose FROM outsider_meals WHERE purpose IS NOT NULL AND purpose != "" ORDER BY purpose')
    db_purposes = [row['purpose'] for row in cur.fetchall()]
    all_purposes = list(set(default_purposes + db_purposes))
    all_purposes.sort()
    form.purpose.choices = [(purpose, purpose) for purpose in all_purposes]
    
    cur.close()
    conn.close()


@admin_bp.route('/update_vendor_details', methods=['POST'])
@login_required
def update_vendor_details():
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.dashboard'))

    vendor_name = request.form.get('vendor_name')
    agreement_date_str = request.form.get('agreement_date')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Update agreement date
    if agreement_date_str:
        try:
            agreement_date = datetime.strptime(agreement_date_str, '%Y-%m-%d').date()
            cur.execute("UPDATE vendors SET agreement_date = %s WHERE name = %s", (agreement_date, vendor_name))
            flash('Agreement date updated successfully.', 'success')
        except ValueError:
            flash('Invalid date format. Please use YYYY-MM-DD.', 'danger')
        except Exception as e:
            flash(f'Error updating agreement date: {e}', 'danger')

    # Handle file upload
    if 'food_licence' in request.files:
        file = request.files['food_licence']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Store path relative to the static folder
            relative_file_path = os.path.join('uploads/food_licences', filename).replace('\\', '/')
            if UPLOAD_FOLDER:
                full_file_path = os.path.join(UPLOAD_FOLDER, filename)
                
                # Ensure the directory exists
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                
                file.save(full_file_path)
            
            # Update database with file path
            cur.execute("UPDATE vendors SET food_licence_path = %s WHERE name = %s", (relative_file_path, vendor_name))
            flash('Food licence uploaded successfully.', 'success')
        elif file.filename:
            flash('Invalid file type. Only PDF files are allowed.', 'danger')

    cur.close()
    conn.close()
    return redirect(url_for('admin.vendor_report', vendor_name=vendor_name))

@admin_bp.route('/delete_vendor', methods=['POST'])
@login_required
def delete_vendor():
    try:
        if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
            flash('Access denied.', 'danger')
            return redirect(url_for('admin.dashboard'))

        vendor_name = request.form.get('vendor_name')
        print(f"[DEBUG] Delete vendor request for: {vendor_name}")
        
        if not vendor_name:
            flash('Vendor name is required.', 'danger')
            return redirect(url_for('admin.vendor_report'))
    except Exception as e:
        print(f"[DEBUG] Error in delete_vendor: {e}")
        flash('An error occurred while processing the request.', 'danger')
        return redirect(url_for('admin.vendor_report'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Check if vendor exists
        cur.execute("SELECT id FROM vendors WHERE name = %s", (vendor_name,))
        vendor = cur.fetchone()
        
        if not vendor:
            flash(f'Vendor "{vendor_name}" not found.', 'danger')
            return redirect(url_for('admin.vendor_report'))
        
        # Delete vendor from database
        cur.execute("DELETE FROM vendors WHERE name = %s", (vendor_name,))
        conn.commit()
        
        flash(f'Vendor "{vendor_name}" deleted successfully.', 'success')
        
    except Exception as e:
        flash(f'Error deleting vendor: {e}', 'danger')
        conn.rollback()
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('admin.vendor_report'))

@admin_bp.route('/update_vendor_report_unit_wise', methods=['POST'])
@login_required
def update_vendor_report_unit_wise():
    form = OutsiderMealVendorForm()
    conn = None
    cur = None
    try:
        if form.validate_on_submit() or request.form.get('name'):
            vendor_name = form.name.data or request.form.get('name')
            purpose = form.purpose.data or request.form.get('purpose')
            unit = request.form.get('unit')
            count = request.form.get('count')
            original_vendor_name = request.form.get('original_vendor_name')
            is_outsider_meal = request.form.get('is_outsider_meal') == 'true'
            
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Add a prefix or tag to distinguish outsider meals if needed
            if is_outsider_meal and purpose and not purpose.startswith('Outsider:'):
                purpose = f'Outsider: {purpose}'
            
            if original_vendor_name:
                # Update existing outsider meal record
                cur.execute('''
                    UPDATE outsider_meals
                    SET visitor_name = %s, purpose = %s, unit = %s, count = %s
                    WHERE visitor_name = %s
                ''', (vendor_name, purpose, unit, count, original_vendor_name))
            else:
                # Check if outsider meal already exists before inserting
                cur.execute('SELECT id FROM outsider_meals WHERE visitor_name = %s', (vendor_name,))
                existing_outsider_meal = cur.fetchone()
                if existing_outsider_meal:
                    flash('An outsider meal with this name already exists. Please use a unique name.', 'danger')
                    return redirect(url_for('admin.vendor_report_unit_wise'))
                
                cur.execute('''
                    INSERT INTO outsider_meals (visitor_name, unit, purpose, count)
                    VALUES (%s, %s, %s, %s)
                ''', (vendor_name, unit, purpose, count))
            conn.commit()
            flash('Outsider meal added successfully.', 'success')
            return redirect(url_for('admin.vendor_report_unit_wise', unit=unit))
        else:
            flash('Form validation failed. Please check your input.', 'danger')
    except IntegrityError as e:
        if e.args[0] == 1062:
            flash('A vendor with this name already exists. Please use a unique vendor name.', 'danger')
        else:
            flash('Database error: ' + str(e), 'danger')
    except Exception as e:
        flash(f'Error processing outsider meal: {e}', 'danger')
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.vendor_report_unit_wise'))

@admin_bp.route('/export_vendor_report_unit_wise')
@login_required
def export_vendor_report_unit_wise():
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    # Get filter parameters
    unit_filter = request.args.get('unit')
    purpose_filter = request.args.get('purpose')
    
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    
        # Build the query to get vendor report by units
        query = '''
            SELECT 
                v.name as vendor_name,
                l.name as unit,
                v.purpose,
                COUNT(DISTINCT b.id) as count
            FROM vendors v
            CROSS JOIN locations l
            LEFT JOIN bookings b ON b.location_id = l.id
            LEFT JOIN employees e ON b.employee_id = e.id AND e.location_id = l.id
        '''
        
        params = []
        where_conditions = []
        
        if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
            # For admin user 'a001', show all unit data
            pass
        elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
            where_conditions.append('l.name = %s')
            params.append(current_user.location)
        
        if unit_filter:
            where_conditions.append('l.name = %s')
            params.append(unit_filter)
        
        if purpose_filter:
            where_conditions.append('v.purpose LIKE %s')
            params.append(f'%{purpose_filter}%')
        
        if where_conditions:
            query += ' WHERE ' + ' AND '.join(where_conditions)
        
        # Only include outsider meals for this report
        if 'WHERE' not in query:
            query += ' WHERE v.purpose LIKE %s'
            params.append('Outsider:%')
        else:
            query += ' AND v.purpose LIKE %s'
            params.append('Outsider:%')
        
        query += '''
            GROUP BY v.id, l.id, v.name, l.name, v.purpose
            ORDER BY l.name, v.name
        '''
        
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        
        # Create Excel file in memory
        df = pd.DataFrame(rows)
        
        # Rename columns for better readability
        df.columns = ['Vendor Name', 'Unit', 'Purpose', 'Count']
        
        # Create Excel file
        import tempfile
        import os
        # Create a temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
        temp_file.close()
        
        try:
            with pd.ExcelWriter(temp_file.name, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='Vendor Report', index=False)
                
                # Get the workbook and worksheet objects
                workbook = writer.book
                worksheet = writer.sheets['Vendor Report']
                
                # Define formats
                header_format = workbook.add_format({
                    'bold': True,
                    'text_wrap': True,
                    'valign': 'top',
                    'fg_color': '#D7E4BC',
                    'border': 1
                })
                
                # Apply header format
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                
                # Set column widths
                worksheet.set_column('A:A', 25)  # Vendor Name
                worksheet.set_column('B:B', 15)  # Unit
                worksheet.set_column('C:C', 20)  # Purpose
                worksheet.set_column('D:D', 10)  # Count
            
            # Read the file content
            with open(temp_file.name, 'rb') as f:
                file_content = f.read()
        finally:
            # Clean up the temporary file
            os.unlink(temp_file.name)
        
        # Create response
        response = make_response(file_content)
        response.headers['Content-Disposition'] = 'attachment; filename=vendor_report.xlsx'
        response.headers['Content-type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()



@admin_bp.route('/export')
@login_required
def export():
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of items per page
    offset = (page - 1) * per_page
    
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    location = request.args.get('location')
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = '''
        SELECT e.name as employee, d.name as department, l.name as location, b.booking_date, b.shift, b.status
        FROM bookings b
        JOIN employees e ON b.employee_id = e.id
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN locations l ON b.location_id = l.id
        WHERE 1=1
    '''
    count_query = '''
        SELECT COUNT(*) as count
        FROM bookings b
        JOIN employees e ON b.employee_id = e.id
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN locations l ON b.location_id = l.id
        WHERE 1=1
    '''
    params = []
    count_params = []  # Define count_params
    # Unit-wise access control
    if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
        # Master admin sees all data
        pass
    elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
        # Unit admin restricted to their location
        query += ' AND l.name = %s'
        count_query += ' AND l.name = %s'
        params.append(current_user.location)
        count_params.append(current_user.location)
        
        if start_date:
            query += ' AND b.booking_date >= %s'
            count_query += ' AND b.booking_date >= %s'
            params.append(start_date)
            count_params.append(start_date)
        if end_date:
            query += ' AND b.booking_date <= %s'
            count_query += ' AND b.booking_date <= %s'
            params.append(end_date)
            count_params.append(end_date)
        if department:
            query += ' AND d.name = %s'
            count_query += ' AND d.name = %s'
            params.append(department)
            count_params.append(department)
        if location:
            # Additional location filter (but unit admin can only filter within their unit)
            if current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
                # Unit admin - ensure location filter matches their unit
                if location != current_user.location:
                    flash('Access denied: You can only export data for your assigned unit.', 'danger')
                    return redirect(url_for('admin.export'))
            query += ' AND l.name = %s'
            count_query += ' AND l.name = %s'
            params.append(location)
            count_params.append(location)
    
    # Get total count for pagination
    cur.execute(count_query, tuple(count_params))
    total_count = cur.fetchone()['count']
    
    # Add ordering and limit for pagination
    query += ' ORDER BY b.booking_date DESC LIMIT %s OFFSET %s'
    params.extend([per_page, offset])
    
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    
    # Calculate pagination info
    total_pages = (total_count + per_page - 1) // per_page
    pagination = {
        'page': page,
        'pages': total_pages,
        'per_page': per_page,
        'total': total_count,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1 if page > 1 else None,
        'next_num': page + 1 if page < total_pages else None
    }
    
    cur.close()
    conn.close()
    return render_template('admin/export.html',
        rows=rows,
        start_date=start_date,
        end_date=end_date,
        department=department,
        location=location,
        pagination=pagination
    )

@admin_bp.route('/export_employee_report')
@login_required
def export_employee_report():
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Build the query with optional date filters
    query = '''
        SELECT e.name as employee, d.name as department, 
               COUNT(b.id) as meals_booked,
               SUM(CASE WHEN b.status = 'Consumed' THEN 1 ELSE 0 END) as meals_consumed
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN bookings b ON e.id = b.employee_id
    '''
    
    params = []
    where_conditions = []
    
    # Unit-wise access control
    if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
        # For admin user 'a001', show all unit data
        pass
    elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
        where_conditions.append('e.location_id = (SELECT id FROM locations WHERE name = %s)')
        params.append(current_user.location)
    
    if start_date:
        where_conditions.append('b.booking_date >= %s')
        params.append(start_date)
    
    if end_date:
        where_conditions.append('b.booking_date <= %s')
        params.append(end_date)
    
    if where_conditions:
        query += ' WHERE ' + ' AND '.join(where_conditions)
    
    query += '''
        GROUP BY e.id, d.name
        ORDER BY e.name
    '''
    
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    
    # Create CSV in memory
    output = []
    header = ['Employee', 'Department', 'Meals Booked', 'Meals Consumed']
    if start_date or end_date:
        header.append('Date Range')
    output.append(header)
    
    for row in rows:
        csv_row = [
            row['employee'],
            row['department'],
            row['meals_booked'],
            row['meals_consumed']
        ]
        if start_date or end_date:
            date_range = f"{start_date or 'All'} to {end_date or 'All'}"
            csv_row.append(date_range)
        output.append(csv_row)
    
    # Convert to CSV string
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerows(output)
    response = make_response(si.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=employee_report.csv'
    response.headers['Content-type'] = 'text/csv'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    cur.close()
    conn.close()
    return response

@admin_bp.route('/export_meal_excel')
@login_required
def export_meal_excel():
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.export'))
    # Get filters from request.args
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    location = request.args.get('location')
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        query = '''
            SELECT e.name as employee, d.name as department, l.name as location, b.booking_date, b.shift, b.status
            FROM bookings b
            JOIN employees e ON b.employee_id = e.id
            LEFT JOIN departments d ON e.department_id = d.id
            LEFT JOIN locations l ON b.location_id = l.id
            WHERE 1=1
        '''
        params = []
        
        # Unit-wise access control
        if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
            # For admin user 'a001', show all unit data
            pass
        elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
            query += ' AND l.name = %s'
            params.append(current_user.location)
            
            # If a unit admin tries to filter by a different location, deny access
            if location and location != current_user.location:
                flash('Access denied: You can only export data for your assigned unit.', 'danger')
                return redirect(url_for('admin.export'))
        
        if start_date:
            query += ' AND b.booking_date >= %s'
            params.append(start_date)
        if end_date:
            query += ' AND b.booking_date <= %s'
            params.append(end_date)
        if department:
            query += ' AND d.name = %s'
            params.append(department)
        if location:
            query += ' AND l.name = %s'
            params.append(location)
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        df = pd.DataFrame(rows)
        # Create Excel file using temporary file approach
        import tempfile
        import os
        # Create a temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
        temp_file.close()
        
        try:
            with pd.ExcelWriter(temp_file.name, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Meal Data')
            
            # Read the file content
            with open(temp_file.name, 'rb') as f:
                file_content = f.read()
        finally:
            # Clean up the temporary file
            os.unlink(temp_file.name)
        
        # Create response
        response = make_response(file_content)
        response.headers['Content-Disposition'] = 'attachment; filename=meal_data.xlsx'
        response.headers['Content-type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return response
    except Exception as e:
        # Handle any exceptions that might occur
        print(f"Error in export_meal_excel: {e}")
        import traceback
        traceback.print_exc()
        flash('Error generating Excel file.', 'danger')
        return redirect(url_for('admin.export'))
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@admin_bp.route('/export_meal_csv')
@login_required
def export_meal_csv():
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.export'))
    # Get filters from request.args
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    location = request.args.get('location')
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        query = '''
            SELECT e.name as employee, d.name as department, l.name as location, b.booking_date, b.shift, b.status
            FROM bookings b
            JOIN employees e ON b.employee_id = e.id
            LEFT JOIN departments d ON e.department_id = d.id
            LEFT JOIN locations l ON b.location_id = l.id
            WHERE 1=1
        '''
        params = []
        
        # Unit-wise access control
        if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
            # For admin user 'a001', show all unit data
            pass
        elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
            query += ' AND l.name = %s'
            params.append(current_user.location)
            
            # If a unit admin tries to filter by a different location, deny access
            if location and location != current_user.location:
                flash('Access denied: You can only export data for your assigned unit.', 'danger')
                return redirect(url_for('admin.export'))
        
        if start_date:
            query += ' AND b.booking_date >= %s'
            params.append(start_date)
        if end_date:
            query += ' AND b.booking_date <= %s'
            params.append(end_date)
        if department:
            query += ' AND d.name = %s'
            params.append(department)
        if location:
            query += ' AND l.name = %s'
            params.append(location)
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        import csv
        import io
        si = io.StringIO()
        if rows:
            writer = csv.DictWriter(si, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        response = make_response(si.getvalue())
        response.headers['Content-Disposition'] = 'attachment; filename=meal_data.csv'
        response.headers['Content-type'] = 'text/csv'
        return response
    except Exception as e:
        # Handle any exceptions that might occur
        print(f"Error in export_meal_csv: {e}")
        import traceback
        traceback.print_exc()
        flash('Error generating CSV file.', 'danger')
        return redirect(url_for('admin.export'))
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@admin_bp.route('/add_user', methods=['GET', 'POST'])
@login_required
def add_user():
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    # Handle both GET and POST requests for user management
    if request.method == 'POST':
        # Process form submission for adding new users
        form = AddUserForm(request.form)
        
        # Populate form choices for adding new users
        conn = get_db_connection()
        cur = conn.cursor()  # Ensure cursor is initialized before use
        
        if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
            # For master admin 'a001', allow all locations and departments
            cur.execute('SELECT id, name FROM locations')
            locations_add = cur.fetchall()
            cur.execute('SELECT id, name FROM departments')
            departments_add = cur.fetchall()
        elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
            # For location admins, restrict to their location
            cur.execute('SELECT id, name FROM locations WHERE name = %s', (current_user.location,))
            locations_add = cur.fetchall()
            cur.execute('SELECT id, name FROM departments')
            departments_add = cur.fetchall()
        else:
            # For finance role, only show locations and departments for filtering
            cur.execute('SELECT id, name FROM locations')
            locations_add = cur.fetchall()
            cur.execute('SELECT id, name FROM departments WHERE name != "Admin"')
            departments_add = cur.fetchall()
        
        cur.execute('SELECT id, name FROM roles WHERE name IN ("Master Admin", "Employee", "Canteen Vendor", "Unit-wise Admin")')
        roles_add = cur.fetchall()
        
        form.location_id.choices = [(l['id'], l['name']) for l in locations_add]
        form.department_id.choices = [(d['id'], d['name']) for d in departments_add]
        form.role_id.choices = [(r['id'], r['name']) for r in roles_add]
        
        # Set default values based on user's role
        if current_user.role == 'Master Admin' and current_user.location:
            if locations_add:
                form.location_id.choices = [(l['id'], l['name']) for l in locations_add]
                form.location_id.data = locations_add[0]['id'] if len(locations_add) > 0 else None  # Pre-select the unit
            if departments_add:
                form.department_id.choices = [(d['id'], d['name']) for d in departments_add]
        
        if current_user.role in ['Master Admin', 'Unit-wise Admin']:
            form.role_id.choices = [(r['id'], r['name']) for r in roles_add]
        else:
            # Limit role choices for other users
            limited_roles = [r for r in roles_add if r['name'] in ['Employee', 'Canteen Vendor']]
            form.role_id.choices = [(r['id'], r['name']) for r in limited_roles]

        if form.validate_on_submit():
            employee_id = form.employee_id.data
            name = form.name.data
            email = form.email.data
            password = form.password.data
            department_id = form.department_id.data
            location_id = form.location_id.data
            role_id = form.role_id.data
            is_active = form.is_active.data
            
            # Validate role assignment permissions
            if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
                flash('Access denied: Only Master Admin or Unit-wise Admin can add users.', 'danger')
                cur.close()
                conn.close()
                return redirect(url_for('admin.add_user'))
            
            # Validate required fields
            if not employee_id or not name or not email:
                flash('Employee ID, Name, and Email are required.', 'danger')
                cur.close()
                conn.close()
                # Get the URL prefix by getting the blueprint's URL prefix
                blueprint_prefix = request.url_rule.rule.split('/')[1] if request.url_rule and len(request.url_rule.rule.split('/')) > 1 else ''
                if blueprint_prefix:
                    blueprint_prefix = '/' + blueprint_prefix
                
                return render_template('admin/add_user.html', form=form, url_prefix=blueprint_prefix)
            
            # Validate email format
            import re
            email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_regex, email):
                flash('Invalid email format.', 'danger')
                cur.close()
                conn.close()
                # Get the URL prefix by getting the blueprint's URL prefix
                blueprint_prefix = request.url_rule.rule.split('/')[1] if request.url_rule and len(request.url_rule.rule.split('/')) > 1 else ''
                if blueprint_prefix:
                    blueprint_prefix = '/' + blueprint_prefix
                
                return render_template('admin/add_user.html', form=form, url_prefix=blueprint_prefix)
            
            # Check if employee_id already exists
            cur.execute("SELECT id FROM employees WHERE employee_id = %s", (employee_id,))
            existing_user = cur.fetchone()
            
            if existing_user:
                flash(f'Error: Employee ID "{employee_id}" already exists. Please use a different Employee ID.', 'danger')
                cur.close()
                conn.close()
                # Get the URL prefix by getting the blueprint's URL prefix
                blueprint_prefix = request.url_rule.rule.split('/')[1] if request.url_rule and len(request.url_rule.rule.split('/')) > 1 else ''
                if blueprint_prefix:
                    blueprint_prefix = '/' + blueprint_prefix
                
                return render_template('admin/add_user.html', form=form, url_prefix=blueprint_prefix)
            
            # Hash password if provided
            password_hash = None
            if password:
                import hashlib
                password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            # Insert new user
            try:
                cur.execute("""
                    INSERT INTO employees 
                    (employee_id, name, email, password_hash, department_id, location_id, role_id, is_active) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (employee_id, name, email, password_hash, department_id, location_id, role_id, is_active))
                
                conn.commit()
                flash('User added successfully!', 'success')
                
            except Exception as e:
                conn.rollback()
                flash('Error adding user: ' + str(e), 'danger')
            finally:
                cur.close()
                conn.close()
                
            return redirect(url_for('admin.add_user'))
        else:
            # If form validation fails, re-populate choices and show form again
            cur.close()
            conn.close()
            # Get the URL prefix by getting the blueprint's URL prefix
            blueprint_prefix = request.url_rule.rule.split('/')[1] if request.url_rule and len(request.url_rule.rule.split('/')) > 1 else ''
            if blueprint_prefix:
                blueprint_prefix = '/' + blueprint_prefix
            
            return render_template('admin/add_user.html', form=form, url_prefix=blueprint_prefix)
    
    # If GET request, show user management page (like cost_subsidy)
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create the add user form for GET requests
    form = AddUserForm()
    
    # Populate form choices for the add user form
    if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
        # For master admin 'a001', allow all locations and departments
        cur.execute('SELECT id, name FROM locations')
        locations_add = cur.fetchall()
        cur.execute('SELECT id, name FROM departments')
        departments_add = cur.fetchall()
    elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
        # For location admins, restrict to their location
        cur.execute('SELECT id, name FROM locations WHERE name = %s', (current_user.location,))
        locations_add = cur.fetchall()
        cur.execute('SELECT id, name FROM departments')
        departments_add = cur.fetchall()
    else:
        # For finance role, only show locations and departments for filtering
        cur.execute('SELECT id, name FROM locations')
        locations_add = cur.fetchall()
        cur.execute('SELECT id, name FROM departments WHERE name != "Admin"')
        departments_add = cur.fetchall()
    
    cur.execute('SELECT id, name FROM roles WHERE name IN ("Master Admin", "Employee", "Canteen Vendor", "Unit-wise Admin")')
    roles_add = cur.fetchall()
    
    form.location_id.choices = [(l['id'], l['name']) for l in locations_add]
    form.department_id.choices = [(d['id'], d['name']) for d in departments_add]
    form.role_id.choices = [(r['id'], r['name']) for r in roles_add]
    
    # Set default values based on user's role
    if current_user.role == 'Master Admin' and current_user.location:
        if locations_add:
            form.location_id.choices = [(l['id'], l['name']) for l in locations_add]
            form.location_id.data = locations_add[0]['id'] if len(locations_add) > 0 else None  # Pre-select the unit
        if departments_add:
            form.department_id.choices = [(d['id'], d['name']) for d in departments_add]
    
    if current_user.role in ['Master Admin', 'Unit-wise Admin']:
        form.role_id.choices = [(r['id'], r['name']) for r in roles_add]
    else:
        # Limit role choices for other users
        limited_roles = [r for r in roles_add if r['name'] in ['Employee', 'Canteen Vendor']]
        form.role_id.choices = [(r['id'], r['name']) for r in limited_roles]
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of items per page
    offset = (page - 1) * per_page
    
    # Get filter parameters
    employee_filter = request.args.get('employee', '').strip()
    department_filter = request.args.get('department', '').strip()
    location_filter = request.args.get('location', '').strip()
    role_filter = request.args.get('role', '').strip()
    is_active_filter = request.args.get('is_active', '').strip()
    
    # Base query to join employees with departments, locations, and roles
    query = """
        SELECT e.id, e.employee_id, e.name as employee, d.name as department, 
               l.name as location, r.name as role, e.is_active, e.created_at
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN locations l ON e.location_id = l.id
        LEFT JOIN roles r ON e.role_id = r.id
    """
    
    count_query = """
        SELECT COUNT(*) as count
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN locations l ON e.location_id = l.id
        LEFT JOIN roles r ON e.role_id = r.id
    """
    
    params = []
    count_params = []
    where_conditions = []
    
    # Unit-wise access control for user listing
    if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
        # Master admin 'a001' can see all users
        pass
    elif current_user.role == 'Unit-wise Admin' and current_user.location:
        # Unit admin can only see users from their assigned unit
        where_conditions.append("l.name = %s")
        params.append(current_user.location)
        count_params.append(current_user.location)
        
        # If a unit admin tries to filter by a different location, deny access
        if location_filter and location_filter != current_user.location:
            flash('Access denied: You can only view users from your assigned unit.', 'danger')
            return redirect(url_for('admin.add_user'))
        location_filter = current_user.location  # Force filter to their unit
    
    # Apply filters
    if employee_filter:
        where_conditions.append("(e.name LIKE %s OR e.employee_id LIKE %s)")
        params.extend([f"%{employee_filter}%", f"%{employee_filter}%"])
        count_params.extend([f"%{employee_filter}%", f"%{employee_filter}%"])
    
    if department_filter:
        where_conditions.append("d.name = %s")
        params.append(department_filter)
        count_params.append(department_filter)
    
    if location_filter and not (current_user.role == 'Master Admin' and current_user.location and location_filter == current_user.location):
        # Apply location filter only if not already applied by unit admin logic
        where_conditions.append("l.name = %s")
        params.append(location_filter)
        count_params.append(location_filter)
    
    if role_filter:
        where_conditions.append("r.name = %s")
        params.append(role_filter)
        count_params.append(role_filter)
    
    if is_active_filter == 'active':
        where_conditions.append("e.is_active = TRUE")
        #params.append(True)  # Not needed since it's a boolean condition
        #count_params.append(True)
    elif is_active_filter == 'inactive':
        where_conditions.append("e.is_active = FALSE")
        #params.append(False)  # Not needed since it's a boolean condition
        #count_params.append(False)
    
    # Add WHERE clause if there are conditions
    if where_conditions:
        query += " WHERE " + " AND ".join(where_conditions)
        count_query += " WHERE " + " AND ".join(where_conditions)
    
    # Add ordering and limit for pagination
    query += " ORDER BY e.name LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
    
    # Execute queries
    cur.execute(count_query, count_params)
    total_count = cur.fetchone()['count']
    
    cur.execute(query, params)
    users = cur.fetchall()
    
    # Calculate pagination info
    total_pages = (total_count + per_page - 1) // per_page
    pagination = {
        'page': page,
        'pages': total_pages,
        'per_page': per_page,
        'total': total_count,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1 if page > 1 else None,
        'next_num': page + 1 if page < total_pages else None
    }
    
    # Get distinct values for filter dropdowns
    cur.execute("SELECT DISTINCT name FROM departments ORDER BY name")
    departments = [row['name'] for row in cur.fetchall()]
    
    cur.execute("SELECT DISTINCT name FROM locations ORDER BY name")
    locations = [row['name'] for row in cur.fetchall()]
    
    cur.execute("SELECT DISTINCT name FROM roles ORDER BY name")
    roles = [row['name'] for row in cur.fetchall()]
    
    cur.close()
    conn.close()
    
    # Get the URL prefix by getting the blueprint's URL prefix
    blueprint_prefix = request.url_rule.rule.split('/')[1] if request.url_rule and len(request.url_rule.rule.split('/')) > 1 else ''
    if blueprint_prefix:
        blueprint_prefix = '/' + blueprint_prefix
    
    return render_template('admin/user_management.html',
                          form=form,
                          users=users,
                          departments=departments,
                          locations=locations,
                          roles=roles,
                          selected_employee=employee_filter,
                          selected_department=department_filter,
                          selected_location=location_filter,
                          selected_role=role_filter,
                          selected_is_active=is_active_filter,
                          pagination=pagination,
                          url_prefix=blueprint_prefix)

# Route to get the edit user form for modal
@admin_bp.route('/get_edit_user_form/<int:user_id>')
@login_required
def get_edit_user_form(user_id):
    # Check if user has permission to edit other users
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        response = jsonify({'success': False, 'message': 'Access denied.'})
        response.status_code = 403
        return response
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get the user to edit
        cur.execute('''
            SELECT e.id, e.employee_id, e.name, e.email, e.department_id, 
                   e.location_id, e.role_id, e.is_active
            FROM employees e
            WHERE e.id = %s
        ''', (user_id,))
        user = cur.fetchone()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found.'}), 404
        
        # Create form and populate with user data
        form = EditUserForm()
        
        # Get current user's role info using current_user from Flask-Login
        current_user_role = current_user.role
        current_user_employee_id = current_user.employee_id
        current_user_location_name = getattr(current_user, 'location', None)
        
        # Populate select field choices
        if current_user_role == 'Master Admin' and current_user_employee_id == 'a001':
            cur.execute('SELECT id, name FROM locations')
            locations = cur.fetchall()
            form.location_id.choices = [(l['id'], l['name']) for l in locations]
        elif current_user_role == 'Unit-wise Admin' and current_user_location_name:
            cur.execute('SELECT id, name FROM locations WHERE name = %s', (current_user_location_name,))
            locations = cur.fetchall()
            if not locations:
                return jsonify({'success': False, 'message': 'Error: Your assigned unit location was not found.'}), 400
            form.location_id.choices = [(l['id'], l['name']) for l in locations]
        else:
            cur.execute('SELECT id, name FROM locations')
            locations = cur.fetchall()
            form.location_id.choices = [(l['id'], l['name']) for l in locations]

        cur.execute('SELECT id, name FROM roles WHERE name IN ("Master Admin", "Employee", "Canteen Vendor", "Unit-wise Admin")')
        roles = cur.fetchall()
        
        if current_user_role == 'Master Admin' and current_user_employee_id == 'a001':
            form.role_id.choices = [(r['id'], r['name']) for r in roles]
        elif current_user_role == 'Unit-wise Admin' and current_user_location_name:
            form.role_id.choices = [(r['id'], r['name']) for r in roles if r['name'] in ["Employee", "Canteen Vendor"]]
        else:
            form.role_id.choices = [(r['id'], r['name']) for r in roles]

        cur.execute('SELECT id, name FROM departments WHERE name != "Admin"')
        departments = cur.fetchall()
        form.department_id.choices = [(d['id'], d['name']) for d in departments]
        
        # Check if user exists and has required fields
        if not user or 'id' not in user:
            return jsonify({'success': False, 'message': 'User not found or invalid user data.'}), 404
        
        # Pre-populate form with user data
        form.employee_id.data = user.get('employee_id', '')
        form.name.data = user.get('name', '')
        form.email.data = user.get('email', '')
        form.department_id.data = user.get('department_id', '')
        form.location_id.data = user.get('location_id', '')
        form.role_id.data = user.get('role_id', '')
        form.is_active.data = bool(user.get('is_active', False))
        
        # Render the form in a simplified template for modal
        form_html = '''
        <form id="editUserForm" method="post">
          <input type="hidden" name="csrf_token" value="'''+generate_csrf()+'''" />
          <div class="row">
            <div class="col-md-6 mb-3">
              <label for="employee_id" class="form-label">Employee ID</label>
              <input type="text" class="form-control" id="employee_id" name="employee_id" value="'''+str(user.get('employee_id', ''))+'''" required>
              <small class="form-text text-muted">Enter a unique Employee ID (letters and numbers only)</small>
            </div>
            <div class="col-md-6 mb-3">
              <label for="name" class="form-label">Name</label>
              <input type="text" class="form-control" id="name" name="name" value="'''+str(user.get('name', ''))+'''" required>
            </div>
            <div class="col-md-6 mb-3">
              <label for="email" class="form-label">Email</label>
              <input type="email" class="form-control" id="email" name="email" value="'''+str(user.get('email', ''))+'''">
            </div>
            <div class="col-md-6 mb-3">
              <label for="password" class="form-label">Password (Leave blank to keep current)</label>
              <input type="password" class="form-control" id="password" name="password">
            </div>
            <div class="col-md-6 mb-3">
              <label for="confirm_password" class="form-label">Confirm Password</label>
              <input type="password" class="form-control" id="confirm_password" name="confirm_password">
            </div>
            <div class="col-md-6 mb-3">
              <label for="department_id" class="form-label">Department</label>
              <select class="form-select" id="department_id" name="department_id" required>
        '''
        
        for dept in departments:
            selected = 'selected' if dept.get('id') == user.get('department_id') else ''
            form_html += f'<option value="{dept.get("id", "")}" {selected}>{dept.get("name", "")}</option>'
        
        form_html += '''
              </select>
            </div>
            <div class="col-md-6 mb-3">
              <label for="location_id" class="form-label">Location</label>
              <select class="form-select" id="location_id" name="location_id" required>
        '''
        
        for loc in locations:
            selected = 'selected' if loc.get('id') == user.get('location_id') else ''
            form_html += f'<option value="{loc.get("id", "")}" {selected}>{loc.get("name", "")}</option>'
        
        # Special case: Always add "All Units" option for Master Admin users
        cur.execute('SELECT name FROM roles WHERE id = %s', (user.get('role_id'),))
        user_role = cur.fetchone()
        if user_role and user_role['name'] == 'Master Admin':
            # Add "All Units" option at the top
            form_html += '<option value="0" selected>All Units</option>'
        else:
            # For non-Master Admin users, add the "All Units" option only if they have location_id = 0
            if user.get('location_id') == 0:
                form_html += '<option value="0" selected>All Units</option>'
        
        form_html += '''
              </select>
            </div>
            <div class="col-md-6 mb-3">
              <label for="role_id" class="form-label">Role</label>
              <select class="form-select" id="role_id" name="role_id" required>
        '''
        
        # Add role options
        for role in roles:
            selected = 'selected' if role.get('id') == user.get('role_id') else ''
            form_html += f'<option value="{role.get("id", "")}" {selected}>{role.get("name", "")}</option>'
        
        form_html += '''
              </select>
            </div>
            <div class="col-md-6 mb-3">
              <label for="is_active" class="form-label">Active Status</label>
              <select class="form-select" id="is_active" name="is_active" required>
                <option value="1" '''+('selected' if user.get('is_active') else '')+'''>Active</option>
                <option value="0" '''+('selected' if not user.get('is_active') else '')+'''>Inactive</option>
              </select>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
            <button type="submit" class="btn btn-primary">Update User</button>
          </div>
        </form>
        '''
        
        return jsonify({'html': form_html})
    
    except Exception as e:
        conn.rollback()
        print(f'Error in get_edit_user_form: {str(e)}')  # For debugging
        import traceback
        traceback.print_exc()  # For debugging
        return jsonify({'success': False, 'message': f'Error loading edit form: {str(e)}'}), 500
    
    finally:
        cur.close()
        conn.close()


@admin_bp.route('/update_user/<int:user_id>', methods=['POST'])
@login_required
def update_user(user_id):
    # Check if current user has permission to update users
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        response = jsonify({'success': False, 'message': 'Access denied.'})
        response.status_code = 403
        return response
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get current user's info from Flask-Login current_user
        current_user_role = current_user.role
        current_user_employee_id = current_user.employee_id
        current_user_location_name = getattr(current_user, 'location', None)
        
        # Get form data
        employee_id = request.form.get('employee_id')
        name = request.form.get('name')
        email = request.form.get('email')
        department_id = request.form.get('department_id')
        location_id = request.form.get('location_id')
        role_id = request.form.get('role_id')
        is_active = 1 if request.form.get('is_active') else 0
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if not employee_id or not name:
            return jsonify({'success': False, 'message': 'Employee ID and Name are required.'})
        
        if password and password != confirm_password:
            return jsonify({'success': False, 'message': 'Passwords do not match.'})
        
        # Enforce location for unit admins - they can only assign users to their own unit
        if current_user_role == 'Master Admin' and current_user_employee_id == 'a001':
            pass  # Master admin can assign to any location
        elif role_id == 6 and location_id == '0':  # 6 is the role_id for Master Admin
            # Special case: Master Admin with "All Units" location
            # Set location_id to NULL or a default value
            location_id = None
        elif current_user_role == 'Master Admin' and current_user_employee_id != 'a001' and current_user_location_name:
            # Check if user is editing their own record
            cur.execute('SELECT employee_id FROM employees WHERE id = %s', (user_id,))
            target_user = cur.fetchone()
            
            # Allow unit admin to change their own location, but restrict changing others
            if not target_user or target_user['employee_id'] != current_user_employee_id:
                # Unit admin editing someone else - verify the selected location matches their assigned unit
                cur.execute('SELECT name FROM locations WHERE id = %s', (location_id,))
                selected_location = cur.fetchone()
                if not selected_location or selected_location['name'] != current_user_location_name:
                    return jsonify({'success': False, 'message': f'Access denied: You can only assign users to your assigned unit ({current_user_location_name}).'})
        
        # Check if employee_id is being changed and if the new ID already exists
        cur.execute("SELECT id FROM employees WHERE employee_id = %s AND id != %s", (employee_id, user_id))
        existing_user = cur.fetchone()
        
        if existing_user:
            return jsonify({'success': False, 'message': f'Error: Employee ID "{employee_id}" already exists. Please use a different Employee ID.'})
        
        # Update user
        update_query = '''
            UPDATE employees 
            SET employee_id = %s, name = %s, email = %s, 
                department_id = %s, location_id = %s, 
                role_id = %s, is_active = %s
            WHERE id = %s
        '''
        cur.execute(update_query, (employee_id, name, email, department_id, location_id, role_id, is_active, user_id))
        
        # If password is provided, update it
        if password:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            cur.execute("UPDATE employees SET password_hash = %s WHERE id = %s", (password_hash, user_id))
        
        conn.commit()
        return jsonify({'success': True, 'message': 'User updated successfully!'})
    
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Error updating user: {str(e)}'})
    
    finally:
        cur.close()
        conn.close()


@admin_bp.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get the user to edit
        cur.execute('''
            SELECT e.id, e.employee_id, e.name, e.email, e.department_id, 
                   e.location_id, e.role_id, e.is_active, l.name as location_name
            FROM employees e
            LEFT JOIN locations l ON e.location_id = l.id
            WHERE e.id = %s
        ''', (user_id,))
        user = cur.fetchone()
        
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('admin.add_user'))
        
        # Check if current user has permission to edit this user
        if current_user.role == 'Master Admin' and current_user.location and not (current_user.employee_id == 'a001'):
            # Unit admin - can only edit users from their assigned unit
            # Master admin 'a001' can edit users from any unit
            if user['location_name'] != current_user.location:
                flash('Access denied: You can only edit users from your assigned unit.', 'danger')
                return redirect(url_for('admin.add_user'))
        
        # Create form and populate with user data
        form = EditUserForm()
        
        # Populate select field choices
        if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
            cur.execute('SELECT id, name FROM locations')
            locations = cur.fetchall()
            form.location_id.choices = [(l['id'], l['name']) for l in locations]
        elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
            # Unit admin - only show their assigned location
            # Master admin 'a001' should see all locations (handled in the first condition)
            cur.execute('SELECT id, name FROM locations WHERE name = %s', (current_user.location,))
            locations = cur.fetchall()
            if not locations:
                flash('Error: Your assigned unit location was not found.', 'danger')
                return redirect(url_for('admin.add_user'))
            form.location_id.choices = [(l['id'], l['name']) for l in locations]
        else:
            cur.execute('SELECT id, name FROM locations')
            locations = cur.fetchall()
            form.location_id.choices = [(l['id'], l['name']) for l in locations]

        cur.execute('SELECT id, name FROM roles WHERE name IN ("Master Admin", "Employee", "Canteen Vendor", "Unit-wise Admin")')
        roles = cur.fetchall()
        
        if current_user.role == 'Master Admin' and current_user.employee_id == 'a001':
            form.role_id.choices = [(r['id'], r['name']) for r in roles]
        elif current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
            # Unit admin - limited role choices
            # Master admin 'a001' gets all roles (handled in first condition)
            form.role_id.choices = [(r['id'], r['name']) for r in roles if r['name'] in ["Employee", "Canteen Vendor"]]
        else:
            form.role_id.choices = [(r['id'], r['name']) for r in roles]

        cur.execute('SELECT id, name FROM departments WHERE name != "Admin"')
        departments = cur.fetchall()
        form.department_id.choices = [(d['id'], d['name']) for d in departments]
        
        if request.method == 'GET':
            # Populate form with user data for GET request
            form.employee_id.data = user['employee_id']
            form.name.data = user['name']
            form.email.data = user['email']
            form.department_id.data = user['department_id']
            form.location_id.data = user['location_id']
            form.role_id.data = user['role_id']
            form.is_active.data = bool(user['is_active'])
        
        if form.validate_on_submit():
            # Update user data
            employee_id = form.employee_id.data
            name = form.name.data
            email = form.email.data
            department_id = form.department_id.data
            location_id = form.location_id.data
            role_id = form.role_id.data
            is_active = 1 if form.is_active.data else 0
            password = form.password.data
            
            # Validation
            if not employee_id or not name:
                flash('Employee ID and Name are required.', 'danger')
                return render_template('admin/edit_user.html', form=form, user=user)
            
            # Validate email format
            import re
            email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if email and not re.match(email_regex, email):
                flash('Invalid email format.', 'danger')
                return render_template('admin/edit_user.html', form=form, user=user)
            
            # Check if employee_id already exists (excluding current user)
            cur.execute("SELECT id FROM employees WHERE employee_id = %s AND id != %s", (employee_id, user_id))
            existing_user = cur.fetchone()
            
            if existing_user:
                flash(f'Error: Employee ID "{employee_id}" already exists. Please use a different Employee ID.', 'danger')
                return render_template('admin/edit_user.html', form=form, user=user)
            
            # Check if location_id belongs to current user's unit (if unit admin)
            if current_user.role == 'Master Admin' and current_user.location and current_user.employee_id != 'a001':
                # Check if user is editing their own record
                if user['employee_id'] != current_user.employee_id:
                    # Unit admin editing someone else - verify the selected location matches their assigned unit
                    cur.execute('SELECT name FROM locations WHERE id = %s', (location_id,))
                    location_result = cur.fetchone()
                    if location_result and location_result['name'] != current_user.location:
                        flash('Access denied: You can only assign users to your assigned unit.', 'danger')
                        return render_template('admin/edit_user.html', form=form, user=user)
            
            # Update user
            update_query = '''
                UPDATE employees 
                SET employee_id = %s, name = %s, email = %s, 
                    department_id = %s, location_id = %s, 
                    role_id = %s, is_active = %s
                WHERE id = %s
            '''
            cur.execute(update_query, (employee_id, name, email, department_id, location_id, role_id, is_active, user_id))
            
            # If password is provided, update it
            if password:
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                cur.execute("UPDATE employees SET password_hash = %s WHERE id = %s", (password_hash, user_id))
            
            conn.commit()
            flash('User updated successfully!', 'success')
            return redirect(url_for('admin.add_user'))
        
        return render_template('admin/edit_user.html', form=form, user=user)
    
    except Exception as e:
        conn.rollback()
        flash('Error updating user: ' + str(e), 'danger')
        return redirect(url_for('admin.add_user'))
    
    finally:
        cur.close()
        conn.close()

@admin_bp.route('/debug_routes')
def debug_routes():
    from flask import current_app
    output = []
    for rule in current_app.url_map.iter_rules():
        output.append(f"{rule.endpoint}: {rule}")
    return '<br>'.join(output)

@admin_bp.route('/special_messages', methods=['GET', 'POST'])
@login_required
def special_messages():
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        flash('Access denied: Only Admin can manage special messages.', 'danger')
        return redirect(url_for('admin.dashboard'))

    message = None
    
    if request.method == 'POST':
        conn = None
        cur = None
        try:
            conn = get_db_connection(False)
            cur = conn.cursor()
            message_text = request.form.get('message_text', '').strip()
            is_active = request.form.get('is_active') == 'on' if 'is_active' in request.form else True

            if message_text:
                try:
                    cur.execute("UPDATE special_messages SET is_active = FALSE")
                    cur.execute(
                        "INSERT INTO special_messages (message_text, is_active) VALUES (%s, %s)",
                        (message_text, is_active)
                    )
                    conn.commit()  # XXXXX
                    flash('Special message updated successfully!', 'success')
                except Exception as e:
                    if conn:
                        conn.rollback()
                    flash(f'Error updating special message: {str(e)}', 'danger')
            else:
                try:
                    cur.execute("UPDATE special_messages SET is_active = FALSE")
                    conn.commit()  # XXXXX
                    flash('All special messages deactivated.', 'info')
                except Exception as e:
                    if conn:
                        conn.rollback()
                    flash(f'Error deactivating messages: {str(e)}', 'danger')
            return redirect(url_for('admin.dashboard'))
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()
    else: # GET request
        conn = None
        cur = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT message_text, is_active FROM special_messages WHERE is_active = TRUE AND DATE(created_at) = CURDATE() ORDER BY created_at DESC LIMIT 1")
            active_message = cur.fetchone()
            if active_message:
                message = active_message['message_text']
                is_active = active_message['is_active']
            else:
                message = ""
                is_active = False
            return render_template('admin/special_messages.html', message=message, is_active=is_active)
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

@admin_bp.route('/edit_vendor/<vendor_name>', methods=['GET'])
@login_required
def edit_vendor(vendor_name):
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.dashboard'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM vendors WHERE name = %s", (vendor_name,))
    vendor_data = cur.fetchone()

    if not vendor_data:
        flash('Vendor not found.', 'danger')
        return redirect(url_for('admin.vendor_report'))

    form = VendorForm(data=vendor_data)
    populate_vendor_form_choices(form)

    # Pre-select values for dropdowns
    form.unit.data = vendor_data['unit']

    return render_template('admin/add_vendor_item.html', form=form, vendor_data=vendor_data, csrf_token=generate_csrf())


def populate_vendor_form_choices(form):
    """Helper function to populate vendor form choices"""
    conn = get_db_connection()
    cur = conn.cursor()

    # Populate unit choices
    cur.execute('SELECT name FROM locations ORDER BY name')
    locations = cur.fetchall()
    form.unit.choices = [(l['name'], l['name']) for l in locations]
    
    cur.close()
    conn.close()

@admin_bp.route('/add_vendor_item', methods=['GET', 'POST'])
@login_required
def add_vendor_item():
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.dashboard'))

    form = VendorForm()
    populate_vendor_form_choices(form)
    
    print(f"[DEBUG] Request method: {request.method}")
    print(f"[DEBUG] Form data: {request.form}")
    print(f"[DEBUG] Form validate_on_submit: {form.validate_on_submit()}")
    if not form.validate_on_submit():
        print(f"[DEBUG] Form errors: {form.errors}")

    if form.validate_on_submit():
        vendor_name = form.name.data
        unit = form.unit.data
        agreement_date = form.agreement_date.data
        original_vendor_name = request.form.get('original_vendor_name') # Get original name for updates
        
        print(f"[DEBUG] Form submitted successfully!")
        print(f"[DEBUG] Vendor name: {vendor_name}")
        print(f"[DEBUG] Unit: {unit}")
        print(f"[DEBUG] Agreement date: {agreement_date}")
        print(f"[DEBUG] Original vendor name: {original_vendor_name}")
        
        food_licence_path = None
        # If editing, retain existing food_licence_path if no new file is uploaded
        if original_vendor_name:
            conn_temp = get_db_connection()
            cur_temp = conn_temp.cursor()
            cur_temp.execute("SELECT food_licence_path FROM vendors WHERE name = %s", (original_vendor_name,))
            existing_vendor = cur_temp.fetchone()
            cur_temp.close()
            conn_temp.close()
            if existing_vendor:
                food_licence_path = existing_vendor['food_licence_path']

        if 'food_licence' in request.files:
            file = request.files['food_licence']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                relative_file_path = os.path.join('uploads/food_licences', filename).replace('\\', '/')
                if UPLOAD_FOLDER:
                    full_file_path = os.path.join(UPLOAD_FOLDER, filename)
                    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                    file.save(full_file_path)
                food_licence_path = relative_file_path
            elif file.filename:
                flash('Invalid file type for food licence. Only PDF files are allowed.', 'danger')
                # Pass vendor_data back to the template if it's an edit operation
                if original_vendor_name:
                    conn_temp = get_db_connection()
                    cur_temp = conn_temp.cursor()
                    cur_temp.execute("SELECT * FROM vendors WHERE name = %s", (original_vendor_name,))
                    vendor_data = cur_temp.fetchone()
                    cur_temp.close()
                    conn_temp.close()
                    populate_vendor_form_choices(form)
                    return render_template('admin/add_vendor_item.html', form=form, vendor_data=vendor_data, csrf_token=generate_csrf())
                populate_vendor_form_choices(form)
                return render_template('admin/add_vendor_item.html', form=form, csrf_token=generate_csrf())

        conn = None
        cur = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            if original_vendor_name:
                # Update existing vendor
                print(f"[DEBUG] Updating existing vendor: {original_vendor_name}")
                cur.execute("""
                    UPDATE vendors
                    SET name = %s, unit = %s, food_licence_path = %s, agreement_date = %s
                    WHERE name = %s
                """, (vendor_name, unit, food_licence_path, agreement_date, original_vendor_name))
                print(f"[DEBUG] Update query executed successfully")
                flash('Vendor item updated successfully!', 'success')
            else:
                # Add new vendor
                print(f"[DEBUG] Adding new vendor: {vendor_name}")
                cur.execute("INSERT INTO vendors (name, unit, food_licence_path, agreement_date) VALUES (%s, %s, %s, %s)",
                            (vendor_name, unit, food_licence_path, agreement_date))
                print(f"[DEBUG] Insert query executed successfully")
                flash('Vendor item added successfully!', 'success')
            conn.commit()
        except IntegrityError as e:
            if e.args[0] == 1062:
                flash('A vendor with this name already exists. Please use a unique vendor name.', 'danger')
            else:
                flash('Database error: ' + str(e), 'danger')
            if conn:
                conn.rollback()
        except Exception as e:
            flash(f'Error processing vendor item: {e}', 'danger')
            if conn:
                conn.rollback()
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()
    
    populate_vendor_form_choices(form)
    return render_template('admin/add_vendor_item.html', form=form, csrf_token=generate_csrf())

@admin_bp.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    """Serve uploaded files"""
    try:
        # Get the static folder path
        static_folder = os.path.join(current_app.root_path, 'static')
        print(f"[DEBUG] Serving file: {filename}")
        print(f"[DEBUG] Static folder: {static_folder}")
        
        # Normalize the filename path for cross-platform compatibility
        filename_normalized = filename.replace('/', os.sep).replace('\\', os.sep)
        full_path = os.path.join(static_folder, filename_normalized)
        print(f"[DEBUG] Full path: {full_path}")
        print(f"[DEBUG] File exists: {os.path.exists(full_path)}")
        
        # If file doesn't exist, try alternative paths
        if not os.path.exists(full_path):
            print(f"[DEBUG] File not found at: {full_path}")
            
            # Try to find the file in the uploads directory
            uploads_folder = os.path.join(static_folder, 'uploads')
            filename_only = os.path.basename(filename_normalized)
            alternative_path = os.path.join(uploads_folder, filename_only)
            print(f"[DEBUG] Trying alternative path: {alternative_path}")
            print(f"[DEBUG] Alternative exists: {os.path.exists(alternative_path)}")
            
            if os.path.exists(alternative_path):
                return send_from_directory(uploads_folder, filename_only)
            else:
                abort(404)
        else:
            return send_from_directory(static_folder, filename)
            
    except FileNotFoundError as e:
        print(f"[DEBUG] File not found: {e}")
        abort(404)
    except Exception as e:
        print(f"[DEBUG] Error serving file: {e}")
        import traceback
        traceback.print_exc()
        abort(500)





@admin_bp.route('/manage_missed_tokens')
@login_required
def manage_missed_tokens():
    print("=== MANAGE MISSED TOKENS ROUTE CALLED ===")
    print(f"Current user: employee_id={current_user.employee_id}, role={current_user.role}, location={current_user.location}")
    
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get form parameters
    location_filter = request.args.get('location', '')
    date_filter = request.args.get('date', '')
    search_employee = request.args.get('employee', '')
    
    try:
        # Build query for missed bookings
        query_parts = [
            "b.id, b.employee_id, b.booking_date, b.shift, b.status,",
            "e.name as employee_name, l.name as location_name"
        ]
        base_query = """ 
            FROM bookings b
            JOIN employees e ON b.employee_id = e.id
            JOIN locations l ON b.location_id = l.id
        """
        
        params = []
        conditions = ["b.booking_date <= CURDATE() AND b.status != 'Consumed'"]
        
        # Apply filters
        if location_filter:
            conditions.append("l.name = %s")
            params.append(location_filter)
        elif current_user.location and not (current_user.role == 'Master Admin' and current_user.employee_id == 'a001'):
            # Unit-specific admin - only show their assigned unit's data
            # Master admin 'a001' should see all units regardless of their assigned location
            print(f"DEBUG: Applying location filter for unit admin. Location: {current_user.location}")
            conditions.append("l.name = %s")
            params.append(current_user.location)
        else:
            print(f"DEBUG: No location filter applied.")
            print(f"  current_user.location = {current_user.location}")
            print(f"  current_user.role = {current_user.role}")  
            print(f"  current_user.employee_id = {current_user.employee_id}")
            print(f"  Condition check: current_user.location = {bool(current_user.location)}")
            print(f"  Condition check: (current_user.role == 'Master Admin' and current_user.employee_id == 'a001') = {(current_user.role == 'Master Admin' and current_user.employee_id == 'a001')}")
            print(f"  Condition check: not (current_user.role == 'Master Admin' and current_user.employee_id == 'a001') = {not (current_user.role == 'Master Admin' and current_user.employee_id == 'a001')}")
            print(f"  Final condition: current_user.location and not (current_user.role == 'Master Admin' and current_user.employee_id == 'a001') = {bool(current_user.location and not (current_user.role == 'Master Admin' and current_user.employee_id == 'a001'))}")
            
        if date_filter:
            conditions.append("b.booking_date = %s")
            params.append(date_filter)
        
        if search_employee:
            conditions.append("(e.name LIKE %s OR e.employee_id LIKE %s)")
            params.extend([f'%{search_employee}%', f'%{search_employee}%'])
        
        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)
        
        # Get missed bookings
        full_query = "SELECT " + " ".join(query_parts) + base_query + " ORDER BY b.booking_date DESC, b.shift, e.name"
        print(f"DEBUG: Final query: {full_query}")
        print(f"DEBUG: Query params: {params}")
        print(f"DEBUG: Conditions applied: {conditions}")
        cur.execute(full_query, params)
        missed_bookings = cur.fetchall()
        print(f"DEBUG: Found {len(missed_bookings)} missed bookings")
        if missed_bookings:
            locations_found = set(row['location_name'] for row in missed_bookings)
            print(f"DEBUG: Locations found in results: {sorted(locations_found)}")
        
        # Get locations for manual booking - filtered by user access rights
        if current_user.employee_id == 'a001':
            # Master admin 'a001' - show all locations
            cur.execute("SELECT * FROM locations ORDER BY name")
            locations = cur.fetchall()
        elif current_user.location:
            # Unit-specific admin - only show their own location
            cur.execute("SELECT * FROM locations WHERE name = %s ORDER BY name", (current_user.location,))
            locations = cur.fetchall()
        else:
            # Other admins - show all locations
            cur.execute("SELECT * FROM locations ORDER BY name")
            locations = cur.fetchall()
        
        # Get employees for manual booking
        if current_user.employee_id == 'a001':
            # Master admin 'a001' - show all employees with role 'employee' from all locations
            cur.execute("""SELECT e.id, e.employee_id, e.name, d.name as department_name, l.name as location_name, r.name as role_name
                          FROM employees e
                          JOIN departments d ON e.department_id = d.id
                          JOIN locations l ON e.location_id = l.id
                          JOIN roles r ON e.role_id = r.id
                          WHERE e.is_active = 1 AND r.name = 'employee'
                          ORDER BY e.name""")
        elif current_user.location:
            # Unit-specific admin - only show employees from their location with role 'employee'
            cur.execute("""SELECT e.id, e.employee_id, e.name, d.name as department_name, l.name as location_name, r.name as role_name
                          FROM employees e
                          JOIN departments d ON e.department_id = d.id
                          JOIN locations l ON e.location_id = l.id
                          JOIN roles r ON e.role_id = r.id
                          WHERE e.is_active = 1 AND l.name = %s AND r.name = 'employee'
                          ORDER BY e.name""", (current_user.location,))
        else:
            # Other admins - show all employees with role 'employee'
            cur.execute("""SELECT e.id, e.employee_id, e.name, d.name as department_name, l.name as location_name, r.name as role_name
                          FROM employees e
                          JOIN departments d ON e.department_id = d.id
                          JOIN locations l ON e.location_id = l.id
                          JOIN roles r ON e.role_id = r.id
                          WHERE e.is_active = 1 AND r.name = 'employee'
                          ORDER BY e.name""")
        employees = cur.fetchall()
        
        # Get available meals
        cur.execute("SELECT * FROM meals ORDER BY name")
        meals = cur.fetchall()
        
        # Determine display location for header
        display_location = None
        if current_user.employee_id != 'a001' and current_user.location:
            display_location = current_user.location
        
        return render_template('admin/manage_missed_tokens.html',
                               missed_bookings=missed_bookings,
                               locations=locations,
                               employees=employees,
                               meals=meals,
                               current_location=display_location,
                               filters={
                                   'location': location_filter,
                                   'date': date_filter,
                                   'employee': search_employee
                               },
                               csrf_token=generate_csrf())
    
    except Exception as e:
        flash(f'Error loading missed tokens page: {str(e)}', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    finally:
        cur.close()
        conn.close()


@admin_bp.route('/issue_missed_token/<int:booking_id>', methods=['POST'])
@login_required
def issue_missed_token(booking_id):
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        return {'success': False, 'message': 'Access denied.'}, 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get the booking details
        cur.execute("""
            SELECT b.*, e.employee_id as emp_id, m.name as meal_name
            FROM bookings b
            JOIN employees e ON b.employee_id = e.id
            JOIN meals m ON b.meal_id = m.id
            WHERE b.id = %s
        """, (booking_id,))
        booking = cur.fetchone()
        
        if not booking:
            return {'success': False, 'message': 'Booking not found.'}, 404
        
        # Check if user has permission for this location
        cur.execute("SELECT name FROM locations WHERE id = %s", (booking['location_id'],))
        location = cur.fetchone()
        if current_user.location and location['name'] != current_user.location:
            return {'success': False, 'message': 'Access denied for this location.'}, 403
        
        # Update booking status to consumed
        cur.execute("""
            UPDATE bookings 
            SET status = 'Consumed', consumed_at = NOW() 
            WHERE id = %s
        """, (booking_id,))
        
        # Log the consumption
        cur.execute("""
            INSERT INTO meal_consumption_log (booking_id, employee_id, meal_id, location_id, vendor_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            booking_id,
            booking['employee_id'],
            booking['meal_id'],
            booking['location_id'],
            current_user.id  # Admin who issued the token
        ))
        
        conn.commit()
        
        return {
            'success': True, 
            'message': f'Missed token issued successfully for {booking["emp_id"]} - {booking["shift"]} on {booking["booking_date"]}'
        }
    
    except Exception as e:
        conn.rollback()
        return {'success': False, 'message': f'Error issuing missed token: {str(e)}'}
    
    finally:
        cur.close()
        conn.close()


@admin_bp.route('/manual_book_meal', methods=['POST'])
@login_required
def manual_book_meal():
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        return {'success': False, 'message': 'Access denied.'}, 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        employee_id = request.form.get('employee_id')
        meal_id = request.form.get('meal_id')
        booking_date = request.form.get('booking_date')
        location_id = request.form.get('location_id')
        
        # Validate inputs
        if not all([employee_id, meal_id, booking_date, location_id]):
            return {'success': False, 'message': 'All fields are required.'}, 400
        
        # Determine shift based on meal name
        cur.execute("SELECT name FROM meals WHERE id = %s", (meal_id,))
        meal = cur.fetchone()
        if not meal:
            return {'success': False, 'message': 'Meal not found.'}, 404
        
        # Map meal names to shifts (assuming typical meal times)
        meal_name = meal['name'].lower()
        if 'breakfast' in meal_name or meal_name == 'bf' or meal_name.startswith('b'):
            shift = 'Breakfast'
        elif 'lunch' in meal_name or meal_name == 'ln' or meal_name.startswith('l'):
            shift = 'Lunch'
        elif 'dinner' in meal_name or 'supper' in meal_name or meal_name == 'dn' or meal_name.startswith('d'):
            shift = 'Dinner'
        else:
            # Default to a shift based on time of day or just use the meal name
            shift = meal['name']
        
        # Verify employee exists and get their details
        cur.execute("SELECT * FROM employees WHERE id = %s", (employee_id,))
        employee = cur.fetchone()
        if not employee:
            return {'success': False, 'message': 'Employee not found.'}, 404
        
        # Verify meal exists
        cur.execute("SELECT * FROM meals WHERE id = %s", (meal_id,))
        meal = cur.fetchone()
        if not meal:
            return {'success': False, 'message': 'Meal not found.'}, 404
        
        # Verify location exists
        cur.execute("SELECT * FROM locations WHERE id = %s", (location_id,))
        location = cur.fetchone()
        if not location:
            return {'success': False, 'message': 'Location not found.'}, 404
        
        # Check if user has permission for this location
        if current_user.location and location['name'] != current_user.location:
            return {'success': False, 'message': 'Access denied for this location.'}, 403
        
        # Check if booking already exists for this employee, date, and shift
        cur.execute("""
            SELECT id FROM bookings 
            WHERE employee_id = %s AND booking_date = %s AND shift = %s
        """, (employee_id, booking_date, shift))
        existing_booking = cur.fetchone()
        if existing_booking:
            return {'success': False, 'message': f'Booking already exists for {employee["name"]} on {booking_date} for {shift}.'}, 400
        
        # Create the new booking
        cur.execute("""
            INSERT INTO bookings (employee_id, meal_id, booking_date, shift, status, location_id, booking_type)
            VALUES (%s, %s, %s, %s, 'Booked', %s, 'Manual')
        """, (employee_id, meal_id, booking_date, shift, location_id))
        
        booking_id = cur.lastrowid
        
        conn.commit()
        
        # Get employee and location names for the response
        cur.execute("SELECT name FROM locations WHERE id = %s", (location_id,))
        location_name = cur.fetchone()['name']
        
        return {
            'success': True, 
            'message': f'Meal booked successfully for {employee["name"]} (ID: {employee["employee_id"]}) for {shift} on {booking_date} at {location_name}',
            'booking_id': booking_id
        }
    
    except Exception as e:
        conn.rollback()
        return {'success': False, 'message': f'Error booking meal: {str(e)}'}
    
    finally:
        cur.close()
        conn.close()


@admin_bp.route('/transfer_booking_unit', methods=['POST'])
@login_required
def transfer_booking_unit():
    if current_user.role not in ['Master Admin', 'Unit-wise Admin']:
        return {'success': False, 'message': 'Access denied.'}, 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        booking_id = request.form.get('booking_id')
        new_location_id = request.form.get('new_location_id')
        
        if not all([booking_id, new_location_id]):
            return {'success': False, 'message': 'Booking ID and new location are required.'}, 400
        
        # Get the booking details
        cur.execute("""
            SELECT b.*, e.name as employee_name, l.name as location_name
            FROM bookings b
            JOIN employees e ON b.employee_id = e.id
            JOIN locations l ON b.location_id = l.id
            WHERE b.id = %s
        """, (booking_id,))
        booking = cur.fetchone()
        
        if not booking:
            return {'success': False, 'message': 'Booking not found.'}, 404
        
        # Verify new location exists
        cur.execute("SELECT * FROM locations WHERE id = %s", (new_location_id,))
        new_location = cur.fetchone()
        if not new_location:
            return {'success': False, 'message': 'New location not found.'}, 404
        
        # Permission logic: Master admin (a001) can transfer anywhere
        # Unit admins can transfer bookings from their assigned location to any location
        if current_user.employee_id != 'a001':  # Not master admin
            # Unit admin must have access to the original booking location
            if current_user.location and booking['location_name'] != current_user.location:
                return {'success': False, 'message': 'Access denied: You can only transfer bookings from your assigned unit.'}, 403
        
        # Check if a booking already exists for this employee, date, and shift at the new location
        cur.execute("""
            SELECT id FROM bookings
            WHERE employee_id = %s AND booking_date = %s AND shift = %s AND location_id = %s
        """, (booking['employee_id'], booking['booking_date'], booking['shift'], new_location_id))
        existing_booking = cur.fetchone()
        if existing_booking:
            return {'success': False, 'message': f"Booking already exists for {booking['employee_name']} at {new_location['name']} for {booking['shift']} on {booking['booking_date']}"}, 400
        
        # Update the booking to the new location
        cur.execute("""
            UPDATE bookings
            SET location_id = %s
            WHERE id = %s
        """, (new_location_id, booking_id))
        
        conn.commit()
        
        # Get location names for the response
        cur.execute("SELECT name FROM locations WHERE id = %s", (new_location_id,))
        new_location_name = cur.fetchone()['name']
        
        return {
            'success': True, 
            'message': f"Booking successfully transferred for {booking['employee_name']} from {booking['location_name']} to {new_location_name} for {booking['shift']} on {booking['booking_date']}"
        }
    
    except Exception as e:
        conn.rollback()
        return {'success': False, 'message': f"Error transferring booking: {str(e)}"}
    
    finally:
        cur.close()
        conn.close()

