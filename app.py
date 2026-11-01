"""AITU TechShare: a simple browser app for renting and exchanging campus equipment.
Run with Python 3.10+: python app.py. No pip installs required.
"""
from datetime import date
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import hashlib
import hmac
import math
import mimetypes
import secrets
import threading
import webbrowser
import os

import database as db

HOST = "0.0.0.0"
ADMIN_EMAIL = "admin@astanait.edu.kz"
STATIC = Path(__file__).resolve().parent / "static"
SESSIONS = {}  # In-memory sessions for a LOCAL STUDENT DEMO, not for production.
IMAGE_BY_CATEGORY = {
    "Study": "study.webp", "Electronics": "electronics.webp",
    "Accessories": "accessories.webp", "Photography": "photography.webp",
    "Audio": "audio.webp", "Tools": "tools.webp"
}


def text(value):
    """HTML-escape everything supplied by a user or database."""
    return escape(str(value), quote=True)


def is_admin(user):
    """Check if the logged-in user is the administrator."""
    return bool(user and user["email"].lower() == ADMIN_EMAIL)


def verify_password(password, stored):
    """Check a stored salted PBKDF2 password hash."""
    try:
        algorithm, count, salt, digest = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(count))
        return hmac.compare_digest(test, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def hash_password(password):
    """Never store a plain password. Each account gets a random salt."""
    salt = secrets.token_bytes(16)
    count = 240000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, count)
    return f"pbkdf2_sha256${count}${salt.hex()}${digest.hex()}"


def layout(title, content, user=None, message=""):
    if user:
        admin_link = '<a href="/admin">Admin</a>' if is_admin(user) else ''
        links = (f'<a href="/#add">Add equipment</a>'
                 '<a href="/requests">Requests</a>'
                 '<a href="/my-equipment">My equipment</a>'
                 f'{admin_link}'
                 f'<span class="account">{text(user["first_name"])}</span>'
                 '<form action="/logout" method="post"><button class="nav-logout">Log out</button></form>')
    else:
        links = '<a href="/login">Log in</a><a class="nav-signup" href="/register">Create account</a>'
    alert = f'<div class="alert" role="status">{text(message)}</div>' if message else ''
    return f'''<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{text(title)} · AITU TechShare</title>
<link rel="icon" href="/static/logo.svg" type="image/svg+xml">
<link rel="stylesheet" href="/static/style.css"></head><body>
<header><div class="topbar"><a class="brand" href="/"><img src="/static/logo.svg" alt="" width="36" height="36"><span>AITU <strong>TechShare</strong></span></a>
<nav aria-label="Main navigation"><a href="/">Catalog</a>{links}</nav></div></header>
<main>{alert}{content}</main>
<footer>AITU TechShare · Student project · Local demonstration only</footer>
</body></html>'''


def item_card(item, user):
    category = item["category"]
    image = IMAGE_BY_CATEGORY.get(category, "electronics.webp")
    owner = f'{text(item["first_name"])} {text(item["last_name"][:1])}.'
    price = f'{float(item["price_per_day"]):,.0f}'
    action = ''
    if user and item["owner_id"] != user["user_id"] and item["status"] == 'Available':
        kinds = ("Rent", "Exchange") if item["listing_type"] == "Both" else (item["listing_type"],)
        kind_options = ''.join(f'<option value="{k}">{k}</option>' for k in kinds)
        action = f'''<details class="request-box"><summary>Send request</summary>
<form method="post" action="/request"><input type="hidden" name="item_id" value="{int(item['item_id'])}">
<label>Request type<select name="request_kind">{kind_options}</select></label>
<label>From<input required type="date" name="start_date"></label>
<label>To<input required type="date" name="end_date"></label>
<label>Message (optional)<input name="message" maxlength="160" placeholder="I need it for a project"></label>
<button class="button" type="submit">Submit request</button></form></details>'''
    elif not user:
        action = '<a href="/login" class="small-link">Log in to request</a>'
    elif item["owner_id"] == user["user_id"]:
        action = '<small class="hint">Your equipment listing</small>'
    mode = item["listing_type"]
    cost = f'<span class="price">{price} ₸<small> / day</small></span>' if mode != 'Exchange' else '<span class="price">Exchange</span>'
    return f'''<article class="item-card"><img loading="lazy" width="512" height="320" src="/static/{image}"
alt="Illustration for {text(category)} equipment" class="product-image"><div class="card-body">
<div class="chips"><span class="chip">{text(category)}</span><span class="chip purple">{text(mode)}</span></div>
<h3>{text(item['title'])}</h3><p class="description">{text(item['description'])}</p>
<div class="price-line">{cost}<span class="status">{text(item['status'])}</span></div>
<p class="owner">From {owner} · ID {int(item['item_id'])}</p>{action}</div></article>'''


