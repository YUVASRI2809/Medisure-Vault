"""
MediSure Vault - Access Token Routes Module

This module handles API routes for patient-controlled time-bound access tokens.
"""

from flask import Blueprint, request, jsonify, session
from auth.utils import login_required, permission_required, get_client_ip
from access.tokens import (
    generate_access_token, revoke_token, get_patient_tokens,
    get_active_tokens, verify_token_validity, extend_token_validity
)


# Create access blueprint
access_bp = Blueprint('access', __name__)


@access_bp.route('/generate', methods=['POST'])
@login_required
@permission_required('generate_access_token')
def generate_token():
    """
    Generate a time-bound one-time access token for prescription sharing.
    Patient-controlled feature (FEATURE 2).
    
    Expected JSON body:
    {
        "prescription_id": int,
        "validity_minutes": int (optional, default from config)
    }
    
    Returns:
        JSON response with generated token
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    prescription_id = data.get('prescription_id')
    validity_minutes = data.get('validity_minutes')
    
    if not prescription_id:
        return jsonify({'error': 'prescription_id required'}), 400
    
    patient_id = session.get('user_id')
    
    access_token, error = generate_access_token(
        prescription_id=prescription_id,
        patient_id=patient_id,
        validity_minutes=validity_minutes
    )
    
    if error:
        return jsonify({'error': error}), 400
    
    return jsonify({
        'message': 'Access token generated successfully',
        'token': access_token.to_dict()
    }), 201


@access_bp.route('/revoke/<int:token_id>', methods=['POST'])
@login_required
@permission_required('revoke_access_token')
def revoke(token_id):
    """
    Revoke an access token (patient can revoke their own tokens).
    
    Expected JSON body (optional):
    {
        "reason": "string"
    }
    
    Args:
        token_id: Token ID to revoke
    
    Returns:
        JSON response confirming revocation
    """
    data = request.get_json() or {}
    reason = data.get('reason')
    
    patient_id = session.get('user_id')
    
    success, error = revoke_token(token_id, patient_id, reason)
    
    if not success:
        return jsonify({'error': error}), 400
    
    return jsonify({
        'message': 'Token revoked successfully',
        'token_id': token_id,
        'reason': reason
    }), 200


@access_bp.route('/my-tokens', methods=['GET'])
@login_required
@permission_required('generate_access_token')
def list_my_tokens():
    """
    Get all access tokens for the current patient.
    
    Query parameters:
        prescription_id: Filter by prescription (optional)
        include_expired: Include expired tokens (default false)
    
    Returns:
        JSON response with token list
    """
    patient_id = session.get('user_id')
    prescription_id = request.args.get('prescription_id', type=int)
    include_expired = request.args.get('include_expired', 'false').lower() == 'true'
    
    tokens = get_patient_tokens(patient_id, prescription_id, include_expired)
    
    return jsonify({
        'tokens': [t.to_dict() for t in tokens],
        'total': len(tokens)
    }), 200


@access_bp.route('/active-tokens', methods=['GET'])
@login_required
@permission_required('generate_access_token')
def list_active_tokens():
    """
    Get all active (valid, unused, non-revoked) tokens for current patient.
    
    Query parameters:
        prescription_id: Filter by prescription (optional)
    
    Returns:
        JSON response with active tokens
    """
    patient_id = session.get('user_id')
    prescription_id = request.args.get('prescription_id', type=int)
    
    tokens = get_active_tokens(patient_id, prescription_id)
    
    return jsonify({
        'tokens': [t.to_dict() for t in tokens],
        'total': len(tokens)
    }), 200


@access_bp.route('/verify/<token_string>', methods=['GET'])
@login_required
def verify_token(token_string):
    """
    Verify if a token is valid without consuming it.
    
    Args:
        token_string: Token string to verify
    
    Returns:
        JSON response with verification result
    """
    is_valid, token_obj, error_msg = verify_token_validity(token_string)
    
    if not is_valid:
        return jsonify({
            'valid': False,
            'error': error_msg
        }), 200
    
    return jsonify({
        'valid': True,
        'token': token_obj.to_dict()
    }), 200


@access_bp.route('/extend/<int:token_id>', methods=['POST'])
@login_required
@permission_required('generate_access_token')
def extend_token(token_id):
    """
    Extend the validity of an existing token.
    
    Expected JSON body:
    {
        "additional_minutes": int
    }
    
    Args:
        token_id: Token ID to extend
    
    Returns:
        JSON response confirming extension
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    additional_minutes = data.get('additional_minutes')
    
    if not additional_minutes:
        return jsonify({'error': 'additional_minutes required'}), 400
    
    patient_id = session.get('user_id')
    
    success, error = extend_token_validity(token_id, patient_id, additional_minutes)
    
    if not success:
        return jsonify({'error': error}), 400
    
    return jsonify({
        'message': 'Token validity extended successfully',
        'token_id': token_id,
        'additional_minutes': additional_minutes
    }), 200
