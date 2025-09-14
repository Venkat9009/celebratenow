# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import sqlite3
from datetime import datetime
import csv
import io
import os
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "vendors.db")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "replace-this-secret-in-production")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            date_registered TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    # Add super admin if not exists (password hashed)
    cur = conn.execute("SELECT * FROM admins WHERE username='admin'").fetchone()
    if not cur:
        hashed = generate_password_hash("admin123")
        conn.execute("INSERT INTO admins (username, password) VALUES (?, ?)", ("admin", hashed))
    conn.commit()
    conn.close()

# initialize DB on startup
init_db()

# ---------- PUBLIC ROUTES ----------
@app.route("/")
def home():
    # landing page
    return render_template("landing.html")

@app.route("/vendor")
def vendor_portal():
    # show vendor portal with stats
    conn = get_db_connection()
    counts = conn.execute("SELECT category, COUNT(*) as total FROM vendors GROUP BY category").fetchall()
    total_count = conn.execute("SELECT COUNT(*) as total FROM vendors").fetchone()['total'] if conn is not None else 0
    conn.close()

    stats = {row["category"]: row["total"] for row in counts} if counts else {}
    stats["total"] = total_count
    return render_template("vendor.html", stats=stats, current_year=datetime.utcnow().year)

@app.route("/register", methods=["POST"])
def register():
    name = request.form.get("name")
    email = request.form.get("email")
    phone = request.form.get("phone")
    category = request.form.get("category")
    description = request.form.get("description", "")

    if not (name and email and phone and category):
        flash("Please fill all required fields", "danger")
        return redirect(url_for("vendor_portal"))

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO vendors (name, email, phone, category, description, date_registered) VALUES (?, ?, ?, ?, ?, ?)",
        (name, email, phone, category, description, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    flash("Registration successful!", "success")
    return redirect(url_for("vendor_portal"))

# contact form
@app.route("/contact", methods=["POST"])
def contact():
    contact_name = request.form.get("contact_name")
    contact_email = request.form.get("contact_email")
    contact_message = request.form.get("contact_message")
    # For now, just flash success. You can store or send email here.
    flash("Your message has been sent successfully! We'll get back to you soon.", "success")
    return redirect(url_for("vendor_portal"))

# ---------- ADMIN AUTH ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        conn = get_db_connection()
        admin = conn.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
        conn.close()
        # Note: fallback allows existing plaintext DB entries to still work once so you can migrate.
        if admin and (check_password_hash(admin["password"], password) or admin["password"] == password):
            session["admin"] = username
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid credentials", "danger")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("home"))

# ---------- ADMIN DASHBOARD ----------
def ensure_admin():
    if "admin" not in session:
        flash("Please log in as admin", "warning")
        return False
    return True

@app.route("/admin/dashboard")
def admin_dashboard():
    if not ensure_admin():
        return redirect(url_for("admin_login"))
    conn = get_db_connection()
    vendors = conn.execute("SELECT * FROM vendors ORDER BY date_registered DESC").fetchall()
    counts = conn.execute("SELECT category, COUNT(*) as total FROM vendors GROUP BY category").fetchall()
    admins = conn.execute("SELECT * FROM admins").fetchall()
    conn.close()

    stats = {row["category"]: row["total"] for row in counts} if counts else {}
    stats["total"] = sum(stats.values()) if stats else 0
    return render_template("admin_dashboard.html", vendors=vendors, stats=stats, admins=admins)

# ---------- ADMIN MANAGEMENT ----------
@app.route("/admin/add", methods=["POST"])
def add_admin():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    if session.get("admin") != "admin":
        flash("Only super admin can add new admins", "danger")
        return redirect(url_for("admin_dashboard"))

    username = request.form.get("username")
    password = request.form.get("password")
    if not (username and password):
        flash("Please provide username and password", "danger")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    count = conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
    if count >= 5:
        flash("Maximum 5 admins allowed!", "danger")
    else:
        try:
            conn.execute("INSERT INTO admins (username, password) VALUES (?, ?)",
                         (username, generate_password_hash(password)))
            conn.commit()
            flash("Admin added successfully!", "success")
        except sqlite3.IntegrityError:
            flash("Admin username already exists!", "danger")
    conn.close()
    return redirect(url_for("admin_dashboard"))

# ---------- VENDOR MANAGEMENT ----------
@app.route("/admin/add_vendor", methods=["POST"])
def add_vendor():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    name = request.form.get("name")
    email = request.form.get("email")
    phone = request.form.get("phone")
    category = request.form.get("category")
    if not (name and email and phone and category):
        flash("Missing required fields", "danger")
        return redirect(url_for("admin_dashboard"))
    conn = get_db_connection()
    conn.execute("INSERT INTO vendors (name, email, phone, category, date_registered) VALUES (?, ?, ?, ?, ?)",
                 (name, email, phone, category, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    flash("Vendor added successfully by admin!", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/delete_vendor/<int:vendor_id>", methods=["POST"])
def delete_vendor(vendor_id):
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    conn = get_db_connection()
    conn.execute("DELETE FROM vendors WHERE id=?", (vendor_id,))
    conn.commit()
    conn.close()
    flash("Vendor removed successfully!", "success")
    return redirect(url_for("admin_dashboard"))

# ---------- DOWNLOAD / EXPORT ----------
@app.route("/admin/download_vendors")
def download_vendors():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    conn = get_db_connection()
    vendors = conn.execute("SELECT * FROM vendors").fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Email", "Phone", "Category", "Description", "Date Registered"])
    for v in vendors:
        writer.writerow([v["id"], v["name"], v["email"], v["phone"], v["category"], v["description"], v["date_registered"]])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()), mimetype="text/csv", as_attachment=True, download_name="vendors.csv")

@app.route("/admin/download_vendor/<int:vendor_id>")
def download_vendor(vendor_id):
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    conn = get_db_connection()
    v = conn.execute("SELECT * FROM vendors WHERE id=?", (vendor_id,)).fetchone()
    conn.close()
    if not v:
        flash("Vendor not found!", "danger")
        return redirect(url_for("admin_dashboard"))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Email", "Phone", "Category", "Description", "Date Registered"])
    writer.writerow([v["id"], v["name"], v["email"], v["phone"], v["category"], v["description"], v["date_registered"]])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()), mimetype="text/csv", as_attachment=True, download_name=f"{v['name']}.csv")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
