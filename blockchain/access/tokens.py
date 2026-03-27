"""
MediSure Vault - Access Token Management Module

This module handles patient-controlled time-bound one-time access tokens
for secure prescription sharing with pharmacies.
"""

from database import db
from models import AccessToken, Prescription
from config import Config
from blockchain.ledger import record_token_event
from audit.logger import log_audit_event
from auth.utils import generate_secure_token, get_client_ip
from datetime import datetime, timedelta


def generate_access_token(prescription_id, patient_id, validity_minutes=None):
    """
    Generate a patient-controlled time-bound one-time access token.
    
    Args:
        prescription_id (int): Prescription ID
        patient_id (int): Patient ID (must own the prescription)
        validity_minutes (int): Token validity period (optional, uses config default)
        
    Returns:
        tuple: (token_object, error_message)
    """
    # Validate prescription exists
    prescription = Prescription.query.get(prescription_id)
    if not prescription:
        return None, 'Prescription not found'
    
    # Verify patient owns the prescription
    if prescription.patient_id != patient_id:
        return None, 'Unauthorized: Not your prescription'
    
    # Check prescription state - can only generate tokens for SHARED or DISPENSED prescriptions
    if prescription.state not in ['SHARED', 'DISPENSED']:
        return None, f'Cannot generate token for prescription in {prescription.state} state. Must be SHARED first.'
    
    # Check if prescription is locked
    if prescription.is_locked():
        return None, 'Cannot generate token for locked prescription'
    
    # Validate and set validity period
    if validity_minutes is None:
        validity_minutes = Config.ACCESS_TOKEN['DEFAULT_VALIDITY_MINUTES']
    
    min_validity = Config.ACCESS_TOKEN['MIN_VALIDITY_MINUTES']
    max_validity = Config.ACCESS_TOKEN['MAX_VALIDITY_MINUTES']
    
    if validity_minutes < min_validity or validity_minutes > max_validity:
        return None, f'Validity must be between {min_validity} and {max_validity} minutes'
    
    # Generate cryptographically secure token
    token_string = generate_secure_token(Config.TOKEN_LENGTH)
    
    # Create access token
    access_token = AccessToken(
        token=token_string,
        prescription_id=prescription_id,
        patient_id=patient_id,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=validity_minutes),
        is_used=False,
        is_revoked=False
    )
    
    db.session.add(access_token)
    db.session.commit()
    
    # Record in blockchain
    record_token_event(
        event_type='TOKEN_GENERATED',
        prescription_id=prescription_id,
        patient_id=patient_id,
        token_id=access_token.id,
        details={
            'validity_minutes': validity_minutes,
            'expires_at': access_token.expires_at.isoformat()
        }
    )
    
    # Log audit event
    log_audit_event(
        event_type='TOKEN_GENERATED',
        user_id=patient_id,
        prescription_id=prescription_id,
        details={
            'token_id': access_token.id,
            'validity_minutes': validity_minutes
        },
        ip_address=get_client_ip()
    )
    
    return access_token, None


