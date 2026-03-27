"""
MediSure Vault - Prescription Routes Module

This module handles all prescription-related HTTP routes including creation,
viewing, dispensing, and state management.
"""

from flask import Blueprint, request, jsonify, session
from auth.utils import login_required, role_required, permission_required, get_client_ip
from prescriptions.services import (
    create_prescription, share_prescription, dispense_prescription,
    lock_prescription, cancel_prescription, update_prescription,
    get_prescription_tamper_score, verify_prescription_integrity
)
from models import Prescription, User
from database import db
from datetime import datetime


# Create prescriptions blueprint
prescriptions_bp = Blueprint('prescriptions', __name__)


@prescriptions_bp.route('/create', methods=['POST'])
@login_required
@permission_required('create_prescription')
def create():
    """
    Create a new prescription (doctors only).
    
    Expected JSON body:
    {
        "patient_id": int,
        "medication_name": "string",
        "dosage": "string",
        "quantity": int,
        "refills_allowed": int (optional, default 0),
        "instructions": "string" (optional),
        "diagnosis": "string" (optional),
        "expires_in_days": int (optional, default 365)
    }
    
    Returns:
        JSON response with created prescription
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Extract required fields
    patient_id = data.get('patient_id')
    medication_name = data.get('medication_name')
    dosage = data.get('dosage')
    quantity = data.get('quantity')
    
    # Validate required fields
    if not all([patient_id, medication_name, dosage, quantity]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Get doctor ID from session
    doctor_id = session.get('user_id')
    
    # Create prescription
    prescription, error = create_prescription(
        doctor_id=doctor_id,
        patient_id=patient_id,
        medication_name=medication_name,
        dosage=dosage,
        quantity=quantity,
        refills_allowed=data.get('refills_allowed', 0),
        instructions=data.get('instructions'),
        diagnosis=data.get('diagnosis'),
        expires_in_days=data.get('expires_in_days', 365)
    )
    
    if error:
        return jsonify({'error': error}), 400
    
    return jsonify({
        'message': 'Prescription created successfully',
        'prescription': prescription.to_dict()
    }), 201


@prescriptions_bp.route('/<int:prescription_id>', methods=['GET'])
@login_required
def get_prescription(prescription_id):
    """
    Get prescription details by ID.
    Access control:
    - Patients can view their own prescriptions
    - Doctors can view prescriptions they created
    - Pharmacists need valid token (handled separately)
    - Admins can view all
    
    Args:
        prescription_id: Prescription ID
    
    Returns:
        JSON response with prescription details
    """
    prescription = Prescription.query.get(prescription_id)
    
    if not prescription:
        return jsonify({'error': 'Prescription not found'}), 404
    
    user_id = session.get('user_id')
    user_role = session.get('role')
    
    # Check access permissions
    if user_role == 'ADMIN':
        # Admins can view all
        pass
    elif user_role == 'PATIENT':
        # Patients can only view their own
        if prescription.patient_id != user_id:
            return jsonify({'error': 'Unauthorized access'}), 403
    elif user_role == 'DOCTOR':
        # Doctors can view prescriptions they created
        if prescription.doctor_id != user_id:
            return jsonify({'error': 'Unauthorized access'}), 403
    elif user_role == 'PHARMACIST':
        # Pharmacists need valid token (checked in dispense route)
        return jsonify({'error': 'Pharmacists must use token-based access'}), 403
    else:
        return jsonify({'error': 'Unauthorized access'}), 403
    
    return jsonify({'prescription': prescription.to_dict()}), 200


@prescriptions_bp.route('/', methods=['GET'])
@login_required
def list_prescriptions():
    """
    List prescriptions based on user role.
    
    Query parameters:
        state: Filter by state (optional)
        patient_id: Filter by patient (admin/doctor only)
        doctor_id: Filter by doctor (admin only)
        page: Page number (default 1)
        per_page: Items per page (default 20)
    
    Returns:
        JSON response with paginated prescription list
    """
    user_id = session.get('user_id')
    user_role = session.get('role')
    
    # Build query based on role
    query = Prescription.query
    
    if user_role == 'PATIENT':
        # Patients see only their prescriptions
        query = query.filter_by(patient_id=user_id)
    elif user_role == 'DOCTOR':
        # Doctors see prescriptions they created
        query = query.filter_by(doctor_id=user_id)
    elif user_role == 'ADMIN':
        # Admins can filter by patient_id or doctor_id
        patient_id_filter = request.args.get('patient_id', type=int)
        doctor_id_filter = request.args.get('doctor_id', type=int)
        
        if patient_id_filter:
            query = query.filter_by(patient_id=patient_id_filter)
        if doctor_id_filter:
            query = query.filter_by(doctor_id=doctor_id_filter)
    else:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Apply state filter if provided
    state_filter = request.args.get('state')
    if state_filter:
        query = query.filter_by(state=state_filter)
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    pagination = query.order_by(Prescription.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'prescriptions': [p.to_dict() for p in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages
    }), 200


@prescriptions_bp.route('/<int:prescription_id>/share', methods=['POST'])
@login_required
@permission_required('edit_prescription')
def share(prescription_id):
    """
    Share a prescription (CREATED -> SHARED transition).
    Only the doctor who created it can share.
    
    Args:
        prescription_id: Prescription ID
    
    Returns:
        JSON response confirming share
    """
    doctor_id = session.get('user_id')
    
    prescription, error = share_prescription(prescription_id, doctor_id)
    
    if error:
        return jsonify({'error': error}), 400
    
    return jsonify({
        'message': 'Prescription shared successfully',
        'prescription': prescription.to_dict()
    }), 200


@prescriptions_bp.route('/<int:prescription_id>/dispense', methods=['POST'])
@login_required
@permission_required('dispense_prescription')
def dispense(prescription_id):
    """
    Dispense a prescription (SHARED -> DISPENSED transition).
    Requires valid access token from patient.
    
    Expected JSON body:
    {
        "token": "string",
        "pharmacy_id": "string"
    }
    
    Args:
        prescription_id: Prescription ID
    
    Returns:
        JSON response confirming dispensing
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    token = data.get('token')
    pharmacy_id = data.get('pharmacy_id')
    
    if not token or not pharmacy_id:
        return jsonify({'error': 'Token and pharmacy_id required'}), 400
    
    pharmacist_id = session.get('user_id')
    
    prescription, error = dispense_prescription(
        prescription_id=prescription_id,
        pharmacist_id=pharmacist_id,
        pharmacy_id=pharmacy_id,
        token=token
    )
    
    if error:
        return jsonify({'error': error}), 400
    
    return jsonify({
        'message': 'Prescription dispensed successfully',
        'prescription': prescription.to_dict()
    }), 200


