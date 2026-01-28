from app.db_config import get_db_connection
import hashlib

# Reset password for A002 to a known value
conn = get_db_connection()
cur = conn.cursor()

try:
    # Set password to 'admin123'
    new_password = 'admin123'
    password_hash = hashlib.sha256(new_password.encode()).hexdigest()
    
    print(f"Setting password for A002 to: {new_password}")
    print(f"Hash: {password_hash}")
    
    cur.execute("""
        UPDATE employees 
        SET password_hash = %s 
        WHERE employee_id = 'A002'
    """, (password_hash,))
    
    conn.commit()
    
    print("✓ Password updated successfully!")
    print("You can now log in with:")
    print("  Username: A002")
    print("  Password: admin123")
    
except Exception as e:
    print(f"✗ Error updating password: {e}")
    conn.rollback()
    
finally:
    cur.close()
    conn.close()