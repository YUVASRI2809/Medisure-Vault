"""
MediSure Vault - Audit Logger Module

This module provides immutable audit logging for all system events.
Critical events are also recorded in the blockchain for additional security.
"""

from database import db
from models import AuditLog
from config import Config
from datetime import datetime
import json


def log_audit_event(event_type, user_id=None, prescription_id=None, details=None,
                   ip_address=None, user_agent=None, is_emergency_access=False,
                   emergency_justification=None, status='SUCCESS', role=None):
    """
    Log an immutable audit event.

    Args:
        event_type (str):   Type of event being logged
        user_id (int):      User ID who performed the action (optional)
        prescription_id (int): Related prescription ID (optional)
        details (dict):     Additional event details (optional)
        ip_address (str):   IP address of the request (optional)
        user_agent (str):   User agent string (optional)
        is_emergency_access (bool): Whether this is an emergency access event
        emergency_justification (str): Justification for emergency access (optional)
        status (str):       'SUCCESS', 'FAILED', or 'WARNING'
        role (str):         Role of the acting user (auto-resolved from session if None)

    Returns:
        AuditLog: Created audit log entry
    """
    if not Config.AUDIT_LOG['ENABLED']:
        return None

    # Auto-resolve role from Flask session if not provided
    if role is None:
        try:
            from flask import session
            role = session.get('role', 'SYSTEM')
        except RuntimeError:
            role = 'SYSTEM'

    # Create audit log entry
    audit_entry = AuditLog(
        event_type=event_type,
        timestamp=datetime.utcnow(),
        user_id=user_id,
        prescription_id=prescription_id,
        details=json.dumps(details) if details else None,
        ip_address=ip_address,
        user_agent=user_agent,
        is_emergency_access=is_emergency_access,
        emergency_justification=emergency_justification,
        status=status,
        role=role
    )
    
    db.session.add(audit_entry)
    db.session.commit()
    
    # Record critical events in blockchain
    if Config.AUDIT_LOG['BLOCKCHAIN_BACKED'] and should_blockchain_record(event_type):
        try:
            from blockchain.ledger import Blockchain
            blockchain = Blockchain()
            
            block = blockchain.add_block(
                event_type=event_type,
                data={
                    'audit_log_id': audit_entry.id,
                    'user_id': user_id,
                    'prescription_id': prescription_id,
                    'details': details,
                    'timestamp': audit_entry.timestamp.isoformat(),
                    'is_emergency': is_emergency_access
                },
                prescription_id=prescription_id,
                user_id=user_id
            )
            
            # Link audit log to blockchain block
            audit_entry.block_id = block.id
            db.session.commit()
            
        except Exception as e:
            # Don't fail audit logging if blockchain fails
            # Log the error but continue
            print(f"Warning: Failed to record audit event in blockchain: {e}")
    
    return audit_entry


def should_blockchain_record(event_type):
    """
    Determine if an event type should be recorded in the blockchain.
    
    Args:
        event_type (str): Event type to check
        
    Returns:
        bool: True if should be recorded in blockchain
    """
    # Critical events that should always be in blockchain
    blockchain_events = Config.BLOCKCHAIN_EVENTS
    
    return event_type in blockchain_events


def get_user_audit_logs(user_id, event_type=None, limit=100):
    """
    Get audit logs for a specific user.
    
    Args:
        user_id (int): User ID
        event_type (str): Optional filter by event type
        limit (int): Maximum number of records to return
        
    Returns:
        list: List of AuditLog objects
    """
    query = AuditLog.query.filter_by(user_id=user_id)
    
    if event_type:
        query = query.filter_by(event_type=event_type)
    
    return query.order_by(AuditLog.timestamp.desc()).limit(limit).all()


def get_prescription_audit_logs(prescription_id, limit=100):
    """
    Get audit logs for a specific prescription.
    
    Args:
        prescription_id (int): Prescription ID
        limit (int): Maximum number of records to return
        
    Returns:
        list: List of AuditLog objects
    """
    return AuditLog.query.filter_by(
        prescription_id=prescription_id
    ).order_by(AuditLog.timestamp.desc()).limit(limit).all()


