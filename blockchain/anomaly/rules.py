"""
MediSure Vault - Anomaly Detection Rules Module

This module implements rule-based prescription anomaly detection including
controlled substance monitoring, dangerous drug combinations, and usage patterns.
"""

from models import Prescription, User
from config import Config
from datetime import datetime, timedelta
from audit.logger import log_audit_event
from auth.utils import get_client_ip


def check_controlled_substance(medication_name, quantity):
    """
    Check if medication is a controlled substance and validate quantity limits.
    
    Args:
        medication_name (str): Name of medication
        quantity (int): Quantity to dispense
        
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    controlled_substances = Config.ANOMALY_RULES['CONTROLLED_SUBSTANCES']
    max_quantity = Config.ANOMALY_RULES['MAX_CONTROLLED_QUANTITY']
    
    # Check if medication is controlled
    is_controlled = any(
        substance.lower() in medication_name.lower() 
        for substance in controlled_substances
    )
    
    if is_controlled:
        if quantity > max_quantity:
            # Log anomaly
            log_audit_event(
                event_type='ANOMALY_DETECTED',
                user_id=None,
                prescription_id=None,
                details={
                    'anomaly_type': 'controlled_substance_quantity',
                    'medication': medication_name,
                    'quantity': quantity,
                    'max_allowed': max_quantity
                },
                ip_address=get_client_ip()
            )
            
            return False, f'Controlled substance quantity exceeds limit ({max_quantity})'
    
    return True, None


def check_doctor_daily_limit(doctor_id):
    """
    Check if doctor has exceeded daily prescription creation limit.
    
    Args:
        doctor_id (int): Doctor user ID
        
    Returns:
        tuple: (within_limit: bool, error_message: str or None)
    """
    max_daily = Config.ANOMALY_RULES['MAX_DAILY_PRESCRIPTIONS_PER_DOCTOR']
    
    # Get today's start
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Count prescriptions created today
    count = Prescription.query.filter(
        Prescription.doctor_id == doctor_id,
        Prescription.created_at >= today_start
    ).count()
    
    if count >= max_daily:
        # Log anomaly
        log_audit_event(
            event_type='ANOMALY_DETECTED',
            user_id=doctor_id,
            prescription_id=None,
            details={
                'anomaly_type': 'doctor_daily_limit_exceeded',
                'current_count': count,
                'max_allowed': max_daily
            },
            ip_address=get_client_ip()
        )
        
        return False, f'Daily prescription limit exceeded ({max_daily} per day)'
    
    return True, None


def check_pharmacy_daily_limit(pharmacy_id):
    """
    Check if pharmacy has exceeded daily dispensing limit.
    
    Args:
        pharmacy_id (str): Pharmacy identifier
        
    Returns:
        tuple: (within_limit: bool, error_message: str or None)
    """
    max_daily = Config.ANOMALY_RULES['MAX_DAILY_DISPENSES_PER_PHARMACY']
    
    # Get today's start
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Count prescriptions dispensed today
    count = Prescription.query.filter(
        Prescription.pharmacy_id == pharmacy_id,
        Prescription.dispensed_at >= today_start
    ).count()
    
    if count >= max_daily:
        # Log anomaly
        log_audit_event(
            event_type='ANOMALY_DETECTED',
            user_id=None,
            prescription_id=None,
            details={
                'anomaly_type': 'pharmacy_daily_limit_exceeded',
                'pharmacy_id': pharmacy_id,
                'current_count': count,
                'max_allowed': max_daily
            },
            ip_address=get_client_ip()
        )
        
        return False, f'Pharmacy daily dispensing limit exceeded ({max_daily} per day)'
    
    return True, None


def check_refill_limit(prescription):
    """
    Check if prescription has exceeded refill limits.
    
    Args:
        prescription (Prescription): Prescription object
        
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    max_refills = Config.ANOMALY_RULES['MAX_REFILLS_ALLOWED']
    
    if prescription.refills_allowed > max_refills:
        # Log anomaly
        log_audit_event(
            event_type='ANOMALY_DETECTED',
            user_id=prescription.doctor_id,
            prescription_id=prescription.id,
            details={
                'anomaly_type': 'excessive_refills',
                'refills_allowed': prescription.refills_allowed,
                'max_allowed': max_refills
            },
            ip_address=get_client_ip()
        )
        
        return False, f'Refills exceed maximum allowed ({max_refills})'
    
    return True, None