def catalog(user, params):
    term = params.get("q", [""])[0].strip()[:80]
    mode = params.get("type", [""])[0]
    items = db.search_items(term, mode)
    count = db.summary()["items"]

    if items:
        cards = '<div class="product-grid">' + ''.join(item_card(item, user) for item in items) + '</div>'
    elif term or mode:
        cards = '<div class="empty-state"><h3>No matching equipment</h3><p>Try another search or category.</p></div>'
    else:
        cards = ('''<div class="empty-state"><div class="empty-illustration" aria-hidden="true">＋</div>
<h3>No equipment yet</h3><p>The catalog is empty. Add your first item and it will appear here automatically.</p>
''' + ('<a class="button inline-button" href="#add">Add my first item</a>' if user else
         '<a class="button inline-button" href="/login">Log in to add an item</a>') + '</div>')
    modes = ''.join(f'<option value="{v}" {"selected" if mode == v else ""}>{label}</option>'
                    for v, label in [("", "All types"), ("Rent", "Rent"),
                                     ("Exchange", "Exchange"), ("Both", "Both")])

    if user:
        side = f'''<section class="panel form-panel" id="add"><h2>Add your equipment</h2>
<p>Fill in the form. Your item will be saved and displayed in the catalog.</p>
<form action="/add" method="post">
<label>Equipment name<input name="title" required maxlength="100" placeholder="e.g. Laptop stand"></label>
<div class="form-row"><label>Category<select name="category">{''.join(f'<option>{text(c)}</option>' for c in db.CATEGORIES)}</select></label>
<label>Offer type<select name="listing_type"><option>Rent</option><option>Exchange</option><option>Both</option></select></label></div>
<label>Rental price, ₸ per day<input type="number" name="price" min="0" max="1000000" step="1" value="0" required></label>
<label>Description<textarea name="description" maxlength="500" required placeholder="Condition and details"></textarea></label>
<button class="button full" type="submit">Add equipment</button></form>
<p class="note">See your saved item in <a href="/my-equipment">My equipment</a>.</p></section>'''
    else:
        side = '''<section class="panel form-panel"><h2>Start sharing</h2>
<p>Log in to add your equipment or request an item from another student.</p>
<a href="/login" class="button full link-button">Log in</a>
<a href="/register" class="secondary-link">Create a new student account</a>
</section>'''

    guide = '''<section class="panel guide"><h2>How it works</h2><p>Three easy steps — no sound needed.</p>
<ol class="steps"><li><span>1</span><div><b>Find a device</b><small>Browse equipment shared by students.</small></div></li>
<li><span>2</span><div><b>List your item</b><small>Add a rental or exchange offer.</small></div></li>
<li><span>3</span><div><b>Send a request</b><small>The owner can accept or decline it.</small></div></li></ol>
<div class="progress-track" aria-label="Animated sharing process"><div class="progress-fill"></div></div>
</section>'''

    category_links = ''.join(
        f'<a class="category-link" href="/?q={category}#equipment">'
        f'<img src="/static/{image}" alt="{category} equipment illustration" width="192" height="120">'
        f'<span>{category}</span></a>'
        for category, image in IMAGE_BY_CATEGORY.items()
    )

    return f'''<section class="hero"><div class="hero-text"><div class="eyebrow">FOR AITU STUDENTS</div>
<h1>Rent or exchange<br>equipment easily.</h1>
<p>Share your devices with other students and find what you need.</p>
<a class="hero-link" href="#equipment">Browse the catalog ↓</a></div>
<img class="hero-image" src="/static/study.webp" alt="" width="512" height="320">
</section>
<section class="category-section" aria-labelledby="categories-heading"><h2 id="categories-heading">Browse by category</h2>
<div class="category-grid">{category_links}</div></section>
<div class="main-grid"><div><section class="panel" id="equipment"><div class="section-heading"><div>
<h2>Equipment catalog</h2><p>{count} item(s) added by students</p></div></div>
<form class="filters" method="get" action="/"><input name="q" value="{text(term)}" placeholder="Search equipment" aria-label="Search equipment">
<select name="type" aria-label="Offer type">{modes}</select><button class="button" type="submit">Search</button></form>
{cards}</section></div><aside>{side}{guide}</aside></div>'''


