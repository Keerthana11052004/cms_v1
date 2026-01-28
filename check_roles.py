from app.db_config import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

print("=== Roles in Database ===")
cur.execute('SELECT id, name FROM roles ORDER BY id')
roles = cur.fetchall()

for role in roles:
    print(f"  {role['id']}: {role['name']}")

print("\n=== A002 User Details ===")
cur.execute('SELECT employee_id, name, role_id, is_active FROM employees WHERE employee_id = %s', ('A002',))
user = cur.fetchone()
if user:
    print(f"  Employee ID: {user['employee_id']}")
    print(f"  Name: {user['name']}")
    print(f"  Role ID: {user['role_id']}")
    print(f"  Is Active: {user['is_active']}")

cur.close()
conn.close()