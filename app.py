import sqlite3
import uuid
import os
import io
import re
import qrcode
import bcrypt
import base64
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import quote
from flask import Flask, render_template, request, redirect, url_for, Response, abort, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-dev-key-change-in-prod')
DATABASE_URL = os.environ.get('DATABASE_URL', '')
IMG_BB_API_KEY = os.environ.get('IMG_BB_API_KEY', '')
DB_FILE = 'contacts.db'
USE_POSTGRES = bool(DATABASE_URL)

def extract_image_url(value):
    """Return a usable image URL from a pasted link or an imgbb embed snippet.
    Accepts a raw URL (Direct link) or a whole 'HTML full linked' snippet
    by pulling the src="..." URL out of it."""
    value = (value or '').strip()
    if not value:
        return ''
    match = re.search(r'src=["\']([^"\']+)["\']', value)
    if match:
        return match.group(1)
    return value

def upload_to_imgbb(image_bytes):
    """Upload cropped image bytes to imgbb and return the hosted image URL."""
    if not IMG_BB_API_KEY:
        raise RuntimeError('IMG_BB_API_KEY is not configured on the server')
    resp = requests.post(
        'https://api.imgbb.com/1/upload',
        data={'key': IMG_BB_API_KEY},
        files={'image': ('cropped_avatar.png', image_bytes, 'image/png')},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get('success'):
        raise RuntimeError(f"imgbb upload failed: {payload.get('error')}")
    return payload['data']['url']

def shorten_url(long_url):
    """Uses TinyURL to shorten the URL"""
    if '127.0.0.1' in long_url or 'localhost' in long_url:
        print(f"DEBUG: Skipping shortening for local URL: {long_url}")
        return long_url

    print(f"DEBUG: Attempting to shorten: {long_url}")
    try:
        api_url = f"http://tinyurl.com/api-create.php?url={long_url}"
        response = requests.get(api_url, timeout=5)
        print(f"DEBUG: TinyURL status: {response.status_code}, length: {len(response.text)}")
        if response.status_code == 200 and response.text.startswith('http'):
            return response.text
        print(f"DEBUG: TinyURL failed or returned non-URL: {response.text}")
        return long_url
    except Exception as e:
        print(f"DEBUG: TinyURL Error: {e}")
        return long_url

# Setup Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class DB:
    """Lightweight wrapper over sqlite3/psycopg2 so call sites stay identical.
    Uses PostgreSQL when DATABASE_URL is set, otherwise local SQLite."""
    def __init__(self, conn):
        self.conn = conn
        self.is_pg = isinstance(conn, psycopg2.extensions.connection)

    def execute(self, sql, params=None):
        if self.is_pg:
            cur = self.conn.cursor()
            cur.execute(sql.replace('?', '%s'), params or ())
            return cur
        return self.conn.execute(sql, params or ())

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

def get_db_connection():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    else:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
    return DB(conn)

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id TEXT PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            company TEXT,
            job_title TEXT,
            address TEXT,
            website TEXT,
            contact_type TEXT,
            mobile TEXT,
            file_path TEXT,
            profile_image TEXT,
            short_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    if USE_POSTGRES:
        # Create users table (PostgreSQL)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash BYTEA NOT NULL,
                is_admin BOOLEAN DEFAULT false,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    else:
        # Create users table (SQLite)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash BLOB NOT NULL,
                is_admin BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    # Migration: add user ownership column to contacts (if missing)
    if USE_POSTGRES:
        conn.execute('ALTER TABLE contacts ADD COLUMN IF NOT EXISTS user_id INTEGER')
    else:
        try:
            conn.execute('ALTER TABLE contacts ADD COLUMN user_id INTEGER')
        except sqlite3.OperationalError:
            pass  # column already exists

    # Backfill owner for contacts created before ownership existed (first user = admin)
    conn.execute('UPDATE contacts SET user_id = (SELECT id FROM users ORDER BY id LIMIT 1) WHERE user_id IS NULL')

    conn.commit()
    conn.close()


class User(UserMixin):
    def __init__(self, id, username, is_admin):
        self.id = id
        self.username = username
        self.is_admin = is_admin

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user_data = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user_data:
        return User(user_data['id'], user_data['username'], bool(user_data['is_admin']))
    return None

def create_default_admin():
    """Create default admin account if no users exist"""
    try:
        conn = get_db_connection()
        user_count = conn.execute('SELECT COUNT(*) AS total FROM users').fetchone()['total']
        
        if user_count == 0:
            # Create default admin
            password_hash = bcrypt.hashpw('admin123'.encode('utf-8'), bcrypt.gensalt())
            conn.execute(
                'INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)',
                ('admin', password_hash, 1)
            )
            conn.commit()
            print("Default admin created: username='admin', password='admin123'")
    except Exception as e:
        print(f"Error creating default admin: {e}")
    finally:
        conn.close()

# Initialize DB and create admin on start
with app.app_context():
    init_db()
    create_default_admin()

@app.template_filter('fmt_date')
def fmt_date(value):
    """Format a date/datetime as YYYY-MM-DD (works for str and datetime)."""
    if value is None:
        return '—'
    return str(value)[:10]

@app.template_filter('avatar_src')
def avatar_src(value):
    """Return a renderable <img> src for a stored profile_image value.
    Accepts full URLs (imgbb etc.) or relative static uploads paths."""
    if not value:
        return None
    if str(value).startswith(('http://', 'https://')):
        return value
    return url_for('static', filename=str(value))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        user_data = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user_data and bcrypt.checkpw(password.encode('utf-8'), bytes(user_data['password_hash'])):
            user = User(user_data['id'], user_data['username'], bool(user_data['is_admin']))
            login_user(user)
            return redirect(url_for('contacts_list'))
        
        flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('contacts_list'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not username or not password:
            flash('Username and password are required')
            return redirect(url_for('signup'))
        if len(password) < 4:
            flash('Password must be at least 4 characters')
            return redirect(url_for('signup'))
        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('signup'))

        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                         (username, password_hash))
            conn.commit()
            conn.close()
            flash('Account created! You can now log in.')
            return redirect(url_for('login'))
        except (sqlite3.IntegrityError, psycopg2.errors.UniqueViolation):
            conn.rollback()
            conn.close()
            flash('Username already exists')
            return redirect(url_for('signup'))

    return render_template('signup.html')

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        conn = get_db_connection()
        user_data = conn.execute('SELECT * FROM users WHERE id = ?', (current_user.id,)).fetchone()
        if not user_data or not bcrypt.checkpw(current_password.encode('utf-8'), bytes(user_data['password_hash'])):
            conn.close()
            flash('Current password is incorrect')
            return redirect(url_for('settings'))
        if len(new_password) < 4:
            conn.close()
            flash('New password must be at least 4 characters')
            return redirect(url_for('settings'))
        if new_password != confirm_password:
            conn.close()
            flash('New passwords do not match')
            return redirect(url_for('settings'))

        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, current_user.id))
        conn.commit()
        conn.close()
        flash('Password updated successfully')
        return redirect(url_for('settings'))

    return render_template('settings.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/users')
