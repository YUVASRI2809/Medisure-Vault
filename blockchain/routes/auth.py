from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from models_auth import db, User

# Create the auth blueprint
auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Handle user registration."""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')  # 'doctor', 'pharmacist', 'patient'

        # Validate role
        if role not in ['doctor', 'pharmacist', 'patient']:
            flash('Invalid role selected.', 'danger')
            return redirect(url_for('auth.register'))

        # Check for duplicate email
        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please log in.', 'warning')
            return redirect(url_for('auth.login'))

        # Check for duplicate username
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'warning')
            return redirect(url_for('auth.register'))

        # Create new user
        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        # Validate credentials
        if not user or not user.check_password(password):
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('auth.login'))

        # Log the user in (Flask-Login manages the session)
        login_user(user)

        # Redirect based on role
        if user.role == 'doctor':
            return redirect(url_for('doctor_dashboard'))
        elif user.role == 'pharmacist':
            return redirect(url_for('pharmacist_dashboard'))
        else:
            return redirect(url_for('patient_dashboard'))

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Log out the current user."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
