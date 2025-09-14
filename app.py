from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import sqlite3
from datetime import datetime
import csv
import io

app = Flask(__name__)
app.secret_key = "secretkey123"  # Change in production

# ---------- DB HELPER ----------
def get_db_connection():
    conn = sqlite3.connect("vendors.db")
    conn.row_factory = sqlite3.Row
    return conn

# ---------- SETUP DATABASE ----------
def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            category TEXT NOT NULL,
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
    # Add super admin if not exists
    super_admin = conn.execute("SELECT * FROM admins WHERE username='admin'").fetchone()
    if not super_admin:
        conn.execute("INSERT INTO admins (username, password) VALUES (?, ?)", ("admin", "admin123"))
    conn.commit()
    conn.close()

init_db()

# ---------- PUBLIC ROUTES ----------
@app.route("/")
def home():
    return render_template("landing.html")   # Tailwind landing page

@app.route("/vendor")
def vendor_portal():
    conn = get_db_connection()
    vendors = conn.execute("SELECT * FROM vendors ORDER BY date_registered DESC").fetchall()
    counts = conn.execute("SELECT category, COUNT(*) as total FROM vendors GROUP BY category").fetchall()
    total_count = conn.execute("SELECT COUNT(*) as total FROM vendors").fetchone()["total"]
    conn.close()

    stats = {row["category"]: row["total"] for row in counts}
    stats["total"] = total_count
    return render_template("vendor.html", stats=stats, current_year=datetime.now().year)

@app.route("/register", methods=["POST"])
def register():
    name = request.form["name"]
    email = request.form["email"]
    phone = request.form["phone"]
    category = request.form["category"]

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO vendors (name, email, phone, category, date_registered) VALUES (?, ?, ?, ?, ?)",
        (name, email, phone, category, datetime.now())
    )
    conn.commit()
    conn.close()
    flash("Registration successful!", "success")
    return redirect(url_for("vendor_portal"))

# ---------- ADMIN ROUTES ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        admin = conn.execute(
            "SELECT * FROM admins WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        conn.close()

        if admin:
            session["admin"] = username
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid credentials", "danger")
    return render_template("admin_login.html")

@app.route("/admin/dashboard")
def admin_dashboard():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    vendors = conn.execute("SELECT * FROM vendors ORDER BY date_registered DESC").fetchall()
    counts = conn.execute("SELECT category, COUNT(*) as total FROM vendors GROUP BY category").fetchall()
    admins = conn.execute("SELECT * FROM admins").fetchall()
    conn.close()

    stats = {row["category"]: row["total"] for row in counts}
    stats["total"] = sum(stats.values()) if stats else 0

    return render_template("admin_dashboard.html", vendors=vendors, stats=stats, admins=admins)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("home"))

# ---------- ADMIN MANAGEMENT ----------
@app.route("/admin/add", methods=["POST"])
def add_admin():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    if session["admin"] != "admin":
        flash("Only super admin can add new admins", "danger")
        return redirect(url_for("admin_dashboard"))

    username = request.form["username"]
    password = request.form["password"]

    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO admins (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
        flash("Admin added successfully!", "success")
    except sqlite3.IntegrityError:
        flash("Admin username already exists!", "danger")
    conn.close()
    return redirect(url_for("admin_dashboard"))

# ---------- VENDOR MANAGEMENT ----------
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

@app.route("/admin/add_vendor", methods=["POST"])
def add_vendor():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    name = request.form["name"]
    email = request.form["email"]
    phone = request.form["phone"]
    category = request.form["category"]

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO vendors (name, email, phone, category, date_registered) VALUES (?, ?, ?, ?, ?)",
        (name, email, phone, category, datetime.now())
    )
    conn.commit()
    conn.close()
    flash("Vendor added successfully by admin!", "success")
    return redirect(url_for("admin_dashboard"))

# ---------- DOWNLOAD VENDORS ----------
@app.route("/admin/download_vendors")
def download_vendors():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    vendors = conn.execute("SELECT * FROM vendors").fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Email", "Phone", "Category", "Date Registered"])
    for v in vendors:
        writer.writerow([v["id"], v["name"], v["email"], v["phone"], v["category"], v["date_registered"]])
    output.seek(0)

    return send_file(io.BytesIO(output.getvalue().encode()), mimetype="text/csv", as_attachment=True,
                     download_name="vendors.csv")

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
    writer.writerow(["ID", "Name", "Email", "Phone", "Category", "Date Registered"])
    writer.writerow([v["id"], v["name"], v["email"], v["phone"], v["category"], v["date_registered"]])
    output.seek(0)

    return send_file(io.BytesIO(output.getvalue().encode()), mimetype="text/csv", as_attachment=True,
                     download_name=f"{v['name']}.csv")

# ---------- CONTACT FORM ----------
@app.route("/contact", methods=["POST"])
def contact():
    name = request.form.get("contact_name")
    email = request.form.get("contact_email")
    message = request.form.get("contact_message")
    flash("Your message has been sent successfully!", "success")
    return redirect(url_for("home"))

# ---------- MAIN ----------
if __name__ == "__main__":
    app.run(debug=True)