def get_emergency_access_logs(limit=100):
    """
    Get all emergency access logs.
    
    Args:
        limit (int): Maximum number of records to return
        
    Returns:
        list: List of AuditLog objects for emergency access
    """
    return AuditLog.query.filter_by(
        is_emergency_access=True
    ).order_by(AuditLog.timestamp.desc()).limit(limit).all()


def get_recent_audit_logs(hours=24, event_type=None, limit=100):
    """
    Get recent audit logs within specified time window.
    
    Args:
        hours (int): Number of hours to look back
        event_type (str): Optional filter by event type
        limit (int): Maximum number of records to return
        
    Returns:
        list: List of AuditLog objects
    """
    from datetime import timedelta
    
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    query = AuditLog.query.filter(AuditLog.timestamp >= cutoff_time)
    
    if event_type:
        query = query.filter_by(event_type=event_type)
    
    return query.order_by(AuditLog.timestamp.desc()).limit(limit).all()


def get_failed_login_attempts(username=None, hours=24):
    """
    Get failed login attempts for security monitoring.
    
    Args:
        username (str): Optional filter by username
        hours (int): Number of hours to look back
        
    Returns:
        list: List of failed login audit logs
    """
    from datetime import timedelta
    
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    query = AuditLog.query.filter(
        AuditLog.event_type == 'LOGIN_FAILED',
        AuditLog.timestamp >= cutoff_time
    )
    
    logs = query.order_by(AuditLog.timestamp.desc()).all()
    
    # Filter by username if provided
    if username:
        filtered_logs = []
        for log in logs:
            try:
                details = json.loads(log.details) if log.details else {}
                if details.get('username') == username:
                    filtered_logs.append(log)
            except json.JSONDecodeError:
                continue
        return filtered_logs
    
    return logs


def get_unauthorized_access_attempts(hours=24):
    """
    Get all unauthorized access attempts for security monitoring.
    
    Args:
        hours (int): Number of hours to look back
        
    Returns:
        list: List of unauthorized access audit logs
    """
    from datetime import timedelta
    
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    return AuditLog.query.filter(
        AuditLog.event_type.in_([
            'UNAUTHORIZED_DISPENSE_ATTEMPT',
            'TOKEN_VALIDATION_FAILED',
            'LOGIN_FAILED'
        ]),
        AuditLog.timestamp >= cutoff_time
    ).order_by(AuditLog.timestamp.desc()).all()


def get_audit_statistics(days=30):
    """
    Get audit log statistics for admin dashboard.
    
    Args:
        days (int): Number of days to look back
        
    Returns:
        dict: Audit statistics
    """
    from datetime import timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Total logs
    total_logs = AuditLog.query.filter(AuditLog.timestamp >= cutoff_date).count()
    
    # Count by event type
    event_type_counts = {}
    logs = AuditLog.query.filter(AuditLog.timestamp >= cutoff_date).all()
    
    for log in logs:
        event_type_counts[log.event_type] = event_type_counts.get(log.event_type, 0) + 1
    
    # Emergency access count
    emergency_count = AuditLog.query.filter(
        AuditLog.is_emergency_access == True,
        AuditLog.timestamp >= cutoff_date
    ).count()
    
    # Failed login attempts
    failed_logins = AuditLog.query.filter(
        AuditLog.event_type == 'LOGIN_FAILED',
        AuditLog.timestamp >= cutoff_date
    ).count()
    
    # Blockchain-backed logs
    blockchain_backed = AuditLog.query.filter(
        AuditLog.block_id.isnot(None),
        AuditLog.timestamp >= cutoff_date
    ).count()
    
    return {
        'total_logs': total_logs,
        'days': days,
        'by_event_type': event_type_counts,
        'emergency_access_count': emergency_count,
        'failed_login_count': failed_logins,
        'blockchain_backed_count': blockchain_backed
    }


