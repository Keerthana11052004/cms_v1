from app.db_config import get_db_connection
import hashlib

# Test more password combinations for A002
conn = get_db_connection()
cur = conn.cursor()

cur.execute("""
    SELECT password_hash
    FROM employees 
    WHERE employee_id = 'A002'
""")
user = cur.fetchone()

if user and user['password_hash']:
    target_hash = user['password_hash']
    print(f"Target hash: {target_hash}")
    
    # Test various password patterns
    test_passwords = [
        'A002', 'a002',
        'admin_unit2', 'Admin_Unit2', 'ADMIN_UNIT2',
        'unit2', 'Unit2', 'UNIT2',
        'admin123', 'Admin123', 'ADMIN123',
        'password', 'Password', 'PASSWORD',
        '123456', '12345678', '123456789',
        'qwerty', 'Qwerty', 'QWERTY',
        'admin', 'Admin', 'ADMIN',
        'test', 'Test', 'TEST',
        'welcome', 'Welcome', 'WELCOME',
        'default', 'Default', 'DEFAULT',
        'master', 'Master', 'MASTER',
        'cms123', 'CMS123', 'Cms123'
    ]
    
    print("Testing password combinations:")
    for pwd in test_passwords:
        hashed = hashlib.sha256(pwd.encode()).hexdigest()
        if hashed == target_hash:
            print(f"✓ FOUND MATCH: '{pwd}'")
            break
    else:
        print("✗ No match found with tested passwords")
        
        # Also test if it might be plaintext (though unlikely)
        print(f"\nChecking if hash might be plaintext:")
        if len(target_hash) < 50:  # SHA256 hashes are typically 64 chars
            print(f"Hash length is {len(target_hash)}, might be plaintext")
            print(f"Possible plaintext: '{target_hash}'")

cur.close()
conn.close()