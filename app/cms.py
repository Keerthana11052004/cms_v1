from flask import Blueprint, render_template, session, current_app


# Define the CMS blueprint
cms_blueprint = Blueprint('cms', __name__)

@cms_blueprint.route('/', defaults={'path': ''})
@cms_blueprint.route('/<path:path>')
def cms_home(path):
    # If the request is for the root path (e.g., /cms or /cms/), render the index.html
    print("DEBUG: cms_home function executed!") # Added debug print
    from flask import session, current_app, flash # Import session and current_app here
    current_lang = session.get('lang', current_app.config['BABEL_DEFAULT_LOCALE'])
    # Check for logout message in session
    logout_msg = session.pop('logout_message', None)
    if logout_msg:
        flash(logout_msg, 'info')
    return render_template('index.html', current_lang=current_lang)

@cms_blueprint.route('/status')
def cms_status():
    return "CMS Status Page"