def login_page():
    return '''<section class="panel auth-panel"><a href="/" class="back">← Back to catalog</a>
<h1>Log in</h1><p>Enter your student account details.</p>
<form method="post" action="/login">
<label>AITU email<input type="email" name="email" required autocomplete="username" placeholder="yourname@astanait.edu.kz"></label>
<label>Password<input type="password" name="password" required autocomplete="current-password" placeholder="Enter your password"></label>
<button type="submit" class="button full">Log in</button></form>
<p class="auth-bottom">Don't have an account? <a href="/register">Create an account</a></p></section>'''


def register_page():
    return '''<section class="panel auth-panel"><a href="/" class="back">← Back to catalog</a>
<h1>Create account</h1><p>Use a test @astanait.edu.kz address for this local student prototype. Email ownership is not verified.</p>
<form method="post" action="/register">
<div class="form-row"><label>First name<input name="first_name" required maxlength="50" placeholder="First name"></label>
<label>Last name<input name="last_name" required maxlength="50" placeholder="Last name"></label></div>
<label>AITU email<input type="email" name="email" required maxlength="100" autocomplete="username" placeholder="yourname@astanait.edu.kz"></label>
<label>Password (at least 8 characters)<input type="password" name="password" required minlength="8" autocomplete="new-password"></label>
<label>Repeat password<input type="password" name="confirm_password" required minlength="8" autocomplete="new-password"></label>
<button class="button full" type="submit">Create account</button></form>
<p class="auth-bottom">Already have an account? <a href="/login">Log in</a></p></section>'''


def requests_page(user):
    incoming = db.list_requests(user["user_id"], incoming=True)
    outgoing = db.list_requests(user["user_id"], incoming=False)
    def table(rows, with_actions):
        if not rows:
            return '<p class="muted">No requests yet.</p>'
        content = ''
        for request in rows:
            actions = ''
            if with_actions and request["status"] == "Pending":
                actions = f'''<form method="post" action="/decide" class="actions">
<input type="hidden" name="request_id" value="{request['request_id']}">
<button class="button small" type="submit" name="decision" value="Accepted">Accept</button>
<button class="button small secondary" type="submit" name="decision" value="Declined">Decline</button></form>'''
            content += f'''<tr><td>{int(request['request_id'])}</td><td>{text(request['title'])}</td>
<td>{text(request['request_kind'])}</td><td>{text(request['start_date'])} → {text(request['end_date'])}</td>
<td>{text(request['status'])}</td><td>{actions}</td></tr>'''
        return f'''<div class="table-wrap"><table><thead><tr><th>ID</th><th>Item</th><th>Type</th><th>Period</th><th>Status</th><th>Action</th></tr></thead><tbody>{content}</tbody></table></div>'''
    return f'''<section class="panel wide"><a href="/" class="back">← Catalog</a><h1 class="page-heading">Rental and exchange requests</h1>
<p class="muted">Here you can manage requests for your equipment and follow the requests you have sent.</p>
<h2>Incoming requests for your items</h2>{table(incoming, True)}<h2>Your sent requests</h2>{table(outgoing, False)}</section>'''


def my_equipment_page(user):
    """Display only listings belonging to the currently logged-in account."""
    items = db.items_by_owner(user["user_id"])
    if not items:
        table = '<p class="muted">You have not added any equipment yet.</p>'
    else:
        rows = ''.join(
            f'<tr><td>{int(item["item_id"])}</td><td>{text(item["title"])}</td>'
            f'<td>{text(item["category"])}</td><td>{text(item["listing_type"])}</td>'
            f'<td>{float(item["price_per_day"]):,.0f} ₸</td><td>{text(item["status"])}</td></tr>'
            for item in items
        )
        table = ('<div class="table-wrap"><table><thead><tr>'
                 '<th>ID</th><th>Equipment</th><th>Category</th><th>Type</th>'
                 '<th>Price/day</th><th>Status</th></tr></thead><tbody>'
                 + rows + '</tbody></table></div>')
    return (f'<section class="panel wide"><a href="/" class="back">← Catalog</a>'
            f'<h1 class="page-heading">My equipment</h1>'
            f'<p class="muted">Only listings from your account are shown here. '
            f'Other students can see your published equipment in the public catalog, '
            f'but not your private records.</p>{table}'
            f'<p><a class="button inline-button" href="/#add">Add another item</a></p></section>')


