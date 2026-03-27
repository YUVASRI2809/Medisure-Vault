"""
MediSure Vault - Pharmacist Module

Routes:
  GET  /pharmacist/dashboard              - view SHARED prescriptions ready to dispense
  GET  /pharmacist/prescription/<id>      - view full prescription details
  POST /pharmacist/verify-token           - validate a patient token and show prescription
  POST /pharmacist/dispense/<id>          - dispense + lock using a valid token
  GET  /pharmacist/history                - dispensing history
  GET  /pharmacist/api/stats              - JSON stats for dashboard
  GET  /pharmacist/api/prescriptions      - JSON list (filter support)
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, abort
from database import db
from models import Prescription, User, AuditLog
from auth.utils import login_required, role_required, get_client_ip
from audit.logger import log_audit_event
from access.tokens import validate_and_consume_token, verify_token_validity
from security import (deduct_tamper_score, handle_pharmacy_collision,
                      is_access_blocked, audit)
from datetime import datetime, date

pharmacist_bp = Blueprint('pharmacist', __name__, url_prefix='/pharmacist')


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _pharmacist_id():
    return session.get('user_id')


def _get_prescription_or_404(prescription_id):
    """Fetch prescription by ID or abort 404."""
    p = Prescription.query.get(prescription_id)
    if not p:
        abort(404)
    return p


def _build_stats():
    """Return a dict of quick stats for the dashboard."""
    today = date.today()
    return {
        'shared':          Prescription.query.filter_by(state='SHARED').count(),
        'dispensed_today': Prescription.query.filter(
                               Prescription.state.in_(['DISPENSED', 'LOCKED']),
                               db.func.date(Prescription.dispensed_at) == today
                           ).count(),
        'dispensed_total': Prescription.query.filter(
                               Prescription.state.in_(['DISPENSED', 'LOCKED'])
                           ).count(),
        'locked':          Prescription.query.filter_by(state='LOCKED').count(),
    }


# ─── Dashboard ───────────────────────────────────────────────────────────────

@pharmacist_bp.route('/dashboard')
@login_required
@role_required('PHARMACIST')
def dashboard():
    """
    Pharmacist dashboard.
    Shows all SHARED prescriptions (ready to dispense) and quick stats.
    """
    pharmacist = User.query.get(_pharmacist_id())

    # Prescriptions ready to dispense (state = SHARED)
    shared_prescriptions = (
        Prescription.query
        .filter_by(state='SHARED')
        .order_by(Prescription.shared_at.desc())
        .all()
    )

    stats = _build_stats()

    # Flagged prescriptions alert
    flagged = Prescription.query.filter(
        (Prescription.is_flagged == True) | (Prescription.tamper_score < 60)
    ).filter(Prescription.state == 'SHARED').all()

    return render_template(
        'pharmacist_dashboard.html',
        current_user=pharmacist,
        pharmacist_profile=pharmacist.pharmacist_profile,
        prescriptions=shared_prescriptions,
        stats=stats,
        flagged=flagged
    )


# ─── View Prescription ────────────────────────────────────────────────────────

@pharmacist_bp.route('/prescription/<int:prescription_id>')
@login_required
@role_required('PHARMACIST')
def view_prescription(prescription_id):
    """Show full details of a prescription before dispensing."""
    prescription = _get_prescription_or_404(prescription_id)
    pharmacist_id = _pharmacist_id()

    # ── Collision detection ──
    # If another pharmacist already accessed this prescription, deduct score
    handle_pharmacy_collision(prescription_id, pharmacist_id)

    # ── Hard block if tamper score is critically low ──
    if is_access_blocked(prescription):
        audit('BLOCKED_ACCESS', user_id=pharmacist_id,
              prescription_id=prescription_id,
              details={'reason': 'tamper_score_too_low',
                       'score': prescription.tamper_score},
              status='FAILED')
        if request.is_json:
            return jsonify({'error': 'Access blocked: prescription tamper score is critically low.'}), 403
        return render_template('pharmacist_prescription_detail.html',
                               prescription=prescription,
                               audit_logs=[],
                               blocked=True)

    # Fetch audit history for this prescription
    audit_logs = (
        AuditLog.query
        .filter_by(prescription_id=prescription_id)
        .order_by(AuditLog.timestamp.desc())
        .limit(10)
        .all()
    )

    return render_template(
        'pharmacist_prescription_detail.html',
        prescription=prescription,
        audit_logs=audit_logs,
        blocked=False
    )


# ─── Token Verification ──────────────────────────────────────────────────────

@pharmacist_bp.route('/verify-token', methods=['GET', 'POST'])
@login_required
@role_required('PHARMACIST')
def verify_token():
    """
    Step 1 of dispensing: pharmacist enters the patient's token.

    GET  → show the token entry form
    POST → validate the token (without consuming it), then redirect to
           the prescription detail page with the token pre-filled so the
           pharmacist can review and confirm before dispensing.

    Validation checks (via verify_token_validity — does NOT consume):
      ✔ token exists
      ✔ not expired
      ✔ not already used
      ✔ not revoked
    """
    if request.method == 'GET':
        return render_template('pharmacist_verify_token.html')

    # ── POST: validate token ──
    data         = request.get_json() if request.is_json else request.form
    token_string = (data.get('token') or '').strip()

    if not token_string:
        err = 'Please enter a token.'
        if request.is_json:
            return jsonify({'error': err}), 400
        return render_template('pharmacist_verify_token.html', error=err, token=token_string)

    # Peek at the token without consuming it
    is_valid, token_obj, error_msg = verify_token_validity(token_string)

    if not is_valid:
        # Map internal messages to user-friendly ones
        friendly = {
            'Token not found':    'Invalid token. Please check and try again.',
            'Token already used': 'This token has already been used.',
            'Token revoked':      'This token has been revoked by the patient.',
            'Token expired':      'This token has expired. Ask the patient to generate a new one.',
        }.get(error_msg, error_msg)

        log_audit_event(
            event_type='TOKEN_VALIDATION_FAILED',
            user_id=_pharmacist_id(),
            details={'reason': error_msg, 'token': token_string[:8] + '…'},
            ip_address=get_client_ip(),
            status='FAILED'
        )

        # Deduct tamper score if we can identify the prescription
        if token_obj and token_obj.prescription_id:
            deduct_tamper_score(
                prescription_id=token_obj.prescription_id,
                reason='invalid_token_attempt',
                user_id=_pharmacist_id(),
                extra_details={'error': error_msg}
            )

        if request.is_json:
            return jsonify({'error': friendly}), 400
        return render_template('pharmacist_verify_token.html', error=friendly, token=token_string)

    # Token is valid — redirect to prescription detail with token in query string
    # The token is NOT consumed yet; consumption happens on dispense confirmation
    prescription_id = token_obj.prescription_id

    if request.is_json:
        return jsonify({
            'valid':           True,
            'prescription_id': prescription_id,
            'medication':      token_obj.prescription.medication_name if token_obj.prescription else '',
            'patient_name':    token_obj.prescription.patient.full_name if token_obj.prescription and token_obj.prescription.patient else '',
            'expires_at':      token_obj.expires_at.isoformat(),
        }), 200

    return redirect(url_for(
        'pharmacist.view_prescription',
        prescription_id=prescription_id,
        token=token_string
    ))


# ─── Dispense + Lock (token-gated) ───────────────────────────────────────────

@pharmacist_bp.route('/dispense/<int:prescription_id>', methods=['POST'])
@login_required
@role_required('PHARMACIST')
def dispense(prescription_id):
    """
    Step 2 of dispensing: consume the token and lock the prescription.

    Requires a valid token in the request body:
      JSON: { "token": "<token_string>" }
      Form: token=<token_string>

    Flow:
      1. Validate + consume the token (one-time use, marks is_used=True)
      2. Guard against already-locked prescriptions
      3. Set state → LOCKED, record dispensed_by / dispensed_at
      4. Write audit log
    """
    pharmacist_id = _pharmacist_id()
    pharmacist    = User.query.get(pharmacist_id)
    prescription  = _get_prescription_or_404(prescription_id)

    # ── Extract token from request ──
    data         = request.get_json() if request.is_json else request.form
    token_string = (data.get('token') or '').strip()

    if not token_string:
        msg = 'A valid patient token is required to dispense this prescription.'
        if request.is_json:
            return jsonify({'error': msg}), 400
        return redirect(url_for('pharmacist.view_prescription',
                                prescription_id=prescription_id))

    # ── Guard: already locked ──
    if prescription.is_locked():
        msg = 'This prescription is already locked and cannot be dispensed again.'
        if request.is_json:
            return jsonify({'error': msg}), 409
        return redirect(url_for('pharmacist.view_prescription',
                                prescription_id=prescription_id,
                                token=token_string))

    if prescription.state != 'SHARED':
        msg = f'Cannot dispense a prescription in "{prescription.state}" state.'
        if request.is_json:
            return jsonify({'error': msg}), 400
        return redirect(url_for('pharmacist.view_prescription',
                                prescription_id=prescription_id,
                                token=token_string))

    # ── Validate + consume token ──
    token_valid, token_error = validate_and_consume_token(
        token_string=token_string,
        prescription_id=prescription_id,
        pharmacist_id=pharmacist_id,
        ip_address=get_client_ip()
    )

    if not token_valid:
        friendly = {
            'Invalid token':                'Invalid token. Please check and try again.',
            'Token does not match prescription': 'This token is not for this prescription.',
            'Token has already been used':  'This token has already been used.',
            'Token has been revoked':       'This token has been revoked by the patient.',
            'Token has expired':            'This token has expired. Ask the patient to generate a new one.',
        }.get(token_error, token_error)

        # Deduct tamper score for failed token attempt
        deduct_tamper_score(
            prescription_id=prescription_id,
            reason='invalid_token_attempt',
            user_id=pharmacist_id,
            extra_details={'error': token_error}
        )

        if request.is_json:
            return jsonify({'error': friendly}), 400
        return redirect(url_for('pharmacist.view_prescription',
                                prescription_id=prescription_id,
                                token_error=friendly))

    # ── Collision detection before dispensing ──
    handle_pharmacy_collision(prescription_id, pharmacist_id)

    # ── Dispense + Lock ──
    prescription.state           = 'LOCKED'
    prescription.dispensed_at    = datetime.utcnow()
    prescription.locked_at       = datetime.utcnow()
    prescription.dispensed_by_id = pharmacist_id
    prescription.pharmacy_id     = pharmacist.pharmacy_id or 'UNKNOWN'
    db.session.commit()

    # ── Audit log ──
    log_audit_event(
        event_type='PRESCRIPTION_DISPENSED',
        user_id=pharmacist_id,
        prescription_id=prescription_id,
        details={
            'action':          'DISPENSED',
            'pharmacist_id':   pharmacist_id,
            'pharmacist_name': pharmacist.full_name,
            'pharmacy_id':     prescription.pharmacy_id,
            'medication':      prescription.medication_name,
            'locked_at':       prescription.locked_at.isoformat(),
            'token_used':      token_string[:8] + '…',
        },
        ip_address=get_client_ip()
    )

    if request.is_json:
        return jsonify({
            'success': True,
            'message': 'Prescription dispensed and locked successfully.',
            'state':   prescription.state
        }), 200

    return redirect(url_for('pharmacist.view_prescription',
                            prescription_id=prescription_id))


# ─── Dispensing History ───────────────────────────────────────────────────────

@pharmacist_bp.route('/history')
@login_required
@role_required('PHARMACIST')
def history():
    """Show all dispensed/locked prescriptions (history view)."""
    filter_type = request.args.get('filter', 'all')

    query = Prescription.query.filter(
        Prescription.state.in_(['DISPENSED', 'LOCKED'])
    )

    if filter_type == 'today':
        query = query.filter(
            db.func.date(Prescription.dispensed_at) == date.today()
        )
    elif filter_type == 'week':
        from datetime import timedelta
        query = query.filter(
            Prescription.dispensed_at >= datetime.utcnow() - timedelta(days=7)
        )

    prescriptions = query.order_by(Prescription.dispensed_at.desc()).all()

    return render_template(
        'pharmacist_history.html',
        prescriptions=prescriptions,
        filter_type=filter_type,
        current_user=User.query.get(_pharmacist_id())
    )


# ─── JSON API: stats ─────────────────────────────────────────────────────────

@pharmacist_bp.route('/api/stats')
@login_required
@role_required('PHARMACIST')
def api_stats():
    return jsonify(_build_stats()), 200


# ─── JSON API: prescriptions list ────────────────────────────────────────────

@pharmacist_bp.route('/api/prescriptions')
@login_required
@role_required('PHARMACIST')
def api_prescriptions():
    """
    JSON list of prescriptions.
    ?state=SHARED  → ready to dispense
    ?state=LOCKED  → dispensed history
    (default: SHARED)
    """
    state = request.args.get('state', 'SHARED')
    prescriptions = (
        Prescription.query
        .filter_by(state=state)
        .order_by(Prescription.created_at.desc())
        .all()
    )

    return jsonify([{
        'id':              p.id,
        'medication_name': p.medication_name,
        'dosage':          p.dosage,
        'quantity':        p.quantity,
        'state':           p.state,
        'is_locked':       p.is_locked(),
        'tamper_score':    p.tamper_score,
        'patient_name':    p.patient.full_name  if p.patient  else 'Unknown',
        'doctor_name':     p.doctor.full_name   if p.doctor   else 'Unknown',
        'created_at':      p.created_at.isoformat()  if p.created_at  else None,
        'dispensed_at':    p.dispensed_at.isoformat() if p.dispensed_at else None,
    } for p in prescriptions]), 200
