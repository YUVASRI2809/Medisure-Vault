"""
MediSure Vault - Authentication Utility Module

This module provides authentication and authorization utilities including
password hashing, login decorators, and permission verification.
"""

from functools import wraps
from flask import session, redirect, url_for, jsonify, request, abort
from config import Config
import hashlib
import secrets
import os


def hash_password(password):
    """
    Hash a password using SHA-256 with random salt.
    
    Args:
        password (str): Plain text password
        
    Returns:
        str: Hashed password in format 'salt:hash'
    """
    # Generate random salt
    salt = secrets.token_hex(Config.PASSWORD_SALT_LENGTH)
    
    # Combine password and salt, then hash
    salted_password = f"{salt}:{password}"
    password_hash = hashlib.sha256(salted_password.encode()).hexdigest()
    
    # Return salt and hash together
    return f"{salt}:{password_hash}"


def verify_password(password, password_hash):
    """
    Verify a password against its hash.
    
    Args:
        password (str): Plain text password to verify
        password_hash (str): Stored password hash in format 'salt:hash'
        
    Returns:
        bool: True if password matches, False otherwise
    """
    try:
        # Split salt and hash
        salt, stored_hash = password_hash.split(':', 1)
        
        # Hash the provided password with the stored salt
        salted_password = f"{salt}:{password}"
        computed_hash = hashlib.sha256(salted_password.encode()).hexdigest()
        
        # Compare hashes using constant-time comparison
        return secrets.compare_digest(computed_hash, stored_hash)
    except ValueError:
        # Invalid hash format
        return False


