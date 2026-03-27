"""
Database initialisation script — run once per environment.

    python init_db.py

What it does:
  1. Creates all tables (safe to re-run — skips existing ones)
  2. Creates the default admin user if none exists
  3. Creates the blockchain genesis block if the chain is empty
"""

import os
from app import create_app

env = os.environ.get('FLASK_ENV', 'production')
app = create_app(env)

with app.app_context():
    from database import db
    from models import User, Block

    # 1. Create tables
    db.create_all()
    print("[OK] Tables ready")

    # 2. Admin user
    if not User.query.filter_by(username='admin').first():
        from auth.utils import hash_password
        password = os.environ.get('ADMIN_PASSWORD', 'ChangeMe123!')
        admin = User(
            username='admin',
            password_hash=hash_password(password),
            email=os.environ.get('ADMIN_EMAIL', 'admin@medisure.local'),
            role='ADMIN',
            full_name='System Administrator'
        )
        db.session.add(admin)
        db.session.commit()
        print(f"[OK] Admin user created  (username: admin  password: {password})")
        print("  ** Change this password immediately after first login! **")
    else:
        print("[OK] Admin user already exists")

    # 3. Genesis block
    if not Block.query.filter_by(index=0).first():
        from blockchain.ledger import Blockchain
        Blockchain()
        print("[OK] Genesis block created")
    else:
        print("[OK] Blockchain already initialised")

print("\nDatabase ready.")