def search_audit_logs(filters=None, page=1, per_page=50):
    """
    Search audit logs with advanced filtering.
    
    Args:
        filters (dict): Filter criteria (event_type, user_id, prescription_id, etc.)
        page (int): Page number for pagination
        per_page (int): Items per page
        
    Returns:
        dict: Paginated search results
    """
    query = AuditLog.query
    
    if filters:
        # Filter by event type
        if filters.get('event_type'):
            query = query.filter_by(event_type=filters['event_type'])
        
        # Filter by user ID
        if filters.get('user_id'):
            query = query.filter_by(user_id=filters['user_id'])
        
        # Filter by prescription ID
        if filters.get('prescription_id'):
            query = query.filter_by(prescription_id=filters['prescription_id'])
        
        # Filter by date range
        if filters.get('start_date'):
            query = query.filter(AuditLog.timestamp >= filters['start_date'])
        
        if filters.get('end_date'):
            query = query.filter(AuditLog.timestamp <= filters['end_date'])
        
        # Filter by emergency access
        if filters.get('is_emergency_access') is not None:
            query = query.filter_by(is_emergency_access=filters['is_emergency_access'])
        
        # Filter by IP address
        if filters.get('ip_address'):
            query = query.filter_by(ip_address=filters['ip_address'])
    
    # Paginate results
    pagination = query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return {
        'logs': [log.to_dict() for log in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages
    }


def verify_audit_log_integrity(audit_log_id):
    """
    Verify integrity of an audit log by checking blockchain reference.
    
    Args:
        audit_log_id (int): Audit log ID
        
    Returns:
        dict: Verification result
    """
    audit_log = AuditLog.query.get(audit_log_id)
    
    if not audit_log:
        return {
            'verified': False,
            'message': 'Audit log not found'
        }
    
    # Check if log has blockchain reference
    if not audit_log.block_id:
        return {
            'verified': True,
            'message': 'Audit log not blockchain-backed (not a critical event)',
            'blockchain_backed': False
        }
    
    # Verify blockchain block exists and is valid
    from blockchain.ledger import Blockchain
    from models import Block
    
    block = Block.query.get(audit_log.block_id)
    
    if not block:
        return {
            'verified': False,
            'message': 'Blockchain block reference not found - possible tampering',
            'blockchain_backed': True
        }
    
    # Verify blockchain integrity
    blockchain = Blockchain()
    is_valid = blockchain.is_chain_valid()
    
    if not is_valid:
        return {
            'verified': False,
            'message': 'Blockchain integrity compromised',
            'blockchain_backed': True,
            'block_id': block.id
        }
    
    # Verify block data matches audit log
    try:
        block_data = json.loads(block.data)
        if block_data.get('audit_log_id') == audit_log.id:
            return {
                'verified': True,
                'message': 'Audit log integrity verified via blockchain',
                'blockchain_backed': True,
                'block_id': block.id,
                'block_hash': block.hash
            }
        else:
            return {
                'verified': False,
                'message': 'Audit log ID mismatch in blockchain block',
                'blockchain_backed': True,
                'block_id': block.id
            }
    except json.JSONDecodeError:
        return {
            'verified': False,
            'message': 'Invalid blockchain block data format',
            'blockchain_backed': True,
            'block_id': block.id
        }


def export_audit_logs(start_date=None, end_date=None, event_types=None):
    """
    Export audit logs for compliance reporting.
    
    Args:
        start_date (datetime): Start date for export
        end_date (datetime): End date for export
        event_types (list): List of event types to include
        
    Returns:
        list: List of audit log dictionaries
    """
    query = AuditLog.query
    
    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)
    
    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)
    
    if event_types:
        query = query.filter(AuditLog.event_type.in_(event_types))
    
    logs = query.order_by(AuditLog.timestamp.asc()).all()
    
    return [log.to_dict() for log in logs]


