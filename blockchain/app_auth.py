from flask import Flask, render_template
from flask_login import LoginManager, login_required
from models_auth import db, User
from routes.auth import auth_bp

app = Flask(__name__)

# --- Config ---
app.config['SECRET_KEY'] = 'change-this-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///medisure.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Init extensions ---
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'  # Redirect here if not logged in

@login_manager.user_loader
def load_user(user_id):
    """Tell Flask-Login how to load a user from the DB."""
    return User.query.get(int(user_id))

# --- Register blueprint ---
app.register_blueprint(auth_bp)

# --- Role-based dashboard routes ---
@app.route('/doctor/dashboard')
@login_required
def doctor_dashboard():
    return render_template('doctor_dashboard.html')

@app.route('/pharmacist/dashboard')
@login_required
def pharmacist_dashboard():
    return render_template('pharmacist_dashboard.html')

@app.route('/patient/dashboard')
@login_required
def patient_dashboard():
    return render_template('patient_dashboard.html')

# --- Create tables and run ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Creates tables if they don't exist
        print("Database ready.")
    app.run(debug=True)