def validate_and_consume_token(token_string, prescription_id, pharmacist_id, ip_address):
    """
    Validate an access token and mark it as used (one-time use).
    
    Args:
        token_string (str): Token string to validate
        prescription_id (int): Expected prescription ID
        pharmacist_id (int): Pharmacist ID consuming the token
        ip_address (str): IP address of the request
        
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    # Find token
    access_token = AccessToken.query.filter_by(token=token_string).first()
    
    if not access_token:
        log_audit_event(
            event_type='TOKEN_VALIDATION_FAILED',
            user_id=pharmacist_id,
            prescription_id=prescription_id,
            details={'reason': 'token_not_found'},
            ip_address=ip_address
        )
        return False, 'Invalid token'
    
    # Verify token matches prescription
    if access_token.prescription_id != prescription_id:
        log_audit_event(
            event_type='TOKEN_VALIDATION_FAILED',
            user_id=pharmacist_id,
            prescription_id=prescription_id,
            details={'reason': 'prescription_mismatch', 'token_id': access_token.id},
            ip_address=ip_address
        )
        return False, 'Token does not match prescription'
    
    # Check if token is already used
    if access_token.is_used:
        log_audit_event(
            event_type='TOKEN_VALIDATION_FAILED',
            user_id=pharmacist_id,
            prescription_id=prescription_id,
            details={'reason': 'token_already_used', 'token_id': access_token.id},
            ip_address=ip_address
        )
        return False, 'Token has already been used'
    
    # Check if token is revoked
    if access_token.is_revoked:
        log_audit_event(
            event_type='TOKEN_VALIDATION_FAILED',
            user_id=pharmacist_id,
            prescription_id=prescription_id,
            details={'reason': 'token_revoked', 'token_id': access_token.id},
            ip_address=ip_address
        )
        return False, 'Token has been revoked'
    
    # Check if token is expired
    if datetime.utcnow() > access_token.expires_at:
        log_audit_event(
            event_type='TOKEN_VALIDATION_FAILED',
            user_id=pharmacist_id,
            prescription_id=prescription_id,
            details={'reason': 'token_expired', 'token_id': access_token.id},
            ip_address=ip_address
        )
        return False, 'Token has expired'
    
    # Token is valid - consume it (one-time use)
    access_token.consume(pharmacist_id, ip_address)
    db.session.commit()
    
    # Record token usage in blockchain
    record_token_event(
        event_type='TOKEN_USED',
        prescription_id=prescription_id,
        patient_id=access_token.patient_id,
        token_id=access_token.id,
        details={
            'pharmacist_id': pharmacist_id,
            'used_from_ip': ip_address,
            'used_at': access_token.used_at.isoformat()
        }
    )
    
    # Log audit event
    log_audit_event(
        event_type='TOKEN_USED',
        user_id=pharmacist_id,
        prescription_id=prescription_id,
        details={
            'token_id': access_token.id,
            'patient_id': access_token.patient_id
        },
        ip_address=ip_address
    )
    
    return True, None


def revoke_token(token_id, patient_id, reason=None):
    """
    Revoke an access token (patient can revoke their own tokens).
    
    Args:
        token_id (int): Token ID to revoke
        patient_id (int): Patient ID (must own the token)
        reason (str): Optional reason for revocation
        
    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    # Find token
    access_token = AccessToken.query.get(token_id)
    
    if not access_token:
        return False, 'Token not found'
    
    # Verify patient owns the token
    if access_token.patient_id != patient_id:
        return False, 'Unauthorized: Not your token'
    
    # Check if token is already used
    if access_token.is_used:
        return False, 'Cannot revoke used token'
    
    # Check if token is already revoked
    if access_token.is_revoked:
        return False, 'Token is already revoked'
    
    # Revoke the token
    access_token.revoke(reason)
    db.session.commit()
    
    # Record in blockchain
    record_token_event(
        event_type='TOKEN_REVOKED',
        prescription_id=access_token.prescription_id,
        patient_id=patient_id,
        token_id=token_id,
        details={
            'reason': reason or 'Revoked by patient',
            'revoked_at': access_token.revoked_at.isoformat()
        }
    )
    
    # Log audit event
    log_audit_event(
        event_type='TOKEN_REVOKED',
        user_id=patient_id,
        prescription_id=access_token.prescription_id,
        details={
            'token_id': token_id,
            'reason': reason
        },
        ip_address=get_client_ip()
    )
    
    return True, None


def get_patient_tokens(patient_id, prescription_id=None, include_expired=False):
    """
    Get all access tokens for a patient.
    
    Args:
        patient_id (int): Patient ID
        prescription_id (int): Optional filter by prescription
        include_expired (bool): Whether to include expired tokens
        
    Returns:
        list: List of AccessToken objects
    """
    query = AccessToken.query.filter_by(patient_id=patient_id)
    
    if prescription_id:
        query = query.filter_by(prescription_id=prescription_id)
    
    if not include_expired:
        query = query.filter(AccessToken.expires_at > datetime.utcnow())
    
    return query.order_by(AccessToken.created_at.desc()).all()


def get_active_tokens(patient_id, prescription_id=None):
    """
    Get all active (unused, not revoked, not expired) tokens for a patient.
    
    Args:
        patient_id (int): Patient ID
        prescription_id (int): Optional filter by prescription
        
    Returns:
        list: List of active AccessToken objects
    """
    query = AccessToken.query.filter_by(
        patient_id=patient_id,
        is_used=False,
        is_revoked=False
    ).filter(AccessToken.expires_at > datetime.utcnow())
    
    if prescription_id:
        query = query.filter_by(prescription_id=prescription_id)
    
    return query.order_by(AccessToken.created_at.desc()).all()