def check_dispense_timing(patient_id):
    """
    Check for suspicious rapid dispensing patterns for a patient.
    Detects if patient is getting prescriptions dispensed too frequently.
    
    Args:
        patient_id (int): Patient user ID
        
    Returns:
        tuple: (is_valid: bool, warning_message: str or None)
    """
    min_hours = Config.ANOMALY_RULES['MIN_TIME_BETWEEN_DISPENSES_HOURS']
    
    # Get most recent dispensed prescription for this patient
    recent_dispense = Prescription.query.filter(
        Prescription.patient_id == patient_id,
        Prescription.dispensed_at.isnot(None)
    ).order_by(Prescription.dispensed_at.desc()).first()
    
    if recent_dispense:
        time_since_last = datetime.utcnow() - recent_dispense.dispensed_at
        hours_since_last = time_since_last.total_seconds() / 3600
        
        if hours_since_last < min_hours:
            # Log anomaly (warning level, not blocking)
            log_audit_event(
                event_type='ANOMALY_DETECTED',
                user_id=patient_id,
                prescription_id=None,
                details={
                    'anomaly_type': 'rapid_dispensing_pattern',
                    'hours_since_last_dispense': hours_since_last,
                    'min_hours_required': min_hours,
                    'last_prescription_id': recent_dispense.id
                },
                ip_address=get_client_ip()
            )
            
            # Return warning but don't block
            return True, f'Warning: Multiple prescriptions dispensed within {min_hours} hours'
    
    return True, None


def check_prescription_age(prescription):
    """
    Check if prescription is too old to be dispensed.
    
    Args:
        prescription (Prescription): Prescription object
        
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    max_age_days = Config.ANOMALY_RULES['MAX_PRESCRIPTION_AGE_DAYS']
    
    if prescription.expires_at and datetime.utcnow() > prescription.expires_at:
        # Log anomaly
        log_audit_event(
            event_type='ANOMALY_DETECTED',
            user_id=prescription.patient_id,
            prescription_id=prescription.id,
            details={
                'anomaly_type': 'expired_prescription',
                'expired_at': prescription.expires_at.isoformat(),
                'age_days': (datetime.utcnow() - prescription.created_at).days
            },
            ip_address=get_client_ip()
        )
        
        return False, 'Prescription has expired'
    
    age_days = (datetime.utcnow() - prescription.created_at).days
    
    if age_days > max_age_days:
        # Log anomaly
        log_audit_event(
            event_type='ANOMALY_DETECTED',
            user_id=prescription.patient_id,
            prescription_id=prescription.id,
            details={
                'anomaly_type': 'prescription_too_old',
                'age_days': age_days,
                'max_allowed_days': max_age_days
            },
            ip_address=get_client_ip()
        )
        
        return False, f'Prescription is too old (over {max_age_days} days)'
    
    return True, None


def check_dangerous_combinations(patient_id, new_medication):
    """
    Check for dangerous drug combinations based on patient's active prescriptions.
    
    Args:
        patient_id (int): Patient user ID
        new_medication (str): New medication being prescribed
        
    Returns:
        tuple: (is_safe: bool, warning_message: str or None)
    """
    blacklisted_combinations = Config.ANOMALY_RULES['BLACKLISTED_COMBINATIONS']
    
    # Get patient's active prescriptions (not cancelled or locked)
    active_prescriptions = Prescription.query.filter(
        Prescription.patient_id == patient_id,
        Prescription.state.in_(['CREATED', 'SHARED', 'DISPENSED'])
    ).all()
    
    # Extract medication names
    active_medications = [p.medication_name for p in active_prescriptions]
    
    # Check for dangerous combinations
    for med1, med2 in blacklisted_combinations:
        # Check if new medication conflicts with any active medication
        if (new_medication.lower() in med1.lower() or new_medication.lower() in med2.lower()):
            for active_med in active_medications:
                if (active_med.lower() in med1.lower() or active_med.lower() in med2.lower()):
                    if new_medication.lower() != active_med.lower():
                        # Log dangerous combination
                        log_audit_event(
                            event_type='ANOMALY_DETECTED',
                            user_id=patient_id,
                            prescription_id=None,
                            details={
                                'anomaly_type': 'dangerous_drug_combination',
                                'new_medication': new_medication,
                                'conflicting_medication': active_med,
                                'blacklisted_pair': f'{med1} + {med2}'
                            },
                            ip_address=get_client_ip()
                        )
                        
                        return False, f'Dangerous combination detected: {new_medication} with existing {active_med}'
    
    return True, None


def check_duplicate_prescription(patient_id, medication_name, dosage):
    """
    Check if patient already has an active prescription for the same medication.
    
    Args:
        patient_id (int): Patient user ID
        medication_name (str): Medication name
        dosage (str): Dosage
        
    Returns:
        tuple: (is_unique: bool, warning_message: str or None)
    """
    # Get active prescriptions for same medication
    duplicate = Prescription.query.filter(
        Prescription.patient_id == patient_id,
        Prescription.medication_name == medication_name,
        Prescription.dosage == dosage,
        Prescription.state.in_(['CREATED', 'SHARED', 'DISPENSED'])
    ).first()
    
    if duplicate:
        # Log anomaly (warning level)
        log_audit_event(
            event_type='ANOMALY_DETECTED',
            user_id=patient_id,
            prescription_id=duplicate.id,
            details={
                'anomaly_type': 'duplicate_prescription',
                'medication': medication_name,
                'dosage': dosage,
                'existing_prescription_id': duplicate.id
            },
            ip_address=get_client_ip()
        )
        
        # Return warning but don't block (doctor may have legitimate reason)
        return True, f'Warning: Patient already has active prescription for {medication_name} {dosage}'
    
    return True, None


def check_quantity_anomaly(medication_name, quantity):
    """
    Check for unusually large quantities that may indicate fraud or error.
    
    Args:
        medication_name (str): Medication name
        quantity (int): Quantity to dispense
        
    Returns:
        tuple: (is_reasonable: bool, warning_message: str or None)
    """
    # Define reasonable quantity thresholds
    reasonable_max = 90  # Most prescriptions are 30-90 days supply
    
    if quantity > reasonable_max:
        # Log anomaly (warning level)
        log_audit_event(
            event_type='ANOMALY_DETECTED',
            user_id=None,
            prescription_id=None,
            details={
                'anomaly_type': 'unusual_quantity',
                'medication': medication_name,
                'quantity': quantity,
                'threshold': reasonable_max
            },
            ip_address=get_client_ip()
        )
        
        # Return warning but don't block
        return True, f'Warning: Unusually large quantity ({quantity} units)'
    
    return True, None


def check_doctor_credentials(doctor_id):
    """
    Verify doctor has valid credentials/license.
    
    Args:
        doctor_id (int): Doctor user ID
        
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    doctor = User.query.get(doctor_id)
    
    if not doctor:
        return False, 'Doctor not found'
    
    if doctor.role != 'DOCTOR':
        return False, 'User is not a doctor'
    
    if not doctor.is_active:
        return False, 'Doctor account is inactive'
    
    # In production, you would check license number against external database
    # For now, just check if license number exists
    if not doctor.license_number:
        log_audit_event(
            event_type='ANOMALY_DETECTED',
            user_id=doctor_id,
            prescription_id=None,
            details={
                'anomaly_type': 'missing_license_number',
                'doctor_id': doctor_id
            },
            ip_address=get_client_ip()
        )
        
        return False, 'Doctor license number not on file'
    
    return True, None