@login_required
def users_list():
    if not current_user.is_admin:
        abort(403)
    
    conn = get_db_connection()
    users = conn.execute('''
        SELECT u.*, COUNT(c.id) AS contact_count
        FROM users u
        LEFT JOIN contacts c ON c.user_id = u.id
        GROUP BY u.id
        ORDER BY u.created_at DESC
    ''').fetchall()
    conn.close()
    
    return render_template('users.html', users=users)

@app.route('/users/<int:user_id>/contacts')
@login_required
def user_contacts(user_id):
    """Admin only: view all contacts belonging to a specific user"""
    if not current_user.is_admin:
        abort(403)
    
    conn = get_db_connection()
    owner = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not owner:
        conn.close()
        abort(404)
    
    contacts = conn.execute('SELECT * FROM contacts WHERE user_id = ? ORDER BY created_at DESC', (user_id,)).fetchall()
    total = conn.execute('SELECT COUNT(*) AS total FROM contacts WHERE user_id = ?', (user_id,)).fetchone()['total']
    conn.close()
    
    return render_template('user_contacts.html', owner=owner, contacts=contacts, total=total)

@app.route('/users/reset-password/<int:user_id>', methods=['POST'])
@login_required
def reset_user_password(user_id):
    """Admin only: reset the password of any user"""
    if not current_user.is_admin:
        abort(403)
    
    new_password = request.form.get('new_password', '')
    if len(new_password) < 4:
        flash('Password must be at least 4 characters')
        return redirect(url_for('users_list'))
    
    password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
    conn = get_db_connection()
    conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, user_id))
    conn.commit()
    conn.close()
    
    flash('Password updated successfully')
    return redirect(url_for('users_list'))

