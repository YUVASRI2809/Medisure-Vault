"""
MediSure Vault - Main Application Module

This is the entry point for the Flask application. It initializes the app,
database, blockchain, and registers all blueprints for the prescription
management system.
"""

from flask import Flask, jsonify, render_template, session, request, redirect, url_for
from database import db
from config import Config
from datetime import datetime
import os


def create_app(config_name=None):
    """
    Application factory pattern for creating and configuring the Flask app.
    
    Args:
        config_name (str): Configuration environment ('development', 'production', 'testing')
        
    Returns:
        Flask: Configured Flask application instance
    """
    app = Flask(__name__)
    
    # Load configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    from config import get_config
    app.config.from_object(get_config(config_name))
    
    # Initialize extensions
    db.init_app(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Initialize database and blockchain
    # In production, run `python init_db.py` once instead of doing this on every startup.
    if config_name != 'production':
        with app.app_context():
            initialize_database()
            initialize_blockchain()
    
    # Register template filters
    register_template_filters(app)
    
    # Register before/after request handlers
    register_request_handlers(app)
    
    return app


def register_blueprints(app):
    """
    Register all Flask blueprints for modular routing.
    
    Args:
        app (Flask): Flask application instance
    """
    # Import blueprints
    from auth.routes import auth_bp
    from prescriptions.routes import prescriptions_bp
    from access.routes import access_bp
    from routes.doctor import doctor_bp
    from routes.pharmacist import pharmacist_bp
    from routes.patient import patient_bp

    # Register blueprints with URL prefixes
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(prescriptions_bp, url_prefix='/prescriptions')
    app.register_blueprint(access_bp, url_prefix='/access')
    app.register_blueprint(doctor_bp)       # url_prefix='/doctor' set in blueprint
    app.register_blueprint(pharmacist_bp)   # url_prefix='/pharmacist' set in blueprint
    app.register_blueprint(patient_bp)      # url_prefix='/patient' set in blueprint
    
    # Additional API routes for dashboard features
    @app.route('/api/anomalies/statistics', methods=['GET'])
    def anomaly_statistics():
        """Get anomaly statistics."""
        from auth.utils import login_required
        from anomaly.rules import get_anomaly_statistics
        
        @login_required
        def _anomaly_statistics():
            days = int(request.args.get('days', 30))
            stats = get_anomaly_statistics(days)
            return jsonify(stats), 200
        
        return _anomaly_statistics()
    
    @app.route('/api/anomalies/high-risk', methods=['GET'])
    def high_risk_prescriptions():
        """Get high-risk prescriptions (tamper score >= 50)."""
        from auth.utils import login_required
        from models import Prescription
        
        @login_required
        def _high_risk_prescriptions():
            threshold = int(request.args.get('threshold', 50))
            prescriptions = Prescription.query.filter(
                Prescription.tamper_score >= threshold
            ).order_by(Prescription.tamper_score.desc()).limit(100).all()
            
            return jsonify({
                'prescriptions': [p.to_dict() for p in prescriptions],
                'total': len(prescriptions),
                'threshold': threshold
            }), 200
        
        return _high_risk_prescriptions()
    
    @app.route('/api/collisions/active', methods=['GET'])
    def active_collisions():
        """Get active pharmacy collision alerts."""
        from auth.utils import login_required
        from models import PharmacyAccess, Prescription
        
        @login_required
        def _active_collisions():
            # Find prescriptions with multiple pharmacy accesses
            from sqlalchemy import func
            
            collision_prescriptions = db.session.query(
                PharmacyAccess.prescription_id,
                func.count(func.distinct(PharmacyAccess.pharmacy_id)).label('pharmacy_count')
            ).group_by(PharmacyAccess.prescription_id).having(
                func.count(func.distinct(PharmacyAccess.pharmacy_id)) > 1
            ).all()
            
            results = []
            for item in collision_prescriptions:
                prescription = Prescription.query.get(item.prescription_id)
                if prescription:
                    accesses = PharmacyAccess.query.filter_by(
                        prescription_id=item.prescription_id
                    ).all()
                    
                    results.append({
                        'prescription_id': item.prescription_id,
                        'pharmacy_count': item.pharmacy_count,
                        'prescription': prescription.to_dict(),
                        'accesses': [a.to_dict() for a in accesses]
                    })
            
            return jsonify({
                'collisions': results,
                'total': len(results)
            }), 200
        
        return _active_collisions()
    
    @app.route('/api/collisions/statistics', methods=['GET'])
    def collision_statistics():
        """Get collision detection statistics."""
        from auth.utils import login_required
        from models import AuditLog
        from datetime import timedelta
        
        @login_required
        def _collision_statistics():
            days = int(request.args.get('days', 30))
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            total_collisions = AuditLog.query.filter(
                AuditLog.event_type == 'PHARMACY_COLLISION_DETECTED',
                AuditLog.timestamp >= cutoff
            ).count()
            
            return jsonify({
                'total_collisions': total_collisions,
                'days': days,
                'auto_lock_enabled': Config.COLLISION_DETECTION.get('AUTO_LOCK_ON_COLLISION', False)
            }), 200
        
        return _collision_statistics()
    
    @app.route('/api/prescriptions/<int:prescription_id>/pharmacy-access', methods=['GET'])
    def prescription_pharmacy_access(prescription_id):
        """Get pharmacy access history for a prescription."""
        from auth.utils import login_required
        from models import PharmacyAccess
        
        @login_required
        def _prescription_pharmacy_access():
            accesses = PharmacyAccess.query.filter_by(
                prescription_id=prescription_id
            ).order_by(PharmacyAccess.access_timestamp.desc()).all()
            
            return jsonify({
                'prescription_id': prescription_id,
                'accesses': [a.to_dict() for a in accesses],
                'total': len(accesses),
                'unique_pharmacies': len(set(a.pharmacy_id for a in accesses))
            }), 200
        
        return _prescription_pharmacy_access()
    
    # Register main routes
    @app.route('/')
    def index():
        """Landing page route - shows portal selection."""
        return render_template('landing.html')
    
    @app.route('/authority-login')
    def authority_login():
        """Authority login page (Doctors, Pharmacists, Admins)."""
        return render_template('authority_login.html')
    
    @app.route('/authority-register')
    def authority_register():
        """Authority registration page."""
        return render_template('authority_register.html')
    
    @app.route('/doctor-register')
    def doctor_register():
        """Doctor registration page."""
        return render_template('doctor_register.html')
    
    @app.route('/pharmacist-register')
    def pharmacist_register():
        """Pharmacist registration page."""
        return render_template('pharmacist_register.html')
    
    @app.route('/patient-login')
    def patient_login():
        """Patient login page."""
        return render_template('patient_login.html')
    
    @app.route('/patient-register')
    def patient_register():
        """Patient registration page."""
        return render_template('patient_register.html')
    
    @app.route('/logout')
    def logout():
        """Logout route - clears session and redirects to landing page."""
        from auth.utils import logout_user
        logout_user()
        return redirect(url_for('index'))
    
    @app.route('/dashboard')
    def dashboard():
        """Dashboard route — redirects to the role-specific blueprint dashboard."""
        from auth.utils import login_required
        from models import User

        @login_required
        def _dashboard():
            user_role = session.get('role', '')
            user_id   = session.get('user_id')

            if user_role == 'DOCTOR':
                return redirect(url_for('doctor.dashboard'))
            elif user_role == 'PHARMACIST':
                return redirect(url_for('pharmacist.dashboard'))
            elif user_role == 'PATIENT':
                return redirect(url_for('patient.dashboard'))
            else:
                # ADMIN or unknown — generic dashboard
                current_user = User.query.get(user_id)
                return render_template('dashboard.html',
                                       role=user_role,
                                       user_id=user_id,
                                       username=current_user.username if current_user else 'Admin')

        return _dashboard()
    
    @app.route('/prescriptions-manager')
    def prescriptions_manager():
        """Prescription management page."""
        from auth.utils import login_required
        
        @login_required
        def _prescriptions_manager():
            return render_template('prescriptions_manager.html')
        
        return _prescriptions_manager()
    
    @app.route('/token-manager')
    def token_manager():
        """Token management page."""
        from auth.utils import login_required
        
        @login_required
        def _token_manager():
            return render_template('token_manager.html')
        
        return _token_manager()
    
    @app.route('/collision-monitor')
    def collision_monitor():
        """Collision detection monitoring page."""
        from auth.utils import login_required
        
        @login_required
        def _collision_monitor():
            return render_template('collision_monitor.html')
        
        return _collision_monitor()
    
    @app.route('/anomaly-dashboard')
    def anomaly_dashboard():
        """Anomaly detection dashboard page."""
        from auth.utils import login_required
        
        @login_required
        def _anomaly_dashboard():
            return render_template('anomaly_dashboard.html')
        
        return _anomaly_dashboard()
    
    @app.route('/health')
    def health_check():
        """Health check endpoint for monitoring."""
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'database': check_database_connection(),
            'blockchain': check_blockchain_integrity()
        }), 200
    
    # ==========================
    # Doctor Dashboard API Routes
    # ==========================
    
    @app.route('/api/doctor/stats', methods=['GET'])
    def doctor_stats():
        """Get statistics for doctor dashboard."""
        from auth.utils import login_required, role_required
        from models import Prescription
        
        @login_required
        @role_required('DOCTOR')
        def _doctor_stats():
            user_id = session.get('user_id')
            
            total = Prescription.query.filter_by(doctor_id=user_id).count()
            pending = Prescription.query.filter_by(doctor_id=user_id, state='CREATED').count()
            dispensed = Prescription.query.filter_by(doctor_id=user_id, state='DISPENSED').count()
            locked = Prescription.query.filter_by(doctor_id=user_id, state='LOCKED').count()
            
            return jsonify({
                'total': total,
                'pending': pending,
                'dispensed': dispensed,
                'locked': locked
            }), 200
        
        return _doctor_stats()
    
    @app.route('/api/doctor/prescriptions', methods=['GET'])
    def doctor_prescriptions():
        """Get all prescriptions created by this doctor."""
        from auth.utils import login_required, role_required
        from models import Prescription, User
        
        @login_required
        @role_required('DOCTOR')
        def _doctor_prescriptions():
            user_id = session.get('user_id')
            state_filter = request.args.get('state', '')
            
            query = Prescription.query.filter_by(doctor_id=user_id)
            if state_filter:
                query = query.filter_by(state=state_filter)
            
            prescriptions = query.order_by(Prescription.created_at.desc()).all()
            
            return jsonify([{
                'id': p.id,
                'medication_name': p.medication_name,
                'dosage': p.dosage,
                'quantity': p.quantity,
                'instructions': p.instructions,
                'state': p.state,
                'tamper_score': p.tamper_score,
                'patient_name': p.patient.full_name if p.patient else 'Unknown',
                'created_at': p.created_at.isoformat() if p.created_at else None,
                'dispensed_at': p.dispensed_at.isoformat() if p.dispensed_at else None
            } for p in prescriptions]), 200
        
        return _doctor_prescriptions()
    
    @app.route('/api/doctor/prescriptions', methods=['POST'])
    def create_prescription():
        """Create a new prescription."""
        from auth.utils import login_required, role_required
        from models import Prescription, User
        from blockchain.ledger import Blockchain
        from audit.logger import log_audit_event
        
        @login_required
        @role_required('DOCTOR')
        def _create_prescription():
            data = request.get_json()
            user_id = session.get('user_id')
            
            # Find patient by username
            patient = User.query.filter_by(username=data.get('patient_username'), role='PATIENT').first()
            if not patient:
                return jsonify({'error': 'Patient not found'}), 404
            
            # Create prescription
            import hashlib
            medication_name = data.get('medication_name', '')
            dosage = data.get('dosage', '')
            quantity = int(data.get('quantity', 1))
            instructions = data.get('instructions', '')
            content = f"{patient.id}:{user_id}:{medication_name}:{dosage}:{quantity}:0:{instructions}:"
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            prescription = Prescription(
                patient_id=patient.id,
                doctor_id=user_id,
                medication_name=medication_name,
                dosage=dosage,
                quantity=quantity,
                instructions=instructions,
                state='CREATED',
                content_hash=content_hash
            )
            
            db.session.add(prescription)
            db.session.commit()
            
            # Log to blockchain
            blockchain = Blockchain()
            blockchain.add_transaction({
                'type': 'PRESCRIPTION_CREATED',
                'prescription_id': prescription.id,
                'doctor_id': user_id,
                'patient_id': patient.id,
                'medication': prescription.medication_name
            })
            
            # Audit log
            log_audit_event(
                event_type='PRESCRIPTION_CREATED',
                user_id=user_id,
                details={'prescription_id': prescription.id},
                ip_address=request.remote_addr
            )
            
            return jsonify({
                'success': True,
                'prescription_id': prescription.id,
                'message': 'Prescription created successfully'
            }), 201
        
        return _create_prescription()
    
    # ==========================
    # Pharmacist Dashboard API Routes
    # ==========================
    
    @app.route('/api/pharmacist/stats', methods=['GET'])
    def pharmacist_stats():
        """Get statistics for pharmacist dashboard."""
        from auth.utils import login_required, role_required
        from models import Prescription, AccessToken
        from datetime import datetime, timedelta
        
        @login_required
        @role_required('PHARMACIST')
        def _pharmacist_stats():
            pending = Prescription.query.filter_by(state='SHARED').count()
            
            # Dispensed today
            today = datetime.utcnow().date()
            dispensed_today = Prescription.query.filter(
                Prescription.state.in_(['DISPENSED', 'LOCKED']),
                db.func.date(Prescription.dispensed_at) == today
            ).count()
            
            # Total dispensed
            dispensed_total = Prescription.query.filter(
                Prescription.state.in_(['DISPENSED', 'LOCKED'])
            ).count()
            
            # Active tokens
            active_tokens = AccessToken.query.filter(
                AccessToken.is_used == False,
                AccessToken.is_revoked == False,
                AccessToken.expires_at > datetime.utcnow()
            ).count()
            
            return jsonify({
                'pending': pending,
                'dispensed_today': dispensed_today,
                'dispensed_total': dispensed_total,
                'active_tokens': active_tokens
            }), 200
        
        return _pharmacist_stats()
    
    @app.route('/api/pharmacist/pending', methods=['GET'])
    def pharmacist_pending():
        """Get pending prescriptions for dispensing."""
        from auth.utils import login_required, role_required
        from models import Prescription
        
        @login_required
        @role_required('PHARMACIST')
        def _pharmacist_pending():
            prescriptions = Prescription.query.filter_by(state='SHARED').order_by(
                Prescription.created_at.desc()
            ).all()
            
            return jsonify([{
                'id': p.id,
                'medication_name': p.medication_name,
                'dosage': p.dosage,
                'quantity': p.quantity,
                'instructions': p.instructions,
                'patient_name': p.patient.full_name if p.patient else 'Unknown',
                'doctor_name': p.doctor.full_name if p.doctor else 'Unknown',
                'created_at': p.created_at.isoformat() if p.created_at else None
            } for p in prescriptions]), 200
        
        return _pharmacist_pending()
    
    @app.route('/api/pharmacist/dispense/<int:prescription_id>', methods=['POST'])
    def pharmacist_dispense(prescription_id):
        """Dispense a prescription and auto-lock it."""
        from auth.utils import login_required, role_required
        from models import Prescription
        from prescriptions.services import dispense_prescription
        from audit.logger import log_audit_event
        
        @login_required
        @role_required('PHARMACIST')
        def _pharmacist_dispense():
            user_id = session.get('user_id')
            
            prescription = Prescription.query.get(prescription_id)
            if not prescription:
                return jsonify({'error': 'Prescription not found'}), 404
            
            if prescription.state != 'SHARED':
                return jsonify({'error': 'Prescription is not available for dispensing'}), 400
            
            data = request.get_json() or {}
            pharmacy_id = data.get('pharmacy_id', session.get('pharmacy_id', 'UNKNOWN'))
            token = data.get('token', '')
            
            # Dispense and lock
            result, error = dispense_prescription(prescription_id, user_id, pharmacy_id, token)
            
            if result:
                # Audit log
                log_audit_event(
                    event_type='PRESCRIPTION_DISPENSED',
                    user_id=user_id,
                    details={'prescription_id': prescription_id},
                    ip_address=request.remote_addr
                )
                
                return jsonify({
                    'success': True,
                    'message': 'Prescription dispensed and locked successfully'
                }), 200
            else:
                return jsonify({'error': error}), 400
        
        return _pharmacist_dispense()
    
    @app.route('/api/pharmacist/history', methods=['GET'])
    def pharmacist_history():
        """Get dispensing history."""
        from auth.utils import login_required, role_required
        from models import Prescription
        from datetime import datetime, timedelta
        
        @login_required
        @role_required('PHARMACIST')
        def _pharmacist_history():
            filter_type = request.args.get('filter', 'today')
            
            query = Prescription.query.filter(
                Prescription.state.in_(['DISPENSED', 'LOCKED'])
            )
            
            if filter_type == 'today':
                today = datetime.utcnow().date()
                query = query.filter(db.func.date(Prescription.dispensed_at) == today)
            elif filter_type == 'week':
                week_ago = datetime.utcnow() - timedelta(days=7)
                query = query.filter(Prescription.dispensed_at >= week_ago)
            elif filter_type == 'month':
                month_ago = datetime.utcnow() - timedelta(days=30)
                query = query.filter(Prescription.dispensed_at >= month_ago)
            
            prescriptions = query.order_by(Prescription.dispensed_at.desc()).all()
            
            return jsonify([{
                'id': p.id,
                'medication_name': p.medication_name,
                'dosage': p.dosage,
                'quantity': p.quantity,
                'state': p.state,
                'patient_name': p.patient.full_name if p.patient else 'Unknown',
                'doctor_name': p.doctor.full_name if p.doctor else 'Unknown',
                'dispensed_at': p.dispensed_at.isoformat() if p.dispensed_at else None
            } for p in prescriptions]), 200
        
        return _pharmacist_history()
    
    # ==========================
    # Patient Dashboard API Routes
    # ==========================
    
    @app.route('/api/patient/stats', methods=['GET'])
    def patient_stats():
        """Get statistics for patient dashboard."""
        from auth.utils import login_required, role_required
        from models import Prescription, AccessToken
        from datetime import datetime
        
        @login_required
        @role_required('PATIENT')
        def _patient_stats():
            user_id = session.get('user_id')
            
            total = Prescription.query.filter_by(patient_id=user_id).count()
            pending = Prescription.query.filter_by(patient_id=user_id, state='CREATED').count()
            dispensed = Prescription.query.filter_by(patient_id=user_id).filter(
                Prescription.state.in_(['DISPENSED', 'LOCKED'])
            ).count()
            
            # Active tokens
            active_tokens = AccessToken.query.filter_by(patient_id=user_id).filter(
                AccessToken.is_used == False,
                AccessToken.is_revoked == False,
                AccessToken.expires_at > datetime.utcnow()
            ).count()
            
            return jsonify({
                'total': total,
                'pending': pending,
                'dispensed': dispensed,
                'active_tokens': active_tokens
            }), 200
        
        return _patient_stats()
    
    @app.route('/api/patient/prescriptions', methods=['GET'])
    def patient_prescriptions():
        """Get all prescriptions for this patient."""
        from auth.utils import login_required, role_required
        from models import Prescription
        
        @login_required
        @role_required('PATIENT')
        def _patient_prescriptions():
            user_id = session.get('user_id')
            state_filter = request.args.get('state', '')
            
            query = Prescription.query.filter_by(patient_id=user_id)
            if state_filter:
                query = query.filter_by(state=state_filter)
            
            prescriptions = query.order_by(Prescription.created_at.desc()).all()
            
            return jsonify([{
                'id': p.id,
                'medication_name': p.medication_name,
                'dosage': p.dosage,
                'quantity': p.quantity,
                'instructions': p.instructions,
                'state': p.state,
                'tamper_score': p.tamper_score,
                'doctor_name': p.doctor.full_name if p.doctor else 'Unknown',
                'created_at': p.created_at.isoformat() if p.created_at else None,
                'dispensed_at': p.dispensed_at.isoformat() if p.dispensed_at else None
            } for p in prescriptions]), 200
        
        return _patient_prescriptions()
    
    @app.route('/api/patient/tokens', methods=['GET'])
    def patient_tokens():
        """Get all access tokens for this patient."""
        from auth.utils import login_required, role_required
        from models import AccessToken, Prescription
        
        @login_required
        @role_required('PATIENT')
        def _patient_tokens():
            user_id = session.get('user_id')
            
            tokens = AccessToken.query.filter_by(patient_id=user_id).order_by(
                AccessToken.created_at.desc()
            ).all()
            
            return jsonify([{
                'token': t.token,
                'prescription_id': t.prescription_id,
                'prescription_name': t.prescription.medication_name if t.prescription else 'Unknown',
                'pharmacy_id': t.pharmacy_id,
                'created_at': t.created_at.isoformat() if t.created_at else None,
                'expires_at': t.expires_at.isoformat() if t.expires_at else None,
                'is_used': t.is_used,
                'is_revoked': t.is_revoked
            } for t in tokens]), 200
        
        return _patient_tokens()
    
    @app.route('/api/patient/tokens', methods=['POST'])
    def patient_create_token():
        """Generate a new access token."""
        from auth.utils import login_required, role_required
        from access.tokens import generate_access_token
        
        @login_required
        @role_required('PATIENT')
        def _patient_create_token():
            user_id = session.get('user_id')
            data = request.get_json()
            
            prescription_id = int(data.get('prescription_id'))
            pharmacy_id = data.get('pharmacy_id')
            expires_hours = int(data.get('expires_hours', 12))
            
            result = generate_access_token(
                prescription_id=prescription_id,
                patient_id=user_id,
                pharmacy_id=pharmacy_id,
                expires_hours=expires_hours
            )
            
            if result.get('success'):
                return jsonify(result), 201
            else:
                return jsonify({'error': result.get('error')}), 400
        
        return _patient_create_token()
    
    @app.route('/api/patient/tokens/<token>', methods=['DELETE'])
    def patient_revoke_token(token):
        """Revoke an access token."""
        from auth.utils import login_required, role_required
        from models import AccessToken
        
        @login_required
        @role_required('PATIENT')
        def _patient_revoke_token():
            user_id = session.get('user_id')
            
            access_token = AccessToken.query.filter_by(token=token, patient_id=user_id).first()
            if not access_token:
                return jsonify({'error': 'Token not found'}), 404
            
            access_token.is_revoked = True
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'Token revoked'}), 200
        
        return _patient_revoke_token()
    
    @app.route('/api/prescriptions/<int:prescription_id>', methods=['GET'])
    def get_prescription_details(prescription_id):
        """Get detailed information about a specific prescription."""
        from auth.utils import login_required
        from models import Prescription
        
        @login_required
        def _get_prescription_details():
            prescription = Prescription.query.get(prescription_id)
            if not prescription:
                return jsonify({'error': 'Prescription not found'}), 404
            
            return jsonify({
                'id': prescription.id,
                'medication_name': prescription.medication_name,
                'dosage': prescription.dosage,
                'quantity': prescription.quantity,
                'instructions': prescription.instructions,
                'state': prescription.state,
                'tamper_score': prescription.tamper_score,
                'patient_name': prescription.patient.full_name if prescription.patient else 'Unknown',
                'doctor_name': prescription.doctor.full_name if prescription.doctor else 'Unknown',
                'created_at': prescription.created_at.isoformat() if prescription.created_at else None,
                'dispensed_at': prescription.dispensed_at.isoformat() if prescription.dispensed_at else None
            }), 200
        
        return _get_prescription_details()


