# Modify the admin.py file to fix the Master Admin location issue
with open('app/admin.py', 'r') as f:
    lines = f.readlines()

# Modify line 2407
lines[2407] = "        if user_role and user_role['name'] == 'Master Admin':\n"

# Modify line 2408
lines[2408] = "            # Check if user already has location_id = 0, otherwise select the current location\n            selected_attr = 'selected' if user.get('location_id') == 0 else ''\n            form_html += f'<option value=\"0\" {selected_attr}>All Units</option>'\n"

with open('app/admin.py', 'w') as f:
    f.writelines(lines)

print("File modified successfully")