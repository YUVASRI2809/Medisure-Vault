"""
MediSure Vault - Prescription Services Module

This module contains business logic for prescription lifecycle management including
creation, state transitions, locking, and tamper detection.
"""

from database import db
from models import Prescription, User, PharmacyAccess
from config import Config
from blockchain.ledger import record_prescription_event
from audit.logger import log_audit_event
from datetime import datetime, timedelta
from auth.utils import get_client_ip
import hashlib


def create_prescription(doctor_id, patient_id, medication_name, dosage, quantity, 
                       refills_allowed=0, instructions=None, diagnosis=None, 
                       expires_in_days=365):
    """
    Create a new prescription in CREATED state.
    
    Args:
        doctor_id (int): ID of doctor creating prescription
        patient_id (int): ID of patient receiving prescription
        medication_name (str): Name of medication
        dosage (str): Dosage information (e.g., "500mg")
        quantity (int): Quantity to dispense
        refills_allowed (int): Number of refills allowed
        instructions (str): Usage instructions
        diagnosis (str): Diagnosis/reason for prescription
        expires_in_days (int): Days until prescription expires
        
    Returns:
        tuple: (prescription, error_message)
    """
    # Validate doctor exists and has DOCTOR role
    doctor = User.query.get(doctor_id)
    if not doctor or doctor.role != 'DOCTOR':
        return None, 'Invalid doctor'
    
    # Validate patient exists and has PATIENT role
    patient = User.query.get(patient_id)
    if not patient or patient.role != 'PATIENT':
        return None, 'Invalid patient'
    
    # Validate quantity and refills
    if quantity <= 0:
        return None, 'Quantity must be positive'
    
    if refills_allowed < 0:
        return None, 'Refills cannot be negative'
    
    # Check anomaly rules for controlled substances
    from anomaly.rules import check_controlled_substance, check_doctor_daily_limit
    
    is_controlled, controlled_error = check_controlled_substance(medication_name, quantity)
    if not is_controlled:
        return None, controlled_error
    
    within_limit, limit_error = check_doctor_daily_limit(doctor_id)
    if not within_limit:
        return None, limit_error
    
    # Create prescription
    prescription = Prescription(
        patient_id=patient_id,
        doctor_id=doctor_id,
        medication_name=medication_name,
        dosage=dosage,
        quantity=quantity,
        refills_allowed=refills_allowed,
        instructions=instructions,
        diagnosis=diagnosis,
        state='CREATED',
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=expires_in_days)
    )
    
    # Compute content hash for integrity
    prescription.content_hash = prescription.compute_content_hash()
    
    # Save to database
    db.session.add(prescription)
    db.session.commit()
    
    # Record in blockchain
    record_prescription_event(
        event_type='PRESCRIPTION_CREATED',
        prescription_id=prescription.id,
        user_id=doctor_id,
        details={
            'patient_id': patient_id,
            'medication': medication_name,
            'dosage': dosage,
            'quantity': quantity,
            'state': 'CREATED'
        }
    )
    
    # Log audit event
    log_audit_event(
        event_type='PRESCRIPTION_CREATED',
        user_id=doctor_id,
        prescription_id=prescription.id,
        details={
            'patient_id': patient_id,
            'medication': medication_name,
            'dosage': dosage,
            'quantity': quantity
        },
        ip_address=get_client_ip()
    )
    
    return prescription, None


def share_prescription(prescription_id, doctor_id):
    """
    Transition prescription from CREATED to SHARED state.
    This makes it available for patient to generate access tokens.
    
    Args:
        prescription_id (int): Prescription ID
        doctor_id (int): Doctor ID (must be prescription creator)
        
    Returns:
        tuple: (prescription, error_message)
    """
    prescription = Prescription.query.get(prescription_id)
    
    if not prescription:
        return None, 'Prescription not found'
    
    # Verify doctor owns this prescription
    if prescription.doctor_id != doctor_id:
        return None, 'Unauthorized: Not your prescription'
    
    # Check if transition is allowed
    if not prescription.can_transition_to('SHARED'):
        return None, f'Cannot transition from {prescription.state} to SHARED'
    
    # Verify content integrity
    if not verify_prescription_integrity(prescription):
        prescription.add_tamper_event(
            'hash_mismatch',
            Config.TAMPER_SCORE_WEIGHTS['hash_mismatch'],
            'Content hash mismatch detected during share'
        )
        db.session.commit()
        return None, 'Prescription integrity compromised'
    
    # Update state
    prescription.state = 'SHARED'
    prescription.shared_at = datetime.utcnow()
    db.session.commit()
    
    # Record in blockchain
    record_prescription_event(
        event_type='PRESCRIPTION_SHARED',
        prescription_id=prescription.id,
        user_id=doctor_id,
        details={
            'previous_state': 'CREATED',
            'new_state': 'SHARED',
            'patient_id': prescription.patient_id
        }
    )
    
    # Log audit event
    log_audit_event(
        event_type='PRESCRIPTION_SHARED',
        user_id=doctor_id,
        prescription_id=prescription.id,
        details={'state_transition': 'CREATED -> SHARED'},
        ip_address=get_client_ip()
    )
    
    return prescription, None


