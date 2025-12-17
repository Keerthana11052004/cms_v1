-- Update existing database schema for QR code functionality
-- Run this script to update your existing database

USE food;

-- Update bookings table to include 'Booked' status
ALTER TABLE bookings 
MODIFY COLUMN status ENUM('Booked', 'Consumed', 'Cancelled') DEFAULT 'Booked';

-- Add qr_code_data column if it doesn't exist (safe method)
SET @sql = (SELECT IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
     WHERE TABLE_SCHEMA = 'food' 
     AND TABLE_NAME = 'bookings' 
     AND COLUMN_NAME = 'qr_code_data') = 0,
    'ALTER TABLE bookings ADD COLUMN qr_code_data TEXT NULL AFTER location_id',
    'SELECT "qr_code_data column already exists" AS message'
));
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Update any existing pending bookings to booked status (if any exist)
UPDATE bookings SET status = 'Booked' WHERE status = 'Pending';

-- Add indexes if they don't exist (safe method)
SET @sql = (SELECT IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS 
     WHERE TABLE_SCHEMA = 'food' 
     AND TABLE_NAME = 'bookings' 
     AND INDEX_NAME = 'idx_employee_date_shift') = 0,
    'CREATE INDEX idx_employee_date_shift ON bookings(employee_id, booking_date, shift)',
    'SELECT "idx_employee_date_shift index already exists" AS message'
));
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS 
     WHERE TABLE_SCHEMA = 'food' 
     AND TABLE_NAME = 'bookings' 
     AND INDEX_NAME = 'idx_status') = 0,
    'CREATE INDEX idx_status ON bookings(status)',
    'SELECT "idx_status index already exists" AS message'
));
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Verify the changes
SELECT 'Database schema updated successfully!' AS status; 