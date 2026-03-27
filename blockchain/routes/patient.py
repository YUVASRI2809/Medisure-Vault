"""
MediSure Vault - Patient Module

Routes:
  GET  /patient/dashboard                        - all prescriptions for this patient
  GET  /patient/prescription/<id>                - full prescription detail + token list
  POST /patient/generate-token/<prescription_id> - generate a one-time access token
  POST /patient/revoke-token/<token_id>          - revoke an active token
  GET  /patient/api/stats                        - JSON stats
  GET  /patient/api/prescriptions                - JSON prescription list
  GET  /patient/api/tokens/<prescription_id>     - JSON tokens for a prescription
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, abort
from database import db
from models import Prescription, AccessToken, User
from auth.utils import login_required, role_required, get_client_ip
from access.tokens import generate_access_token, revoke_token, get_active_tokens
from audit.logger import log_audit_event
from security import deduct_tamper_score, check_rapid_token_requests, audit
from datetime import datetime

patient_bp = Blueprint('patient', __name__, url_prefix='/patient')


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _patient_id():
    """Return the logged-in patient's user ID."""
    return session.get('user_id')


def _get_own_prescription_or_404(prescription_id):
    """
    Fetch a prescription that belongs to the logged-in patient.
    Aborts 404 if not found, 403 if it belongs to someone else.
    """
    p = Prescription.query.get(prescription_id)
    if not p:
        abort(404)
    if p.patient_id != _patient_id():
        abort(403)
    return p


def _build_stats(patient_id):
    """Quick stats dict for the dashboard."""
    all_rx = Prescription.query.filter_by(patient_id=patient_id).all()
    active_tokens = AccessToken.query.filter_by(
        patient_id=patient_id,
        is_used=False,
        is_revoked=False
    ).filter(AccessToken.expires_at > datetime.utcnow()).count()

    return {
        'total':        len(all_rx),
        'shared':       sum(1 for p in all_rx if p.state == 'SHARED'),
        'dispensed':    sum(1 for p in all_rx if p.state in ('DISPENSED', 'LOCKED')),
        'active_tokens': active_tokens,
    }


# ─── Dashboard ───────────────────────────────────────────────────────────────

@patient_bp.route('/dashboard')
@login_required
@role_required('PATIENT')
def dashboard():
    """
    Patient dashboard — shows all prescriptions and quick stats.
    """
    pid     = _patient_id()
    patient = User.query.get(pid)

    prescriptions = (
        Prescription.query
        .filter_by(patient_id=pid)
        .order_by(Prescription.created_at.desc())
        .all()
    )

    stats = _build_stats(pid)

    return render_template(
        'patient_dashboard.html',
        current_user=patient,
        patient_profile=patient.patient_profile,
        prescriptions=prescriptions,
        stats=stats
    )


# ─── View Prescription ────────────────────────────────────────────────────────

@patient_bp.route('/prescription/<int:prescription_id>')
@login_required
@role_required('PATIENT')
def view_prescription(prescription_id):
    """
    Show full prescription details plus all tokens the patient has
    generated for it.
    """
    prescription = _get_own_prescription_or_404(prescription_id)

    # All tokens for this prescription (newest first)
    tokens = (
        AccessToken.query
        .filter_by(prescription_id=prescription_id, patient_id=_patient_id())
        .order_by(AccessToken.created_at.desc())
        .all()
    )

    # Count active (valid) tokens
    active_count = sum(1 for t in tokens if t.is_valid())

    return render_template(
        'patient_prescription_detail.html',
        prescription=prescription,
        tokens=tokens,
        active_count=active_count,
        now_dt=datetime.utcnow()
    )


# ─── Generate Token ───────────────────────────────────────────────────────────

