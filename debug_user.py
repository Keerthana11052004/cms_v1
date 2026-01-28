import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, mysql

def debug_user():
    app = create_app()
    with app.app_context():
        conn = mysql.connection
        cur = conn.cursor()
        
        print("=== DEBUGGING USER A001 ===")
        
        # Check user details
        cur.execute("SELECT id, employee_id, name, role_id, location_id FROM employees WHERE employee_id = 'a001'")
        user = cur.fetchone()
        
        if user:
            print(f"User found:")
            print(f"  ID: {user['id']}")
            print(f"  Employee ID: {user['employee_id']}")
            print(f"  Name: {user['name']}")
            print(f"  Role ID: {user['role_id']}")
            
            # Check role name
            cur.execute("SELECT name FROM roles WHERE id = %s", (user['role_id'],))
            role = cur.fetchone()
            if role:
                print(f"  Role Name: {role['name']}")
            
            # Check location if exists
            if user['location_id']:
                cur.execute("SELECT name FROM locations WHERE id = %s", (user['location_id'],))
                location = cur.fetchone()
                if location:
                    print(f"  Location: {location['name']}")
                else:
                    print(f"  Location ID {user['location_id']} not found in locations table")
            else:
                print("  No location assigned")
        else:
            print("User A001 not found!")
        
        # Check all roles
        print("\n=== ALL ROLES ===")
        cur.execute("SELECT id, name FROM roles ORDER BY id")
        roles = cur.fetchall()
        for role in roles:
            print(f"  {role['id']}: {role['name']}")
        
        # Check all locations
        print("\n=== ALL LOCATIONS ===")
        cur.execute("SELECT id, name FROM locations ORDER BY id")
        locations = cur.fetchall()
        for location in locations:
            print(f"  {location['id']}: {location['name']}")
        
        # Check if user is assigned to any location
        print("\n=== USER-LOCATION MAPPING ===")
        cur.execute("""
            SELECT e.employee_id, e.name, l.name as location_name
            FROM employees e
            LEFT JOIN locations l ON e.location_id = l.id
            WHERE e.employee_id = 'a001'
        """)
        mapping = cur.fetchone()
        if mapping:
            print(f"  {mapping['employee_id']} ({mapping['name']}) -> {mapping['location_name'] or 'NO LOCATION'}")
        
        cur.close()
        conn.close()

if __name__ == "__main__":
    debug_user()