def register_error_handlers(app):
    """
    Register custom error handlers for common HTTP errors.
    
    Args:
        app (Flask): Flask application instance
    """
    
    @app.errorhandler(400)
    def bad_request(error):
        """Handle 400 Bad Request errors."""
        return jsonify({
            'error': 'Bad Request',
            'message': str(error),
            'timestamp': datetime.utcnow().isoformat()
        }), 400
    
    @app.errorhandler(401)
    def unauthorized(error):
        """Handle 401 Unauthorized errors."""
        return jsonify({
            'error': 'Unauthorized',
            'message': 'Authentication required',
            'timestamp': datetime.utcnow().isoformat()
        }), 401
    
    @app.errorhandler(403)
    def forbidden(error):
        """Handle 403 Forbidden errors."""
        return jsonify({
            'error': 'Forbidden',
            'message': 'You do not have permission to access this resource',
            'timestamp': datetime.utcnow().isoformat()
        }), 403
    
    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 Not Found errors."""
        return jsonify({
            'error': 'Not Found',
            'message': 'The requested resource was not found',
            'timestamp': datetime.utcnow().isoformat()
        }), 404
    
    @app.errorhandler(409)
    def conflict(error):
        """Handle 409 Conflict errors (e.g., multi-pharmacy collision)."""
        return jsonify({
            'error': 'Conflict',
            'message': str(error),
            'timestamp': datetime.utcnow().isoformat()
        }), 409
    
    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 Internal Server errors."""
        # Rollback database session on error
        db.session.rollback()
        
        return jsonify({
            'error': 'Internal Server Error',
            'message': 'An unexpected error occurred',
            'timestamp': datetime.utcnow().isoformat()
        }), 500