@patient_bp.route('/generate-token/<int:prescription_id>', methods=['POST'])
@login_required
@role_required('PATIENT')
def generate_token(prescription_id):
    """
    Generate a one-time access token for a prescription.

    Rules enforced by access.tokens.generate_access_token:
      - Patient must own the prescription
      - Prescription must be in SHARED state
      - Prescription must not be locked
      - Validity capped by config (default 15 min, max 60 min)

    Accepts JSON { "validity_minutes": 15 } or falls back to default.
    """
    # Ownership check first
    _get_own_prescription_or_404(prescription_id)

    pid = _patient_id()

    # ── Rapid token request detection ──
    if check_rapid_token_requests(prescription_id, pid):
        deduct_tamper_score(
            prescription_id=prescription_id,
            reason='rapid_token_requests',
            user_id=pid,
            extra_details={'window_minutes': 10}
        )

    # Optional custom validity from request body
    validity_minutes = None
    if request.is_json:
        data = request.get_json() or {}
        validity_minutes = data.get('validity_minutes')

    token, error = generate_access_token(
        prescription_id=prescription_id,
        patient_id=pid,
        validity_minutes=validity_minutes
    )

    if error:
        if request.is_json:
            return jsonify({'error': error}), 400
        # HTML fallback — redirect back with error in query string
        return redirect(url_for('patient.view_prescription',
                                prescription_id=prescription_id,
                                error=error))

    # Audit log
    log_audit_event(
        event_type='TOKEN_GENERATED',
        user_id=pid,
        prescription_id=prescription_id,
        details={
            'action':          'TOKEN_GENERATED',
            'patient_id':      pid,
            'prescription_id': prescription_id,
            'token_id':        token.id,
            'expires_at':      token.expires_at.isoformat(),
        },
        ip_address=get_client_ip()
    )

    if request.is_json:
        return jsonify({
            'success':    True,
            'token':      token.token,
            'expires_at': token.expires_at.isoformat(),
            'token_id':   token.id,
        }), 201

    return redirect(url_for('patient.view_prescription',
                            prescription_id=prescription_id))


# ─── Revoke Token ─────────────────────────────────────────────────────────────

@patient_bp.route('/revoke-token/<int:token_id>', methods=['POST'])
@login_required
@role_required('PATIENT')
def revoke(token_id):
    """
    Revoke an active token so it can no longer be used by a pharmacist.
    Only the patient who owns the token can revoke it.
    """
    pid = _patient_id()
    success, error = revoke_token(token_id, pid, reason='Revoked by patient')

    if request.is_json:
        if error:
            return jsonify({'error': error}), 400
        return jsonify({'success': True}), 200

    # For HTML: figure out which prescription to redirect back to
    token_obj = AccessToken.query.get(token_id)
    prescription_id = token_obj.prescription_id if token_obj else None

    if prescription_id:
        return redirect(url_for('patient.view_prescription',
                                prescription_id=prescription_id))
    return redirect(url_for('patient.dashboard'))


# ─── JSON API: stats ─────────────────────────────────────────────────────────

@patient_bp.route('/api/stats')
@login_required
@role_required('PATIENT')
def api_stats():
    return jsonify(_build_stats(_patient_id())), 200


# ─── JSON API: prescriptions ─────────────────────────────────────────────────

@patient_bp.route('/api/prescriptions')
@login_required
@role_required('PATIENT')
def api_prescriptions():
    """JSON list of this patient's prescriptions, optionally filtered by state."""
    state = request.args.get('state', '')
    query = Prescription.query.filter_by(patient_id=_patient_id())
    if state:
        query = query.filter_by(state=state)

    prescriptions = query.order_by(Prescription.created_at.desc()).all()

    return jsonify([{
        'id':              p.id,
        'medication_name': p.medication_name,
        'dosage':          p.dosage,
        'quantity':        p.quantity,
        'state':           p.state,
        'is_locked':       p.is_locked(),
        'doctor_name':     p.doctor.full_name if p.doctor else 'Unknown',
        'created_at':      p.created_at.isoformat() if p.created_at else None,
        'dispensed_at':    p.dispensed_at.isoformat() if p.dispensed_at else None,
        'can_generate_token': p.state == 'SHARED' and not p.is_locked(),
    } for p in prescriptions]), 200


# ─── JSON API: tokens for a prescription ─────────────────────────────────────

@patient_bp.route('/api/tokens/<int:prescription_id>')
@login_required
@role_required('PATIENT')
def api_tokens(prescription_id):
    """JSON list of tokens the patient has generated for a prescription."""
    _get_own_prescription_or_404(prescription_id)

    tokens = (
        AccessToken.query
        .filter_by(prescription_id=prescription_id, patient_id=_patient_id())
        .order_by(AccessToken.created_at.desc())
        .all()
    )

    now = datetime.utcnow()
    return jsonify([{
        'id':           t.id,
        'token':        t.token,
        'created_at':   t.created_at.isoformat() if t.created_at else None,
        'expires_at':   t.expires_at.isoformat() if t.expires_at else None,
        'is_used':      t.is_used,
        'is_revoked':   t.is_revoked,
        'is_expired':   t.expires_at < now if t.expires_at else True,
        'is_valid':     t.is_valid(),
        'minutes_left': max(0, int((t.expires_at - now).total_seconds() // 60))
                        if t.expires_at and t.expires_at > now else 0,
    } for t in tokens]), 200
