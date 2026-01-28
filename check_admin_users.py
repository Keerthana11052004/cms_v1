from app.db_config import get_db_connection

# Check all employees and their roles
conn = get_db_connection()
cur = conn.cursor()

print("=== All Employees ===")
cur.execute("""
    SELECT e.id, e.employee_id, e.name, e.email, r.name as role_name, l.name as location_name
    FROM employees e
    LEFT JOIN roles r ON e.role_id = r.id
    LEFT JOIN locations l ON e.location_id = l.id
    ORDER BY e.employee_id
""")
employees = cur.fetchall()

for emp in employees:
    print(f"ID: {emp['id']}, Employee_ID: {emp['employee_id']}, Name: {emp['name']}, Role: {emp['role_name']}, Location: {emp['location_name']}")

print("\n=== Admin Users Only ===")
cur.execute("""
    SELECT e.id, e.employee_id, e.name, e.email, r.name as role_name, l.name as location_name
    FROM employees e
    JOIN roles r ON e.role_id = r.id
    LEFT JOIN locations l ON e.location_id = l.id
    WHERE r.name IN ('Master Admin', 'Unit-wise Admin')
    ORDER BY e.employee_id
""")
admin_users = cur.fetchall()

for admin in admin_users:
    print(f"ID: {admin['id']}, Employee_ID: {admin['employee_id']}, Name: {admin['name']}, Role: {admin['role_name']}, Location: {admin['location_name']}")

print(f"\nTotal admin users found: {len(admin_users)}")

cur.close()
conn.close()