def get_user_activity_summary(user_id, days=30):
    """
    Get activity summary for a specific user.
    
    Args:
        user_id (int): User ID
        days (int): Number of days to look back
        
    Returns:
        dict: User activity summary
    """
    from datetime import timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    logs = AuditLog.query.filter(
        AuditLog.user_id == user_id,
        AuditLog.timestamp >= cutoff_date
    ).all()
    
    # Count by event type
    by_event_type = {}
    for log in logs:
        by_event_type[log.event_type] = by_event_type.get(log.event_type, 0) + 1
    
    # Get last login
    last_login = AuditLog.query.filter(
        AuditLog.user_id == user_id,
        AuditLog.event_type == 'LOGIN_SUCCESS'
    ).order_by(AuditLog.timestamp.desc()).first()
    
    # Count failed logins
    failed_logins = AuditLog.query.filter(
        AuditLog.user_id == user_id,
        AuditLog.event_type == 'LOGIN_FAILED',
        AuditLog.timestamp >= cutoff_date
    ).count()
    
    return {
        'user_id': user_id,
        'days': days,
        'total_actions': len(logs),
        'by_event_type': by_event_type,
        'last_login': last_login.timestamp.isoformat() if last_login else None,
        'failed_login_count': failed_logins
    }


def cleanup_old_audit_logs():
    """
    Archive or clean up old audit logs based on retention policy.
    This should be run periodically as a maintenance task.
    
    Note: Emergency access logs are NEVER deleted due to legal requirements.
    
    Returns:
        dict: Cleanup statistics
    """
    from datetime import timedelta
    
    retention_days = Config.AUDIT_LOG['RETENTION_DAYS']
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
    
    # Count logs to be archived (excluding emergency access)
    old_logs = AuditLog.query.filter(
        AuditLog.timestamp < cutoff_date,
        AuditLog.is_emergency_access == False
    ).all()
    
    # In production, you would archive these to cold storage
    # For now, we'll just count them (don't actually delete due to immutability requirement)
    
    return {
        'logs_eligible_for_archival': len(old_logs),
        'retention_days': retention_days,
        'cutoff_date': cutoff_date.isoformat(),
        'note': 'Audit logs are immutable - archive to cold storage instead of deletion'
    }


def detect_suspicious_patterns(hours=24):
    """
    Detect suspicious patterns in audit logs for security monitoring.
    
    Args:
        hours (int): Number of hours to analyze
        
    Returns:
        dict: Detected suspicious patterns
    """
    from datetime import timedelta
    
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    suspicious_patterns = []
    
    # Pattern 1: Multiple failed logins from same IP
    logs = AuditLog.query.filter(
        AuditLog.event_type == 'LOGIN_FAILED',
        AuditLog.timestamp >= cutoff_time
    ).all()
    
    ip_failed_counts = {}
    for log in logs:
        if log.ip_address:
            ip_failed_counts[log.ip_address] = ip_failed_counts.get(log.ip_address, 0) + 1
    
    for ip, count in ip_failed_counts.items():
        if count >= 5:
            suspicious_patterns.append({
                'type': 'multiple_failed_logins',
                'ip_address': ip,
                'count': count,
                'severity': 'HIGH'
            })
    
    # Pattern 2: Unauthorized access attempts
    unauthorized = AuditLog.query.filter(
        AuditLog.event_type == 'UNAUTHORIZED_DISPENSE_ATTEMPT',
        AuditLog.timestamp >= cutoff_time
    ).count()
    
    if unauthorized > 0:
        suspicious_patterns.append({
            'type': 'unauthorized_access_attempts',
            'count': unauthorized,
            'severity': 'MEDIUM'
        })
    
    # Pattern 3: Rapid emergency access events
    emergency = AuditLog.query.filter(
        AuditLog.is_emergency_access == True,
        AuditLog.timestamp >= cutoff_time
    ).count()
    
    if emergency > 3:
        suspicious_patterns.append({
            'type': 'multiple_emergency_accesses',
            'count': emergency,
            'severity': 'CRITICAL'
        })
    
    return {
        'hours_analyzed': hours,
        'patterns_detected': len(suspicious_patterns),
        'patterns': suspicious_patterns
    }
