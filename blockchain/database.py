"""
MediSure Vault - Database Instance Module

This module creates the SQLAlchemy instance to avoid circular imports.
"""

from flask_sqlalchemy import SQLAlchemy

# Create single SQLAlchemy instance
db = SQLAlchemy()
