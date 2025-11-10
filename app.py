import sqlite3
import os
from datetime import datetime
from flask import Flask, request, jsonify, session, g, render_template, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import requests
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- CONFIG FOR FILE UPLOADS ---
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Create the folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Define categories
CATEGORIES = ["Feeding", "Transportation", "Academic", "Hostel", "Social", "Miscellaneous"]

# --- Database Connection Management ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect("database.db")
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                fullname TEXT NOT NULL,
                matric TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                profile_picture TEXT
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                date TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS incomes (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                amount REAL NOT NULL,
                description TEXT,
                date TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, category)
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                name TEXT NOT NULL,
                target_amount REAL NOT NULL,
                current_amount REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
        ''')
        db.commit()

# --- Auth Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.accept_mimetypes.best == 'application/json':
                return jsonify({'status': 'error', 'message': 'User not logged in'}), 401
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Function for Default Picture ---
def get_user_picture_path(user_id):
    conn = get_db()
    cursor = conn.cursor()
    user = cursor.execute("SELECT profile_picture FROM users WHERE id = ?", (user_id,)).fetchone()
    if user and user['profile_picture']:
        return user['profile_picture']
    return 'uploads/default_avatar.png' 

# --- Routes ---
@app.route("/")
def index():
    if 'user_id' in session:
        conn = get_db()
        cursor = conn.cursor()
        user_id = session.get('user_id')
        user = cursor.execute("SELECT fullname, matric, email FROM users WHERE id = ?", (user_id,)).fetchone()
        
        # Handle case where user might be deleted but session exists
        if not user:
            session.pop('user_id', None)
            return redirect(url_for('index'))
            
        user_name = user['fullname']
        user_matric = user['matric']
        user_email = user['email']
        user_picture = get_user_picture_path(user_id)
        
        return render_template(
            "dashboard.html", 
            user_name=user_name, 
            user_matric=user_matric, 
            categories=CATEGORIES,
            user_email=user_email,
            user_picture=user_picture
        )
    return render_template("index.html")

@app.route("/dashboard")
def dashboard_redirect():
    return redirect(url_for('index'))

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    conn = get_db()
    cursor = conn.cursor()
    user = cursor.execute("SELECT id, password FROM users WHERE email = ?", (email,)).fetchone()
    if user and check_password_hash(user['password'], password):
        session['user_id'] = user['id']
        return jsonify({'status': 'success', 'message': 'Login successful!'})
    return jsonify({'status': 'error', 'message': 'Invalid email or password.'}), 401

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    fullname = data.get('fullname')
    matric = data.get('matric')
    email = data.get('email')
    password = data.get('password')
    if not all([fullname, matric, email, password]):
        return jsonify({'status': 'error', 'message': 'All fields are required.'}), 400
    if len(password) < 6:
        return jsonify({'status': 'error', 'message': 'Password must be at least 6 characters.'}), 400
    hashed_password = generate_password_hash(password)
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (fullname, matric, email, password) VALUES (?, ?, ?, ?)",
                         (fullname, matric, email, hashed_password))
        conn.commit()
        return jsonify({'status': 'success', 'message': 'Registration successful! You can now log in.'})
    except sqlite3.IntegrityError:
        return jsonify({'status': 'error', 'message': 'Matric number or email already exists.'}), 409
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route("/logout")
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

@app.route("/add_expense", methods=["POST"])
@login_required
def add_expense():
    user_id = session.get('user_id')
    data = request.get_json()
    amount = data.get('amount')
    category = data.get('category')
    description = data.get('description', '')
    date_str = data.get('date')

    # --- Standard Validation (no change) ---
    if not all([amount, category, date_str]):
        return jsonify({'status': 'error', 'message': 'Amount, category, and date are required.'}), 400
    try:
        amount = float(amount)
        if amount <= 0:
            return jsonify({'status': 'error', 'message': 'Amount must be a positive number.'}), 400
        datetime.strptime(date_str, '%Y-%m-%d')
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': 'Invalid amount or date format.'}), 400

    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # --- CHECK 1: TOTAL BALANCE (No change) ---
        total_income = cursor.execute("SELECT SUM(amount) FROM incomes WHERE user_id = ?", (user_id,)).fetchone()[0] or 0
        total_expenses = cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ?", (user_id,)).fetchone()[0] or 0
        total_goals_funded = cursor.execute("SELECT SUM(current_amount) FROM goals WHERE user_id = ?", (user_id,)).fetchone()[0] or 0
        total_balance = total_income - total_expenses - total_goals_funded

        if amount > total_balance:
            return jsonify({
                'status': 'error',
                'message': f"Insufficient Funds! Your total balance is only ₦{total_balance:,.2f}."
            }), 400
        
        # --- ### NEW CHECK 2: BUDGET MUST EXIST ### ---
        
        # 1. Find the budget for this category
        cursor.execute("SELECT amount FROM budgets WHERE user_id = ? AND category = ?", (user_id, category))
        budget_row = cursor.fetchone()
        
        # 2. Check if a budget has been set AT ALL
        if budget_row is None:
            return jsonify({
                'status': 'error',
                'message': f'You have not set a budget for "{category}". Please set a budget first.'
            }), 400
            
        # --- ### CHECK 3: BUDGET NOT EXCEEDED (Original Check) ### ---
        
        budget_amount = budget_row['amount']

        # 3. Find what they have already spent in this category
        cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ? AND category = ?", (user_id, category))
        total_spending = cursor.fetchone()[0] or 0
        
        # 4. Check the budget rule
        if (total_spending + amount) > budget_amount:
            remaining_budget = budget_amount - total_spending
            if remaining_budget < 0: remaining_budget = 0.0
            
            return jsonify({
                'status': 'error', 
                'message': f'Budget Exceeded! You only have ₦{remaining_budget:,.2f} left in your "{category}" budget.'
            }), 400

        # --- END OF CHECKS ---
        
        # If ALL checks pass, add the expense
        cursor.execute("INSERT INTO expenses (user_id, amount, category, description, date) VALUES (?, ?, ?, ?, ?)",
                         (user_id, amount, category, description, date_str))
        conn.commit()
        return jsonify({'status': 'success', 'message': "Expense added successfully!"})

    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
    
    
@app.route("/set_budget", methods=["POST"])
@login_required
def set_budget():
    user_id = session.get('user_id')
    data = request.get_json()
    category = data.get('category')
    amount = data.get('amount')

    # --- Standard Validation (no change) ---
    if not all([category, amount]):
        return jsonify({'status': 'error', 'message': 'Category and amount are required.'}), 400
    if category not in CATEGORIES:
        return jsonify({'status': 'error', 'message': 'Invalid category.'}), 400
    try:
        amount = float(amount)
        if amount < 0: # Allow 0 budget
            return jsonify({'status': 'error', 'message': 'Amount must be a positive number.'}), 400
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': 'Invalid amount format.'}), 400

    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # --- ### NEW BUDGET BALANCE CHECK ### ---
        
        # 1. Get user's current total available balance
        total_income = cursor.execute("SELECT SUM(amount) FROM incomes WHERE user_id = ?", (user_id,)).fetchone()[0] or 0
        total_expenses = cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ?", (user_id,)).fetchone()[0] or 0
        total_goals_funded = cursor.execute("SELECT SUM(current_amount) FROM goals WHERE user_id = ?", (user_id,)).fetchone()[0] or 0
        total_balance = total_income - total_expenses - total_goals_funded
        
        # 2. Get the sum of all *other* budgets (excluding the one we're about to set)
        cursor.execute("SELECT SUM(amount) FROM budgets WHERE user_id = ? AND category != ?", (user_id, category))
        other_budgets_total = cursor.fetchone()[0] or 0
        
        # 3. Check the rule
        new_total_budgeted_amount = other_budgets_total + amount
        
        if new_total_budgeted_amount > total_balance:
            # User doesn't have enough balance to cover this new total budget
            available_to_budget = total_balance - other_budgets_total
            if available_to_budget < 0: available_to_budget = 0
            
            return jsonify({
                'status': 'error',
                'message': f"Insufficient Balance! You only have ₦{available_to_budget:,.2f} available to budget."
            }), 400

        # --- ### END OF NEW CHECK ### ---
        
        # If the check passes, set the budget
        cursor.execute("INSERT OR REPLACE INTO budgets (user_id, category, amount) VALUES (?, ?, ?)",
                         (user_id, category, amount))
        conn.commit()
        return jsonify({'status': 'success', 'message': 'Budget set successfully!'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@app.route("/get_dashboard_data")
@login_required
def get_dashboard_data():
    user_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor()
    try:
        total_income = cursor.execute("SELECT SUM(amount) FROM incomes WHERE user_id = ?", (user_id,)).fetchone()[0] or 0
        total_expenses = cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ?", (user_id,)).fetchone()[0] or 0
        total_goals_funded = cursor.execute("SELECT SUM(current_amount) FROM goals WHERE user_id = ?", (user_id,)).fetchone()[0] or 0
        total_balance = total_income - total_expenses - total_goals_funded
        spending_by_category_data = cursor.execute("SELECT category, SUM(amount) FROM expenses WHERE user_id = ? GROUP BY category", (user_id,)).fetchall()
        spending_by_category = dict(spending_by_category_data)
        budgets_data = cursor.execute("SELECT category, amount FROM budgets WHERE user_id = ?", (user_id,)).fetchall()
        budgets = {row['category']: row['amount'] for row in budgets_data}
        return jsonify({
            "status": "success",
            "total_balance": total_balance,
            "total_income": total_income,
            "total_expenses": total_expenses,
            "spending_by_category": spending_by_category,
            "budgets": budgets
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route("/get_all_transactions")
@login_required
def get_all_transactions():
    user_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor()
    try:
        expenses = cursor.execute("SELECT 'expense' as type, amount, category, description, date FROM expenses WHERE user_id = ?", (user_id,)).fetchall()
        incomes = cursor.execute("SELECT 'income' as type, amount, NULL as category, description, date FROM incomes WHERE user_id = ?", (user_id,)).fetchall()
        all_transactions = expenses + incomes
        all_transactions.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'), reverse=True)
        transactions_list = []
        for t in all_transactions:
            transactions_list.append({k: t[k] for k in t.keys()})
        return jsonify({'status': 'success', 'transactions': transactions_list})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route("/reset_data", methods=["POST"])
@login_required
def reset_data():
    user_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Delete transactions
        cursor.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM incomes WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM budgets WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM goals WHERE user_id = ?", (user_id,))
        
        # Don't delete user info, just transactions
        # cursor.execute("UPDATE users SET profile_picture = NULL WHERE user_id = ?", (user_id,))
        
        conn.commit()
        return jsonify({'status': 'success', 'message': 'All financial data has been reset.'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': 'An error occurred while resetting data.'}), 500

# --- Goal Routes (No Change) ---
@app.route("/add_goal", methods=["POST"])
@login_required
def add_goal():
    user_id = session.get('user_id')
    data = request.get_json()
    name = data.get('name')
    target_amount = data.get('target_amount')
    if not all([name, target_amount]):
        return jsonify({'status': 'error', 'message': 'Goal name and target amount are required.'}), 400
    try:
        target_amount = float(target_amount)
        if target_amount <= 0:
            return jsonify({'status': 'error', 'message': 'Target amount must be a positive number.'}), 400
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': 'Invalid target amount format.'}), 400
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO goals (user_id, name, target_amount, current_amount) VALUES (?, ?, ?, 0)",
                         (user_id, name, target_amount))
        conn.commit()
        return jsonify({'status': 'success', 'message': 'Financial goal added successfully!'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route("/get_goals")
@login_required
def get_goals():
    user_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor()
    try:
        goals_data = cursor.execute("SELECT id, name, target_amount, current_amount FROM goals WHERE user_id = ?", (user_id,)).fetchall()
        goals_list = [ {k: row[k] for k in row.keys()} for row in goals_data]
        return jsonify({'status': 'success', 'goals': goals_list})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route("/add_to_goal", methods=["POST"])
@login_required
def add_to_goal():
    user_id = session.get('user_id')
    data = request.get_json()
    goal_id = data.get('goal_id')
    amount = data.get('amount')
    if not all([goal_id, amount]):
        return jsonify({'status': 'error', 'message': 'Goal ID and amount are required.'}), 400
    try:
        amount = float(amount)
        if amount <= 0:
            return jsonify({'status': 'error', 'message': 'Amount must be a positive number.'}), 400
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': 'Invalid amount format.'}), 400
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT current_amount, target_amount FROM goals WHERE id = ? AND user_id = ?", (goal_id, user_id))
        goal = cursor.fetchone()
        if not goal:
            return jsonify({'status': 'error', 'message': 'Goal not found.'}), 404
        current_amount, target_amount = goal['current_amount'], goal['target_amount']
        new_amount = current_amount + amount
        if new_amount > target_amount:
            return jsonify({'status': 'error', 'message': f'Cannot fund more than the goal target. You can add ₦{(target_amount - current_amount):.2f}.'}), 400
        total_income = cursor.execute("SELECT SUM(amount) FROM incomes WHERE user_id = ?", (user_id,)).fetchone()[0] or 0
        total_expenses = cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ?", (user_id,)).fetchone()[0] or 0
        total_goals_funded = cursor.execute("SELECT SUM(current_amount) FROM goals WHERE user_id = ?", (user_id,)).fetchone()[0] or 0
        current_balance = total_income - total_expenses - total_goals_funded
        if amount > current_balance:
            return jsonify({'status': 'error', 'message': 'Insufficient balance to fund this goal.'}), 400
        cursor.execute("UPDATE goals SET current_amount = ? WHERE id = ?", (new_amount, goal_id))
        conn.commit()
        return jsonify({'status': 'success', 'message': 'Funds added to goal successfully!'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# --- Paystack Route (No Change) ---
@app.route('/payment/callback')
@login_required
def payment_callback():
    reference = request.args.get('reference')
    if not reference:
        flash('Payment verification failed. No reference provided.', 'danger')
        return redirect(url_for('index'))
    url = f'https://api.paystack.co/transaction/verify/{reference}'
    headers = {
        'Authorization': 'Bearer sk_test_1b9bdd452cff713f93e3856f2dd9a5e87c902479' # Your Test Key
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data['status'] == True and data['data']['status'] == 'success':
            amount_kobo = data['data']['amount']
            amount_naira = amount_kobo / 100
            conn = get_db()
            cursor = conn.cursor()
            user_id = session.get('user_id')
            date_str = datetime.now().strftime('%Y-%m-%d')
            description = f"Account funding (Ref: {reference})"
            cursor.execute("INSERT INTO incomes (user_id, amount, description, date) VALUES (?, ?, ?, ?)",
                             (user_id, amount_naira, description, date_str))
            conn.commit()
            flash('Payment of NGN {amount_naira:,.2f} was successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Payment verification failed. Please contact support.', 'danger')
            return redirect(url_for('index'))
    except requests.exceptions.RequestException as e:
        print(f"Error verifying payment: {e}")
        flash('An error occurred while verifying your payment. Please try again.', 'danger')
        return redirect(url_for('index'))

#
# --- ### NEW SETTINGS ROUTES ### ---
#
@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    user_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        # --- Handle Profile Info & Picture Update ---
        fullname = request.form.get('fullname')
        matric = request.form.get('matric')
        
        # Update text fields
        cursor.execute("UPDATE users SET fullname = ?, matric = ? WHERE id = ?", (fullname, matric, user_id))
        conn.commit()
        
        # Check for file
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"user_{user_id}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)
                
                db_path = os.path.join('uploads', unique_filename).replace("\\", "/")
                
                cursor.execute("UPDATE users SET profile_picture = ? WHERE id = ?", (db_path, user_id))
                conn.commit()

        flash('Profile updated successfully!', 'success')
        return redirect(url_for('settings'))

    # --- GET Request ---
    user = cursor.execute("SELECT fullname, matric, email FROM users WHERE id = ?", (user_id,)).fetchone()
    user_picture = get_user_picture_path(user_id)
    
    return render_template('settings.html', user=user, user_picture=user_picture)

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    user_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor()

    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    user = cursor.execute("SELECT password FROM users WHERE id = ?", (user_id,)).fetchone()
    
    # 1. Check if current password is correct
    if not check_password_hash(user['password'], current_password):
        flash('Incorrect current password.', 'danger')
        return redirect(url_for('settings'))
    
    # 2. Check if new passwords match
    if new_password != confirm_password:
        flash('New passwords do not match.', 'danger')
        return redirect(url_for('settings'))
        
    # 3. Check for password length
    if len(new_password) < 6:
        flash('Password must be at least 6 characters.', 'danger')
        return redirect(url_for('settings'))

    # All checks passed. Update the password.
    new_hashed_password = generate_password_hash(new_password)
    cursor.execute("UPDATE users SET password = ? WHERE id = ?", (new_hashed_password, user_id))
    conn.commit()

    flash('Password changed successfully!', 'success')
    return redirect(url_for('settings'))
# --- ### END OF NEW SETTINGS ROUTES ### ---


if __name__ == "__main__":
    init_db()
    app.run(debug=True)