@app.route('/users/create', methods=['POST'])
@login_required
def create_user():
    if not current_user.is_admin:
        abort(403)
    
    username = request.form.get('username')
    password = request.form.get('password')
    is_admin = request.form.get('is_admin') == 'on'
    
    if not username or not password:
        flash('Username and password are required')
        return redirect(url_for('users_list'))
    
    try:
        # Hash password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)',
            (username, password_hash, is_admin)
        )
        conn.commit()
        conn.close()
        flash('User created successfully')
    except (sqlite3.IntegrityError, psycopg2.errors.UniqueViolation):
        conn.rollback()
        conn.close()
        flash('Username already exists')
    
    return redirect(url_for('users_list'))

@app.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        abort(403)
    
    if user_id == current_user.id:
        flash('Cannot delete your own account')
        return redirect(url_for('users_list'))
    
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    flash('User deleted successfully')
    return redirect(url_for('users_list'))

@app.route('/', methods=['GET'])
@login_required
def index():
    return render_template('index.html')



@app.route('/contacts')
@login_required
def contacts_list():
    """Display saved contacts with search and pagination.
    Regular users only see their own contacts; admins see all."""
    search_query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    per_page = 12

    user_filter = request.args.get('user', type=int)
    if not current_user.is_admin:
        user_filter = current_user.id

    where = []
    params = []
    if user_filter is not None:
        where.append('c.user_id = ?')
        params.append(user_filter)
    if search_query:
        where.append('(c.first_name LIKE ? OR c.last_name LIKE ? OR c.phone LIKE ? OR c.email LIKE ? OR c.company LIKE ?)')
        params.extend([f'%{search_query}%'] * 5)
    where_sql = 'WHERE ' + ' AND '.join(where) if where else ''

    conn = get_db_connection()

    contacts = conn.execute(f'''
        SELECT c.*, u.username AS owner_username
        FROM contacts c
        LEFT JOIN users u ON u.id = c.user_id
        {where_sql}
        ORDER BY c.created_at DESC
        LIMIT ? OFFSET ?
    ''', (*params, per_page, (page - 1) * per_page)).fetchall()

    total = conn.execute(f'''
        SELECT COUNT(*) AS total FROM contacts c
        {where_sql}
    ''', params).fetchone()['total']

    users = []
    if current_user.is_admin:
        users = conn.execute('SELECT id, username FROM users ORDER BY username').fetchall()

    conn.close()

    total_pages = (total + per_page - 1) // per_page

    return render_template('contacts.html',
                         contacts=contacts,
                         page=page,
                         total_pages=total_pages,
                         search_query=search_query,
                         users=users,
                         user_filter=user_filter)



@app.route('/fetch-image')
@login_required
def fetch_image():
    """Proxy a pasted imgbb URL as a same-origin image.
    Loading a cross-origin image directly would 'taint' the canvas and make
    cropper.js unable to export it — proxying through the app fixes that."""
    url = request.args.get('url', '')
    if not url.startswith(('http://', 'https://')):
        abort(400, description='Invalid image URL')
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        abort(400, description='Could not fetch the image')

    ctype = resp.headers.get('Content-Type', '').split(';')[0].lower()
    if not ctype.startswith('image/'):
        abort(400, description='The link does not point to an image')
    if len(resp.content) > 10 * 1024 * 1024:
        abort(400, description='The image is too large')

    return Response(resp.content, mimetype=ctype)

