"""
MediSure Vault - Doctor Prescription Module

Handles all doctor-specific routes:
  GET  /doctor/dashboard          - view all prescriptions created by this doctor
  GET  /doctor/create             - show create prescription form
  POST /doctor/create             - save new prescription
  GET  /doctor/prescription/<id>  - view a single prescription's details
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, abort
from database import db
from models import User, Prescription
from auth.utils import login_required, role_required
from prescriptions.services import create_prescription, share_prescription, cancel_prescription
from audit.logger import log_audit_event
from auth.utils import get_client_ip
from security import audit, deduct_tamper_score
from datetime import datetime
import hashlib

# Blueprint with /doctor prefix (registered in app.py)
doctor_bp = Blueprint('doctor', __name__, url_prefix='/doctor')


# ─── Helper ──────────────────────────────────────────────────────────────────

def _current_doctor_id():
    """Return the logged-in user's id from the session."""
    return session.get('user_id')


def _get_prescription_or_404(prescription_id):
    """
    Fetch a prescription that belongs to the logged-in doctor.
    Aborts with 404 if not found, 403 if it belongs to another doctor.
    Aborts with 403 with a clear message if the prescription is locked.
    """
    prescription = Prescription.query.get(prescription_id)
    if not prescription:
        abort(404)
    if prescription.doctor_id != _current_doctor_id():
        abort(403)
    return prescription


def _assert_not_locked(prescription):
    """
    Raise a 403 JSON/HTML error if the prescription is locked.
    Call this before any write operation (share, cancel, edit).
    """
    if prescription.is_locked():
        msg = 'This prescription is locked and cannot be modified.'
        if request.is_json:
            abort(403, description=msg)
        # For HTML requests return a redirect back with an error flash
        from flask import flash
        # We can't flash here without a request context trick, so just abort
        abort(403, description=msg)


# ─── Dashboard ───────────────────────────────────────────────────────────────

@doctor_bp.route('/dashboard')
@login_required
@role_required('DOCTOR')
def dashboard():
    """
    Doctor dashboard - shows all prescriptions created by this doctor,
    grouped by status, plus quick stats.
    """
    doctor_id = _current_doctor_id()
    doctor = User.query.get(doctor_id)

    # Fetch all prescriptions for this doctor, newest first
    all_prescriptions = (
        Prescription.query
        .filter_by(doctor_id=doctor_id)
        .order_by(Prescription.created_at.desc())
        .all()
    )

    # Quick stats
    stats = {
        'total':     len(all_prescriptions),
        'created':   sum(1 for p in all_prescriptions if p.state == 'CREATED'),
        'shared':    sum(1 for p in all_prescriptions if p.state == 'SHARED'),
        'dispensed': sum(1 for p in all_prescriptions if p.state == 'DISPENSED'),
        'locked':    sum(1 for p in all_prescriptions if p.state == 'LOCKED'),
        'cancelled': sum(1 for p in all_prescriptions if p.state == 'CANCELLED'),
    }

    # Flagged / low-score prescriptions for the alert banner
    flagged = [p for p in all_prescriptions if p.is_flagged or p.tamper_score < 60]

    return render_template(
        'doctor_dashboard.html',
        current_user=doctor,
        doctor_profile=doctor.doctor_profile,
        prescriptions=all_prescriptions,
        stats=stats,
        flagged=flagged
    )


# ─── Create Prescription ─────────────────────────────────────────────────────

@doctor_bp.route('/create', methods=['GET'])
@login_required
@role_required('DOCTOR')
def create_form():
    """Show the create-prescription form with a list of active patients."""
    # Only show active patients in the dropdown
    patients = User.query.filter_by(role='PATIENT', is_active=True).order_by(User.full_name).all()
    return render_template('doctor_create_prescription.html', patients=patients)


@doctor_bp.route('/create', methods=['POST'])
@login_required
@role_required('DOCTOR')
def create_submit():
    """
    Handle prescription form submission.
    Accepts both JSON (API) and form-encoded (HTML form) data.
    """
    doctor_id = _current_doctor_id()

    # Support both JSON and HTML form POST
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()

    # --- Validate required fields ---
    patient_id   = data.get('patient_id')
    medication   = (data.get('medication_name') or '').strip()
    dosage       = (data.get('dosage') or '').strip()
    instructions = (data.get('instructions') or '').strip()
    diagnosis    = (data.get('diagnosis') or '').strip()

    errors = []
    if not patient_id:
        errors.append('Patient is required.')
    if not medication:
        errors.append('Medication name is required.')
    if not dosage:
        errors.append('Dosage is required.')

    try:
        quantity = int(data.get('quantity', 0))
        if quantity <= 0:
            errors.append('Quantity must be a positive number.')
    except (ValueError, TypeError):
        errors.append('Quantity must be a valid number.')
        quantity = 0

    try:
        refills = int(data.get('refills_allowed', 0))
        if refills < 0:
            errors.append('Refills cannot be negative.')
    except (ValueError, TypeError):
        refills = 0

    if errors:
        if request.is_json:
            return jsonify({'error': '; '.join(errors)}), 400
        patients = User.query.filter_by(role='PATIENT', is_active=True).all()
        return render_template('doctor_create_prescription.html',
                               patients=patients, errors=errors, form_data=data)

    # --- Verify patient exists ---
    patient = User.query.filter_by(id=patient_id, role='PATIENT').first()
    if not patient:
        err = 'Selected patient does not exist.'
        if request.is_json:
            return jsonify({'error': err}), 404
        patients = User.query.filter_by(role='PATIENT', is_active=True).all()
        return render_template('doctor_create_prescription.html',
                               patients=patients, errors=[err], form_data=data)

    # --- Create prescription via service layer ---
    prescription, error = create_prescription(
        doctor_id=doctor_id,
        patient_id=int(patient_id),
        medication_name=medication,
        dosage=dosage,
        quantity=quantity,
        refills_allowed=refills,
        instructions=instructions or None,
        diagnosis=diagnosis or None,
    )

    if error:
        if request.is_json:
            return jsonify({'error': error}), 400
        patients = User.query.filter_by(role='PATIENT', is_active=True).all()
        return render_template('doctor_create_prescription.html',
                               patients=patients, errors=[error], form_data=data)

    if request.is_json:
        return jsonify({
            'success': True,
            'message': 'Prescription created successfully.',
            'prescription_id': prescription.id
        }), 201

    return redirect(url_for('doctor.view_prescription', prescription_id=prescription.id))


