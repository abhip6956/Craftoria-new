import os
import sqlite3
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-before-deployment")

DATABASE_URL = os.environ.get("DATABASE_URL")
default_db = "/tmp/craftoria.db" if os.environ.get("VERCEL") else "craftoria.db"
DB_PATH = os.environ.get("DATABASE_PATH", default_db)

MANAGER_ID = os.environ.get("MANAGER_ID", "admin")
MANAGER_PASSWORD = os.environ.get("MANAGER_PASSWORD", "Craftoria@123")


class DBWrapper:
    """SQLite aur PostgreSQL dono ko support karta hai taaki Vercel par accounts aur orders reset na hon"""
    def __init__(self):
        self.is_pg = bool(DATABASE_URL and psycopg2)
        if self.is_pg:
            self.conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            self.conn = sqlite3.connect(DB_PATH)
            self.conn.row_factory = sqlite3.Row

    def execute(self, query, params=()):
        if self.is_pg:
            pg_query = query.replace("?", "%s")
            cur = self.conn.cursor()
            if pg_query.strip().upper().startswith("INSERT") and "RETURNING" not in pg_query.upper():
                pg_query = pg_query.rstrip().rstrip(";") + " RETURNING id"
                cur.execute(pg_query, params)
                row = cur.fetchone()
                cur.lastrowid = row["id"] if row else None
                return cur
            cur.execute(pg_query, params)
            return cur
        return self.conn.execute(query, params)

    def executemany(self, query, seq):
        if self.is_pg:
            pg_query = query.replace("?", "%s")
            cur = self.conn.cursor()
            cur.executemany(pg_query, seq)
            return cur
        return self.conn.executemany(query, seq)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def db():
    return DBWrapper()


def clean_image_path(image_path):
    if not image_path:
        return ""
    image_path = image_path.strip()
    if image_path.startswith("http"):
        return image_path
    normalized = image_path.replace("\\", "/")
    if "static/" in normalized:
        normalized = normalized.split("static/", 1)[1]
    return normalized.lstrip("/")


def init_db():
    connection = db()
    id_col = "SERIAL PRIMARY KEY" if connection.is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    connection.execute(f"""
    CREATE TABLE IF NOT EXISTS users (
        id {id_col},
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL
    )
    """)
    connection.execute(f"""
    CREATE TABLE IF NOT EXISTS products (
        id {id_col},
        name TEXT NOT NULL,
        price REAL NOT NULL,
        description TEXT DEFAULT '',
        image TEXT DEFAULT ''
    )
    """)
    connection.execute(f"""
    CREATE TABLE IF NOT EXISTS orders (
        id {id_col},
        user_id INTEGER NOT NULL,
        customer_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        address TEXT NOT NULL,
        total REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'Received',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    connection.execute(f"""
    CREATE TABLE IF NOT EXISTS order_items (
        id {id_col},
        order_id INTEGER NOT NULL,
        product_id INTEGER,
        product_name TEXT NOT NULL,
        price REAL NOT NULL,
        quantity INTEGER NOT NULL
    )
    """)
    row = connection.execute("SELECT COUNT(*) AS cnt FROM products").fetchone()
    count = row["cnt"] if isinstance(row, dict) else row[0]
    if count == 0:
        samples = [
            ("Crochet Ballerina Doll", 500, "A colourful collection of creative art.", "photos/pic1.jpeg"),
            ("Crochet Daisy Flower Pot", 300, "A unique accent for your home.", "photos/pic2.jpeg"),
            ("Mini Crochet Flower Basket", 250, "A special gift for someone special.", "photos/pic3.jpeg"),
            ("Crochet Peacock Feather Hanging", 100, "A thoughtful handmade art piece.", "photos/pic4.jpeg"),
        ]
        connection.executemany(
            "INSERT INTO products (name, price, description, image) VALUES (?, ?, ?, ?)", samples
        )
    connection.commit()
    connection.close()


def customer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def manager_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("manager_logged_in"):
            return redirect(url_for("manager_login"))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def common_context():
    return {"cart_count": sum(session.get("cart", {}).values())}


@app.route("/")
def home():
    connection = db()
    products = connection.execute("SELECT * FROM products ORDER BY id DESC LIMIT 4").fetchall()
    connection.close()
    return render_template("index.html", products=products)


@app.route("/products")
def products():
    connection = db()
    items = connection.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    connection.close()
    return render_template("products.html", products=items)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        if not name or not email or len(password) < 6:
            flash("Enter your name, a valid email and a password of at least 6 characters.")
            return render_template("register.html")
        connection = db()
        try:
            existing = connection.execute(
                "SELECT id FROM users WHERE LOWER(TRIM(email)) = ?", (email,)
            ).fetchone()
            if existing:
                flash("This email is already registered. Please log in.")
                return render_template("register.html")

            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password))
            )
            connection.commit()
            session["user_id"] = cursor.lastrowid
            session["user_name"] = name
            session["cart"] = session.get("cart", {})
            flash("Account created successfully.")
            return redirect(url_for("home"))
        except Exception as e:
            flash(f"Registration error: {e}")
        finally:
            connection.close()
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        connection = db()
        user = connection.execute("SELECT * FROM users WHERE LOWER(TRIM(email)) = ?", (email,)).fetchone()
        connection.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            flash("Welcome back!")
            return redirect(request.args.get("next") or url_for("home"))
        flash("Incorrect email or password.")
    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        new_password = request.form.get("new_password", "").strip()

        if not name or not email or len(new_password) < 6:
            flash("Enter your registered name, email, and a new password (min 6 characters).")
            return render_template("forgot_password.html")

        connection = db()
        user = connection.execute(
            "SELECT * FROM users WHERE LOWER(TRIM(email)) = ? AND LOWER(TRIM(name)) = LOWER(?)",
            (email, name)
        ).fetchone()

        if user:
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(new_password), user["id"])
            )
            connection.commit()
            connection.close()
            flash("Password reset successful! Please log in with your new password.")
            return redirect(url_for("login"))

        connection.close()
        flash("Name and email do not match our records.")
    return render_template("forgot_password.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("user_name", None)
    flash("You have been logged out.")
    return redirect(url_for("home"))


@app.route("/add-to-cart/<int:product_id>", methods=["POST"])
def add_to_cart(product_id):
    connection = db()
    product = connection.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
    connection.close()
    if not product:
        abort(404)
    cart = session.get("cart", {})
    key = str(product_id)
    cart[key] = min(cart.get(key, 0) + 1, 99)
    session["cart"] = cart
    flash("Product added to your cart.")
    return redirect(request.referrer or url_for("products"))


@app.route("/cart")
def cart():
    cart = session.get("cart", {})
    items, total = [], 0
    connection = db()
    for product_id, quantity in cart.items():
        product = connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if product:
            subtotal = product["price"] * quantity
            items.append({"product": product, "quantity": quantity, "subtotal": subtotal})
            total += subtotal
    connection.close()
    return render_template("cart.html", items=items, total=total)


@app.route("/cart/update/<int:product_id>", methods=["POST"])
def update_cart(product_id):
    try:
        quantity = int(request.form.get("quantity", "1"))