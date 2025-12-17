-- Add daily_menus table
CREATE TABLE daily_menus (
    id INT AUTO_INCREMENT PRIMARY KEY,
    location_id INT NOT NULL,
    menu_date DATE NOT NULL,
    meal_type ENUM('Breakfast', 'Lunch', 'Dinner') NOT NULL,
    items TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (location_id) REFERENCES locations(id),
    UNIQUE KEY (location_id, menu_date, meal_type)
);