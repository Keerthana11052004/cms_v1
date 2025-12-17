import qrcode
import json
import base64
from io import BytesIO
from datetime import datetime
from . import Curr_Proj_Name, mysql, User
from .db_config import get_db_connection

def generate_meal_qr_code(booking_id, employee_id, date, shift):
    """
    Generate a QR code with a unique booking ID.
    Args:
        booking_id (int): The unique ID of the booking.
        employee_id (str): Employee ID.
        date (str): Booking date.
        shift (str): Meal shift (Breakfast/Lunch/Dinner).
    Returns:
        tuple: (qr_code_image_base64, qr_code_data_string)
    """
    # Create a unique, comma-separated string for the QR code
    qr_data_string = f"{booking_id},{employee_id},{date},{shift}"
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data_string)
    qr.make(fit=True)
    # Create QR code image
    img = qr.make_image(fill_color="black", back_color="white")
    # Convert to base64 for storage/display
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    qr_image_base64 = base64.b64encode(buffer.getvalue()).decode()
    return qr_image_base64, qr_data_string

def decode_qr_code(qr_data_string):
    """
    Decode QR code data from a comma-separated string into a dictionary.
    Args:
        qr_data_string (str): Comma-separated string from the QR code.
    Returns:
        dict: Decoded QR code data, or None if the format is invalid.
    """
    try:
        parts = qr_data_string.split(',')
        if len(parts) == 4:
            return {
                'booking_id': parts[0],
                'employee_id': parts[1],
                'date': parts[2],
                'shift': parts[3]
            }
    except Exception:
        # Log the error or handle it as needed
        pass
    return None

from flask import session
from flask_login import current_user
from datetime import date

def get_menu_context(mysql):
    """
    Fetches data for today's menu and unit selection for the sidebar.
    This function is intended to be used as a Flask context processor.
    """
    todays_menu = []
    locations = []
    selected_unit_id = None
    selected_unit_name = "Select Unit"

    conn = get_db_connection()
    cur = conn.cursor()
    today = date.today()

    # Fetch all locations for the unit selection dropdown
    cur.execute("SELECT id, name FROM locations ORDER BY name")
    locations = cur.fetchall()

    # Determine the location for displaying the menu
    # Priority: session selected_unit_id > user's default location > first available location
    selected_unit_id = session.get('selected_unit_id')
    
    if selected_unit_id is None and current_user.is_authenticated:
        # If no unit selected in session, try to get user's default location
        cur.execute("SELECT location_id FROM employees WHERE id = %s", (current_user.id,))
        user_location = cur.fetchone()
        if user_location and user_location['location_id'] is not None:
            selected_unit_id = user_location['location_id']
        elif locations:
            # Fallback to the first available location if user has no default
            selected_unit_id = locations[0]['id']
            session['selected_unit_id'] = selected_unit_id # Store for consistency
        else:
            selected_unit_id = None # Ensure it's None if no locations are available
    elif selected_unit_id is None and not current_user.is_authenticated and locations:
        # If not logged in and no unit in session, default to first location
        selected_unit_id = locations[0]['id']
        session['selected_unit_id'] = selected_unit_id

    if selected_unit_id:
        # Fetch today's menu for the determined location
        cur.execute("""
            SELECT meal_type, items
            FROM daily_menus
            WHERE location_id = %s AND menu_date = %s
            ORDER BY FIELD(meal_type, 'Breakfast', 'Lunch', 'Dinner')
        """, (selected_unit_id, today))
        todays_menu = cur.fetchall()

        # Get the name of the selected unit
        cur.execute("SELECT name FROM locations WHERE id = %s", (selected_unit_id,))
        unit_name_result = cur.fetchone()
        if unit_name_result:
            selected_unit_name = unit_name_result['name']
            
    cur.close()
    conn.close()
    
    return {
        'todays_menu': todays_menu,
        'locations': locations,
        'selected_unit_id': selected_unit_id,
        'selected_unit_name': selected_unit_name
    }