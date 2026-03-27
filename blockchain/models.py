"""
MediSure Vault - Database Models Module

This module defines all SQLAlchemy ORM models for the prescription management
system including Users, Prescriptions, Access Tokens, Audit Logs, and Blockchain.
"""

from database import db
from datetime import datetime, timedelta
from sqlalchemy import Index, CheckConstraint
import json


class User(db.Model):
    """
    User model for storing account information with role-based access control.
    
    Roles: PATIENT, DOCTOR, PHARMACIST, ADMIN
    """
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False, default='PATIENT')
    full_name = db.Column(db.String(200), nullable=False)
    
    # Professional credentials (for doctors and pharmacists)
    license_number = db.Column(db.String(50), unique=True, nullable=True)
    pharmacy_id = db.Column(db.String(50), nullable=True)  # For pharmacists
    
    # Account status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    prescriptions_created = db.relationship('Prescription', 
                                           foreign_keys='Prescription.doctor_id',
                                           backref='doctor', 
                                           lazy='dynamic')
    prescriptions_received = db.relationship('Prescription', 
                                            foreign_keys='Prescription.patient_id',
                                            backref='patient', 
                                            lazy='dynamic')
    access_tokens = db.relationship('AccessToken', 
                                   foreign_keys='AccessToken.patient_id',
                                   backref='patient', 
                                   lazy='dynamic',
                                   cascade='all, delete-orphan')
    audit_logs = db.relationship('AuditLog', 
                                foreign_keys='AuditLog.user_id',
                                backref='user', 
                                lazy='dynamic',
                                cascade='all, delete-orphan')
    
    # Constraints
    __table_args__ = (
        CheckConstraint(role.in_(['PATIENT', 'DOCTOR', 'PHARMACIST', 'ADMIN']), 
                       name='valid_role'),
    )
    
    def __repr__(self):
        return f'<User {self.username} ({self.role})>'
    
    def has_permission(self, permission):
        """
        Check if user has a specific permission based on their role.
        
        Args:
            permission (str): Permission to check
            
        Returns:
            bool: True if user has permission, False otherwise
        """
        from config import Config
        role_permissions = Config.ROLES.get(self.role, {}).get('permissions', [])
        return permission in role_permissions
    
    def to_dict(self):
        """Convert user to dictionary representation."""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'full_name': self.full_name,
            'license_number': self.license_number,
            'pharmacy_id': self.pharmacy_id,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }


class Prescription(db.Model):
    """
    Prescription model with explicit lifecycle states and immutability after dispensing.
    
    States: CREATED → SHARED → DISPENSED → LOCKED (terminal state)
    """
    __tablename__ = 'prescriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Prescription details
    medication_name = db.Column(db.String(200), nullable=False)
    dosage = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    refills_allowed = db.Column(db.Integer, default=0, nullable=False)
    instructions = db.Column(db.Text, nullable=True)
    diagnosis = db.Column(db.String(500), nullable=True)
    
    # Lifecycle state management
    state = db.Column(db.String(20), default='CREATED', nullable=False, index=True)
    
    # Timestamps for state transitions
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    shared_at = db.Column(db.DateTime, nullable=True)
    dispensed_at = db.Column(db.DateTime, nullable=True)
    locked_at = db.Column(db.DateTime, nullable=True)
    
    # Dispensing information
    dispensed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    dispensed_by = db.relationship('User', foreign_keys=[dispensed_by_id])
    pharmacy_id = db.Column(db.String(50), nullable=True)  # Pharmacy that dispensed
    
    # Tamper detection
    tamper_score = db.Column(db.Integer, default=0, nullable=False)
    tamper_events = db.Column(db.Text, default='[]', nullable=False)  # JSON array of events
    
    # Hash for integrity verification
    content_hash = db.Column(db.String(64), nullable=False)  # SHA-256 hash
    
    # Expiration
    expires_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    access_tokens = db.relationship('AccessToken', 
                                   backref='prescription', 
                                   lazy='dynamic',
                                   cascade='all, delete-orphan')
    
    # Constraints
    __table_args__ = (
        CheckConstraint(state.in_(['CREATED', 'SHARED', 'DISPENSED', 'LOCKED', 'CANCELLED']), 
                       name='valid_state'),
        CheckConstraint(quantity > 0, name='positive_quantity'),
        CheckConstraint(refills_allowed >= 0, name='non_negative_refills'),
        CheckConstraint(tamper_score >= 0, name='non_negative_tamper_score'),
        CheckConstraint(tamper_score <= 100, name='max_tamper_score'),
        Index('idx_prescription_state_patient', 'state', 'patient_id'),
        Index('idx_prescription_created_at', 'created_at'),
    )
    
    def __repr__(self):
        return f'<Prescription {self.id} - {self.medication_name} ({self.state})>'
    
    def can_transition_to(self, new_state):
        """
        Check if prescription can transition to a new state.
        
        Args:
            new_state (str): Target state
            
        Returns:
            bool: True if transition is allowed, False otherwise
        """
        from config import Config
        allowed_transitions = Config.PRESCRIPTION_STATES.get(self.state, {}).get('allowed_transitions', [])
        return new_state in allowed_transitions
    
    def is_locked(self):
        """Check if prescription is in LOCKED state (immutable)."""
        return self.state == 'LOCKED'
    
    def is_editable(self):
        """Check if prescription can be edited."""
        from config import Config
        return Config.PRESCRIPTION_STATES.get(self.state, {}).get('can_edit', False)
    
    def compute_content_hash(self):
        """
        Compute SHA-256 hash of prescription content for integrity verification.
        
        Returns:
            str: Hexadecimal hash string
        """
        import hashlib
        
        content = f"{self.patient_id}:{self.doctor_id}:{self.medication_name}:{self.dosage}:{self.quantity}:{self.refills_allowed}:{self.instructions or ''}:{self.diagnosis or ''}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def add_tamper_event(self, event_type, severity, description):
        """
        Record a tamper event and update tamper score.
        
        Args:
            event_type (str): Type of tamper event
            severity (int): Severity score to add
            description (str): Description of the event
        """
        from config import Config
        
        # Parse existing events
        events = json.loads(self.tamper_events)
        
        # Add new event
        events.append({
            'timestamp': datetime.utcnow().isoformat(),
            'type': event_type,
            'severity': severity,
            'description': description
        })
        
        # Update tamper events
        self.tamper_events = json.dumps(events)
        
        # Update tamper score (cap at 100)
        self.tamper_score = min(self.tamper_score + severity, 100)
    
    def get_tamper_severity(self):
        """
        Get tamper severity level based on score.
        
        Returns:
            str: Severity level (LOW, MEDIUM, HIGH, CRITICAL)
        """
        from config import Config
        
        for level, (min_score, max_score) in Config.TAMPER_SCORE_THRESHOLDS.items():
            if min_score <= self.tamper_score <= max_score:
                return level
        
        return 'LOW'
    
    def to_dict(self):
        """Convert prescription to dictionary representation."""
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'patient_name': self.patient.full_name if self.patient else None,
            'doctor_id': self.doctor_id,
            'doctor_name': self.doctor.full_name if self.doctor else None,
            'medication_name': self.medication_name,
            'dosage': self.dosage,
            'quantity': self.quantity,
            'refills_allowed': self.refills_allowed,
            'instructions': self.instructions,
            'diagnosis': self.diagnosis,
            'state': self.state,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'shared_at': self.shared_at.isoformat() if self.shared_at else None,
            'dispensed_at': self.dispensed_at.isoformat() if self.dispensed_at else None,
            'locked_at': self.locked_at.isoformat() if self.locked_at else None,
            'dispensed_by': self.dispensed_by.full_name if self.dispensed_by else None,
            'pharmacy_id': self.pharmacy_id,
            'tamper_score': self.tamper_score,
            'tamper_severity': self.get_tamper_severity(),
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_locked': self.is_locked(),
            'is_editable': self.is_editable()
        }