def register_template_filters(app):
    """
    Register custom Jinja2 template filters.
    
    Args:
        app (Flask): Flask application instance
    """
    
    @app.template_filter('format_datetime')
    def format_datetime(value, format_string='%Y-%m-%d %H:%M:%S'):
        """Format datetime object for display."""
        if value is None:
            return ''
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        return value.strftime(format_string)
    
    @app.template_filter('tamper_severity')
    def tamper_severity(score):
        """Get tamper severity level based on score."""
        if score >= 76:
            return 'CRITICAL'
        elif score >= 51:
            return 'HIGH'
        elif score >= 21:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    @app.template_filter('state_badge_class')
    def state_badge_class(state):
        """Get CSS class for prescription state badge."""
        state_classes = {
            'CREATED': 'badge-secondary',
            'SHARED': 'badge-info',
            'DISPENSED': 'badge-warning',
            'LOCKED': 'badge-danger',
            'CANCELLED': 'badge-dark'
        }
        return state_classes.get(state, 'badge-light')


def register_request_handlers(app):
    """
    Register before/after request handlers for logging and security.
    
    Args:
        app (Flask): Flask application instance
    """
    
    @app.before_request
    def before_request():
        """Execute before each request - update session activity."""
        if 'user_id' in session:
            session.permanent = True
            session.modified = True
    
    @app.after_request
    def after_request(response):
        """Execute after each request - add security headers."""
        # Security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return response


