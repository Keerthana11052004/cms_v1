import os
import sys
import platform
from flask import Flask, render_template, request, session, g
from flask_mysqldb import MySQL
from flask_login import LoginManager, UserMixin
from flask_bootstrap import Bootstrap
from flask_wtf import CSRFProtect
from datetime import datetime
from dotenv import load_dotenv  # Add this import
# import pymysql  # Import pymysql to access DictCursor
# from . import Curr_Proj_Name, mysql, User
from .db_config import get_db_connection
from .biometric_integration import start_biometric_service

# Explicitly add user site-packages path for stubborn module imports
if platform.system() == "Windows":
    user_site_packages = r'c:\users\vtgs_lap_01\appdata\local\packages\pythonsoftwarefoundation.python.3.13_qbz5n2kfra8p0\localcache\local-packages\python313\site-packages'
    if user_site_packages not in sys.path:
        sys.path.insert(0, user_site_packages)

# ✅ Try importing Babel, else define a dummy class
try:
    from flask_babel import Babel
    babel = Babel()
    BABEL_AVAILABLE = True
except ImportError:
    print("⚠️ flask-babel not installed. Multilingual features will be disabled.")
    BABEL_AVAILABLE = False

Curr_Proj_Name = 'CMS'

# Initialize extensions
mysql = MySQL()
login_manager = LoginManager()
bootstrap = Bootstrap()
csrf = CSRFProtect()


# User class
class User(UserMixin):
    def __init__(self, id, name='Guest', email=None, role=None, department=None, location=None, employee_id=None):
        self.id = id
        self.name = name
        self.email = email
        self.role = role
        self.department = department
        self.location = location
        self.employee_id = employee_id


# User loader
@login_manager.user_loader
def load_user(user_id):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM employees WHERE id=%s", (user_id,))
        user = cur.fetchone()
        if user:
            role_map = {1: 'Employee', 2: 'Canteen Vendor', 3: 'Unit-wise Admin', 6: 'Master Admin'}
            role = role_map.get(user['role_id'], 'Employee')

            department, location = None, None
            if 'department_id' in user and user['department_id']:
                cur.execute("SELECT name FROM departments WHERE id=%s", (user['department_id'],))
                dept = cur.fetchone()
                if dept:
                    department = dept['name']
            if 'location_id' in user and user['location_id']:
                cur.execute("SELECT name FROM locations WHERE id=%s", (user['location_id'],))
                loc = cur.fetchone()
                if loc:
                    location = loc['name']

            return User(user['id'], name=user['name'], email=user['email'],
                        role=role, department=department, location=location,
                        employee_id=user['employee_id'])
    except Exception as e:
        import traceback
        with open("app_errors.log", "a") as log_file:
            log_file.write(f"[{datetime.now()}] Error loading user: {e}\n")
            traceback.print_exc(file=log_file)
        print(f"Error loading user: {e}")
        traceback.print_exc()
        return None
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# App factory
def create_app():
    # Load environment variables from .env file
    load_dotenv()
    
    print("Flask application creation started.")
    app = Flask(__name__, static_folder='static', static_url_path="/static")
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-in-production')
    app.config['LANGUAGES'] = ['en', 'ta', 'hi']
    app.config['BABEL_DEFAULT_LOCALE'] = 'en'
    app.debug = True
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
    app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
    
    # Load URL prefix from environment
    app.config['URL_PREFIX'] = os.environ.get('URL_PREFIX', 'cms')

    
    mysql.init_app(app)
    login_manager.init_app(app)
    bootstrap.init_app(app)
    csrf.init_app(app)

    # ✅ Only enable Babel if available
    if BABEL_AVAILABLE:
        def get_locale():
            if request.args.get('lang'):
                session['lang'] = request.args.get('lang')
            locale = session.get('lang', app.config['BABEL_DEFAULT_LOCALE'])
            g.locale = locale
            return locale

        babel.init_app(app, locale_selector=get_locale)

    # Register blueprints
    from .cms import cms_blueprint
    from .employee import employee_bp
    from .vendor import vendor_bp
    from .admin import admin_bp, init_admin_config

    init_admin_config(app)

    # Use configured URL prefix
    url_prefix = app.config['URL_PREFIX']
    app.register_blueprint(cms_blueprint, url_prefix=f'/{url_prefix}')
    app.register_blueprint(employee_bp, url_prefix=f'/{url_prefix}/employee')
    app.register_blueprint(vendor_bp, url_prefix=f'/{url_prefix}/vendor')
    app.register_blueprint(admin_bp, url_prefix=f'/{url_prefix}/admin')

    # Start biometric services after app initialization
    # Temporarily disabled due to connection timeouts
    # try:
    #     start_biometric_service()
    #     print("✅ Biometric service started successfully")
    # except Exception as e:
    #     print(f"⚠️ Could not start biometric service: {e}")
    
    # try:
    #     from .biometric_integration import biometric_consumption
    #     biometric_consumption.start_polling()
    #     print("✅ Biometric consumption service started successfully")
    # except Exception as e:
    #     print(f"⚠️ Could not start biometric consumption service: {e}")

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        import traceback
        tb = traceback.format_exc()
        print(f"Unhandled Internal Server Error: {error}")
        print(tb)
        return f"<h1>Internal Server Error</h1><pre>{tb}</pre>", 500

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        import traceback
        tb = traceback.format_exc()
        print(f"Caught unhandled exception: {e}")
        print(tb)
        return f"<h1>Unhandled Exception</h1><pre>{tb}</pre>", 500

    @app.route('/favicon.ico')
    def favicon_root():
        from flask import send_from_directory
        import os
        # The favicon is in the project root's static directory, not the app's static directory
        static_dir = os.path.join(os.path.dirname(app.root_path), 'static')
        return send_from_directory(static_dir, 'favicon.ico', mimetype='image/vnd.microsoft.icon')
                                   
    @app.route(f'/{app.config["URL_PREFIX"]}/favicon.ico')
    def favicon_cms():
        from flask import send_from_directory
        import os
        # The favicon is in the project root's static directory, not the app's static directory
        static_dir = os.path.join(os.path.dirname(app.root_path), 'static')
        return send_from_directory(static_dir, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

    @app.context_processor
    def inject_url_prefix():
        """Make URL prefix available to all templates"""
        return dict(url_prefix=app.config['URL_PREFIX'])
    
    @app.route('/')
    def index():
        # Redirect root requests to the CMS home page
        from flask import redirect, url_for, flash, session
        # Check for logout message in session
        logout_msg = session.pop('logout_message', None)
        if logout_msg:
            flash(logout_msg, 'info')
        return redirect(url_for('cms.cms_home'))

    return app
