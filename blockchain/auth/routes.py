"""
MediSure Vault - Authentication Routes Module

This module handles all authentication-related routes including login, logout,
registration, and user management.
"""

from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
from auth.utils import (
    hash_password, verify_password, login_user, logout_user, 
    login_required, role_required, get_client_ip, get_user_agent,
    validate_email, validate_username, validate_password_strength,
    sanitize_input
)
from models import User
from database import db
from audit.logger import log_audit_event
from datetime import datetime


# Create authentication blueprint
auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register a new user account.
    
    Expected JSON body:
    {
        "username": "string",
        "password": "string",
        "email": "string",
        "full_name": "string",
        "role": "PATIENT|DOCTOR|PHARMACIST",
        "license_number": "string" (optional, for doctors/pharmacists),
        "pharmacy_id": "string" (optional, for pharmacists)
    }
    
    Returns:
        JSON response with user data or error
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Extract and validate required fields
    username = sanitize_input(data.get('username'))
    password = data.get('password')
    email = sanitize_input(data.get('email'))
    full_name = sanitize_input(data.get('full_name'))
    role = data.get('role', 'PATIENT')
    
    # Validate required fields
    if not all([username, password, email, full_name]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Validate username format
    if not validate_username(username):
        return jsonify({'error': 'Invalid username format (3-80 alphanumeric characters)'}), 400
    
    # Validate email format
    if not validate_email(email):
        return jsonify({'error': 'Invalid email format'}), 400
    
    # Validate password strength
    is_strong, password_message = validate_password_strength(password)
    if not is_strong:
        return jsonify({'error': password_message}), 400
    
    # Validate role
    if role not in ['PATIENT', 'DOCTOR', 'PHARMACIST']:
        return jsonify({'error': 'Invalid role. Must be PATIENT, DOCTOR, or PHARMACIST'}), 400
    
    # Check if username already exists
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({'error': 'Username already exists'}), 409
    
    # Check if email already exists
    existing_email = User.query.filter_by(email=email).first()
    if existing_email:
        return jsonify({'error': 'Email already exists'}), 409
    
    # Create new user
    new_user = User(
        username=username,
        password_hash=hash_password(password),
        email=email,
        full_name=full_name,
        role=role,
        license_number=sanitize_input(data.get('license_number')) if data.get('license_number') else None,
        pharmacy_id=sanitize_input(data.get('pharmacy_id')) if data.get('pharmacy_id') else None,
        is_active=True
    )
    
    db.session.add(new_user)
    db.session.flush()  # Flush to get user.id before commit
    
    # Create role-specific profile
    if role == 'DOCTOR':
        from models import Doctor
        doctor_profile = Doctor(
            user_id=new_user.id,
            license_number=sanitize_input(data.get('license_number')),
            specialization=sanitize_input(data.get('specialization', 'General Practice')),
            hospital=sanitize_input(data.get('hospital', '')),
            years_experience=int(data.get('years_experience', 0))
        )
        db.session.add(doctor_profile)
    
    elif role == 'PHARMACIST':
        from models import Pharmacist
        from datetime import datetime
        pharmacist_profile = Pharmacist(
            user_id=new_user.id,
            pharmacy_name=sanitize_input(data.get('pharmacy_name', '')),
            license_number=sanitize_input(data.get('license_number')),
            location=sanitize_input(data.get('location', '')),
            certification_date=datetime.strptime(data.get('certification_date'), '%Y-%m-%d').date() if data.get('certification_date') else None
        )
        db.session.add(pharmacist_profile)
    
    elif role == 'PATIENT':
        from models import Patient
        patient_profile = Patient(
            user_id=new_user.id,
            age=int(data.get('age', 0)),
            contact_number=sanitize_input(data.get('contact_number', '')),
            address=sanitize_input(data.get('address')) if data.get('address') else None,
            emergency_contact=sanitize_input(data.get('emergency_contact')) if data.get('emergency_contact') else None,
            blood_group=sanitize_input(data.get('blood_group')) if data.get('blood_group') else None
        )
        db.session.add(patient_profile)
    
    db.session.commit()
    
    # Log registration event
    log_audit_event(
        event_type='USER_REGISTERED',
        user_id=new_user.id,
        details={'username': username, 'role': role},
        ip_address=get_client_ip()
    )
    
    return jsonify({
        'message': 'Registration successful',
        'user': new_user.to_dict()
    }), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Authenticate user and create session.
    
    Expected JSON body:
    {
        "username": "string",
        "password": "string"
    }
    
    Returns:
        JSON response with user data and session info
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    username = sanitize_input(data.get('username'))
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    # Find user by username
    user = User.query.filter_by(username=username).first()
    
    if not user:
        # Log failed login attempt
        log_audit_event(
            event_type='LOGIN_FAILED',
            user_id=None,
            details={'username': username, 'reason': 'user_not_found'},
            ip_address=get_client_ip()
        )
        return jsonify({'error': 'Invalid username or password'}), 401
    
    # Verify password
    if not verify_password(password, user.password_hash):
        # Log failed login attempt
        log_audit_event(
            event_type='LOGIN_FAILED',
            user_id=user.id,
            details={'username': username, 'reason': 'incorrect_password'},
            ip_address=get_client_ip()
        )
        return jsonify({'error': 'Invalid username or password'}), 401
    
    # Check if account is active
    if not user.is_active:
        log_audit_event(
            event_type='LOGIN_FAILED',
            user_id=user.id,
            details={'username': username, 'reason': 'account_inactive'},
            ip_address=get_client_ip()
        )
        return jsonify({'error': 'Account is inactive'}), 403
    
    # Login user (creates session)
    login_user(user)
    
    # Log successful login
    log_audit_event(
        event_type='LOGIN_SUCCESS',
        user_id=user.id,
        details={'username': username, 'role': user.role},
        ip_address=get_client_ip()
    )
    
    return jsonify({
        'message': 'Login successful',
        'user': user.to_dict()
    }), 200


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """
    Log out current user and destroy session.
    
    Returns:
        JSON response confirming logout
    """
    user_id = session.get('user_id')
    username = session.get('username')
    
    # Log logout event
    log_audit_event(
        event_type='LOGOUT',
        user_id=user_id,
        details={'username': username},
        ip_address=get_client_ip()
    )
    
    # Clear session
    logout_user()
    
    return jsonify({'message': 'Logout successful'}), 200


@auth_bp.route('/me', methods=['GET'])
@login_required
def get_current_user():
    """
    Get current authenticated user's information.
    
    Returns:
        JSON response with user data
    """
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({'user': user.to_dict()}), 200


@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """
    Change current user's password.
    
    Expected JSON body:
    {
        "current_password": "string",
        "new_password": "string"
    }
    
    Returns:
        JSON response confirming password change
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    if not current_password or not new_password:
        return jsonify({'error': 'Current and new password required'}), 400
    
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Verify current password
    if not verify_password(current_password, user.password_hash):
        log_audit_event(
            event_type='PASSWORD_CHANGE_FAILED',
            user_id=user.id,
            details={'reason': 'incorrect_current_password'},
            ip_address=get_client_ip()
        )
        return jsonify({'error': 'Current password is incorrect'}), 401
    
    # Validate new password strength
    is_strong, password_message = validate_password_strength(new_password)
    if not is_strong:
        return jsonify({'error': password_message}), 400
    
    # Update password
    user.password_hash = hash_password(new_password)
    db.session.commit()
    
    # Log password change
    log_audit_event(
        event_type='PASSWORD_CHANGED',
        user_id=user.id,
        details={'username': user.username},
        ip_address=get_client_ip()
    )
    
    return jsonify({'message': 'Password changed successfully'}), 200


@auth_bp.route('/users', methods=['GET'])
@login_required
@role_required('ADMIN')
def list_users():
    """
    Get list of all users (admin only).
    
    Query parameters:
        role: Filter by role (optional)
        active: Filter by active status (optional)
        page: Page number (default: 1)
        per_page: Items per page (default: 20)
    
    Returns:
        JSON response with paginated user list
    """
    # Get query parameters
    role_filter = request.args.get('role')
    active_filter = request.args.get('active')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Build query
    query = User.query
    
    if role_filter:
        query = query.filter_by(role=role_filter)
    
    if active_filter is not None:
        is_active = active_filter.lower() == 'true'
        query = query.filter_by(is_active=is_active)
    
    # Paginate results
    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'users': [user.to_dict() for user in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages
    }), 200


@auth_bp.route('/users/<int:user_id>', methods=['GET'])
@login_required
@role_required('ADMIN')
def get_user(user_id):
    """
    Get specific user by ID (admin only).
    
    Args:
        user_id: User ID
    
    Returns:
        JSON response with user data
    """
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({'user': user.to_dict()}), 200


@auth_bp.route('/users/<int:user_id>/deactivate', methods=['POST'])
@login_required
@role_required('ADMIN')
def deactivate_user(user_id):
    """
    Deactivate a user account (admin only).
    
    Args:
        user_id: User ID to deactivate
    
    Returns:
        JSON response confirming deactivation
    """
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.id == session.get('user_id'):
        return jsonify({'error': 'Cannot deactivate your own account'}), 400
    
    user.is_active = False
    db.session.commit()
    
    # Log deactivation
    log_audit_event(
        event_type='USER_DEACTIVATED',
        user_id=session.get('user_id'),
        details={'deactivated_user_id': user_id, 'username': user.username},
        ip_address=get_client_ip()
    )
    
    return jsonify({'message': 'User deactivated successfully'}), 200


@auth_bp.route('/users/<int:user_id>/activate', methods=['POST'])
@login_required
@role_required('ADMIN')
def activate_user(user_id):
    """
    Activate a user account (admin only).
    
    Args:
        user_id: User ID to activate
    
    Returns:
        JSON response confirming activation
    """
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    user.is_active = True
    db.session.commit()
    
    # Log activation
    log_audit_event(
        event_type='USER_ACTIVATED',
        user_id=session.get('user_id'),
        details={'activated_user_id': user_id, 'username': user.username},
        ip_address=get_client_ip()
    )
    
    return jsonify({'message': 'User activated successfully'}), 200


@auth_bp.route('/verify-session', methods=['GET'])
def verify_session():
    """
    Verify if current session is valid.
    
    Returns:
        JSON response with session validity status
    """
    if 'user_id' in session:
        return jsonify({
            'valid': True,
            'user_id': session.get('user_id'),
            'username': session.get('username'),
            'role': session.get('role')
        }), 200
    else:
        return jsonify({'valid': False}), 200
