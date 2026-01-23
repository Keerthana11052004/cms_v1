from app.db_config import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

# Check locations
print("=== LOCATIONS ===")
cur.execute('SELECT id, name FROM locations ORDER BY id')
locations = cur.fetchall()
for loc in locations:
    print(f"{loc['id']}: {loc['name']}")

print("\n=== MENU DATA ===")
cur.execute('SELECT * FROM daily_menus WHERE menu_date = "2026-01-23"')
menus = cur.fetchall()
for menu in menus:
    print(f"Location {menu['location_id']}: {menu['meal_type']} - {menu['items']}")

print("\n=== EMPLOYEE SAMPLE ===")
cur.execute('SELECT id, employee_id, name, location_id FROM employees LIMIT 5')
employees = cur.fetchall()
for emp in employees:
    print(f"{emp['id']}: {emp['name']} (Location: {emp['location_id']})")

cur.close()
conn.close()