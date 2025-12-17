import os
import platform
import sys # Import sys

# Add the parent directory to the Python path to allow importing modules like CSV_Param
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from app import create_app, babel # Import babel here
from waitress import serve
import socket
from flask.cli import FlaskGroup

# Windows compatibility for site-packages
if platform.system() == "Windows":
    site_packages_path = os.path.join(
        os.environ['LOCALAPPDATA'],
        'Packages',
        'PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0',
        'LocalCache', 'local-packages', 'Python313', 'site-packages'
    )
    if site_packages_path not in os.sys.path:
        os.sys.path.append(site_packages_path)

def create_cli_app():
    app = create_app()
    return app

cli = FlaskGroup(create_app=create_cli_app)

if __name__ == '__main__':
    print("Starting Waitress server...")
    try:
        serve(create_app(), host='0.0.0.0', port=5002)
    except socket.error as e:
        print(f"Error starting server: {e}")
        print("Port 5002 might be in use. Trying another port...")
        serve(create_app(), host='0.0.0.0', port=5003)