-- Database migration to add meal_type column to vendors table
-- Run this SQL command in your MySQL database

USE food;

-- Add meal_type column to vendors table
ALTER TABLE vendors 
ADD COLUMN meal_type VARCHAR(50) AFTER unit;

-- Verify the column was added
DESCRIBE vendors;
