"""
MediSure Vault - Security Utility Module

Central module for:
  - Tamper score management (deduct points for suspicious activity)
  - Multi-pharmacy collision detection
  - Suspicious activity flagging (is_flagged)
  - Enhanced audit logging helpers

Tamper score starts at 100 and decreases on suspicious events.
Minimum is 0. If score drops below FLAG_THRESHOLD the prescription
is automatically flagged.

Usage:
    from security import deduct_tamper_score, check_pharmacy_collision, flag_if_needed
"""

from database import db
from datetime import datetime, timedelta
import json

# ─── Thresholds ───────────────────────────────────────────────────────────────

FLAG_THRESHOLD   = 60   # auto-flag when score drops below this
BLOCK_THRESHOLD  = 30   # show hard warning / block access below this

# ─── Deduction weights ────────────────────────────────────────────────────────

DEDUCTIONS = {
    'expired_token_used':        30,   # token used after expiry
    'multi_pharmacy_collision':  40,   # >1 pharmacist accessed same prescription
    'rapid_token_requests':      20,   # multiple tokens generated in short window
    'unauthorized_access':       50,   # access attempt without valid token
    'invalid_token_attempt':     15,   # wrong/bad token submitted
    'state_violation':           25,   # illegal state transition attempted
}


# ─── Core utility ─────────────────────────────────────────────────────────────

def deduct_tamper_score(prescription_id, reason, user_id=None, extra_details=None):
    """
    Deduct points from a prescription's tamper score and auto-flag if needed.

    Args:
        prescription_id (int): Target prescription
        reason (str):          Key from DEDUCTIONS dict (e.g. 'expired_token_used')
        user_id (int):         User who triggered the event (optional)
        extra_details (dict):  Any extra context to store in the tamper event log

    Returns:
        Prescription: Updated prescription object, or None if not found
    """
    from models import Prescription
    from audit.logger import log_audit_event
    from auth.utils import get_client_ip

    prescription = Prescription.query.get(prescription_id)
    if not prescription:
        return None

    deduction = DEDUCTIONS.get(reason, 10)
    old_score = prescription.tamper_score

    # Deduct — floor at 0
    prescription.tamper_score = max(0, prescription.tamper_score - deduction)

    # Record the tamper event inside the prescription's JSON log
    events = json.loads(prescription.tamper_events or '[]')
    events.append({
        'timestamp':  datetime.utcnow().isoformat(),
        'reason':     reason,
        'deduction':  deduction,
        'score_before': old_score,
        'score_after':  prescription.tamper_score,
        'user_id':    user_id,
        'details':    extra_details or {}
    })
    prescription.tamper_events = json.dumps(events)

    # Auto-flag if score drops below threshold
    flag_if_needed(prescription)

    db.session.commit()

    # Write audit log
    log_audit_event(
        event_type='TAMPER_SCORE_DEDUCTED',
        user_id=user_id,
        prescription_id=prescription_id,
        details={
            'reason':       reason,
            'deduction':    deduction,
            'score_before': old_score,
            'score_after':  prescription.tamper_score,
            'is_flagged':   prescription.is_flagged,
            **(extra_details or {})
        },
        ip_address=get_client_ip(),
        status='WARNING'
    )

    return prescription


def flag_if_needed(prescription):
    """
    Set is_flagged = True if tamper_score < FLAG_THRESHOLD.
    Does NOT commit — caller must commit.
    """
    if prescription.tamper_score < FLAG_THRESHOLD and not prescription.is_flagged:
        prescription.is_flagged = True


def is_access_blocked(prescription):
    """
    Return True if the prescription's tamper score is so low that
    access should be hard-blocked (score < BLOCK_THRESHOLD).
    """
    return prescription.tamper_score < BLOCK_THRESHOLD


# ─── Multi-pharmacy collision detection ──────────────────────────────────────

def check_pharmacy_collision(prescription_id, current_pharmacist_id):
    """
    Detect if more than one pharmacist has accessed this prescription.

    Looks at the audit log for TOKEN_VALIDATION_FAILED or PRESCRIPTION_DISPENSED
    events from a *different* pharmacist within the last 24 hours.

    Args:
        prescription_id (int):      Prescription being accessed
        current_pharmacist_id (int): Pharmacist currently accessing

    Returns:
        tuple: (collision_detected: bool, other_pharmacist_ids: list[int])
    """
    from models import AuditLog

    cutoff = datetime.utcnow() - timedelta(hours=24)

    # Find all pharmacist accesses to this prescription in the last 24 h
    logs = AuditLog.query.filter(
        AuditLog.prescription_id == prescription_id,
        AuditLog.timestamp >= cutoff,
        AuditLog.event_type.in_([
            'TOKEN_USED',
            'PRESCRIPTION_DISPENSED',
            'TOKEN_VALIDATION_FAILED',
        ])
    ).all()

    other_ids = set()
    for log in logs:
        if log.user_id and log.user_id != current_pharmacist_id:
            other_ids.add(log.user_id)

    return bool(other_ids), list(other_ids)


def handle_pharmacy_collision(prescription_id, current_pharmacist_id):
    """
    If a collision is detected, deduct tamper score and log the event.

    Returns:
        bool: True if collision was detected and handled
    """
    collision, others = check_pharmacy_collision(prescription_id, current_pharmacist_id)
    if collision:
        deduct_tamper_score(
            prescription_id=prescription_id,
            reason='multi_pharmacy_collision',
            user_id=current_pharmacist_id,
            extra_details={'other_pharmacist_ids': others}
        )
    return collision


# ─── Rapid token request detection ───────────────────────────────────────────

def check_rapid_token_requests(prescription_id, patient_id, window_minutes=10):
    """
    Detect if a patient has generated more than 2 tokens for the same
    prescription within `window_minutes`.

    Args:
        prescription_id (int): Prescription to check
        patient_id (int):      Patient generating the token
        window_minutes (int):  Time window to check

    Returns:
        bool: True if rapid requests detected
    """
    from models import AccessToken

    cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
    count = AccessToken.query.filter(
        AccessToken.prescription_id == prescription_id,
        AccessToken.patient_id == patient_id,
        AccessToken.created_at >= cutoff
    ).count()

    return count >= 2   # 3rd request in window = suspicious


# ─── Enhanced audit log helper ────────────────────────────────────────────────

def audit(event_type, user_id=None, prescription_id=None,
          details=None, status='SUCCESS', ip_address=None):
    """
    Thin wrapper around log_audit_event that also passes `status` and
    auto-resolves the caller's role from the session.

    Args:
        event_type (str):      e.g. 'LOGIN', 'DISPENSE', 'TOKEN_USED'
        user_id (int):         Acting user
        prescription_id (int): Related prescription (optional)
        details (dict):        Extra context
        status (str):          'SUCCESS' or 'FAILED'
        ip_address (str):      Client IP (auto-resolved if None)
    """
    from audit.logger import log_audit_event
    from auth.utils import get_client_ip
    from flask import session

    role = session.get('role', 'UNKNOWN')
    merged_details = {'role': role, **(details or {})}

    log_audit_event(
        event_type=event_type,
        user_id=user_id,
        prescription_id=prescription_id,
        details=merged_details,
        ip_address=ip_address or get_client_ip(),
        status=status
    )