def dispense_prescription(prescription_id, pharmacist_id, pharmacy_id, token):
    """
    Dispense a prescription (transition to DISPENSED state).
    Requires valid access token and performs collision detection.
    
    Args:
        prescription_id (int): Prescription ID
        pharmacist_id (int): Pharmacist ID
        pharmacy_id (str): Pharmacy identifier
        token (str): Access token provided by patient
        
    Returns:
        tuple: (prescription, error_message)
    """
    from access.tokens import validate_and_consume_token
    
    prescription = Prescription.query.get(prescription_id)
    
    if not prescription:
        return None, 'Prescription not found'
    
    # Verify pharmacist exists and has PHARMACIST role
    pharmacist = User.query.get(pharmacist_id)
    if not pharmacist or pharmacist.role != 'PHARMACIST':
        return None, 'Invalid pharmacist'
    
    # Check if prescription can be dispensed
    if not prescription.can_transition_to('DISPENSED'):
        return None, f'Cannot dispense prescription in {prescription.state} state'
    
    # Validate and consume access token
    token_valid, token_error = validate_and_consume_token(
        token, prescription_id, pharmacist_id, get_client_ip()
    )
    
    if not token_valid:
        # Log unauthorized access attempt
        prescription.add_tamper_event(
            'unauthorized_access',
            Config.TAMPER_SCORE_WEIGHTS['unauthorized_access'],
            f'Dispense attempted without valid token: {token_error}'
        )
        db.session.commit()
        
        log_audit_event(
            event_type='UNAUTHORIZED_DISPENSE_ATTEMPT',
            user_id=pharmacist_id,
            prescription_id=prescription.id,
            details={'error': token_error, 'pharmacy_id': pharmacy_id},
            ip_address=get_client_ip()
        )
        
        return None, f'Invalid access token: {token_error}'
    
    # Check for multi-pharmacy collision
    collision_detected, collision_pharmacy = detect_pharmacy_collision(
        prescription_id, pharmacy_id
    )
    
    if collision_detected:
        # Add tamper event for collision
        prescription.add_tamper_event(
            'collision_detected',
            Config.TAMPER_SCORE_WEIGHTS['collision_detected'],
            f'Multiple pharmacies detected: {collision_pharmacy} and {pharmacy_id}'
        )
        db.session.commit()
        
        log_audit_event(
            event_type='PHARMACY_COLLISION_DETECTED',
            user_id=pharmacist_id,
            prescription_id=prescription.id,
            details={
                'current_pharmacy': pharmacy_id,
                'colliding_pharmacy': collision_pharmacy,
                'tamper_score': prescription.tamper_score
            },
            ip_address=get_client_ip()
        )
        
        # Auto-lock on collision if configured
        if Config.COLLISION_DETECTION['AUTO_LOCK_ON_COLLISION']:
            lock_prescription(prescription_id, pharmacist_id, 
                            reason='Auto-locked due to multi-pharmacy collision')
            return None, 'Prescription locked due to multi-pharmacy collision detected'
        
        return None, 'Multi-pharmacy collision detected'
    
    # Record pharmacy access
    record_pharmacy_access(prescription_id, pharmacy_id, pharmacist_id, 'DISPENSE')
    
    # Check anomaly rules
    from anomaly.rules import check_dispense_timing, check_dangerous_combinations
    
    timing_valid, timing_error = check_dispense_timing(prescription.patient_id)
    if not timing_valid:
        log_audit_event(
            event_type='ANOMALY_DETECTED',
            user_id=pharmacist_id,
            prescription_id=prescription.id,
            details={'anomaly_type': 'timing', 'message': timing_error},
            ip_address=get_client_ip()
        )
    
    # Update prescription state
    previous_state = prescription.state
    prescription.state = 'DISPENSED'
    prescription.dispensed_at = datetime.utcnow()
    prescription.dispensed_by_id = pharmacist_id
    prescription.pharmacy_id = pharmacy_id
    db.session.commit()
    
    # Record in blockchain
    record_prescription_event(
        event_type='PRESCRIPTION_DISPENSED',
        prescription_id=prescription.id,
        user_id=pharmacist_id,
        details={
            'previous_state': previous_state,
            'new_state': 'DISPENSED',
            'pharmacy_id': pharmacy_id,
            'pharmacist_id': pharmacist_id
        }
    )
    
    # Log audit event
    log_audit_event(
        event_type='PRESCRIPTION_DISPENSED',
        user_id=pharmacist_id,
        prescription_id=prescription.id,
        details={
            'state_transition': f'{previous_state} -> DISPENSED',
            'pharmacy_id': pharmacy_id
        },
        ip_address=get_client_ip()
    )
    
    return prescription, None


