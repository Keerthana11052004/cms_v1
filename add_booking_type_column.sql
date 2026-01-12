-- Add booking_type column to track whether booking was made via biometric or app
USE food;

-- Add booking_type column with default value 'App'
ALTER TABLE bookings ADD COLUMN booking_type ENUM('Biometric', 'App') DEFAULT 'App' AFTER location_id;

-- Update any existing bookings to have 'App' as the booking type
UPDATE bookings SET booking_type = 'App' WHERE booking_type IS NULL;

-- Add index for better performance on booking_type column
CREATE INDEX idx_booking_type ON bookings(booking_type);

SELECT 'Booking type column added successfully!' AS message;