def admin_page():
    """Display all database tables and delete controls for admin@astanait.edu.kz."""
    users, items, requests = db.admin_data()

    item_rows = ''.join(
        f'<tr><td>{int(i["item_id"])}</td><td>{text(i["title"])}</td>'
        f'<td>{text(i["category"])}</td><td>{text(i["owner_email"])}</td>'
        f'<td>{float(i["price_per_day"]):,.0f} ₸</td><td>{text(i["status"])}</td>'
        f'<td><form method="post" action="/delete-item">'
        f'<input type="hidden" name="item_id" value="{int(i["item_id"])}">'
        f'<button class="button small secondary" type="submit">Delete</button>'
        f'</form></td></tr>'
        for i in items
    )
    items_table = (
        '<div class="table-wrap"><table><thead><tr>'
        '<th>ID</th><th>Title</th><th>Category</th><th>Owner</th>'
        '<th>Price</th><th>Status</th><th>Action</th></tr></thead><tbody>'
        + item_rows + '</tbody></table></div>'
    ) if items else '<p class="muted">No items in database.</p>'

    user_rows = ''.join(
        f'<tr><td>{int(u["user_id"])}</td><td>{text(u["first_name"])} {text(u["last_name"])}</td>'
        f'<td>{text(u["email"])}</td></tr>'
        for u in users
    )
    users_table = (
        '<div class="table-wrap"><table><thead><tr>'
        '<th>ID</th><th>Name</th><th>Email</th></tr></thead><tbody>'
        + user_rows + '</tbody></table></div>'
    ) if users else '<p class="muted">No users registered.</p>'

    req_rows = ''.join(
        f'<tr><td>{int(r["request_id"])}</td><td>{text(r["title"])}</td>'
        f'<td>{text(r["borrower_email"])}</td><td>{text(r["request_kind"])}</td>'
        f'<td>{text(r["start_date"])} → {text(r["end_date"])}</td>'
        f'<td>{text(r["status"])}</td></tr>'
        for r in requests
    )
    requests_table = (
        '<div class="table-wrap"><table><thead><tr>'
        '<th>ID</th><th>Item</th><th>Borrower</th><th>Type</th>'
        '<th>Period</th><th>Status</th></tr></thead><tbody>'
        + req_rows + '</tbody></table></div>'
    ) if requests else '<p class="muted">No rental requests.</p>'

    return (f'<section class="panel wide"><a href="/" class="back">← Catalog</a>'
            f'<h1 class="page-heading">Admin Panel</h1>'
            f'<p class="muted">Full database overview for {ADMIN_EMAIL}.</p>'
            f'<h2>All Equipment (Items)</h2>{items_table}'
            f'<h2>All Students (Users)</h2>{users_table}'
            f'<h2>All Requests (RentalRequests)</h2>{requests_table}</section>')


