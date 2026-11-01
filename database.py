"""All SQLite operations for the AITU TechShare teaching prototype."""
from contextlib import closing
from datetime import date
from pathlib import Path
import sqlite3

DATABASE_FILE = Path(__file__).resolve().parent / "database" / "techshare.db"
CATEGORIES = ("Study", "Electronics", "Accessories", "Photography", "Audio", "Tools")


def connect():
    """Open the same database file for every page and form."""
    connection = sqlite3.connect(DATABASE_FILE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    """Create tables if needed; upgrade the old Assignment 3 database without erasing data."""
    DATABASE_FILE.parent.mkdir(exist_ok=True)
    with closing(connect()) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS Users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS Items (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                price_per_day REAL NOT NULL CHECK (price_per_day >= 0),
                status TEXT NOT NULL DEFAULT 'Available',
                FOREIGN KEY (owner_id) REFERENCES Users(user_id)
            );
            CREATE TABLE IF NOT EXISTS RentalRequests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                borrower_id INTEGER NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                FOREIGN KEY (item_id) REFERENCES Items(item_id),
                FOREIGN KEY (borrower_id) REFERENCES Users(user_id)
            );
        """)
        # These two new fields also work with the existing Assignment 3 database.
        fields = {field[1] for field in conn.execute("PRAGMA table_info(Items)")}
        if "listing_type" not in fields:
            conn.execute("ALTER TABLE Items ADD COLUMN listing_type TEXT NOT NULL DEFAULT 'Rent'")
        fields = {field[1] for field in conn.execute("PRAGMA table_info(RentalRequests)")}
        if "request_kind" not in fields:
            conn.execute("ALTER TABLE RentalRequests ADD COLUMN request_kind TEXT NOT NULL DEFAULT 'Rent'")
        if "message" not in fields:
            conn.execute("ALTER TABLE RentalRequests ADD COLUMN message TEXT NOT NULL DEFAULT ''")
        conn.commit()


def find_user(email):
    with closing(connect()) as conn:
        return conn.execute("SELECT * FROM Users WHERE email = ?", (email,)).fetchone()


def create_user(first, last, email, password_hash):
    """Create a student account; return False when the email already exists."""
    with closing(connect()) as conn:
        try:
            conn.execute("INSERT INTO Users (email, password_hash, first_name, last_name) VALUES (?, ?, ?, ?)",
                         (email, password_hash, first, last))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def get_user(user_id):
    with closing(connect()) as conn:
        return conn.execute("SELECT user_id, first_name, last_name, email FROM Users WHERE user_id = ?", (user_id,)).fetchone()


def summary():
    with closing(connect()) as conn:
        return {
            "items": conn.execute("SELECT COUNT(*) FROM Items").fetchone()[0],
            "available": conn.execute("SELECT COUNT(*) FROM Items WHERE status = 'Available'").fetchone()[0],
            "users": conn.execute("SELECT COUNT(*) FROM Users").fetchone()[0],
            "requests": conn.execute("SELECT COUNT(*) FROM RentalRequests").fetchone()[0],
        }


def search_items(query="", listing_type=""):
    """Parameterized SQL protects the catalog search from SQL injection."""
    sql = """SELECT i.*, u.first_name, u.last_name FROM Items i
             JOIN Users u ON u.user_id = i.owner_id WHERE 1=1"""
    values = []
    if query:
        sql += " AND (i.title LIKE ? OR i.description LIKE ? OR i.category LIKE ?)"
        values += [f"%{query}%"] * 3
    if listing_type in ("Rent", "Exchange", "Both"):
        sql += " AND i.listing_type = ?"
        values.append(listing_type)
    sql += " ORDER BY i.item_id DESC LIMIT 36"
    with closing(connect()) as conn:
        return conn.execute(sql, values).fetchall()


def add_item(user_id, title, category, description, price, listing_type):
    """INSERT is the write operation that students can demonstrate live."""
    with closing(connect()) as conn:
        cursor = conn.execute("""
            INSERT INTO Items (owner_id, title, category, description, price_per_day, status, listing_type)
            VALUES (?, ?, ?, ?, ?, 'Available', ?)
        """, (user_id, title, category, description, price, listing_type))
        conn.commit()
        return cursor.lastrowid


def create_request(borrower_id, item_id, start_date, end_date, message, requested_kind):
    with closing(connect()) as conn:
        item = conn.execute("SELECT owner_id, listing_type, status FROM Items WHERE item_id = ?", (item_id,)).fetchone()
        if not item or item["status"] != "Available":
            return "Item is not available."
        if item["owner_id"] == borrower_id:
            return "You cannot request your own item."
        allowed_kinds = {
            "Rent": ("Rent",), "Exchange": ("Exchange",),
            "Both": ("Rent", "Exchange")
        }
        if requested_kind not in allowed_kinds.get(item["listing_type"], ()):
            return "This request type is not available for this item."
        request_kind = requested_kind
        conn.execute("""INSERT INTO RentalRequests
                      (item_id, borrower_id, start_date, end_date, status, request_kind, message)
                      VALUES (?, ?, ?, ?, 'Pending', ?, ?)""",
                     (item_id, borrower_id, start_date, end_date, request_kind, message))
        conn.commit()
    return None


def list_requests(user_id, incoming=False):
    sql = """SELECT r.*, i.title, i.owner_id, u.first_name, u.last_name
             FROM RentalRequests r JOIN Items i ON i.item_id = r.item_id
             JOIN Users u ON u.user_id = r.borrower_id"""
    if incoming:
        sql += " WHERE i.owner_id = ?"
    else:
        sql += " WHERE r.borrower_id = ?"
    sql += " ORDER BY r.request_id DESC LIMIT 40"
    with closing(connect()) as conn:
        return conn.execute(sql, (user_id,)).fetchall()


def decide_request(owner_id, request_id, decision):
    """Only an owner can decide. Transaction prevents overlapping accepted rentals."""
    with closing(connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("""
            SELECT r.*, i.owner_id FROM RentalRequests r
            JOIN Items i ON i.item_id = r.item_id WHERE r.request_id = ?
        """, (request_id,)).fetchone()
        if row is None or row["owner_id"] != owner_id or row["status"] != "Pending":
            conn.rollback()
            return "This request cannot be changed."
        if decision == "Accepted" and row["request_kind"] == "Rent":
            conflict = conn.execute("""
                SELECT 1 FROM RentalRequests
                WHERE item_id = ? AND request_id != ? AND status = 'Accepted'
                AND request_kind = 'Rent' AND start_date <= ? AND end_date >= ? LIMIT 1
            """, (row["item_id"], request_id, row["end_date"], row["start_date"])).fetchone()
            if conflict:
                conn.rollback()
                return "Dates overlap with an accepted rental. Please decline this request."
        conn.execute("UPDATE RentalRequests SET status = ? WHERE request_id = ?", (decision, request_id))
        conn.commit()
    return None


def items_by_owner(user_id):
    """Only return listings of the authenticated owner."""
    with closing(connect()) as conn:
        return conn.execute("""SELECT item_id, title, category, listing_type,
                                     price_per_day, status FROM Items
                              WHERE owner_id = ? ORDER BY item_id DESC""",
                            (user_id,)).fetchall()


def admin_data():
    """Return all Users, Items, and RentalRequests for the admin panel."""
    with closing(connect()) as conn:
        users = conn.execute(
            "SELECT user_id, first_name, last_name, email FROM Users ORDER BY user_id DESC"
        ).fetchall()
        items = conn.execute("""
            SELECT i.*, u.email AS owner_email
            FROM Items i JOIN Users u ON u.user_id = i.owner_id
            ORDER BY i.item_id DESC
        """).fetchall()
        requests = conn.execute("""
            SELECT r.*, i.title, u.email AS borrower_email
            FROM RentalRequests r
            JOIN Items i ON i.item_id = r.item_id
            JOIN Users u ON u.user_id = r.borrower_id
            ORDER BY r.request_id DESC
        """).fetchall()
        return users, items, requests


def delete_item(item_id):
    """Delete an item and its rental requests without breaking foreign keys."""
    with closing(connect()) as conn:
        conn.execute("DELETE FROM RentalRequests WHERE item_id = ?", (item_id,))
        conn.execute("DELETE FROM Items WHERE item_id = ?", (item_id,))
        conn.commit()