from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    # Role: 'doctor', 'pharmacist', or 'patient'
    role = db.Column(db.String(20), nullable=False, default='patient')

    def set_password(self, password):
        """Hash and store the password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check a plain password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'