class Site(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print('[TechShare]', format % args)

    def current_user(self):
        cookie = SimpleCookie(self.headers.get('Cookie', ''))
        token = cookie.get('techshare_session')
        user_id = SESSIONS.get(token.value) if token else None
        return db.get_user(user_id) if user_id else None

    def send_page(self, title, content, user=None, message='', status=200):
        body = layout(title, content, user, message).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; img-src 'self'; media-src 'self'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def go(self, location, set_cookie=None):
        self.send_response(303)
        self.send_header('Location', location)
        if set_cookie:
            self.send_header('Set-Cookie', set_cookie)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def serve_asset(self, path):
        file = (STATIC / path.removeprefix('/static/')).resolve()
        if not file.is_relative_to(STATIC) or not file.is_file():
            self.send_error(404)
            return
        body = file.read_bytes()
        content_type = mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'public, max-age=3600')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        url = urlparse(self.path)
        if url.path.startswith('/static/'):
            return self.serve_asset(url.path)
        params = parse_qs(url.query)
        user = self.current_user()
        messages = {
            'saved': 'Equipment saved to SQLite. The new listing appears first in the catalog.',
            'deleted': 'Equipment deleted from SQLite by administrator.',
            'loggedin': 'Welcome back! You can add equipment and send requests.',
            'request': 'Your request was saved in the RentalRequests table.',
            'accepted': 'Request status updated in SQLite.',
            'invalid': 'Please check the form and try again.',
            'login': 'Incorrect email or password. Please try again.',
            'register': 'Account created. You can now log in.',
            'exists': 'This email already has an account. Please log in.',
            'register_error': 'Check your name, AITU email and password (8+ characters).',
            'owner': 'This action is not allowed or the dates overlap with an accepted rental.'
        }
        notice = messages.get(params.get('msg', [''])[0], '')
        if url.path == '/':
            return self.send_page('Catalog', catalog(user, params), user, notice)
        if url.path == '/login':
            return self.send_page('Log in', login_page(), user, notice)
        if url.path == '/register':
            return self.send_page('Create account', register_page(), user, notice)
        if url.path == '/requests' and user:
            return self.send_page('Requests', requests_page(user), user, notice)
        if url.path == '/my-equipment' and user:
            return self.send_page('My equipment', my_equipment_page(user), user, notice)
        if url.path == '/admin' and is_admin(user):
            return self.send_page('Admin panel', admin_page(), user, notice)
        self.send_page('Not found', '<section class="panel wide">Page not found. <a href="/">Go home</a>.</section>', user, status=404)

    def form(self):
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return {}
        if size <= 0 or size > 20000:
            return {}
        return parse_qs(self.rfile.read(size).decode('utf-8', 'replace'))

    def do_POST(self):
        route = urlparse(self.path).path
        form = self.form()
        def val(name):
            return form.get(name, [''])[0].strip()
        if route == '/login':
            user = db.find_user(val('email').lower()[:100])
            if user and verify_password(val('password'), user['password_hash']):
                token = secrets.token_urlsafe(32)
                SESSIONS[token] = user['user_id']
                self.go('/?msg=loggedin', f'techshare_session={token}; HttpOnly; SameSite=Lax; Path=/')
            else:
                self.go('/login?msg=login')
            return
        if route == '/register':
            first, last = val('first_name'), val('last_name')
            email, password = val('email').lower(), val('password')
            if (not first or len(first) > 50 or not last or len(last) > 50 or
                not email.endswith('@astanait.edu.kz') or len(email) > 100 or
                email.count('@') != 1 or len(email.split('@')[0]) == 0 or
                len(password) < 8 or len(password) > 128 or password != val('confirm_password')):
                return self.go('/register?msg=register_error')
            if db.find_user(email):
                return self.go('/register?msg=exists')
            if not db.create_user(first, last, email, hash_password(password)):
                return self.go('/register?msg=exists')
            return self.go('/login?msg=register')
        if route == '/logout':
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
            token = cookie.get('techshare_session')
            if token:
                SESSIONS.pop(token.value, None)
            self.go('/', 'techshare_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            return
        user = self.current_user()
        if not user:
            return self.go('/login')
        if route == '/add':
            try:
                price = float(val('price'))
            except ValueError:
                price = -1
            title, category, mode, description = (val(k) for k in ('title', 'category', 'listing_type', 'description'))
            if (not title or len(title) > 100 or category not in db.CATEGORIES
                or mode not in ('Rent', 'Exchange', 'Both') or not description
                or len(description) > 500 or not math.isfinite(price) or price < 0 or price > 1000000):
                return self.go('/?msg=invalid')
            db.add_item(user['user_id'], title, category, description, price, mode)
            return self.go('/?msg=saved')
        if route == '/request':
            try:
                item_id = int(val('item_id'))
                start, end = date.fromisoformat(val('start_date')), date.fromisoformat(val('end_date'))
            except ValueError:
                return self.go('/?msg=invalid')
            if start < date.today() or end < start or (end - start).days > 180 or len(val('message')) > 160:
                return self.go('/?msg=invalid')
            error = db.create_request(user['user_id'], item_id, start.isoformat(), end.isoformat(), val('message'), val('request_kind'))
            return self.go('/?msg=invalid' if error else '/?msg=request')
        if route == '/decide':
            try:
                request_id = int(val('request_id'))
            except ValueError:
                return self.go('/requests?msg=owner')
            decision = val('decision')
            if decision not in ('Accepted', 'Declined'):
                return self.go('/requests?msg=owner')
            error = db.decide_request(user['user_id'], request_id, decision)
            return self.go('/requests?msg=owner' if error else '/requests?msg=accepted')
        if route == '/delete-item' and is_admin(user):
            try:
                db.delete_item(int(val('item_id')))
            except ValueError:
                pass
            return self.go('/admin?msg=deleted')
        self.send_error(404)


def main():
    db.initialize_database()
    if not db.find_user(ADMIN_EMAIL):
        db.create_user("Admin", "AITU", ADMIN_EMAIL, hash_password("admin12345"))
    port = int(os.environ.get("PORT", 8765))
    server = ThreadingHTTPServer((HOST, port), Site)
    url = f"http://{HOST}:{port}"
    print("\nAITU TechShare")
    print("Website:", url)
    print("Database:", db.DATABASE_FILE)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Website stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()