# ─── View Prescription ────────────────────────────────────────────────────────

@doctor_bp.route('/prescription/<int:prescription_id>')
@login_required
@role_required('DOCTOR')
def view_prescription(prescription_id):
    """Show full details of a single prescription (doctor's own only)."""
    prescription = _get_prescription_or_404(prescription_id)
    return render_template('doctor_prescription_detail.html', prescription=prescription)


# ─── Share Prescription ───────────────────────────────────────────────────────

@doctor_bp.route('/prescription/<int:prescription_id>/share', methods=['POST'])
@login_required
@role_required('DOCTOR')
def share(prescription_id):
    """
    Transition prescription from CREATED → SHARED so the patient
    can generate access tokens for pharmacies.
    """
    prescription = _get_prescription_or_404(prescription_id)
    _assert_not_locked(prescription)   # ← lock guard
    updated, error = share_prescription(prescription_id, _current_doctor_id())

    if request.is_json:
        if error:
            return jsonify({'error': error}), 400
        return jsonify({'success': True, 'state': updated.state}), 200

    if error:
        return redirect(url_for('doctor.view_prescription',
                                prescription_id=prescription_id, error=error))
    return redirect(url_for('doctor.view_prescription', prescription_id=prescription_id))


# ─── Cancel Prescription ──────────────────────────────────────────────────────

@doctor_bp.route('/prescription/<int:prescription_id>/cancel', methods=['POST'])
@login_required
@role_required('DOCTOR')
def cancel(prescription_id):
    """Cancel a prescription (only allowed before dispensing)."""
    prescription = _get_prescription_or_404(prescription_id)
    _assert_not_locked(prescription)   # ← lock guard
    updated, error = cancel_prescription(prescription_id, _current_doctor_id())

    if request.is_json:
        if error:
            return jsonify({'error': error}), 400
        return jsonify({'success': True, 'state': updated.state}), 200

    return redirect(url_for('doctor.dashboard'))


# ─── API: list prescriptions (JSON) ──────────────────────────────────────────

@doctor_bp.route('/api/prescriptions')
@login_required
@role_required('DOCTOR')
def api_prescriptions():
    """
    JSON endpoint used by the existing doctor dashboard JS
    (replaces the /api/doctor/prescriptions route in app.py).
    """
    doctor_id = _current_doctor_id()
    state_filter = request.args.get('state', '')

    query = Prescription.query.filter_by(doctor_id=doctor_id)
    if state_filter:
        query = query.filter_by(state=state_filter)

    prescriptions = query.order_by(Prescription.created_at.desc()).all()

    return jsonify([{
        'id': p.id,
        'medication_name': p.medication_name,
        'dosage': p.dosage,
        'quantity': p.quantity,
        'instructions': p.instructions,
        'diagnosis': p.diagnosis,
        'state': p.state,
        'tamper_score': p.tamper_score,
        'patient_name': p.patient.full_name if p.patient else 'Unknown',
        'patient_id': p.patient_id,
        'created_at': p.created_at.isoformat() if p.created_at else None,
        'dispensed_at': p.dispensed_at.isoformat() if p.dispensed_at else None,
    } for p in prescriptions]), 200


# ─── API: stats (JSON) ────────────────────────────────────────────────────────

@doctor_bp.route('/api/stats')
@login_required
@role_required('DOCTOR')
def api_stats():
    """JSON stats endpoint used by the doctor dashboard."""
    doctor_id = _current_doctor_id()
    all_p = Prescription.query.filter_by(doctor_id=doctor_id).all()

    return jsonify({
        'total':     len(all_p),
        'created':   sum(1 for p in all_p if p.state == 'CREATED'),
        'shared':    sum(1 for p in all_p if p.state == 'SHARED'),
        'dispensed': sum(1 for p in all_p if p.state == 'DISPENSED'),
        'locked':    sum(1 for p in all_p if p.state == 'LOCKED'),
        'cancelled': sum(1 for p in all_p if p.state == 'CANCELLED'),
    }), 200
