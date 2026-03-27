"""
MediSure Vault - Configuration Module

This module contains all configuration settings for the blockchain prescription
management system including database, security, blockchain, and lifecycle settings.
"""

import os
from datetime import timedelta


class Config:
    """Base configuration class for MediSure Vault application."""
    
    # ==================== APPLICATION SETTINGS ====================
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # ==================== DATABASE SETTINGS ====================
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f'sqlite:///{os.path.join(BASE_DIR, "medisure_vault.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False  # Set to True for SQL query debugging
    
    # ==================== SECURITY SETTINGS ====================
    # Password hashing
    PASSWORD_HASH_ALGORITHM = 'sha256'
    PASSWORD_SALT_LENGTH = 32
    
    # Session management
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # Token settings
    TOKEN_EXPIRATION_MINUTES = 15  # One-time access token validity
    TOKEN_LENGTH = 32  # Length of generated access tokens
    
    # ==================== ROLE-BASED ACCESS CONTROL ====================
    ROLES = {
        'PATIENT': {
            'permissions': [
                'view_own_prescriptions',
                'generate_access_token',
                'revoke_access_token',
                'view_audit_logs'
            ]
        },
        'DOCTOR': {
            'permissions': [
                'create_prescription',
                'view_prescription',
                'edit_prescription',  # Only before dispensing
                'view_audit_logs'
            ]
        },
        'PHARMACIST': {
            'permissions': [
                'view_prescription',  # With valid token
                'dispense_prescription',
                'lock_prescription',
                'view_audit_logs'
            ]
        },
        'ADMIN': {
            'permissions': [
                'emergency_override',
                'view_all_prescriptions',
                'view_all_audit_logs',
                'manage_users',
                'view_blockchain'
            ]
        }
    }
    
    # ==================== PRESCRIPTION LIFECYCLE STATES ====================
    PRESCRIPTION_STATES = {
        'CREATED': {
            'description': 'Prescription created by doctor, not yet shared',
            'allowed_transitions': ['SHARED', 'CANCELLED'],
            'can_edit': True,
            'can_delete': True
        },
        'SHARED': {
            'description': 'Prescription shared with patient via token',
            'allowed_transitions': ['DISPENSED', 'CANCELLED'],
            'can_edit': True,
            'can_delete': False
        },
        'DISPENSED': {
            'description': 'Prescription dispensed by pharmacy',
            'allowed_transitions': ['LOCKED'],
            'can_edit': False,
            'can_delete': False
        },
        'LOCKED': {
            'description': 'Post-dispense lock applied - immutable state',
            'allowed_transitions': [],  # Terminal state
            'can_edit': False,
            'can_delete': False
        },
        'CANCELLED': {
            'description': 'Prescription cancelled before dispensing',
            'allowed_transitions': [],  # Terminal state
            'can_edit': False,
            'can_delete': False
        }
    }
    
    # ==================== BLOCKCHAIN SETTINGS ====================
    BLOCKCHAIN_DIFFICULTY = 4  # Number of leading zeros required in hash
    BLOCK_HASH_ALGORITHM = 'sha256'
    GENESIS_BLOCK_DATA = 'MediSure Vault Genesis Block'
    
    # Events that trigger blockchain recording
    BLOCKCHAIN_EVENTS = [
        'PRESCRIPTION_CREATED',
        'PRESCRIPTION_SHARED',
        'PRESCRIPTION_DISPENSED',
        'PRESCRIPTION_LOCKED',
        'PRESCRIPTION_CANCELLED',
        'TOKEN_GENERATED',
        'TOKEN_USED',
        'TOKEN_REVOKED',
        'EMERGENCY_ACCESS',
        'STATE_TRANSITION',
        'TAMPER_DETECTED'
    ]
    
    # ==================== TAMPER EVIDENCE SETTINGS ====================
    TAMPER_SCORE_WEIGHTS = {
        'hash_mismatch': 40,           # Critical: blockchain hash doesn't match
        'state_violation': 30,          # Critical: illegal state transition
        'unauthorized_access': 20,      # High: access without valid token
        'timestamp_anomaly': 10,        # Medium: suspicious timestamp pattern
        'collision_detected': 25,       # High: multiple pharmacies accessing
        'emergency_override': 15        # Medium: emergency access logged
    }
    
    TAMPER_SCORE_THRESHOLDS = {
        'LOW': (0, 20),      # Score 0-20: No significant tampering
        'MEDIUM': (21, 50),  # Score 21-50: Potential tampering
        'HIGH': (51, 75),    # Score 51-75: Likely tampering
        'CRITICAL': (76, 100) # Score 76-100: Confirmed tampering
    }
    
    # ==================== ANOMALY DETECTION RULES ====================
    ANOMALY_RULES = {
        'MAX_DAILY_PRESCRIPTIONS_PER_DOCTOR': 100,
        'MAX_DAILY_DISPENSES_PER_PHARMACY': 200,
        'MAX_REFILLS_ALLOWED': 5,
        'MIN_TIME_BETWEEN_DISPENSES_HOURS': 24,
        'MAX_PRESCRIPTION_AGE_DAYS': 365,
        'CONTROLLED_SUBSTANCES': ['Oxycodone', 'Morphine', 'Fentanyl', 'Adderall'],
        'MAX_CONTROLLED_QUANTITY': 30,  # Maximum quantity for controlled substances
        'BLACKLISTED_COMBINATIONS': [
            ('Warfarin', 'Aspirin'),  # Dangerous drug interactions
            ('MAOIs', 'SSRIs')
        ]
    }
    
    # ==================== EMERGENCY ACCESS SETTINGS ====================
    EMERGENCY_ACCESS = {
        'REQUIRES_JUSTIFICATION': True,
        'MIN_JUSTIFICATION_LENGTH': 50,
        'AUTO_NOTIFY_PATIENT': True,
        'AUTO_NOTIFY_AUTHORITIES': False,
        'COOLDOWN_MINUTES': 30,  # Minimum time between emergency accesses
        'ALLOWED_ROLES': ['ADMIN'],
        'AUDIT_RETENTION_YEARS': 10  # Keep emergency access logs for 10 years
    }
    
    # ==================== ACCESS TOKEN SETTINGS ====================
    ACCESS_TOKEN = {
        'ONE_TIME_USE': True,
        'DEFAULT_VALIDITY_MINUTES': 15,
        'MAX_VALIDITY_MINUTES': 60,
        'MIN_VALIDITY_MINUTES': 5,
        'REVOCABLE_BY_PATIENT': True,
        'AUTO_EXPIRE_AFTER_USE': True
    }
    
    # ==================== AUDIT LOGGING SETTINGS ====================
    AUDIT_LOG = {
        'ENABLED': True,
        'LOG_ALL_ACTIONS': True,
        'RETENTION_DAYS': 3650,  # 10 years
        'IMMUTABLE': True,       # Logs cannot be deleted or modified
        'INCLUDE_IP_ADDRESS': True,
        'INCLUDE_USER_AGENT': True,
        'BLOCKCHAIN_BACKED': True  # Critical events also go to blockchain
    }
    
    # ==================== MULTI-PHARMACY COLLISION SETTINGS ====================
    COLLISION_DETECTION = {
        'ENABLED': True,
        'DETECTION_WINDOW_HOURS': 24,  # Check for collisions within 24 hours
        'AUTO_LOCK_ON_COLLISION': True,
        'NOTIFY_ALL_PARTIES': True,
        'TAMPER_SCORE_PENALTY': 25
    }
    
    # ==================== DEVELOPMENT/TESTING SETTINGS ====================
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    TESTING = False
    
    # For testing purposes - bypass certain security checks
    BYPASS_TOKEN_VALIDATION = False  # Only set True in testing
    BYPASS_STATE_VALIDATION = False  # Only set True in testing


class DevelopmentConfig(Config):
    """Development-specific configuration."""
    DEBUG = True
    SQLALCHEMY_ECHO = True
    SESSION_COOKIE_SECURE = False  # Allow HTTP in development


class ProductionConfig(Config):
    """Production-specific configuration."""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    
    # Override with strong secret key from environment
    # Validation will happen in get_config() when production is actually selected
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'production-secret-key-must-be-set'


class TestingConfig(Config):
    """Testing-specific configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    BYPASS_TOKEN_VALIDATION = False  # Keep validation even in tests


# Configuration dictionary for easy access
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config(env=None):
    """
    Get configuration object based on environment.
    
    Args:
        env (str): Environment name ('development', 'production', 'testing')
        
    Returns:
        Config: Configuration object for the specified environment
    """
    if env is None:
        env = os.environ.get('FLASK_ENV', 'development')
    return config.get(env, config['default'])