def lock_prescription(prescription_id, user_id, reason=None):
    """
    Lock a prescription (transition to LOCKED state - terminal/immutable).
    This is the post-dispense locking mechanism.
    
    Args:
        prescription_id (int): Prescription ID
        user_id (int): User ID performing the lock
        reason (str): Optional reason for locking
        
    Returns:
        tuple: (prescription, error_message)
    """
    prescription = Prescription.query.get(prescription_id)
    
    if not prescription:
        return None, 'Prescription not found'
    
    # Check if prescription can be locked
    if not prescription.can_transition_to('LOCKED'):
        return None, f'Cannot lock prescription in {prescription.state} state. Must be DISPENSED first.'
    
    # Update to LOCKED state (terminal - no further transitions allowed)
    previous_state = prescription.state
    prescription.state = 'LOCKED'
    prescription.locked_at = datetime.utcnow()
    db.session.commit()
    
    # Record in blockchain
    record_prescription_event(
        event_type='PRESCRIPTION_LOCKED',
        prescription_id=prescription.id,
        user_id=user_id,
        details={
            'previous_state': previous_state,
            'new_state': 'LOCKED',
            'reason': reason or 'Post-dispense lock applied',
            'tamper_score': prescription.tamper_score
        }
    )
    
    # Log audit event
    log_audit_event(
        event_type='PRESCRIPTION_LOCKED',
        user_id=user_id,
        prescription_id=prescription.id,
        details={
            'state_transition': f'{previous_state} -> LOCKED',
            'reason': reason or 'Post-dispense lock applied'
        },
        ip_address=get_client_ip()
    )
    
    return prescription, None


def cancel_prescription(prescription_id, user_id):
    """
    Cancel a prescription before it is dispensed.
    
    Args:
        prescription_id (int): Prescription ID
        user_id (int): User ID (doctor who created it)
        
    Returns:
        tuple: (prescription, error_message)
    """
    prescription = Prescription.query.get(prescription_id)
    
    if not prescription:
        return None, 'Prescription not found'
    
    # Only doctor who created it can cancel
    if prescription.doctor_id != user_id:
        return None, 'Unauthorized: Only the prescribing doctor can cancel'
    
    # Check if cancellation is allowed
    if not prescription.can_transition_to('CANCELLED'):
        return None, f'Cannot cancel prescription in {prescription.state} state'
    
    # Update state
    previous_state = prescription.state
    prescription.state = 'CANCELLED'
    db.session.commit()
    
    # Record in blockchain
    record_prescription_event(
        event_type='PRESCRIPTION_CANCELLED',
        prescription_id=prescription.id,
        user_id=user_id,
        details={
            'previous_state': previous_state,
            'new_state': 'CANCELLED'
        }
    )
    
    # Log audit event
    log_audit_event(
        event_type='PRESCRIPTION_CANCELLED',
        user_id=user_id,
        prescription_id=prescription.id,
        details={'state_transition': f'{previous_state} -> CANCELLED'},
        ip_address=get_client_ip()
    )
    
    return prescription, None


def verify_prescription_integrity(prescription):
    """
    Verify prescription content integrity by comparing stored hash.
    
    Args:
        prescription (Prescription): Prescription object to verify
        
    Returns:
        bool: True if integrity intact, False if tampered
    """
    current_hash = prescription.compute_content_hash()
    return current_hash == prescription.content_hash


