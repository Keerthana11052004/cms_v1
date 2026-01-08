import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    # Connect to database
    connection = mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'food'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', '')
    )
    
    if connection.is_connected():
        cursor = connection.cursor()
        
        # Check if outsider_meals table exists
        cursor.execute("SHOW TABLES LIKE 'outsider_meals';")
        result = cursor.fetchone()
        if result:
            print('outsider_meals table exists')
        else:
            print('outsider_meals table does not exist, creating it...')
            # Create the outsider_meals table
            create_table_query = '''
            CREATE TABLE outsider_meals (
                id INT AUTO_INCREMENT PRIMARY KEY,
                visitor_name VARCHAR(100) NOT NULL,
                unit VARCHAR(255),
                purpose VARCHAR(255),
                count INT DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            '''
            cursor.execute(create_table_query)
            print('Created outsider_meals table')
            
            # Add indexes
            cursor.execute('CREATE INDEX idx_outsider_meals_unit ON outsider_meals(unit);')
            cursor.execute('CREATE INDEX idx_outsider_meals_purpose ON outsider_meals(purpose);')
            print('Added indexes to outsider_meals table')
        
        # Check for outsider records in vendors table
        cursor.execute("SELECT COUNT(*) FROM vendors WHERE purpose LIKE 'Outsider:%';")
        outsider_count = cursor.fetchone()[0]
        print(f'Found {outsider_count} outsider records in vendors table')
        
        if outsider_count > 0:
            print('Migrating outsider records...')
            # Migrate existing outsider meal records from vendors table to outsider_meals table
            migrate_query = '''
            INSERT INTO outsider_meals (visitor_name, unit, purpose, count)
            SELECT name, unit, purpose, IFNULL(`count`, 1) 
            FROM vendors 
            WHERE purpose LIKE 'Outsider:%';
            '''
            cursor.execute(migrate_query)
            print(f'Migrated {cursor.rowcount} outsider meal records')
            
            # Remove the migrated records from vendors table
            delete_query = "DELETE FROM vendors WHERE purpose LIKE 'Outsider:%';"
            cursor.execute(delete_query)
            print(f'Deleted {cursor.rowcount} outsider meal records from vendors table')
        
        connection.commit()
        print('Database schema update completed successfully!')

except Error as e:
    print(f'Database Error: {e}')
except Exception as e:
    print(f'Error: {e}')
finally:
    if connection.is_connected():
        cursor.close()
        connection.close()
        print('MySQL connection closed')