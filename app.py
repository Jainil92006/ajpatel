from flask import Flask, request, redirect, session, send_from_directory, jsonify, send_file, Response,render_template
import os
import sqlite3
from werkzeug.utils import secure_filename
import pandas as pd
import io

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

DB_FILE = "expenses.db"

# Load HTML from same directory as app.py
def load_html(filename):
    try:
        full_path = os.path.join(os.path.dirname(__file__), filename)
        with open(full_path, 'r', encoding='utf-8') as f:
            return Response(f.read(), mimetype='text/html')
    except FileNotFoundError:
        return "HTML file not found", 404

# Initialize DBs
def init_db():
    with sqlite3.connect("database.db") as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT, filename TEXT, upload_date TEXT
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE, password TEXT, email TEXT UNIQUE
            )""")
        if not conn.execute("SELECT * FROM users WHERE username='admin'").fetchone():
            conn.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
                         ('admin', 'admin', 'admin@example.com'))

    with sqlite3.connect(DB_FILE) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT NOT NULL,
                date TEXT NOT NULL
            )
        ''')

init_db()

@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect('/dashboard')

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect("database.db") as conn:
            user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password)).fetchone()
            if user:
                session['user'] = username
                return redirect('/dashboard')

    return load_html('index.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/')
    return load_html('dashboard.html')



@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/confirm_password', methods=['POST'])
def confirm_password():
    if 'user' not in session:
        return jsonify(ok=False), 401
    data = request.get_json()
    password = data.get('password', '')
    with sqlite3.connect("database.db") as conn:
        user = conn.execute("SELECT password FROM users WHERE username = ?", (session['user'],)).fetchone()
        if user and user[0] == password:
            return jsonify(ok=True)
    return jsonify(ok=False)

@app.route('/upload', methods=['POST'])
def upload():
    if 'user' not in session:
        return jsonify(success=False, error='Unauthorized'), 401
    files = request.files.getlist('files[]')
    name = request.form['name']
    date = request.form['date']
    if not files:
        return jsonify(success=False, error='No files selected')
    with sqlite3.connect("database.db") as conn:
        for f in files:
            if f.filename:
                filename = secure_filename(f.filename)
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                conn.execute("INSERT INTO documents (name, filename, upload_date) VALUES (?, ?, ?)",
                             (name, filename, date))
    return jsonify(success=True)

@app.route('/fetch_by_date', methods=['POST'])
def fetch_by_date():
    if 'user' not in session:
        return jsonify([]), 401
    date = request.form.get('date', '')
    if not date:
        return jsonify([])
    with sqlite3.connect("database.db") as conn:
        rows = conn.execute("SELECT * FROM documents WHERE upload_date=?", (date,)).fetchall()
    return jsonify(rows)

@app.route('/delete/<int:id>', methods=['DELETE'])
def delete(id):
    if 'user' not in session:
        return jsonify(success=False), 401
    with sqlite3.connect("database.db") as conn:
        fn = conn.execute("SELECT filename FROM documents WHERE id=?", (id,)).fetchone()
        if fn:
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], fn[0]))
            except:
                pass
        conn.execute("DELETE FROM documents WHERE id=?", (id,))
    return jsonify(success=True)

@app.route('/update/<int:id>', methods=['POST'])
def update(id):
    if 'user' not in session:
        return jsonify(success=False), 401
    new_name = request.form.get('new_name', '')
    with sqlite3.connect("database.db") as conn:
        conn.execute("UPDATE documents SET name=? WHERE id=?", (new_name, id))
    return jsonify(success=True)

@app.route('/uploads/<filename>')
def uploads(filename):
    if 'user' not in session:
        return redirect('/')
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/forget_password', methods=['GET', 'POST'])
def forget_password():
    msg = ''
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['new_password']
        with sqlite3.connect("database.db") as conn:
            user = conn.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
            if user:
                conn.execute("UPDATE users SET password=? WHERE username=?", (p, u))
                msg = 'Password updated.'
            else:
                msg = 'Username not found.'
        return msg
    return load_html('forget_password.html')

@app.route('/add_expense', methods=['POST'])
def add_expense():
    name = request.form['name']
    amount = float(request.form['amount'])
    description = request.form['description']
    date = request.form['date']
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("INSERT INTO expenses (name, amount, description, date) VALUES (?, ?, ?, ?)",
                     (name, amount, description, date))
    return jsonify(success=True)

@app.route('/get_expenses')
def get_expenses():
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("SELECT id, name, amount, description, date FROM expenses ORDER BY name, date DESC").fetchall()
    grouped = {}
    for row in rows:
        id_, name, amount, description, date = row
        grouped.setdefault(name, []).append({
            "id": id_, "amount": amount, "description": description, "date": date
        })
    return jsonify(grouped)

@app.route('/delete_expense/<int:id>', methods=['DELETE'])
def delete_expense(id):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DELETE FROM expenses WHERE id = ?", (id,))
    return jsonify(success=True)

@app.route('/update_expense/<int:id>', methods=['POST'])
def update_expense(id):
    amount = float(request.form['amount'])
    description = request.form['description']
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("UPDATE expenses SET amount = ?, description = ? WHERE id = ?", (amount, description, id))
    return jsonify(success=True)

@app.route('/export_excel/<string:name>')
def export_excel(name):
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query("""
            SELECT amount, description, date 
            FROM expenses 
            WHERE name = ? 
            ORDER BY date DESC
        """, conn, params=(name,))
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name=name)
    output.seek(0)
    return send_file(output, download_name=f"{name}_Expenses.xlsx", as_attachment=True)

@app.route('/img/<path:filename>')
def serve_image(filename):
    return send_from_directory('.', filename)  # or use 'uploads' if that's where images are


if __name__ == '__main__':
    app.run(debug=True)