def detect_pharmacy_collision(prescription_id, current_pharmacy_id):
    """
    Detect if multiple pharmacies have accessed the same prescription.
    This is a key tamper detection mechanism.
    
    Args:
        prescription_id (int): Prescription ID
        current_pharmacy_id (str): Current pharmacy attempting access
        
    Returns:
        tuple: (collision_detected: bool, colliding_pharmacy_id: str or None)
    """
    if not Config.COLLISION_DETECTION['ENABLED']:
        return False, None
    
    # Get detection window
    window_hours = Config.COLLISION_DETECTION['DETECTION_WINDOW_HOURS']
    window_start = datetime.utcnow() - timedelta(hours=window_hours)
    
    # Check for previous pharmacy accesses
    previous_accesses = PharmacyAccess.query.filter(
        PharmacyAccess.prescription_id == prescription_id,
        PharmacyAccess.accessed_at >= window_start
    ).all()
    
    # Check if any access is from a different pharmacy
    for access in previous_accesses:
        if access.pharmacy_id != current_pharmacy_id:
            return True, access.pharmacy_id
    
    return False, None


def record_pharmacy_access(prescription_id, pharmacy_id, pharmacist_id, access_type):
    """
    Record pharmacy access for collision detection.
    
    Args:
        prescription_id (int): Prescription ID
        pharmacy_id (str): Pharmacy identifier
        pharmacist_id (int): Pharmacist user ID
        access_type (str): Type of access (VIEW or DISPENSE)
    """
    access_record = PharmacyAccess(
        prescription_id=prescription_id,
        pharmacy_id=pharmacy_id,
        pharmacist_id=pharmacist_id,
        access_type=access_type,
        accessed_at=datetime.utcnow()
    )
    
    db.session.add(access_record)
    db.session.commit()


def get_prescription_tamper_score(prescription_id):
    """
    Get current tamper score and severity for a prescription.
    
    Args:
        prescription_id (int): Prescription ID
        
    Returns:
        dict: Tamper score information
    """
    prescription = Prescription.query.get(prescription_id)
    
    if not prescription:
        return None
    
    return {
        'prescription_id': prescription_id,
        'tamper_score': prescription.tamper_score,
        'severity': prescription.get_tamper_severity(),
        'events': prescription.tamper_events,
        'state': prescription.state,
        'is_locked': prescription.is_locked()
    }


def compute_prescription_tamper_score(prescription_id):
    """
    Recompute tamper score from blockchain and database comparison.
    
    Args:
        prescription_id (int): Prescription ID
        
    Returns:
        int: Computed tamper score
    """
    from blockchain.ledger import Blockchain
    
    prescription = Prescription.query.get(prescription_id)
    if not prescription:
        return 0
    
    score = 0
    
    # Check content hash integrity
    if not verify_prescription_integrity(prescription):
        score += Config.TAMPER_SCORE_WEIGHTS['hash_mismatch']
    
    # Check blockchain integrity
    blockchain = Blockchain()
    tamper_result = blockchain.detect_tampering(prescription_id)
    
    if tamper_result.get('tampered'):
        score += Config.TAMPER_SCORE_WEIGHTS['hash_mismatch']
    
    # Check for pharmacy collisions
    collision_detected, _ = detect_pharmacy_collision(prescription_id, 
                                                      prescription.pharmacy_id or 'none')
    if collision_detected:
        score += Config.TAMPER_SCORE_WEIGHTS['collision_detected']
    
    return min(score, 100)  # Cap at 100


def update_prescription(prescription_id, doctor_id, **kwargs):
    """
    Update prescription details (only allowed in CREATED or SHARED state).
    
    Args:
        prescription_id (int): Prescription ID
        doctor_id (int): Doctor ID (must be creator)
        **kwargs: Fields to update
        
    Returns:
        tuple: (prescription, error_message)
    """
    prescription = Prescription.query.get(prescription_id)
    
    if not prescription:
        return None, 'Prescription not found'
    
    # Verify doctor owns this prescription
    if prescription.doctor_id != doctor_id:
        return None, 'Unauthorized: Not your prescription'

    # Block edits on locked prescriptions
    if prescription.is_locked():
        return None, 'Prescription is locked and cannot be edited.'

    # Check if prescription is editable (state-based check)
    if not prescription.is_editable():
        return None, f'Cannot edit prescription in {prescription.state} state'
    
    # Update allowed fields
    allowed_fields = ['medication_name', 'dosage', 'quantity', 'refills_allowed', 
                     'instructions', 'diagnosis']
    
    for field, value in kwargs.items():
        if field in allowed_fields and value is not None:
            setattr(prescription, field, value)
    
    # Recompute content hash after update
    prescription.content_hash = prescription.compute_content_hash()
    
    db.session.commit()
    
    # Log update
    log_audit_event(
        event_type='PRESCRIPTION_UPDATED',
        user_id=doctor_id,
        prescription_id=prescription.id,
        details={'updated_fields': list(kwargs.keys())},
        ip_address=get_client_ip()
    )
    
    return prescription, None
