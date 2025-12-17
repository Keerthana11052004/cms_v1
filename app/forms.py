from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, DateField, BooleanField, FileField
from wtforms.validators import DataRequired, Email
from flask_babel import lazy_gettext as _l
from datetime import date

class LoginForm(FlaskForm):
    employee_id = StringField(_l('Employee ID'), validators=[DataRequired()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    submit = SubmitField(_l('Login'))

class BookMealForm(FlaskForm):
    shift = SelectField(_l('Shift'), choices=[('Breakfast', 'Breakfast'), ('Lunch', 'Lunch'), ('Dinner', 'Dinner')], validators=[DataRequired()])
    date = DateField(_l('Date'), validators=[DataRequired()])
    recurrence = SelectField(_l('Recurrence'), choices=[('None', 'None'), ('Daily', 'Daily'), ('Weekly', 'Weekly')], default='None')
    submit = SubmitField(_l('Book'))

class AddUserForm(FlaskForm):
    employee_id = StringField('Employee ID', validators=[DataRequired()])
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    department_id = SelectField('Department', coerce=int, validators=[DataRequired()])
    location_id = SelectField('Location', coerce=int, validators=[DataRequired()])
    role_id = SelectField('Role', coerce=int, validators=[DataRequired()])
    is_active = BooleanField('Active', default=True)
    submit = SubmitField('Add User')

class ProfileUpdateForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', render_kw={'readonly': True})
    employee_id = StringField('Employee ID', render_kw={'readonly': True})
    department_id = SelectField('Department', coerce=int)
    location_id = SelectField('Location', coerce=int)
    password = PasswordField('New Password')
    confirm_password = PasswordField('Confirm Password')
    submit = SubmitField('Update Profile')

class VendorForm(FlaskForm):
    name = StringField('Vendor Name', validators=[DataRequired()])
    contact_info = StringField('Contact Info')
    unit = SelectField('Unit', choices=[])
    purpose = StringField('Purpose')
    food_licence = FileField('Food Licence')
    agreement_date = DateField('Agreement for Approval')
    submit = SubmitField('Save')

class OutsiderMealVendorForm(FlaskForm):
    name = StringField('Vendor Name', validators=[DataRequired()])
    unit = SelectField('Unit', choices=[])
    purpose = SelectField('Purpose', choices=[])
    submit = SubmitField('Save')

class AddMenuForm(FlaskForm):
    location_id = SelectField('Unit', coerce=int, validators=[DataRequired()])
    menu_date = DateField('Menu Date', validators=[DataRequired()], default=date.today)
    meal_type = SelectField('Meal Type', choices=[('Breakfast', 'Breakfast'), ('Lunch', 'Lunch'), ('Dinner', 'Dinner')], validators=[DataRequired()])
    items = StringField('Menu Items', validators=[DataRequired()])
    submit = SubmitField('Add Menu')