from app.db_config import get_db_connection
import hashlib

# Check password for A002
conn = get_db_connection()
cur = conn.cursor()

print("=== Checking A002 User ===")
cur.execute("""
    SELECT id, employee_id, name, email, password_hash, role_id
    FROM employees 
    WHERE employee_id = 'A002'
""")
user = cur.fetchone()

if user:
    print(f"User found:")
    print(f"  ID: {user['id']}")
    print(f"  Employee ID: {user['employee_id']}")
    print(f"  Name: {user['name']}")
    print(f"  Email: {user['email']}")
    print(f"  Role ID: {user['role_id']}")
    print(f"  Password hash exists: {bool(user['password_hash'])}")
    
    if user['password_hash']:
        print(f"  Password hash: {user['password_hash']}")
        
        # Test common passwords
        common_passwords = ['admin123', 'password', '123456', 'admin', 'A002']
        print("\nTesting common passwords:")
        for pwd in common_passwords:
            hashed = hashlib.sha256(pwd.encode()).hexdigest()
            if hashed == user['password_hash']:
                print(f"  ✓ Password '{pwd}' matches!")
                break
        else:
            print("  ✗ None of the common passwords match")
else:
    print("User A002 not found!")

cur.close()
conn.close()