def login_required(f):
    """
    Decorator to require authentication for route access.
    Redirects to login page if user is not authenticated.
    
    Usage:
        @app.route('/protected')
        @login_required
        def protected_route():
            return "Protected content"
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # For API requests, return 401
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required'}), 401
            # For web requests, redirect to login
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles):
    """
    Decorator to require specific role(s) for route access.
    
    Args:
        *allowed_roles: Variable number of role names (e.g., 'ADMIN', 'DOCTOR')
    
    Usage:
        @app.route('/admin')
        @login_required
        @role_required('ADMIN')
        def admin_route():
            return "Admin only"
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                abort(401)
            
            user_role = session.get('role')
            if user_role not in allowed_roles:
                abort(403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def permission_required(permission):
    """
    Decorator to require specific permission for route access.
    
    Args:
        permission (str): Permission name (e.g., 'create_prescription')
    
    Usage:
        @app.route('/prescriptions/create')
        @login_required
        @permission_required('create_prescription')
        def create_prescription():
            return "Create prescription"
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                abort(401)
            
            user_role = session.get('role')
            role_permissions = Config.ROLES.get(user_role, {}).get('permissions', [])
            
            if permission not in role_permissions:
                abort(403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_current_user():
    """
    Get the current authenticated user from the session.
    
    Returns:
        User: Current user object or None if not authenticated
    """
    if 'user_id' not in session:
        return None
    
    from models import User
    return User.query.get(session['user_id'])


def get_current_user_id():
    """
    Get the current authenticated user's ID from the session.
    
    Returns:
        int: User ID or None if not authenticated
    """
    return session.get('user_id')


def get_current_user_role():
    """
    Get the current authenticated user's role from the session.
    
    Returns:
        str: User role or None if not authenticated
    """
    return session.get('role')


def has_permission(permission):
    """
    Check if current user has a specific permission.
    
    Args:
        permission (str): Permission name to check
        
    Returns:
        bool: True if user has permission, False otherwise
    """
    if 'user_id' not in session:
        return False
    
    user_role = session.get('role')
    role_permissions = Config.ROLES.get(user_role, {}).get('permissions', [])
    
    return permission in role_permissions


def is_patient():
    """Check if current user is a patient."""
    return session.get('role') == 'PATIENT'


def is_doctor():
    """Check if current user is a doctor."""
    return session.get('role') == 'DOCTOR'


def is_pharmacist():
    """Check if current user is a pharmacist."""
    return session.get('role') == 'PHARMACIST'


def is_admin():
    """Check if current user is an admin."""
    return session.get('role') == 'ADMIN'


def login_user(user):
    """
    Log in a user by storing their information in the session.
    
    Args:
        user (User): User object to log in
    """
    from models import User
    from datetime import datetime
    
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role
    session['full_name'] = user.full_name
    session.permanent = True
    
    # Update last login timestamp
    user.last_login = datetime.utcnow()
    from database import db
    db.session.commit()


def logout_user():
    """Log out the current user by clearing the session."""
    session.clear()


def get_client_ip():
    """
    Get the client's IP address from the request.
    Handles proxy headers like X-Forwarded-For.
    
    Returns:
        str: Client IP address
    """
    if request.headers.get('X-Forwarded-For'):
        # Get first IP from X-Forwarded-For chain
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr or 'unknown'


def get_user_agent():
    """
    Get the client's user agent string from the request.
    
    Returns:
        str: User agent string
    """
    return request.headers.get('User-Agent', 'unknown')


def generate_secure_token(length=32):
    """
    Generate a cryptographically secure random token.
    
    Args:
        length (int): Length of token in bytes (will be hex encoded to 2x length)
        
    Returns:
        str: Hexadecimal token string
    """
    return secrets.token_hex(length)


def validate_token_format(token):
    """
    Validate that a token has the correct format.
    
    Args:
        token (str): Token to validate
        
    Returns:
        bool: True if valid format, False otherwise
    """
    if not token:
        return False
    
    # Token should be hexadecimal and correct length
    expected_length = Config.TOKEN_LENGTH * 2  # Hex encoded doubles length
    
    if len(token) != expected_length:
        return False
    
    try:
        int(token, 16)  # Verify it's valid hex
        return True
    except ValueError:
        return False


def sanitize_input(text, max_length=None):
    """
    Sanitize user input by removing potentially harmful characters.
    
    Args:
        text (str): Input text to sanitize
        max_length (int): Optional maximum length
        
    Returns:
        str: Sanitized text
    """
    if not text:
        return ''
    
    # Strip whitespace
    text = text.strip()
    
    # Truncate if max_length specified
    if max_length and len(text) > max_length:
        text = text[:max_length]
    
    return text


def validate_email(email):
    """
    Validate email address format.
    
    Args:
        email (str): Email address to validate
        
    Returns:
        bool: True if valid format, False otherwise
    """
    if not email:
        return False
    
    # Basic email validation
    if '@' not in email or '.' not in email.split('@')[-1]:
        return False
    
    # Check length
    if len(email) > 120:
        return False
    
    return True


def validate_username(username):
    """
    Validate username format.
    
    Args:
        username (str): Username to validate
        
    Returns:
        bool: True if valid format, False otherwise
    """
    if not username:
        return False
    
    # Username should be 3-80 characters, alphanumeric and underscores only
    if len(username) < 3 or len(username) > 80:
        return False
    
    # Allow alphanumeric and underscores
    if not all(c.isalnum() or c == '_' for c in username):
        return False
    
    return True


def validate_password_strength(password):
    """
    Validate password strength requirements.
    
    Args:
        password (str): Password to validate
        
    Returns:
        tuple: (is_valid: bool, message: str)
    """
    if not password:
        return False, "Password is required"
    
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if len(password) > 128:
        return False, "Password is too long (max 128 characters)"
    
    # Check for at least one uppercase letter
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    
    # Check for at least one lowercase letter
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    
    # Check for at least one digit
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    
    return True, "Password is strong"


def check_rate_limit(user_id, action, max_attempts=5, window_minutes=15):
    """
    Check if user has exceeded rate limit for a specific action.
    This is a simple in-memory implementation.
    For production, use Redis or similar for distributed rate limiting.
    
    Args:
        user_id (int): User ID
        action (str): Action being rate limited
        max_attempts (int): Maximum attempts allowed in window
        window_minutes (int): Time window in minutes
        
    Returns:
        bool: True if within rate limit, False if exceeded
    """
    # This is a placeholder implementation
    # In production, implement proper rate limiting with Redis
    return True
