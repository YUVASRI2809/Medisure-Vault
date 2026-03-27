"""
Run this once to add missing columns to the existing database.
    python migrate.py
"""
import os
os.environ['FLASK_ENV'] = 'development'

from app import create_app
app = create_app('development')

with app.app_context():
    from database import db
    from sqlalchemy import text

    migrations = [
        ("audit_logs",   "role",       "ALTER TABLE audit_logs ADD COLUMN role VARCHAR(20)"),
        ("audit_logs",   "status",     "ALTER TABLE audit_logs ADD COLUMN status VARCHAR(10) NOT NULL DEFAULT 'SUCCESS'"),
        ("prescriptions","is_flagged", "ALTER TABLE prescriptions ADD COLUMN is_flagged BOOLEAN NOT NULL DEFAULT 0"),
    ]

    with db.engine.connect() as conn:
        for table, col, sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
                print(f"[OK] Added column '{col}' to '{table}'")
            except Exception as e:
                msg = str(e)
                if 'duplicate column' in msg.lower() or 'already exists' in msg.lower():
                    print(f"[SKIP] '{col}' already exists in '{table}'")
                else:
                    print(f"[ERROR] {col}: {msg[:80]}")

    print("\nMigration complete.")
