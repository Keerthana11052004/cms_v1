-- Canteen Management System Schema for 'food' database
-- Run this script in your MySQL client

CREATE DATABASE IF NOT EXISTS food;
USE food;

-- Locations Table
CREATE TABLE locations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

-- Departments Table
CREATE TABLE departments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

-- Roles Table
CREATE TABLE roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE -- e.g., Employee, Staff, Supervisor, HR, Accounts, Admin
);

-- Employees Table
CREATE TABLE employees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255), -- nullable if using SSO
    department_id INT,
    location_id INT,
    role_id INT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(id),
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (role_id) REFERENCES roles(id)
);

-- Vendors Table (for reimbursement)
CREATE TABLE vendors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    contact_info VARCHAR(255),
    purpose VARCHAR(255),
    cost DECIMAL(10,2)
);

-- Meals Table
CREATE TABLE meals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name ENUM('Breakfast', 'Lunch', 'Dinner') NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    cost DECIMAL(10,2) NOT NULL,
    subsidy DECIMAL(10,2) NOT NULL
);

-- Bookings Table
CREATE TABLE bookings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    meal_id INT NOT NULL,
    booking_date DATE NOT NULL,
    shift ENUM('Breakfast', 'Lunch', 'Dinner') NOT NULL,
    recurrence ENUM('None', 'Daily', 'Weekly') DEFAULT 'None',
    status ENUM('Booked', 'Consumed', 'Cancelled') DEFAULT 'Booked',
    location_id INT NOT NULL,
    qr_code_data TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    consumed_at TIMESTAMP NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(id),
    FOREIGN KEY (meal_id) REFERENCES meals(id),
    FOREIGN KEY (location_id) REFERENCES locations(id)
);

-- QR Tokens Table
CREATE TABLE qr_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT NOT NULL,
    token VARCHAR(255) NOT NULL UNIQUE,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    scanned_at TIMESTAMP NULL,
    status ENUM('Active', 'Scanned', 'Expired') DEFAULT 'Active',
    FOREIGN KEY (booking_id) REFERENCES bookings(id)
);

-- Meal Consumption Log (for audit)
CREATE TABLE meal_consumption_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT NOT NULL,
    employee_id INT NOT NULL,
    meal_id INT NOT NULL,
    location_id INT NOT NULL,
    consumed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    staff_id INT, -- who validated
    FOREIGN KEY (booking_id) REFERENCES bookings(id),
    FOREIGN KEY (employee_id) REFERENCES employees(id),
    FOREIGN KEY (meal_id) REFERENCES meals(id),
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (staff_id) REFERENCES employees(id)
);

-- Special Messages Table
CREATE TABLE special_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    message_text TEXT NOT NULL,
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pre-populate Locations
INSERT INTO locations (name) VALUES
('Unit 1'), ('Unit 2'), ('Unit 3'), ('Unit 4'), ('Unit 5'), ('Pallavaram');

-- Pre-populate Roles
INSERT INTO roles (name) VALUES
('Employee'), ('Staff'), ('Supervisor'), ('HR'), ('Accounts'), ('Admin');

-- Example Departments (add as needed)
INSERT INTO departments (name) VALUES
('IT'), ('HR'), ('Finance'), ('Operations'), ('Admin');

-- Pre-populate Meals
INSERT INTO meals (name, start_time, end_time, cost, subsidy) VALUES
('Breakfast', '07:00:00', '09:00:00', 50.00, 30.00),
('Lunch', '12:00:00', '14:00:00', 100.00, 60.00),
('Dinner', '19:00:00', '21:00:00', 80.00, 50.00); 