@app.route('/create', methods=['POST'])
@login_required
def create_contact():
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    phone = request.form.get('phone')
    
    if not first_name or not last_name or not phone:
        return "First Name, Last Name, and Phone are required", 400

    email = request.form.get('email')
    company = request.form.get('company')
    job_title = request.form.get('job_title')
    address = request.form.get('address')
    website = request.form.get('website')
    contact_type = request.form.get('contact_type')
    mobile = request.form.get('mobile')
    
    profile_image = None
    cropped_base64 = request.form.get('cropped_image_base64')
    profile_image_url = extract_image_url(request.form.get('profile_image_url'))

    if cropped_base64 and ',' in cropped_base64:
        # User cropped the pasted image — re-upload the result to imgbb
        try:
            _, imgstr = cropped_base64.split(';base64,')
            img_data = base64.b64decode(imgstr)
            profile_image = upload_to_imgbb(img_data)
        except Exception as e:
            print(f"Error uploading cropped image to imgbb: {e}")
            profile_image = profile_image_url
    elif profile_image_url.startswith(('http://', 'https://')):
        profile_image = profile_image_url
    
    # Generate shorter 6-character ID for simpler QR codes
    unique_id = str(uuid.uuid4())[:6]
    
    # Generate Long URL for shortening
    contact_url = url_for('contact_link', unique_id=unique_id, _external=True)
    short_url = shorten_url(contact_url)
    
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO contacts (id, first_name, last_name, phone, email, company, job_title, address, website, contact_type, mobile, profile_image, short_url, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (unique_id, first_name, last_name, phone, email, company, job_title, address, website, contact_type, mobile, profile_image, short_url, current_user.id))
    conn.commit()
    conn.close()
    
    return redirect(url_for('success', unique_id=unique_id))

@app.route('/success/<unique_id>')
@login_required
def success(unique_id):
    conn = get_db_connection()
    contact = conn.execute('SELECT * FROM contacts WHERE id = ?', (unique_id,)).fetchone()
    conn.close()
    
    if not contact:
        abort(404)
    
    # Always generate the current live URL based on the present request host
    contact_url = url_for('contact_link', unique_id=unique_id, _external=True)
    
    # We will pass the live contact_url to the template. 
    # The template will display this live URL instead of the shortened one which might be expired.
    
    # Generate QR code URL for the link (dynamically matches the current host)
    qr_code_url = url_for('qr_code', unique_id=unique_id, _external=True)
    
    return render_template('success.html', 
                         contact_url=contact_url,
                         qr_code_url=qr_code_url,
                         unique_id=unique_id,
                         contact=dict(contact))

@app.route('/edit/<unique_id>')
@login_required
def edit_contact(unique_id):
    conn = get_db_connection()
    contact = conn.execute('SELECT * FROM contacts WHERE id = ?', (unique_id,)).fetchone()
    conn.close()
    
    if not contact:
        abort(404)
    if not current_user.is_admin and contact['user_id'] != current_user.id:
        abort(403)
    
    return render_template('edit.html', contact=contact, unique_id=unique_id)

@app.route('/update/<unique_id>', methods=['POST'])
@login_required
def update_contact(unique_id):
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    phone = request.form.get('phone')
    
    if not first_name or not last_name or not phone:
        return "First Name, Last Name, and Phone are required", 400

    email = request.form.get('email')
    company = request.form.get('company')
    job_title = request.form.get('job_title')
    address = request.form.get('address')
    website = request.form.get('website')
    contact_type = request.form.get('contact_type')
    mobile = request.form.get('mobile')
    
    conn = get_db_connection()
    
    contact = conn.execute('SELECT * FROM contacts WHERE id = ?', (unique_id,)).fetchone()
    if not contact:
        conn.close()
        abort(404)
    if not current_user.is_admin and contact['user_id'] != current_user.id:
        conn.close()
        abort(403)

    # Handle Profile Image (imgbb only)
    cropped_base64 = request.form.get('cropped_image_base64')
    profile_image_url = extract_image_url(request.form.get('profile_image_url'))

    if cropped_base64 and ',' in cropped_base64:
        # User cropped the pasted image — re-upload the result to imgbb
        try:
            _, imgstr = cropped_base64.split(';base64,')
            img_data = base64.b64decode(imgstr)
            new_img = upload_to_imgbb(img_data)
            conn.execute('UPDATE contacts SET profile_image = ? WHERE id = ?', (new_img, unique_id))
        except Exception as e:
            print(f"Error uploading cropped image to imgbb: {e}")
            if profile_image_url.startswith(('http://', 'https://')):
                conn.execute('UPDATE contacts SET profile_image = ? WHERE id = ?', (profile_image_url, unique_id))
    elif profile_image_url.startswith(('http://', 'https://')):
        conn.execute('UPDATE contacts SET profile_image = ? WHERE id = ?', (profile_image_url, unique_id))

    # Update other fields
    conn.execute('''
        UPDATE contacts 
        SET first_name = ?, last_name = ?, phone = ?, email = ?, company = ?, job_title = ?, address = ?, website = ?, contact_type = ?, mobile = ?
        WHERE id = ?
    ''', (first_name, last_name, phone, email, company, job_title, address, website, contact_type, mobile, unique_id))
    
    # We no longer rely on short_url for temporary tunnel sessions
    # as it becomes invalid when the tunnel restarts.
        
    conn.commit()
    conn.close()
    
    return redirect(url_for('success', unique_id=unique_id))
