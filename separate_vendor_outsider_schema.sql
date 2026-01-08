-- Schema to separate vendor and outsider meal data into distinct tables

USE food;

-- Create the outsider_meals table for storing outsider meal data
CREATE TABLE IF NOT EXISTS outsider_meals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    visitor_name VARCHAR(100) NOT NULL,
    unit VARCHAR(255),
    purpose VARCHAR(255),
    count INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_outsider_meals_unit ON outsider_meals(unit);
CREATE INDEX IF NOT EXISTS idx_outsider_meals_purpose ON outsider_meals(purpose);

-- Migrate existing outsider meal records from vendors table to outsider_meals table
-- This will move records where purpose starts with 'Outsider:'
INSERT INTO outsider_meals (visitor_name, unit, purpose, count)
SELECT name, unit, purpose, IFNULL(`count`, 1) 
FROM vendors 
WHERE purpose LIKE 'Outsider:%';

-- Remove the migrated records from vendors table
DELETE FROM vendors WHERE purpose LIKE 'Outsider:%';

-- Now the vendors table will only contain actual vendor information
-- with fields: name, contact_info, unit, food_licence_path, agreement_date
-- (cost field can be kept for vendor-related costs if needed)