@prescriptions_bp.route('/<int:prescription_id>/lock', methods=['POST'])
@login_required
@permission_required('lock_prescription')
def lock(prescription_id):
    """
    Lock a prescription (DISPENSED -> LOCKED terminal state).
    Post-dispense locking for immutability.
    
    Expected JSON body (optional):
    {
        "reason": "string"
    }
    
    Args:
        prescription_id: Prescription ID
    
    Returns:
        JSON response confirming lock
    """
    data = request.get_json() or {}
    reason = data.get('reason')
    
    user_id = session.get('user_id')
    
    prescription, error = lock_prescription(prescription_id, user_id, reason)
    
    if error:
        return jsonify({'error': error}), 400
    
    return jsonify({
        'message': 'Prescription locked successfully',
        'prescription': prescription.to_dict()
    }), 200


@prescriptions_bp.route('/<int:prescription_id>/cancel', methods=['POST'])
@login_required
@permission_required('edit_prescription')
def cancel(prescription_id):
    """
    Cancel a prescription before dispensing.
    Only the doctor who created it can cancel.
    
    Args:
        prescription_id: Prescription ID
    
    Returns:
        JSON response confirming cancellation
    """
    doctor_id = session.get('user_id')
    
    prescription, error = cancel_prescription(prescription_id, doctor_id)
    
    if error:
        return jsonify({'error': error}), 400
    
    return jsonify({
        'message': 'Prescription cancelled successfully',
        'prescription': prescription.to_dict()
    }), 200