class AccessToken(db.Model):
    """
    Patient-controlled time-bound one-time access tokens for prescription sharing.
    Tokens are generated by patients and consumed by pharmacists.
    """
    __tablename__ = 'access_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    
    # Foreign keys
    prescription_id = db.Column(db.Integer, db.ForeignKey('prescriptions.id'), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Token lifecycle
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    
    # Token status
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    is_revoked = db.Column(db.Boolean, default=False, nullable=False)
    
    # Usage tracking
    used_at = db.Column(db.DateTime, nullable=True)
    used_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    used_by = db.relationship('User', foreign_keys=[used_by_id])
    used_from_ip = db.Column(db.String(45), nullable=True)  # IPv6 support
    
    # Revocation tracking
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoked_reason = db.Column(db.String(500), nullable=True)
    
    # Constraints
    __table_args__ = (
        Index('idx_token_status', 'is_used', 'is_revoked', 'expires_at'),
    )
    
    def __repr__(self):
        return f'<AccessToken {self.token[:8]}... (Prescription {self.prescription_id})>'
    
    def is_valid(self):
        """
        Check if token is valid for use.
        
        Returns:
            bool: True if token is valid, False otherwise
        """
        if self.is_used or self.is_revoked:
            return False
        
        if datetime.utcnow() > self.expires_at:
            return False
        
        return True
    
    def revoke(self, reason=None):
        """
        Revoke the token, preventing further use.
        
        Args:
            reason (str): Optional reason for revocation
        """
        self.is_revoked = True
        self.revoked_at = datetime.utcnow()
        self.revoked_reason = reason
    
    def consume(self, user_id, ip_address=None):
        """
        Mark token as used (one-time use).
        
        Args:
            user_id (int): ID of user consuming the token
            ip_address (str): IP address of the request
        """
        self.is_used = True
        self.used_at = datetime.utcnow()
        self.used_by_id = user_id
        self.used_from_ip = ip_address
    
    def to_dict(self):
        """Convert access token to dictionary representation."""
        return {
            'id': self.id,
            'token': self.token,
            'prescription_id': self.prescription_id,
            'patient_id': self.patient_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_used': self.is_used,
            'is_revoked': self.is_revoked,
            'is_valid': self.is_valid(),
            'used_at': self.used_at.isoformat() if self.used_at else None,
            'used_by': self.used_by.full_name if self.used_by else None,
            'revoked_at': self.revoked_at.isoformat() if self.revoked_at else None,
            'revoked_reason': self.revoked_reason
        }


class AuditLog(db.Model):
    """
    Immutable audit log for tracking all system events.
    Critical events are also recorded in the blockchain.
    """
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Event information
    event_type = db.Column(db.String(50), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # User and resource tracking
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey('prescriptions.id'), nullable=True, index=True)
    
    # Event details (JSON)
    details = db.Column(db.Text, nullable=True)  # JSON object with event-specific data
    
    # Request metadata
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    
    # Blockchain reference (if event was recorded on blockchain)
    block_id = db.Column(db.Integer, db.ForeignKey('blocks.id'), nullable=True)
    
    # Emergency access tracking
    is_emergency_access = db.Column(db.Boolean, default=False, nullable=False)
    emergency_justification = db.Column(db.Text, nullable=True)
    
    # Constraints
    __table_args__ = (
        Index('idx_audit_event_type_timestamp', 'event_type', 'timestamp'),
        Index('idx_audit_user_timestamp', 'user_id', 'timestamp'),
    )
    
    def __repr__(self):
        return f'<AuditLog {self.event_type} at {self.timestamp}>'
    
    def to_dict(self):
        """Convert audit log to dictionary representation."""
        return {
            'id': self.id,
            'event_type': self.event_type,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'user_id': self.user_id,
            'username': self.user.username if self.user else None,
            'prescription_id': self.prescription_id,
            'details': json.loads(self.details) if self.details else None,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'block_id': self.block_id,
            'is_emergency_access': self.is_emergency_access,
            'emergency_justification': self.emergency_justification
        }


class Block(db.Model):
    """
    Blockchain block for immutable audit trail.
    Each block contains a hash of the previous block, creating an immutable chain.
    """
    __tablename__ = 'blocks'
    
    id = db.Column(db.Integer, primary_key=True)
    index = db.Column(db.Integer, unique=True, nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Block data (JSON containing event information)
    data = db.Column(db.Text, nullable=False)
    
    # Blockchain integrity
    previous_hash = db.Column(db.String(64), nullable=False)
    hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    nonce = db.Column(db.Integer, default=0, nullable=False)
    
    # Relationships
    audit_logs = db.relationship('AuditLog', backref='block', lazy='dynamic')
    
    def __repr__(self):
        return f'<Block {self.index} - {self.hash[:8]}...>'
    
    def compute_hash(self):
        """
        Compute SHA-256 hash of block contents.
        
        Returns:
            str: Hexadecimal hash string
        """
        import hashlib
        
        block_string = f"{self.index}{self.timestamp.isoformat()}{self.data}{self.previous_hash}{self.nonce}"
        return hashlib.sha256(block_string.encode()).hexdigest()
    
    def to_dict(self):
        """Convert block to dictionary representation."""
        return {
            'id': self.id,
            'index': self.index,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'data': json.loads(self.data) if self.data else None,
            'previous_hash': self.previous_hash,
            'hash': self.hash,
            'nonce': self.nonce
        }


class PharmacyAccess(db.Model):
    """
    Track pharmacy access to prescriptions for collision detection.
    Multiple pharmacies accessing the same prescription triggers tamper alert.
    """
    __tablename__ = 'pharmacy_access'
    
    id = db.Column(db.Integer, primary_key=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey('prescriptions.id'), nullable=False, index=True)
    pharmacy_id = db.Column(db.String(50), nullable=False, index=True)
    pharmacist_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    accessed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    access_type = db.Column(db.String(20), nullable=False)  # VIEW, DISPENSE
    
    # Relationships
    prescription = db.relationship('Prescription', backref='pharmacy_accesses')
    pharmacist = db.relationship('User', backref='pharmacy_accesses')
    
    # Constraints
    __table_args__ = (
        Index('idx_pharmacy_access_prescription_time', 'prescription_id', 'accessed_at'),
        CheckConstraint(access_type.in_(['VIEW', 'DISPENSE']), name='valid_access_type'),
    )
    
    def __repr__(self):
        return f'<PharmacyAccess Prescription {self.prescription_id} by Pharmacy {self.pharmacy_id}>'
    
    def to_dict(self):
        """Convert pharmacy access to dictionary representation."""
        return {
            'id': self.id,
            'prescription_id': self.prescription_id,
            'pharmacy_id': self.pharmacy_id,
            'pharmacist_id': self.pharmacist_id,
            'pharmacist_name': self.pharmacist.full_name if self.pharmacist else None,
            'accessed_at': self.accessed_at.isoformat() if self.accessed_at else None,
            'access_type': self.access_type
        }


class Doctor(db.Model):
    """
    Doctor-specific profile information extending the User model.
    Stores medical professional credentials and specialization.
    """
    __tablename__ = 'doctors'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), 
                       unique=True, nullable=False)
    license_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    specialization = db.Column(db.String(100), nullable=False)
    hospital = db.Column(db.String(200), nullable=False)
    years_experience = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship to User
    user = db.relationship('User', backref=db.backref('doctor_profile', uselist=False))
    
    def __repr__(self):
        return f'<Doctor {self.license_number} - {self.specialization}>'
    
    def to_dict(self):
        """Convert doctor profile to dictionary representation."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'license_number': self.license_number,
            'specialization': self.specialization,
            'hospital': self.hospital,
            'years_experience': self.years_experience,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Pharmacist(db.Model):
    """
    Pharmacist-specific profile information extending the User model.
    Stores pharmacy credentials and location information.
    """
    __tablename__ = 'pharmacists'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), 
                       unique=True, nullable=False)
    pharmacy_name = db.Column(db.String(200), nullable=False)
    license_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    location = db.Column(db.String(300), nullable=False)
    certification_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship to User
    user = db.relationship('User', backref=db.backref('pharmacist_profile', uselist=False))
    
    def __repr__(self):
        return f'<Pharmacist {self.license_number} - {self.pharmacy_name}>'
    
    def to_dict(self):
        """Convert pharmacist profile to dictionary representation."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'pharmacy_name': self.pharmacy_name,
            'license_number': self.license_number,
            'location': self.location,
            'certification_date': self.certification_date.isoformat() if self.certification_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Patient(db.Model):
    """
    Patient-specific profile information extending the User model.
    Stores patient demographics and contact information.
    """
    __tablename__ = 'patients'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), 
                       unique=True, nullable=False)
    age = db.Column(db.Integer, nullable=False)
    contact_number = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(300), nullable=True)
    emergency_contact = db.Column(db.String(100), nullable=True)
    blood_group = db.Column(db.String(5), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship to User
    user = db.relationship('User', backref=db.backref('patient_profile', uselist=False))
    
    __table_args__ = (
        CheckConstraint('age >= 0 AND age <= 150', name='valid_age'),
    )
    
    def __repr__(self):
        return f'<Patient {self.user_id} - Age {self.age}>'
    
    def to_dict(self):
        """Convert patient profile to dictionary representation."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'age': self.age,
            'contact_number': self.contact_number,
            'address': self.address,
            'emergency_contact': self.emergency_contact,
            'blood_group': self.blood_group,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
