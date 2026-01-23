from app.db_config import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

# Check specific employee
cur.execute("SELECT id, name, location_id FROM employees WHERE employee_id = 'e001'")
emp = cur.fetchone()
if emp:
    print(f"Employee e001: {emp['name']} at Location {emp['location_id']}")

# Check session data for unit selection
print("\nSession unit selection would need to be checked in the browser")

cur.close()
conn.close()