@app.route('/contact-qr/<unique_id>.png')
def contact_qr_code(unique_id):
    """Generates a QR code linking to the vCard download route"""
    conn = get_db_connection()
    contact = conn.execute('SELECT * FROM contacts WHERE id = ?', (unique_id,)).fetchone()
    conn.close()
    
    if not contact:
        abort(404)
        
    # Generate the direct download URL
    download_url = url_for('download_vcard_fallback', unique_id=unique_id, _external=True)
    
    # Create QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(download_url)
    qr.make(fit=True)
    
    # Create image
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to bytes
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return Response(img_io.getvalue(), mimetype='image/png')
@app.route('/process-scanned-vcard', methods=['POST'])
def process_scanned_vcard():
    """Receives raw vCard data from JS scanner and returns it as a file"""
    data = request.get_json()
    vcard_data = data.get('vcard')
    
    if not vcard_data:
        return "No data", 400
        
    return Response(
        vcard_data,
        mimetype="text/vcard",
        headers={
            "Content-Disposition": "attachment; filename=\"scanned_contact.vcf\""
        }
    )

@app.route('/delete/<unique_id>', methods=['POST'])
@login_required
def delete_contact(unique_id):
    conn = get_db_connection()
    contact = conn.execute('SELECT * FROM contacts WHERE id = ?', (unique_id,)).fetchone()
    
    if not contact:
        conn.close()
        abort(404)
    if not current_user.is_admin and contact['user_id'] != current_user.id:
        conn.close()
        abort(403)
    
    # Delete from database
    conn.execute('DELETE FROM contacts WHERE id = ?', (unique_id,))
    conn.commit()
    conn.close()
    
    flash('Contact deleted successfully')
    
    # Redirect back to the same page and search context
    page = request.args.get('page', 1)
    search_query = request.args.get('q', '')
    
    return redirect(url_for('contacts_list', page=page, q=search_query))

@app.route('/<unique_id>')
def contact_link(unique_id):
    conn = get_db_connection()
    contact = conn.execute('SELECT * FROM contacts WHERE id = ?', (unique_id,)).fetchone()
    conn.close()
    
    if not contact:
        abort(404)
    
    return render_template('mobile_contact.html', contact=dict(contact))

@app.route('/download/<unique_id>')
def download_vcard_fallback(unique_id):
    conn = get_db_connection()
    contact = conn.execute('SELECT * FROM contacts WHERE id = ?', (unique_id,)).fetchone()
    conn.close()
    
    if not contact:
        abort(404)
    
    vcard = generate_vcard(contact)
    filename = f"{contact['first_name']}_{contact['last_name']}.vcf"
    
    return Response(
        vcard,
        mimetype="text/vcard",
        headers={
            "Content-Disposition": f"inline; filename=\"{filename}\"",
            "Content-Type": "text/vcard; charset=utf-8"
        }
    )

