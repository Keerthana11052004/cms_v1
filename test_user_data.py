from app.db_config import get_db_connection

# Check the data for user A001
conn = get_db_connection()
cur = conn.cursor()

cur.execute("SELECT * FROM employees WHERE employee_id = 'A001'")
user = cur.fetchone()

print("User A001 data:")
print(f"ID: {user['id']}")
print(f"Employee ID: {user['employee_id']}")
print(f"Name: {user['name']}")
print(f"Role ID: {user['role_id']}")
print(f"Location ID: {user['location_id']}")

# Check the role name
cur.execute("SELECT name FROM roles WHERE id = %s", (user['role_id'],))
role = cur.fetchone()
print(f"Role Name: {role['name']}")

# Check the location name
cur.execute("SELECT name FROM locations WHERE id = %s", (user['location_id'],))
location = cur.fetchone()
if location:
    print(f"Location Name: {location['name']}")
else:
    print("Location not found")

cur.close()
conn.close()