def initialize_database():
    """
    Initialize database tables and create default admin user if needed.
    Creates all tables defined in models.py and sets up initial data.
    """
    from models import User, Prescription, AccessToken, AuditLog, Doctor, Pharmacist, Patient
    
    # Create all tables
    db.create_all()
    
    # Check if admin user exists
    admin_user = User.query.filter_by(username='admin').first()
    
    if not admin_user:
        # Create default admin user
        from auth.utils import hash_password
        
        admin = User(
            username='admin',
            password_hash=hash_password('admin123'),  # Change in production
            email='admin@medisure.local',
            role='ADMIN',
            full_name='System Administrator'
        )
        
        db.session.add(admin)
        db.session.commit()
        
        # Log admin creation
        from audit.logger import log_audit_event
        log_audit_event(
            event_type='ADMIN_CREATED',
            user_id=admin.id,
            details={'message': 'Default admin user created'},
            ip_address='127.0.0.1'
        )


def initialize_blockchain():
    """
    Initialize the blockchain ledger with genesis block if it doesn't exist.
    The genesis block serves as the foundation of the immutable audit trail.
    """
    from blockchain.ledger import Blockchain
    from models import Block
    
    # Check if genesis block exists
    genesis = Block.query.filter_by(index=0).first()
    
    if not genesis:
        # Create blockchain instance (will create genesis block)
        blockchain = Blockchain()
        
        # The Blockchain constructor automatically creates and saves genesis block
        print("[OK] Genesis block created successfully")
    else:
        print("[OK] Blockchain already initialized")