def generate_vcard(contact):
    # vCard 3.0 format with CRLF line endings
    full_name = f"{contact['first_name']} {contact['last_name']}"
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"FN;CHARSET=UTF-8:{full_name}",
        f"N;CHARSET=UTF-8:{contact['last_name']};{contact['first_name']};;;",
        f"TEL;TYPE=CELL:{contact['phone']}"
    ]
    
    if contact['email']:
        lines.append(f"EMAIL;TYPE=INTERNET:{contact['email']}")
    
    if contact['company']:
        lines.append(f"ORG;CHARSET=UTF-8:{contact['company']}")
        
    if contact['job_title']:
        lines.append(f"TITLE;CHARSET=UTF-8:{contact['job_title']}")
        
    if contact['address']:
        lines.append(f"ADR;TYPE=WORK;CHARSET=UTF-8:;;{contact['address']};;;;")
        
    if contact['website']:
        lines.append(f"URL:{contact['website']}")
        
    # Add profile image to vCard if it exists
    if contact['profile_image']:
        try:
            # profile_image is a hosted URL (imgbb etc.) — fetch its bytes
            img_url = str(contact['profile_image'])
            if img_url.startswith(('http://', 'https://')):
                resp = requests.get(img_url, timeout=15)
                resp.raise_for_status()
                ctype = resp.headers.get('Content-Type', '').split(';')[0].lower()
                if ctype.startswith('image/') and len(resp.content) <= 10 * 1024 * 1024:
                    encoded_string = base64.b64encode(resp.content).decode('utf-8')
                    # PHOTO property in vCard 3.0
                    lines.append(f"PHOTO;TYPE=JPEG;ENCODING=b:{encoded_string}")
        except Exception as e:
            print(f"Error encoding photo for vCard: {e}")

    lines.append("END:VCARD")
    
    # Join with CRLF
    return "\r\n".join(lines)

def detect_mobile_os(user_agent):
    """Detect mobile OS from user agent string"""
    user_agent = user_agent.lower()
    
    if 'iphone' in user_agent or 'ipad' in user_agent or 'ipod' in user_agent:
        return 'ios'
    elif 'android' in user_agent:
        return 'android'
    else:
        return 'desktop'

def generate_google_contacts_url(contact):
    """Generate Google Contacts URL with pre-filled data
    
    Note: Google Contacts only supports these URL parameters:
    - givenname (lowercase!)
    - familyname (lowercase!)
    - email
    - phone
    
    Organization and jobTitle are NOT supported via URL parameters.
    """
    params = []
    
    # Use lowercase parameter names (Google Contacts requirement)
    if contact['first_name']:
        params.append(f"givenname={quote(contact['first_name'])}")
    if contact['last_name']:
        params.append(f"familyname={quote(contact['last_name'])}")
    
    # Add supported fields
    if contact['phone']:
        params.append(f"phone={quote(contact['phone'])}")
    if contact['email']:
        params.append(f"email={quote(contact['email'])}")
    
    # Note: organization, jobTitle, address, website are NOT supported
    # Users will need to add these manually after saving the contact
    
    # Don't double-encode the ampersand - just join with &
    return f"https://contacts.google.com/new?{'&'.join(params)}"

@app.route('/vcard-qr/<unique_id>.png')
def vcard_qr_code(unique_id):
    """Generate QR code containing vCard data (not URL)"""
    conn = get_db_connection()
    contact = conn.execute('SELECT * FROM contacts WHERE id = ?', (unique_id,)).fetchone()
    conn.close()
    
    if not contact:
        abort(404)
    
    # Generate vCard data
    vcard_data = generate_vcard(contact)
    
    # Create QR code with vCard data
    qr = qrcode.QRCode(
        version=None,  # Auto-size based on data
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(vcard_data)
    qr.make(fit=True)
    
    # Create image
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to bytes
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return Response(
        img_io.getvalue(),
        mimetype='image/png',
        headers={
            'Content-Disposition': f'inline; filename="vcard_qr_{unique_id}.png"',
            'Cache-Control': 'no-store, no-cache, must-revalidate'
        }
    )

@app.route('/qr/<unique_id>.png')
def qr_code(unique_id):
    """Generate QR code for the contact link URL"""
    # Generate the contact link URL
    contact_url = url_for('contact_link', unique_id=unique_id, _external=True)
    
    # Create a fresh local QRCode instance to prevent data accumulation
    qr_local = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr_local.add_data(contact_url)
    qr_local.make(fit=True)
    
    # Create image
    img = qr_local.make_image(fill_color="black", back_color="white")
    
    # Convert to bytes
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return Response(
        img_io.getvalue(),
        mimetype='image/png',
        headers={
            'Content-Disposition': f'inline; filename="contact_qr_{unique_id}.png"',
            'Cache-Control': 'no-store, no-cache, must-revalidate'
        }
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5003)
