import sys
import os
sys.path.append('./app')

from app.db_config import get_db_connection

def check_menus():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check all menus for today
    cur.execute('SELECT * FROM daily_menus WHERE menu_date = %s ORDER BY location_id, meal_type', ('2026-01-22',))
    menus = cur.fetchall()
    print('Menus for today (2026-01-22):')
    for menu in menus:
        print(f'Location ID: {menu["location_id"]}, Meal: {menu["meal_type"]}, Items: {menu["items"]}')
    
    # Also check for any recent menus
    cur.execute('SELECT * FROM daily_menus ORDER BY menu_date DESC, location_id, meal_type LIMIT 10')
    recent_menus = cur.fetchall()
    print('\nRecent 10 menus:')
    for menu in recent_menus:
        print(f'Date: {menu["menu_date"]}, Location ID: {menu["location_id"]}, Meal: {menu["meal_type"]}, Items: {menu["items"]}')
    
    # Check locations
    cur.execute('SELECT * FROM locations ORDER BY id')
    locations = cur.fetchall()
    print('\nAvailable locations:')
    for loc in locations:
        print(f'ID: {loc["id"]}, Name: {loc["name"]}')
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    check_menus()