def cleanup_expired_tokens():
    """
    Clean up expired tokens (for maintenance).
    This is a background job that should run periodically.
    
    Returns:
        int: Number of tokens cleaned up
    """
    # Find all expired, unused, non-revoked tokens
    expired_tokens = AccessToken.query.filter(
        AccessToken.expires_at < datetime.utcnow(),
        AccessToken.is_used == False,
        AccessToken.is_revoked == False
    ).all()
    
    count = 0
    for token in expired_tokens:
        # Mark as revoked with reason
        token.revoke('Auto-revoked: Token expired')
        count += 1
    
    db.session.commit()
    
    return count


def get_token_statistics(patient_id=None):
    """
    Get statistics about access tokens.
    
    Args:
        patient_id (int): Optional patient ID to filter by
        
    Returns:
        dict: Token statistics
    """
    query = AccessToken.query
    
    if patient_id:
        query = query.filter_by(patient_id=patient_id)
    
    total = query.count()
    used = query.filter_by(is_used=True).count()
    revoked = query.filter_by(is_revoked=True).count()
    expired = query.filter(
        AccessToken.expires_at < datetime.utcnow(),
        AccessToken.is_used == False,
        AccessToken.is_revoked == False
    ).count()
    active = query.filter_by(
        is_used=False,
        is_revoked=False
    ).filter(AccessToken.expires_at > datetime.utcnow()).count()
    
    return {
        'total': total,
        'used': used,
        'revoked': revoked,
        'expired': expired,
        'active': active
    }


def verify_token_validity(token_string):
    """
    Check if a token is valid without consuming it.
    
    Args:
        token_string (str): Token string to verify
        
    Returns:
        tuple: (is_valid: bool, token_object or None, error_message or None)
    """
    # Find token
    access_token = AccessToken.query.filter_by(token=token_string).first()
    
    if not access_token:
        return False, None, 'Token not found'
    
    if access_token.is_used:
        return False, access_token, 'Token already used'
    
    if access_token.is_revoked:
        return False, access_token, 'Token revoked'
    
    if datetime.utcnow() > access_token.expires_at:
        return False, access_token, 'Token expired'
    
    return True, access_token, None


def extend_token_validity(token_id, patient_id, additional_minutes):
    """
    Extend the validity of an existing token (if not used/revoked).
    
    Args:
        token_id (int): Token ID
        patient_id (int): Patient ID (must own token)
        additional_minutes (int): Minutes to add to expiration
        
    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    # Find token
    access_token = AccessToken.query.get(token_id)
    
    if not access_token:
        return False, 'Token not found'
    
    # Verify patient owns the token
    if access_token.patient_id != patient_id:
        return False, 'Unauthorized: Not your token'
    
    # Check if token is used or revoked
    if access_token.is_used:
        return False, 'Cannot extend used token'
    
    if access_token.is_revoked:
        return False, 'Cannot extend revoked token'
    
    # Check if token is already expired
    if datetime.utcnow() > access_token.expires_at:
        return False, 'Cannot extend expired token'
    
    # Validate additional minutes
    if additional_minutes <= 0:
        return False, 'Additional minutes must be positive'
    
    # Calculate new expiration
    new_expiration = access_token.expires_at + timedelta(minutes=additional_minutes)
    
    # Check against max validity from creation
    max_expiration = access_token.created_at + timedelta(
        minutes=Config.ACCESS_TOKEN['MAX_VALIDITY_MINUTES']
    )
    
    if new_expiration > max_expiration:
        return False, f'Cannot extend beyond {Config.ACCESS_TOKEN["MAX_VALIDITY_MINUTES"]} minutes from creation'
    
    # Update expiration
    old_expiration = access_token.expires_at
    access_token.expires_at = new_expiration
    db.session.commit()
    
    # Log audit event
    log_audit_event(
        event_type='TOKEN_EXTENDED',
        user_id=patient_id,
        prescription_id=access_token.prescription_id,
        details={
            'token_id': token_id,
            'old_expiration': old_expiration.isoformat(),
            'new_expiration': new_expiration.isoformat(),
            'additional_minutes': additional_minutes
        },
        ip_address=get_client_ip()
    )
    
    return True, None
