#!/usr/bin/env python3
"""Script to fix the transfer_booking_unit function in admin.py"""

import re

def fix_transfer_booking_unit():
    # Read the entire file
    with open('app/admin.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the start and end of the function
    start_pos = content.find('def transfer_booking_unit():')
    if start_pos != -1:
        # Find the end by looking for the next function or the end of the file
        # Look for conn.close() which should be in the finally block
        end_pos = content.find('conn.close()', start_pos)
        if end_pos != -1:
            # Find the end of that line
            end_pos = content.find('\n', end_pos)
            if end_pos == -1:
                end_pos = len(content)  # End of file
        
        # Define the correct function
        correct_function = """def transfer_booking_unit():
    if current_user.role != 'Admin':
        return {'success': False, 'message': 'Access denied.'}, 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        booking_id = request.form.get('booking_id')
        new_location_id = request.form.get('new_location_id')
        
        if not all([booking_id, new_location_id]):
            return {'success': False, 'message': 'Booking ID and new location are required.'}, 400
        
        # Get the booking details
        cur.execute(\"\"\"
            SELECT b.*, e.name as employee_name, l.name as location_name
            FROM bookings b
            JOIN employees e ON b.employee_id = e.id
            JOIN locations l ON b.location_id = l.id
            WHERE b.id = %s
        \"\"\", (booking_id,))
        booking = cur.fetchone()
        
        if not booking:
            return {'success': False, 'message': 'Booking not found.'}, 404
        
        # Verify new location exists
        cur.execute(\"SELECT * FROM locations WHERE id = %s\", (new_location_id,))
        new_location = cur.fetchone()
        if not new_location:
            return {'success': False, 'message': 'New location not found.'}, 404
        
        # Check if user has permission for the new location
        if current_user.location and new_location['name'] != current_user.location:
            return {'success': False, 'message': 'Access denied for the target location.'}, 403
        
        # Check if a booking already exists for this employee, date, and shift at the new location
        cur.execute(\"\"\"
            SELECT id FROM bookings
            WHERE employee_id = %s AND booking_date = %s AND shift = %s AND location_id = %s
        \"\"\", (booking['employee_id'], booking['booking_date'], booking['shift'], new_location_id))
        existing_booking = cur.fetchone()
        if existing_booking:
            return {'success': False, 'message': f'Booking already exists for {booking[\"employee_name\"]} at {new_location[\"name\"]] for {booking[\"shift\"]} on {booking[\"booking_date\"]}.'}, 400
        
        # Update the booking to the new location
        cur.execute(\"\"\"
            UPDATE bookings
            SET location_id = %s
            WHERE id = %s
        \"\"\", (new_location_id, booking_id))
        
        conn.commit()
        
        # Get location names for the response
        cur.execute(\"SELECT name FROM locations WHERE id = %s\", (new_location_id,))
        new_location_name = cur.fetchone()['name']
        
        return {
            'success': True, 
            'message': f'Booking successfully transferred for {booking[\"employee_name\"]} from {booking[\"location_name\"]} to {new_location_name} for {booking[\"shift\"]} on {booking[\"booking_date\"]}'
        }
    
    except Exception as e:
        conn.rollback()
        return {'success': False, 'message': f'Error transferring booking: {str(e)}'}
    
    finally:
        cur.close()
        conn.close()"""

        # Replace the function
        new_content = content[:start_pos] + correct_function + content[end_pos:]
        
        # Write back to file
        with open('app/admin.py', 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print('Successfully fixed the transfer_booking_unit function')
    else:
        print('Function not found')

if __name__ == "__main__":
    fix_transfer_booking_unit()