USE food;

ALTER TABLE vendors
ADD COLUMN food_licence_status VARCHAR(255) DEFAULT 'Pending',
ADD COLUMN agreement_date DATE,
ADD COLUMN unit VARCHAR(255),
ADD COLUMN count INT;