def check_database_connection():
    """
    Check if database connection is healthy.
    
    Returns:
        str: 'connected' if database is accessible, 'disconnected' otherwise
    """
    try:
        # Execute a simple query
        from sqlalchemy import text
        db.session.execute(text('SELECT 1'))
        return 'connected'
    except Exception as e:
        print(f"Database connection error: {e}")
        return 'disconnected'


def check_blockchain_integrity():
    """
    Verify blockchain integrity by checking chain validity.
    
    Returns:
        str: 'valid' if blockchain is intact, 'corrupted' otherwise
    """
    try:
        from blockchain.ledger import Blockchain
        blockchain = Blockchain()
        
        if blockchain.is_chain_valid():
            return 'valid'
        else:
            return 'corrupted'
    except Exception:
        return 'error'


def get_system_statistics():
    """
    Get system-wide statistics for admin dashboard.
    
    Returns:
        dict: Dictionary containing system statistics
    """
    from models import User, Prescription, AccessToken, AuditLog, Block
    
    return {
        'total_users': User.query.count(),
        'total_prescriptions': Prescription.query.count(),
        'active_tokens': AccessToken.query.filter_by(is_used=False, is_revoked=False).count(),
        'audit_entries': AuditLog.query.count(),
        'blockchain_height': Block.query.count(),
        'locked_prescriptions': Prescription.query.filter_by(state='LOCKED').count(),
        'dispensed_prescriptions': Prescription.query.filter_by(state='DISPENSED').count()
    }


# Application entry point
if __name__ == '__main__':
    """
    Run the Flask development server.
    Production deployment should use WSGI server (gunicorn, uWSGI, etc.)
    """
    app = create_app()
    
    # Get host and port from environment or use defaults
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', 5000))
    
    print("=" * 60)
    print("MediSure Vault - Blockchain Prescription Management System")
    print("=" * 60)
    print(f"Running on: http://{host}:{port}")
    print("Default Admin Credentials:")
    print("  Username: admin")
    print("  Password: admin123")
    print("=" * 60)
    
    app.run(host=host, port=port, debug=app.config['DEBUG'])