def check_pharmacist_credentials(pharmacist_id, pharmacy_id):
    """
    Verify pharmacist has valid credentials and pharmacy association.
    
    Args:
        pharmacist_id (int): Pharmacist user ID
        pharmacy_id (str): Pharmacy identifier
        
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    pharmacist = User.query.get(pharmacist_id)
    
    if not pharmacist:
        return False, 'Pharmacist not found'
    
    if pharmacist.role != 'PHARMACIST':
        return False, 'User is not a pharmacist'
    
    if not pharmacist.is_active:
        return False, 'Pharmacist account is inactive'
    
    # Check if pharmacist is associated with the pharmacy
    if pharmacist.pharmacy_id and pharmacist.pharmacy_id != pharmacy_id:
        log_audit_event(
            event_type='ANOMALY_DETECTED',
            user_id=pharmacist_id,
            prescription_id=None,
            details={
                'anomaly_type': 'pharmacy_mismatch',
                'pharmacist_id': pharmacist_id,
                'registered_pharmacy': pharmacist.pharmacy_id,
                'attempted_pharmacy': pharmacy_id
            },
            ip_address=get_client_ip()
        )
        
        return False, 'Pharmacist not authorized for this pharmacy'
    
    return True, None


def run_all_prescription_checks(prescription):
    """
    Run all relevant anomaly checks for a prescription.
    
    Args:
        prescription (Prescription): Prescription object
        
    Returns:
        list: List of anomaly warnings/errors
    """
    anomalies = []
    
    # Check prescription age
    is_valid, msg = check_prescription_age(prescription)
    if not is_valid:
        anomalies.append({'type': 'error', 'message': msg})
    
    # Check refill limits
    is_valid, msg = check_refill_limit(prescription)
    if not is_valid:
        anomalies.append({'type': 'error', 'message': msg})
    
    # Check controlled substance
    is_valid, msg = check_controlled_substance(
        prescription.medication_name, 
        prescription.quantity
    )
    if not is_valid:
        anomalies.append({'type': 'error', 'message': msg})
    
    # Check dangerous combinations
    is_safe, msg = check_dangerous_combinations(
        prescription.patient_id,
        prescription.medication_name
    )
    if not is_safe:
        anomalies.append({'type': 'warning', 'message': msg})
    
    # Check quantity anomaly
    is_reasonable, msg = check_quantity_anomaly(
        prescription.medication_name,
        prescription.quantity
    )
    if msg:
        anomalies.append({'type': 'warning', 'message': msg})
    
    return anomalies


def get_anomaly_statistics(days=30):
    """
    Get statistics about detected anomalies.
    
    Args:
        days (int): Number of days to look back
        
    Returns:
        dict: Anomaly statistics
    """
    from models import AuditLog
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Get all anomaly detection events
    anomaly_logs = AuditLog.query.filter(
        AuditLog.event_type == 'ANOMALY_DETECTED',
        AuditLog.timestamp >= cutoff_date
    ).all()
    
    # Count by anomaly type
    by_type = {}
    for log in anomaly_logs:
        import json
        details = json.loads(log.details) if log.details else {}
        anomaly_type = details.get('anomaly_type', 'unknown')
        by_type[anomaly_type] = by_type.get(anomaly_type, 0) + 1
    
    return {
        'total_anomalies': len(anomaly_logs),
        'days': days,
        'by_type': by_type
    }
