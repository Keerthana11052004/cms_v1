# Fix the admin.py file by removing the old condition
with open('app/admin.py', 'r') as f:
    lines = f.readlines()

# Remove line 2407 (the old condition)
lines.pop(2407)

with open('app/admin.py', 'w') as f:
    f.writelines(lines)

print("File fixed successfully")