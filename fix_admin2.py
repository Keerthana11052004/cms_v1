# Fix the admin.py file by modifying the condition
with open('app/admin.py', 'r') as f:
    lines = f.readlines()

# Modify line 2407
lines[2407] = "        if user_role and user_role['name'] == 'Master Admin':\n"

with open('app/admin.py', 'w') as f:
    f.writelines(lines)

print("File fixed successfully")