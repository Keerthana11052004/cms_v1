-- Simple database fix for QR code functionality
-- Run this script to add the missing qr_code_data column

USE food;

-- Add qr_code_data column
ALTER TABLE bookings ADD COLUMN qr_code_data TEXT NULL AFTER location_id;

-- Update status enum to remove Pending
ALTER TABLE bookings MODIFY COLUMN status ENUM('Booked', 'Consumed', 'Cancelled') DEFAULT 'Booked';

-- Add performance indexes
CREATE INDEX idx_employee_date_shift ON bookings(employee_id, booking_date, shift);
CREATE INDEX idx_status ON bookings(status);

SELECT 'Database fixed successfully!' AS message; 