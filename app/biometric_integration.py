"""
Biometric Integration Module for ESSL MB160
Handles communication with the ESSL MB160 biometric device and meal booking
"""
try:
    from zk import ZK
except ImportError:
    print("⚠️ pyzk library not installed. Please install it using: pip install pyzk")
    ZK = None
from datetime import datetime, time
from .db_config import get_db_connection
import threading
import time as time_module
import logging

class BiometricMealBooking:
    def __init__(self, device_ip='192.168.105.200', port=4370, password=0, timeout=60):
        self.device_ip = device_ip
        self.port = port
        self.password = password
        self.timeout = timeout
        self.poll_interval = 10  # seconds
        # Initialize to start of today to catch today's punches but ignore older ones
        today_start = datetime.combine(datetime.now().date(), time.min)
        self.last_punch_time = today_start
        self.running = False
        self.zk = None
        self.conn = None
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def connect_device(self):
        """Connect to the ESSL MB160 device"""
        if ZK is None:
            self.logger.error("❌ ZK library not available. Please install pyzk.")
            return False
        
        try:
            self.zk = ZK(
                self.device_ip,
                port=self.port,
                timeout=self.timeout,
                password=self.password,
                force_udp=False,
                ommit_ping=False
            )
            
            self.conn = self.zk.connect()
            self.logger.info(f"✅ Connected to ESSL MB160 at {self.device_ip}")
            
            # Load users from device
            users = self.conn.get_users()
            self.user_map = {user.user_id: user.name for user in users}
            self.logger.info(f"👤 Users Loaded: {len(users)}")
            
            return True
        except Exception as e:
            self.logger.error(f"❌ Connection failed: {e}")
            return False

    def disconnect_device(self):
        """Disconnect from the biometric device"""
        try:
            if self.conn:
                self.conn.disconnect()
                self.logger.info("Disconnected from biometric device")
                self.conn = None
        except Exception as e:
            # Don't log connection reset errors as severe errors
            if 'forcibly closed' in str(e) or '10054' in str(e):
                self.logger.info("Biometric device connection already closed by remote host")
            else:
                self.logger.error(f"Error disconnecting: {e}")
        finally:
            self.conn = None

    def get_meal_type_by_time(self, punch_time):
        """Determine meal type based on punch time"""
        punch_hour = punch_time.hour
        punch_minute = punch_time.minute
        
        # Time-based meal booking logic with your specified timings:
        # Breakfast: 5 AM to 8 AM
        # Lunch: 8 AM to 2 PM
        # Dinner: 2 PM to 10 PM
        if 5 <= punch_hour < 8:  # 5 AM - 8 AM
            return ['Breakfast']
        elif 8 <= punch_hour < 14:  # 8 AM - 2 PM
            return ['Lunch']
        elif 14 <= punch_hour < 22:  # 2 PM - 10 PM
            return ['Dinner']
        else:
            # Outside normal booking hours, default to next meal
            current_time = datetime.now().time()
            if time(5, 0) <= current_time < time(8, 0):
                return ['Breakfast']
            elif time(8, 0) <= current_time < time(14, 0):
                return ['Lunch']
            elif time(14, 0) <= current_time < time(22, 0):
                return ['Dinner']
            else:
                return ['Dinner']  # Default to dinner for late night hours

    def book_meal(self, user_id, meal_types, booking_date=None):
        """Book meal(s) for a user based on their biometric ID"""
        if booking_date is None:
            from datetime import date
            booking_date = date.today()
        
        conn_db = None
        cur = None
        
        try:
            conn_db = get_db_connection()
            cur = conn_db.cursor()
            
            # First, check if employee exists in our system
            cur.execute("SELECT id, employee_id, location_id FROM employees WHERE employee_id = %s", (str(user_id),))
            employee = cur.fetchone()
            
            if not employee:
                self.logger.warning(f"Employee with ID {user_id} not found in our system")
                return False
            
            employee_db_id = employee['id']
            location_id = employee['location_id']
            
            if not location_id:
                self.logger.warning(f"Employee {user_id} does not have a location set")
                return False
            
            # Check if each specific meal type is already booked for today
            meal_types_to_book = []
            for meal_type in meal_types:
                cur.execute("""
                    SELECT id FROM bookings 
                    WHERE employee_id = %s AND booking_date = %s AND shift = %s AND status = 'Booked'
                """, (employee_db_id, booking_date, meal_type))
                
                existing_booking = cur.fetchone()
                if existing_booking:
                    self.logger.info(f"User {user_id} already has a {meal_type} booked for today")
                else:
                    meal_types_to_book.append(meal_type)
            
            meal_types = meal_types_to_book  # Update meal_types to only include ones that need to be booked
            
            # Book each meal type
            for meal_type in meal_types:
                # Get meal ID
                cur.execute("SELECT id FROM meals WHERE name = %s", (meal_type,))
                meal = cur.fetchone()
                
                if not meal:
                    self.logger.error(f"Meal type {meal_type} not found in database")
                    continue
                
                meal_id = meal['id']
                
                # Insert booking record
                cur.execute("""
                    INSERT INTO bookings (employee_id, employee_id_str, meal_id, booking_date, shift, location_id, booking_type, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (employee_db_id, str(user_id), meal_id, booking_date, meal_type, location_id, 'Biometric', 'Booked'))
                
                booking_id = cur.lastrowid
                
                # Generate QR code for the booking
                from .utils import generate_meal_qr_code
                qr_image_base64, qr_data_string = generate_meal_qr_code(
                    booking_id=booking_id,
                    employee_id=str(user_id),
                    date=str(booking_date),
                    shift=meal_type
                )
                
                # Update booking with QR code
                cur.execute("""
                    UPDATE bookings SET qr_code_data = %s
                    WHERE id = %s
                """, (qr_image_base64, booking_id))
                
                self.logger.info(f"✅ Meal booked for user {user_id} - {meal_type}")
            
            conn_db.commit()
            # Return True if at least one new meal was booked, False if all were duplicates
            return len(meal_types_to_book) > 0
            
        except Exception as e:
            self.logger.error(f"Error booking meal: {e}")
            if conn_db:
                conn_db.rollback()
            return False
        finally:
            if cur:
                cur.close()
            if conn_db:
                conn_db.close()

    def poll_biometric_device(self):
        """Poll the biometric device for new punches"""
        while self.running:
            try:
                if not self.conn:
                    if not self.connect_device():
                        time_module.sleep(10)  # Wait 10 seconds before retrying
                        continue

                logs = self.conn.get_attendance() if self.conn else []

                for log in logs:
                    punch_time = log.timestamp

                    # Process only NEW punches
                    if self.last_punch_time is None or punch_time > self.last_punch_time:
                        user_id = log.user_id
                        name = self.user_map.get(user_id, "Unknown")

                        self.logger.info(
                            f"🟢 PUNCH DETECTED | "
                            f"UserID: {user_id} | "
                            f"Name: {name} | "
                            f"Time: {punch_time}"
                        )

                        # Determine meal type based on time
                        meal_types = self.get_meal_type_by_time(punch_time)
                        
                        # Book meal(s) based on punch
                        success = self.book_meal(user_id, meal_types, punch_time.date())
                        
                        if success:
                            self.logger.info(f"🍽️ Meals booked successfully for {name} (ID: {user_id})")
                        else:
                            self.logger.warning(f"❌ Failed to book meal for {name} (ID: {user_id})")

                        self.last_punch_time = punch_time

                time_module.sleep(self.poll_interval)

            except Exception as e:
                error_msg = str(e)
                if 'forcibly closed' in error_msg or '10054' in error_msg or 'connection lost' in error_msg.lower():
                    self.logger.info(f"⚠️ Biometric device connection lost: {e}")
                else:
                    self.logger.error(f"⚠️ Polling error: {e}")
                
                self.disconnect_device()
                time_module.sleep(5)  # Wait before reconnecting

    def start_polling(self):
        """Start polling the biometric device in a separate thread"""
        if ZK is None:
            self.logger.error("❌ Cannot start biometric polling: ZK library not available. Please install pyzk.")
            return False
        
        if not self.connect_device():
            return False
            
        self.running = True
        self.poll_thread = threading.Thread(target=self.poll_biometric_device)
        self.poll_thread.daemon = True
        self.poll_thread.start()
        self.logger.info("🔄 Biometric polling started")
        return True

    def stop_polling(self):
        """Stop polling the biometric device"""
        self.running = False
        self.disconnect_device()
        self.logger.info("🛑 Biometric polling stopped")

# Global instance for the application
biometric_booking = BiometricMealBooking()


class BiometricMealConsumption:
    def __init__(self, device_ip='192.168.105.201', port=4370, password=0, timeout=60):
        self.device_ip = device_ip
        self.port = port
        self.password = password
        self.timeout = timeout
        self.poll_interval = 10  # seconds
        # Initialize to start of today to catch today's punches but ignore older ones
        today_start = datetime.combine(datetime.now().date(), time.min)
        self.last_punch_time = today_start
        self.running = False
        self.zk = None
        self.conn = None
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__ + '_consumption')

    def connect_device(self):
        """Connect to the ESSL MB160 device for consumption verification"""
        if ZK is None:
            self.logger.error("❌ ZK library not available. Please install pyzk.")
            return False
        
        try:
            self.zk = ZK(
                self.device_ip,
                port=self.port,
                timeout=self.timeout,
                password=self.password,
                force_udp=False,
                ommit_ping=False
            )
            
            self.conn = self.zk.connect()
            self.logger.info(f"✅ Connected to ESSL MB160 at {self.device_ip} for consumption verification")
            
            # Load users from device
            users = self.conn.get_users()
            self.user_map = {user.user_id: user.name for user in users}
            self.logger.info(f"👤 Users Loaded: {len(users)} for consumption verification")
            
            return True
        except Exception as e:
            self.logger.error(f"❌ Connection failed: {e}")
            return False

    def disconnect_device(self):
        """Disconnect from the biometric device"""
        try:
            if self.conn:
                self.conn.disconnect()
                self.logger.info("Disconnected from biometric consumption device")
                self.conn = None
        except Exception as e:
            # Don't log connection reset errors as severe errors
            if 'forcibly closed' in str(e) or '10054' in str(e):
                self.logger.info("Biometric consumption device connection already closed by remote host")
            else:
                self.logger.error(f"Error disconnecting: {e}")
        finally:
            self.conn = None

    def verify_consumption(self, user_id, vendor_location_id=None, vendor_id=None):
        """Verify meal consumption for a user based on their biometric ID"""
        conn_db = None
        cur = None
        
        try:
            conn_db = get_db_connection()
            cur = conn_db.cursor()
            
            # First, check if employee exists in our system
            cur.execute("SELECT id, name, employee_id FROM employees WHERE employee_id = %s", (str(user_id),))
            employee = cur.fetchone()
            
            if not employee:
                self.logger.warning(f"Employee with ID {user_id} not found in our system")
                return {'success': False, 'message': f'Employee with biometric ID {user_id} not found in system.'}
            
            employee_db_id = employee['id']
            employee_name = employee['name']
            employee_id = employee['employee_id']
            
            # Find today's booking for this employee that is still 'Booked'
            from datetime import date
            today = date.today()
            cur.execute("""
                SELECT b.*, m.name as meal_name, l.name as location_name, l.id as location_id
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
                return {
                    'success': False,
                    'message': f'{employee_name} (ID: {employee_id}) needs to book meals before consumption.',
                    'booking': {
                        'employee_name': employee_name,
                        'employee_id': employee_id,
                        'date': today.strftime('%Y-%m-%d'),
                        'status': 'No Booking'
                    }
                }
            
            # Check the booking status
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
                
                return {
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
            
            elif status.strip() != 'Booked':
                return {
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
            
            # Determine location for consumption logging
            # If vendor_location_id is provided, use that location (for cross-location consumption)
            # Otherwise, use the original booking location
            consumption_location_id = booking['location_id'] if vendor_location_id is None else vendor_location_id
            consumption_location_name = booking['location_name'] if vendor_location_id is None else self._get_location_name_by_id(cur, vendor_location_id)
            
            # Update booking status to consumed
            cur.execute("""
                UPDATE bookings 
                SET status = 'Consumed', consumed_at = NOW() 
                WHERE id = %s
            """, (booking['id'],))
            
            # Log the consumption
            cur.execute("""
                INSERT INTO meal_consumption_log (booking_id, employee_id, meal_id, location_id, vendor_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (booking['id'], employee_db_id, booking['meal_id'], consumption_location_id, vendor_id))  # vendor_id can be None when called from polling service
            
            conn_db.commit()
            
            return {
                'success': True,
                'message': f'✅ Meal Consumed Successfully for {employee_name} (ID: {employee_id})',
                'booking': {
                    'employee_name': employee_name,
                    'employee_id': employee_id,
                    'unit': consumption_location_name,  # Show the location where consumption happened
                    'date': booking['booking_date'].strftime('%Y-%m-%d'),
                    'shift': booking['shift'],
                    'status': 'Consumed'
                }
            }
        
        except Exception as e:
            self.logger.error(f"Error processing meal consumption: {e}")
            if conn_db:
                conn_db.rollback()
            return {'success': False, 'message': f'Error processing meal: {str(e)}'}
        finally:
            if cur:
                cur.close()
            if conn_db:
                conn_db.close()  # Make sure to close the connection
    
    def _get_location_name_by_id(self, cur, location_id):
        """Helper method to get location name by ID"""
        cur.execute("SELECT name FROM locations WHERE id = %s", (location_id,))
        result = cur.fetchone()
        return result['name'] if result else 'Unknown Location'


    def start_service(self):
        """Start the biometric consumption service"""
        if ZK is None:
            self.logger.error("❌ Cannot start biometric consumption service: ZK library not available. Please install pyzk.")
            return False
        
        if not self.connect_device():
            return False
            
        self.running = True
        self.logger.info("🔄 Biometric consumption service ready")
        return True

    def poll_biometric_device(self):
        """Poll the biometric consumption device for new punches to mark as consumed"""
        while self.running:
            try:
                if not self.conn:
                    if not self.connect_device():
                        time_module.sleep(10)  # Wait 10 seconds before retrying
                        continue

                logs = self.conn.get_attendance() if self.conn else []

                for log in logs:
                    punch_time = log.timestamp

                    # Process only NEW punches
                    if self.last_punch_time is None or punch_time > self.last_punch_time:
                        user_id = log.user_id
                        name = self.user_map.get(user_id, "Unknown")

                        self.logger.info(
                            f"🟢 PUNCH DETECTED | "
                            f"UserID: {user_id} | "
                            f"Name: {name} | "
                            f"Time: {punch_time}"
                        )

                        # Verify meal consumption based on punch
                        # For background polling service, use default parameters (no vendor location override)
                        result = self.verify_consumption(user_id, vendor_location_id=None, vendor_id=None)
                        
                        if result['success']:
                            self.logger.info(f"🍽️ Meal consumed successfully for {name} (ID: {user_id})")
                        else:
                            # Log the reason for failure (e.g., no booking, already consumed, etc.)
                            self.logger.warning(f"❌ Failed to process consumption for {name} (ID: {user_id}): {result.get('message', 'Unknown error')}")

                        self.last_punch_time = punch_time

                time_module.sleep(10)  # Poll every 10 seconds

            except Exception as e:
                error_msg = str(e)
                if 'forcibly closed' in error_msg or '10054' in error_msg or 'connection lost' in error_msg.lower():
                    self.logger.info(f"⚠️ Biometric consumption device connection lost: {e}")
                else:
                    self.logger.error(f"⚠️ Consumption polling error: {e}")
                
                self.disconnect_device()
                time_module.sleep(5)  # Wait before reconnecting

    def start_polling(self):
        """Start polling the biometric consumption device in a separate thread"""
        if ZK is None:
            self.logger.error("❌ Cannot start biometric consumption polling: ZK library not available. Please install pyzk.")
            return False
        
        if not self.connect_device():
            return False
            
        self.running = True
        self.poll_thread = threading.Thread(target=self.poll_biometric_device)
        self.poll_thread.daemon = True
        self.poll_thread.start()
        self.logger.info("🔄 Biometric consumption polling started")
        return True

    def stop_service(self):
        """Stop the biometric consumption service"""
        self.running = False
        self.disconnect_device()
        self.logger.info("🛑 Biometric consumption service stopped")


# Global instance for consumption verification
biometric_consumption = BiometricMealConsumption()

def start_biometric_service():
    """Start the biometric service"""
    return biometric_booking.start_polling()

def stop_biometric_service():
    """Stop the biometric service"""
    biometric_booking.stop_polling()

def clear_biometric_attendance():
    """Clear all attendance data from the biometric device"""
    if ZK is None:
        print("❌ Cannot clear attendance: ZK library not available. Please install pyzk.")
        return False
    
    try:
        zk = ZK('192.168.105.200', port=4370, timeout=60, password=0)
        conn = zk.connect()
        
        # Clear attendance data
        conn.clear_attendance()
        print("🗑️ All attendance data cleared successfully")
        
        conn.disconnect()
        return True
    except Exception as e:
        print(f"❌ Failed to clear attendance data: {e}")
        return False

def clear_old_punches_except_today():
    """Clear only old punch data, keeping today's data"""
    if ZK is None:
        print("❌ Cannot clear old punches: ZK library not available. Please install pyzk.")
        return False
    
    try:
        from datetime import date
        
        zk = ZK('192.168.105.200', port=4370, timeout=60, password=0)
        conn = zk.connect()
        
        # Get all attendance logs
        attendance_logs = conn.get_attendance()
        
        # Filter logs to keep only today's punches
        today = date.today()
        old_punches_count = 0
        
        for log in attendance_logs:
            if log.timestamp.date() != today:
                old_punches_count += 1
        
        print(f"Found {len(attendance_logs)} total punches")
        print(f"{len(attendance_logs) - old_punches_count} punches from today ({today})")
        print(f"{old_punches_count} old punches from previous dates")
        
        # Since the pyzk library doesn't support deleting specific records,
        # we inform the user about the limitation
        if old_punches_count > 0:
            print("⚠️ The pyzk library doesn't support deleting specific records.")
            print("The device stores all punches and doesn't have selective deletion capability.")
            print("For your use case (meal booking), only recent punches matter.")
            conn.disconnect()
            return False
        else:
            print("No old punches to delete - all punches are from today")
            conn.disconnect()
            return True
    
    except Exception as e:
        print(f"❌ Failed to process old punches: {e}")
        return False

def sync_cms_users_to_biometric():
    """Sync users from CMS database to the biometric device"""
    if ZK is None:
        print("❌ Cannot sync users: ZK library not available. Please install pyzk.")
        return False
    
    conn_db = None
    cur = None
    
    try:
        # Connect to the biometric device
        zk = ZK('192.168.105.200', port=4370, timeout=60, password=0)
        conn_bio = zk.connect()
        
        # Get users from CMS database
        conn_db = get_db_connection()
        cur = conn_db.cursor()
        
        # Get all active employees from the CMS database
        cur.execute("SELECT employee_id, name FROM employees WHERE is_active = 1 OR is_active IS NULL")
        cms_users = cur.fetchall()
        
        print(f"Found {len(cms_users)} users in CMS database")
        
        # Get existing users on the biometric device
        bio_users = conn_bio.get_users()
        bio_user_ids = {user.user_id for user in bio_users}
        
        print(f"Found {len(bio_users)} users on biometric device")
        
        # Sync users from CMS to biometric device
        synced_count = 0
        for cms_user in cms_users:
            employee_id = cms_user['employee_id']
            name = cms_user['name']
            
            # Check if the employee ID is numeric (required for biometric device)
            try:
                user_id = int(employee_id)
            except (ValueError, TypeError):
                print(f"⚠️ Skipping user {name} with non-numeric employee ID: {employee_id}")
                continue
            
            # Check if user already exists on the device
            if str(user_id) in bio_user_ids:
                print(f"User {name} (ID: {user_id}) already exists on device")
                continue
            
            # Add user to the biometric device
            try:
                # The ZK library's set_user method adds a new user to the device
                conn_bio.set_user(
                    user_id=str(user_id),
                    name=name,
                    password='',  # No password required
                    card=0  # No card number
                )
                print(f"✅ Added user {name} (ID: {user_id}) to biometric device")
                synced_count += 1
            except Exception as e:
                print(f"❌ Failed to add user {name} (ID: {user_id}) to device: {e}")
        
        print(f"✅ Sync completed. {synced_count} users added to biometric device.")
        
        conn_bio.disconnect()
        return True
        
    except Exception as e:
        print(f"❌ Failed to sync users: {e}")
        return False
    
    finally:
        if cur:
            cur.close()
        if conn_db:
            conn_db.close()