@prescriptions_bp.route('/<int:prescription_id>/update', methods=['PUT'])
@login_required
@permission_required('edit_prescription')
def update(prescription_id):
    """
    Update prescription details (only in CREATED or SHARED state).
    
    Expected JSON body:
    {
        "medication_name": "string" (optional),
        "dosage": "string" (optional),
        "quantity": int (optional),
        "refills_allowed": int (optional),
        "instructions": "string" (optional),
        "diagnosis": "string" (optional)
    }
    
    Args:
        prescription_id: Prescription ID
    
    Returns:
        JSON response with updated prescription
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    doctor_id = session.get('user_id')
    
    prescription, error = update_prescription(prescription_id, doctor_id, **data)
    
    if error:
        return jsonify({'error': error}), 400
    
    return jsonify({
        'message': 'Prescription updated successfully',
        'prescription': prescription.to_dict()
    }), 200


@prescriptions_bp.route('/<int:prescription_id>/tamper-score', methods=['GET'])
@login_required
def get_tamper_score(prescription_id):
    """
    Get tamper evidence score for a prescription.
    
    Args:
        prescription_id: Prescription ID
    
    Returns:
        JSON response with tamper score and severity
    """
    # Check access permissions
    prescription = Prescription.query.get(prescription_id)
    if not prescription:
        return jsonify({'error': 'Prescription not found'}), 404
    
    user_id = session.get('user_id')
    user_role = session.get('role')
    
    # Check access
    if user_role not in ['ADMIN']:
        if user_role == 'PATIENT' and prescription.patient_id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        elif user_role == 'DOCTOR' and prescription.doctor_id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
    
    tamper_info = get_prescription_tamper_score(prescription_id)
    
    if not tamper_info:
        return jsonify({'error': 'Prescription not found'}), 404
    
    return jsonify(tamper_info), 200


@prescriptions_bp.route('/<int:prescription_id>/verify', methods=['GET'])
@login_required
def verify_integrity(prescription_id):
    """
    Verify prescription integrity using blockchain.
    
    Args:
        prescription_id: Prescription ID
    
    Returns:
        JSON response with verification result
    """
    from blockchain.ledger import Blockchain
    
    prescription = Prescription.query.get(prescription_id)
    if not prescription:
        return jsonify({'error': 'Prescription not found'}), 404
    
    # Check access permissions
    user_id = session.get('user_id')
    user_role = session.get('role')
    
    if user_role not in ['ADMIN']:
        if user_role == 'PATIENT' and prescription.patient_id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        elif user_role == 'DOCTOR' and prescription.doctor_id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
    
    # Verify content integrity
    content_valid = verify_prescription_integrity(prescription)
    
    # Verify blockchain integrity
    blockchain = Blockchain()
    blockchain_verification = blockchain.verify_prescription_history(prescription_id)
    blockchain_tamper = blockchain.detect_tampering(prescription_id)
    
    return jsonify({
        'prescription_id': prescription_id,
        'content_integrity': {
            'valid': content_valid,
            'message': 'Content hash matches' if content_valid else 'Content hash mismatch - possible tampering'
        },
        'blockchain_history': blockchain_verification,
        'tamper_detection': blockchain_tamper,
        'tamper_score': prescription.tamper_score,
        'tamper_severity': prescription.get_tamper_severity()
    }), 200


@prescriptions_bp.route('/<int:prescription_id>/history', methods=['GET'])
@login_required
def get_history(prescription_id):
    """
    Get complete audit history for a prescription from blockchain.
    
    Args:
        prescription_id: Prescription ID
    
    Returns:
        JSON response with prescription history
    """
    from blockchain.ledger import Blockchain
    
    prescription = Prescription.query.get(prescription_id)
    if not prescription:
        return jsonify({'error': 'Prescription not found'}), 404
    
    # Check access permissions
    user_id = session.get('user_id')
    user_role = session.get('role')
    
    if user_role not in ['ADMIN']:
        if user_role == 'PATIENT' and prescription.patient_id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        elif user_role == 'DOCTOR' and prescription.doctor_id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
    
    # Get blockchain history
    blockchain = Blockchain()
    blocks = blockchain.get_blocks_by_prescription(prescription_id)
    
    history = [block.to_dict() for block in blocks]
    
    return jsonify({
        'prescription_id': prescription_id,
        'history': history,
        'total_blocks': len(history)
    }), 200


@prescriptions_bp.route('/statistics', methods=['GET'])
@login_required
@role_required('ADMIN')
def get_statistics():
    """
    Get prescription statistics (admin only).
    
    Returns:
        JSON response with statistics
    """
    total_prescriptions = Prescription.query.count()
    by_state = {}
    
    for state in ['CREATED', 'SHARED', 'DISPENSED', 'LOCKED', 'CANCELLED']:
        by_state[state] = Prescription.query.filter_by(state=state).count()
    
    # High tamper score prescriptions
    high_tamper = Prescription.query.filter(Prescription.tamper_score >= 50).count()
    
    # Recent prescriptions (last 24 hours)
    from datetime import timedelta
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent = Prescription.query.filter(Prescription.created_at >= yesterday).count()
    
    return jsonify({
        'total_prescriptions': total_prescriptions,
        'by_state': by_state,
        'high_tamper_score_count': high_tamper,
        'created_last_24h': recent
    }), 200


@prescriptions_bp.route('/emergency-access/<int:prescription_id>', methods=['POST'])
@login_required
@role_required('ADMIN')
def emergency_access(prescription_id):
    """
    Emergency override access to prescription (admin only).
    Requires justification and is immutably logged.
    
    Expected JSON body:
    {
        "justification": "string (min 50 characters)"
    }
    
    Args:
        prescription_id: Prescription ID
    
    Returns:
        JSON response with prescription and emergency access log
    """
    from blockchain.ledger import record_emergency_access
    from config import Config
    
    data = request.get_json()
    
    if not data or not data.get('justification'):
        return jsonify({'error': 'Justification required'}), 400
    
    justification = data.get('justification')
    
    # Validate justification length
    if len(justification) < Config.EMERGENCY_ACCESS['MIN_JUSTIFICATION_LENGTH']:
        return jsonify({
            'error': f'Justification must be at least {Config.EMERGENCY_ACCESS["MIN_JUSTIFICATION_LENGTH"]} characters'
        }), 400
    
    prescription = Prescription.query.get(prescription_id)
    if not prescription:
        return jsonify({'error': 'Prescription not found'}), 404
    
    admin_id = session.get('user_id')
    
    # Record emergency access in blockchain
    block = record_emergency_access(
        prescription_id=prescription_id,
        admin_id=admin_id,
        justification=justification,
        details={
            'admin_username': session.get('username'),
            'patient_id': prescription.patient_id,
            'timestamp': datetime.utcnow().isoformat()
        }
    )
    
    # Add tamper event
    prescription.add_tamper_event(
        'emergency_override',
        Config.TAMPER_SCORE_WEIGHTS['emergency_override'],
        f'Emergency access by admin: {justification[:100]}'
    )
    db.session.commit()
    
    # Log audit event
    from audit.logger import log_audit_event
    log_audit_event(
        event_type='EMERGENCY_ACCESS',
        user_id=admin_id,
        prescription_id=prescription_id,
        details={
            'justification': justification,
            'block_id': block.id
        },
        ip_address=get_client_ip(),
        is_emergency_access=True,
        emergency_justification=justification
    )
    
    return jsonify({
        'message': 'Emergency access granted and logged',
        'prescription': prescription.to_dict(),
        'emergency_log': {
            'block_id': block.id,
            'block_hash': block.hash,
            'justification': justification,
            'timestamp': block.timestamp.isoformat()
        }
    }), 200
