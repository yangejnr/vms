from flask import Flask, render_template, request, jsonify, redirect, send_file, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, date
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode
from PIL import Image, ImageOps
import atexit
import os
import signal
import base64
import uuid
from io import BytesIO

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)

# Flask resolves the instance folder from the application root. When this file is
# run directly ("python ncs_vms/app.py") the root becomes the working directory,
# so the database location would depend on where the app was launched from. Pin
# the instance path to the package directory so it is always the same file.
app.instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
os.makedirs(app.instance_path, exist_ok=True)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ncs_vms.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
CORS(app)
db = SQLAlchemy(app)

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    type = db.Column(db.String(20))  # 'department','command','unit'
    parent_id = db.Column(db.Integer)

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200), nullable=True)
    landing_endpoint = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    service_no = db.Column(db.String(40), unique=True, nullable=False)
    fullname = db.Column(db.String(150), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    rank = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    location_type = db.Column(db.String(10), nullable=True)  # 'HQ' or 'Command'
    department_id = db.Column(db.Integer, nullable=True)
    unit_id = db.Column(db.Integer, nullable=True)
    active = db.Column(db.Boolean, default=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    role = db.relationship('Role', backref='users')

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw_password)

ROLE_ADMIN = 'Admin'
ROLE_OFFICER = 'Officer'
ROLE_DEPARTMENT = 'Department'

DEFAULT_ROLES = [
    (ROLE_ADMIN, 'Full system administration and reporting', 'admin_dashboard'),
    (ROLE_OFFICER, 'Reception desk check-in and visitor handling', 'checkin'),
    (ROLE_DEPARTMENT, 'Camera-only visitor verification at a department', 'verify'),
]

# Recognised NCS ranks, in seniority order. Stored as free text so existing
# records remain readable, but new and edited users are limited to this list.
NCS_RANKS = [
    'AC', 'CSC', 'DSC', 'SC',
    'CA III', 'CA II', 'CA I',
    'AIC', 'IC', 'ASC II', 'ASC I',
]

class Officer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    svn = db.Column(db.String(20), unique=True)
    rank = db.Column(db.String(50))
    location_type = db.Column(db.String(10))  # 'HQ' or 'Command'
    department_id = db.Column(db.Integer)
    unit_id = db.Column(db.Integer)

class Visitor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(150))
    phone = db.Column(db.String(20), unique=True)
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    organization = db.Column(db.String(150), nullable=True)
    id_type = db.Column(db.String(60), nullable=True)
    id_number = db.Column(db.String(80), nullable=True)
    gender = db.Column(db.String(30), nullable=True)
    photo_path = db.Column(db.String(200), nullable=True)         # stored image file or path
    face_fingerprint = db.Column(db.Text, nullable=True)
    finger_template = db.Column(db.LargeBinary, nullable=True)    # for future fingerprint
    voice_sample_path = db.Column(db.String(200), nullable=True)  # for future voice sample
    created_by = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(db.Integer, db.ForeignKey('visitor.id'))
    visit_no = db.Column(db.String(30), unique=True)
    date = db.Column(db.Date, default=date.today)
    purpose = db.Column(db.String(20))  # 'official','personal'
    host_name = db.Column(db.String(150), nullable=True)
    destination = db.Column(db.String(150), nullable=True)
    documents = db.Column(db.Text)
    group_size = db.Column(db.Integer, default=1)
    status = db.Column(db.String(10), default='in')  # 'in','out'
    signin_time = db.Column(db.DateTime, default=datetime.utcnow)
    signout_time = db.Column(db.DateTime, nullable=True)
    qr_path = db.Column(db.String(200), nullable=True)
    created_by = db.Column(db.String(80), nullable=True)
    signed_out_by = db.Column(db.String(80), nullable=True)
    synced = db.Column(db.Boolean, default=False)

def add_missing_columns(table_name, columns):
    existing = {
        row[1]
        for row in db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    }
    for name, definition in columns.items():
        if name not in existing:
            db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}"))
    db.session.commit()

def migrate_database():
    db.create_all()
    add_missing_columns('visitor', {
        'organization': 'VARCHAR(150)',
        'id_type': 'VARCHAR(60)',
        'id_number': 'VARCHAR(80)',
        'gender': 'VARCHAR(30)',
        'face_fingerprint': 'TEXT',
        'created_by': 'VARCHAR(80)',
        'updated_at': 'DATETIME'
    })
    add_missing_columns('visit', {
        'host_name': 'VARCHAR(150)',
        'destination': 'VARCHAR(150)',
        'created_by': 'VARCHAR(80)',
        'signed_out_by': 'VARCHAR(80)'
    })
    seed_roles()

def seed_roles():
    """Ensure the Admin and Officer roles exist, then create a default admin."""
    changed = False
    for name, description, landing in DEFAULT_ROLES:
        role = Role.query.filter_by(name=name).first()
        if not role:
            db.session.add(Role(name=name, description=description, landing_endpoint=landing))
            changed = True
        elif role.landing_endpoint != landing:
            role.landing_endpoint = landing
            changed = True
    if changed:
        db.session.commit()

    if User.query.count() == 0:
        admin_role = Role.query.filter_by(name=ROLE_ADMIN).first()
        default_service_no = os.environ.get('DEFAULT_ADMIN_SERVICE_NO', 'ADMIN')
        default_password = os.environ.get('DEFAULT_ADMIN_PASSWORD', 'NCS-1234')
        admin = User(
            service_no=default_service_no,
            fullname='System Administrator',
            role_id=admin_role.id,
            active=True
        )
        admin.set_password(default_password)
        db.session.add(admin)
        db.session.commit()
        print(f"Created default admin account: {default_service_no} / {default_password}")

with app.app_context():
    migrate_database()

def generate_visit_no():
    today = date.today()
    prefix = f"NCS/{today.year % 100:02d}/{today.month:02d}/{today.day:02d}/"
    last = db.session.query(
        func.max(Visit.visit_no)
    ).filter(Visit.date == today).scalar()
    if last:
        seq = int(last.split('/')[-1]) + 1
    else:
        seq = 1
    return prefix + f"{seq:04d}"

@app.route('/')
def index():
    if session.get('user_id'):
        return redirect(url_for(landing_endpoint_for_session()))
    return render_template('login.html')

def landing_endpoint_for_session():
    """Where the signed-in user should land, based on their role."""
    landing = session.get('role_landing')
    if landing and landing in app.view_functions:
        return landing
    return 'checkin'

@app.route('/login', methods=['POST'])
def login():
    service_no = (
        request.form.get('service_no')
        or request.form.get('officer_name')
        or ''
    ).strip()
    password = request.form.get('password') or request.form.get('access_code') or ''

    user = User.query.filter(func.lower(User.service_no) == service_no.lower()).first()

    if not user or not user.check_password(password):
        return render_template(
            'login.html',
            error='Invalid service number or password.',
            service_no=service_no
        ), 401

    if not user.active:
        return render_template(
            'login.html',
            error='This account has been disabled. Contact the administrator.',
            service_no=service_no
        ), 403

    start_user_session(user)
    return redirect(url_for(landing_endpoint_for_session()))

def start_user_session(user):
    role = user.role
    session.clear()
    session['user_id'] = user.id
    session['desk_officer'] = user.service_no
    session['user_name'] = user.fullname
    session['role'] = role.name if role else None
    session['role_landing'] = (role.landing_endpoint if role else None) or 'checkin'
    user.last_login_at = datetime.utcnow()
    db.session.commit()

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

def current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return db.session.get(User, user_id)

def current_role():
    return session.get('role')

def is_admin():
    return current_role() == ROLE_ADMIN

def is_department():
    return current_role() == ROLE_DEPARTMENT

def require_officer_session():
    """Any authenticated user may reach the reception module."""
    if not session.get('user_id'):
        return redirect(url_for('index'))
    return None

def require_reception_session():
    """Reception pages are for officers and admins, not department stations.

    Department accounts are deliberately limited to the camera verification
    screen so they cannot browse visitor records.
    """
    if not session.get('user_id'):
        return redirect(url_for('index'))
    if is_department():
        return redirect(url_for('verify'))
    return None

def require_api_reception_session():
    if not session.get('user_id'):
        return jsonify({'ok': False, 'error': 'login_required'}), 401
    if is_department():
        return jsonify({'ok': False, 'error': 'forbidden'}), 403
    return None

def require_admin_session():
    if not session.get('user_id'):
        return redirect(url_for('index'))
    if not is_admin():
        return render_template('forbidden.html'), 403
    return None

def require_api_officer_session():
    if not session.get('user_id'):
        return jsonify({'ok': False, 'error': 'login_required'}), 401
    return None

def require_api_admin_session():
    if not session.get('user_id'):
        return jsonify({'ok': False, 'error': 'login_required'}), 401
    if not is_admin():
        return jsonify({'ok': False, 'error': 'forbidden'}), 403
    return None

def normalize_name(value):
    """Visitor and officer names are stored uppercase, with tidy spacing."""
    if not value:
        return value
    return ' '.join(str(value).split()).upper()

def digits_only(value):
    if not value:
        return ''
    return ''.join(ch for ch in str(value) if ch.isdigit())

def valid_phone(value):
    """Nigerian mobile-style numbers: exactly 11 digits."""
    digits = digits_only(value)
    return len(digits) == 11

def decode_data_image(photo_data):
    if not photo_data or not photo_data.startswith('data:image'):
        return None
    header, b64data = photo_data.split(',', 1)
    img_bytes = base64.b64decode(b64data)
    return Image.open(BytesIO(img_bytes)).convert('RGB')

def make_professional_portrait(img):
    img = ImageOps.exif_transpose(img).convert('RGB')
    img.thumbnail((520, 650), Image.Resampling.LANCZOS)
    portrait = Image.new('RGB', (480, 600), 'white')
    x = (portrait.width - img.width) // 2
    y = max(34, (portrait.height - img.height) // 2)
    portrait.paste(img, (x, y))
    return portrait

def crop_to_content(img, threshold=245):
    """Trim the uniform white canvas so hashing sees the face, not the border.

    Portraits are pasted onto a white 480x600 canvas, which means roughly a third
    of the image carries no facial information. Hashing the full canvas lets the
    background dominate the result and destroys discrimination between people.
    """
    gray = img.convert('L')
    mask = gray.point(lambda v: 255 if v < threshold else 0)
    bbox = mask.getbbox()
    if not bbox:
        return img
    # Guard against a degenerate crop.
    if (bbox[2] - bbox[0]) < 16 or (bbox[3] - bbox[1]) < 16:
        return img
    return img.crop(bbox)


def normalize_for_hash(img):
    """Normalise brightness and contrast so hashing tolerates lighting changes.

    Without this, a uniformly brighter or darker frame produces a completely
    different hash for the same person.
    """
    gray = ImageOps.grayscale(img)
    return ImageOps.autocontrast(gray, cutoff=1)


def image_fingerprint(img, size=16):
    """Difference hash: compare horizontally adjacent pixels on a grey image."""
    gray = normalize_for_hash(img).resize((size + 1, size), Image.Resampling.LANCZOS)
    pixels = list(gray.getdata())
    bits = []
    for row in range(size):
        start = row * (size + 1)
        for col in range(size):
            bits.append(1 if pixels[start + col] > pixels[start + col + 1] else 0)
    return bits


def average_fingerprint(img, size=16):
    """Average hash: threshold each pixel against the mean of the image."""
    gray = normalize_for_hash(img).resize((size, size), Image.Resampling.LANCZOS)
    pixels = list(gray.getdata())
    avg = sum(pixels) / len(pixels)
    return [pixel >= avg for pixel in pixels]


def center_fingerprint(img):
    """Average hash of a centred square crop, for framing tolerance."""
    width, height = img.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    crop = img.crop((left, top, left + side, top + side))
    return average_fingerprint(crop)


def fingerprint_distance(left, right):
    return sum(1 for a, b in zip(left, right) if a != b)

FINGERPRINT_VERSION = 'v2'

def encode_fingerprint(bits):
    return ''.join('1' if bit else '0' for bit in bits)

def decode_fingerprint(value):
    if not value:
        return None
    if value.startswith(FINGERPRINT_VERSION + ':'):
        value = value[len(FINGERPRINT_VERSION) + 1:]
    if '|' in value:
        return [
            [char == '1' for char in part]
            for part in value.split('|')
            if part
        ]
    return [char == '1' for char in value]

def portrait_fingerprints(img):
    """Fingerprints computed from the cropped face region, not the white canvas.

    The portrait is normalised onto a white canvas first, so the content crop
    reliably removes the empty border before hashing.
    """
    portrait = make_professional_portrait(img)
    content = crop_to_content(portrait)
    return [
        image_fingerprint(content),
        average_fingerprint(content),
        center_fingerprint(content)
    ]

def encode_fingerprints(fingerprints):
    body = '|'.join(encode_fingerprint(bits) for bits in fingerprints)
    return f"{FINGERPRINT_VERSION}:{body}"

def fingerprint_match_distance(probe_fingerprints, stored_value):
    """Total Hamming distance between probe and stored fingerprints.

    Distances are **summed** across the fingerprint components, not minimised.
    Taking the minimum would mean a match only needs one component to be close,
    which collapses discrimination: three components each scoring ~25 would
    report 25 instead of ~75 and match almost anyone.

    Returns None when the stored value is missing or was produced by an older
    fingerprint format, so callers can rebuild it rather than silently failing.
    """
    if not stored_value:
        return None
    if not stored_value.startswith(FINGERPRINT_VERSION + ':'):
        return None

    stored = decode_fingerprint(stored_value)
    if not stored:
        return None

    if stored and isinstance(stored[0], bool):
        stored = [stored]

    # Preferred path: components correspond one-to-one, so sum them.
    if len(probe_fingerprints) == len(stored):
        total = 0
        for probe, candidate in zip(probe_fingerprints, stored):
            if len(probe) != len(candidate):
                break
            total += fingerprint_distance(probe, candidate)
        else:
            return total

    # Fallback for mismatched shapes: best single-component distance.
    distances = []
    for probe in probe_fingerprints:
        for candidate in stored:
            if len(probe) == len(candidate):
                distances.append(fingerprint_distance(probe, candidate))
    return min(distances) if distances else None

# Maximum total Hamming distance (of 768 bits) still treated as the same person.
#
# Measured on synthetic test faces with the v2 fingerprints:
#   identical image ................ 0
#   same person, mild lighting ..... up to ~10
#   different people ............... 38 or more (average ~75)
#
# 60 sits in the gap. It is deliberately conservative: a false "verified" is far
# more damaging than asking someone to try again.
#
# IMPORTANT: this is perceptual image hashing, not biometric face recognition.
# It compares overall image structure and is sensitive to pose, expression and
# strong lighting changes. Treat a match as a convenience signal, never as proof
# of identity. See docs/TECHNICAL_DOCUMENTATION.md section 13.
FINGERPRINT_MATCH_THRESHOLD = 60

# Total bits in a v2 fingerprint set (16x16 dhash + 16x16 ahash + 16x16 centre).
FINGERPRINT_BITS = 16 * 16 * 3

def match_score(distance):
    """Convert a Hamming distance into a 0..1 confidence score."""
    if distance is None:
        return 0
    return max(0, round((FINGERPRINT_BITS - distance) / FINGERPRINT_BITS, 2))

def save_visitor_photo(photo_data):
    img = decode_data_image(photo_data)
    if not img:
        return None, None

    portrait = make_professional_portrait(img)
    photos_dir = os.path.join(app.instance_path, 'photos')
    os.makedirs(photos_dir, exist_ok=True)
    filename = f"visitor_{uuid.uuid4().hex}.jpg"
    full_path = os.path.join(photos_dir, filename)
    portrait.save(full_path, format='JPEG', quality=88, optimize=True)
    # Use portrait_fingerprints so the stored value matches the probe path
    # (content-cropped and normalised). Hashing the raw portrait here would
    # produce a fingerprint that never matches a probe.
    return full_path, encode_fingerprints(portrait_fingerprints(img))

def portrait_data_url(photo_data):
    img = decode_data_image(photo_data)
    if not img:
        return None
    portrait = make_professional_portrait(img)
    output = BytesIO()
    portrait.save(output, format='JPEG', quality=88, optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode('ascii')
    return f"data:image/jpeg;base64,{encoded}"

def visitor_to_dict(visitor, include_photo_url=True):
    data = {
        'id': visitor.id,
        'fullname': visitor.fullname,
        'phone': visitor.phone,
        'email': visitor.email,
        'address': visitor.address,
        'organization': visitor.organization,
        'id_type': visitor.id_type,
        'id_number': visitor.id_number,
        'gender': visitor.gender,
        'created_by': visitor.created_by,
        'created_at': visitor.created_at.isoformat() if visitor.created_at else None,
        'updated_at': visitor.updated_at.isoformat() if visitor.updated_at else None,
        'has_photo': bool(visitor.photo_path)
    }
    if include_photo_url and visitor.photo_path:
        data['photo_url'] = url_for('visitor_photo', visitor_id=visitor.id)
    return data

def visit_to_dict(visit, visitor=None):
    visitor = visitor or db.session.get(Visitor, visit.visitor_id)
    return {
        'id': visit.id,
        'visitor_id': visit.visitor_id,
        'visitor_name': visitor.fullname if visitor else '',
        'visitor_phone': visitor.phone if visitor else '',
        'visit_no': visit.visit_no,
        'date': visit.date.isoformat() if visit.date else None,
        'purpose': visit.purpose,
        'host_name': visit.host_name,
        'destination': visit.destination,
        'documents': visit.documents,
        'group_size': visit.group_size,
        'status': visit.status,
        'signin_time': visit.signin_time.isoformat() if visit.signin_time else None,
        'signout_time': visit.signout_time.isoformat() if visit.signout_time else None,
        'qr_path': visit.qr_path,
        'created_by': visit.created_by,
        'signed_out_by': visit.signed_out_by
    }

def visitor_history(visitor_id):
    visits = Visit.query.filter_by(visitor_id=visitor_id).order_by(Visit.signin_time.desc()).all()
    return [visit_to_dict(visit) for visit in visits]

def active_visit_for_visitor(visitor_id, on_date=None):
    """Return the visitor's currently active (signed-in) visit, if any.

    A visitor may only hold one active visit per day, so this is used to
    prevent a second check-in while an earlier visit is still open.
    """
    query = Visit.query.filter_by(visitor_id=visitor_id, status='in')
    if on_date is not None:
        query = query.filter(Visit.date == on_date)
    return query.order_by(Visit.signin_time.desc()).first()

def clean_form_value(data, key):
    value = data.get(key)
    if value is None:
        return None
    value = value.strip()
    return value or None

@app.route('/checkin')
def checkin():
    gate = require_reception_session()
    if gate:
        return gate
    return render_template('checkin.html')

@app.route('/verify')
def verify():
    """Camera-only visitor verification for department staff.

    Deliberately minimal: the operator sees a live camera and a status result,
    never visitor records or personal details.
    """
    gate = require_officer_session()
    if gate:
        return gate
    return render_template('verify.html')

def verification_result(visitor, active_visit, distance):
    """Build the privacy-limited payload returned to the verification screen."""
    if not visitor:
        return {
            'status': 'unknown',
            'label': 'NOT VERIFIED',
            'message': 'No matching visitor record found.',
            'visitor_name': None,
            'visit_no': None,
            'signed_in_at': None,
            'match_score': 0
        }

    if active_visit:
        return {
            'status': 'active',
            'label': 'VERIFIED — ON SITE',
            'message': 'Visitor is verified and currently signed in.',
            'visitor_name': visitor.fullname,
            'visit_no': active_visit.visit_no,
            'signed_in_at': active_visit.signin_time.strftime('%H:%M') if active_visit.signin_time else None,
            'match_score': match_score(distance)
        }

    return {
        'status': 'inactive',
        'label': 'VERIFIED — NOT SIGNED IN',
        'message': 'Visitor is known but has no active visit today.',
        'visitor_name': visitor.fullname,
        'visit_no': None,
        'signed_in_at': None,
        'match_score': match_score(distance)
    }

@app.route('/api/verify/face', methods=['POST'])
def api_verify_face():
    """Match a camera frame and report the visitor's sign-in status only.

    Returns no contact details, address, ID numbers or visit history — the
    department operator only needs to know whether the person may proceed.
    """
    gate = require_api_officer_session()
    if gate:
        return gate

    photo_data = request.form.get('photo_data')
    img = decode_data_image(photo_data)
    if not img:
        return jsonify({'ok': False, 'error': 'invalid_photo'}), 400

    probe = portrait_fingerprints(img)
    best = None
    best_distance = None

    visitors = Visitor.query.filter(Visitor.photo_path.isnot(None)).all()
    for visitor in visitors:
        try:
            distance = fingerprint_match_distance(probe, visitor.face_fingerprint)
            if distance is None and visitor.photo_path and os.path.exists(visitor.photo_path):
                stored_img = Image.open(visitor.photo_path).convert('RGB')
                visitor.face_fingerprint = encode_fingerprints(portrait_fingerprints(stored_img))
                distance = fingerprint_match_distance(probe, visitor.face_fingerprint)
            if distance is None:
                continue
        except Exception as e:
            print("Verify compare error:", e)
            continue

        if best_distance is None or distance < best_distance:
            best = visitor
            best_distance = distance

    if best and best_distance is not None and best_distance <= FINGERPRINT_MATCH_THRESHOLD:
        db.session.commit()
        active = active_visit_for_visitor(best.id, date.today())
        result = verification_result(best, active, best_distance)
        result['ok'] = True
        return jsonify(result)

    result = verification_result(None, None, None)
    result['ok'] = True
    return jsonify(result)

@app.route('/api/verify/status')
def api_verify_status():
    """Lightweight health check for the verification station."""
    gate = require_api_officer_session()
    if gate:
        return gate
    return jsonify({
        'ok': True,
        'visitors_with_photos': Visitor.query.filter(Visitor.photo_path.isnot(None)).count(),
        'active_visits': Visit.query.filter(Visit.status == 'in').count()
    })

@app.route('/admin')
def admin():
    gate = require_admin_session()
    if gate:
        return gate
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/dashboard')
def admin_dashboard():
    gate = require_admin_session()
    if gate:
        return gate

    today = date.today()
    stats = {
        'visitors_total': Visitor.query.count(),
        'visits_total': Visit.query.count(),
        'visits_today': Visit.query.filter(Visit.date == today).count(),
        'active_visits': Visit.query.filter(Visit.status == 'in').count(),
        'users_total': User.query.count(),
        'users_active': User.query.filter(User.active.is_(True)).count(),
        'roles_total': Role.query.count(),
        'locations_total': Location.query.count()
    }

    recent_visits = Visit.query.order_by(Visit.signin_time.desc()).limit(8).all()
    recent_rows = []
    for v in recent_visits:
        visitor = db.session.get(Visitor, v.visitor_id)
        recent_rows.append({
            'visit_no': v.visit_no,
            'fullname': visitor.fullname if visitor else '',
            'date': v.date.strftime('%Y-%m-%d') if v.date else '',
            'status': v.status,
            'purpose': v.purpose
        })

    return render_template('admin_dashboard.html', stats=stats, recent_visits=recent_rows)

@app.route('/admin/users')
def admin_users():
    gate = require_admin_session()
    if gate:
        return gate

    users = User.query.order_by(User.fullname).all()
    roles = Role.query.order_by(Role.name).all()
    locations = Location.query.order_by(Location.name).all()

    rows = []
    for u in users:
        rows.append({
            'id': u.id,
            'service_no': u.service_no,
            'fullname': u.fullname,
            'rank': u.rank or '',
            'email': u.email or '',
            'phone': u.phone or '',
            'role_id': u.role_id,
            'role_name': u.role.name if u.role else '',
            'active': u.active,
            'last_login_at': u.last_login_at.strftime('%Y-%m-%d %H:%M') if u.last_login_at else 'Never'
        })

    return render_template(
        'admin_users.html',
        users=rows,
        ranks=NCS_RANKS,
        roles=[{'id': r.id, 'name': r.name, 'description': r.description or ''} for r in roles],
        locations=[{'id': l.id, 'name': l.name, 'type': l.type or ''} for l in locations]
    )

@app.route('/admin/roles')
def admin_roles():
    gate = require_admin_session()
    if gate:
        return gate

    roles = Role.query.order_by(Role.name).all()
    rows = []
    for r in roles:
        rows.append({
            'id': r.id,
            'name': r.name,
            'description': r.description or '',
            'landing_endpoint': r.landing_endpoint or '',
            'user_count': User.query.filter_by(role_id=r.id).count()
        })
    return render_template('admin_roles.html', roles=rows)

@app.route('/admin/locations')
def admin_locations():
    gate = require_admin_session()
    if gate:
        return gate

    locations = Location.query.order_by(Location.type, Location.name).all()
    rows = []
    for l in locations:
        parent = db.session.get(Location, l.parent_id) if l.parent_id else None
        rows.append({
            'id': l.id,
            'name': l.name,
            'type': l.type or '',
            'parent_name': parent.name if parent else ''
        })
    return render_template('admin_locations.html', locations=rows)

@app.route('/admin/reports')
def admin_reports():
    gate = require_admin_session()
    if gate:
        return gate

    query = build_history_query(request.args)
    total = query.count()
    visits = query.order_by(Visit.signin_time.desc()).limit(500).all()

    rows = []
    for v in visits:
        visitor = db.session.get(Visitor, v.visitor_id)
        rows.append({
            'visit_no': v.visit_no,
            'fullname': visitor.fullname if visitor else '',
            'phone': visitor.phone if visitor else '',
            'purpose': v.purpose,
            'host_name': v.host_name or '',
            'destination': v.destination or '',
            'status': v.status,
            'date': v.date.strftime('%Y-%m-%d') if v.date else '',
            'signin_time': v.signin_time.strftime('%H:%M') if v.signin_time else '',
            'signout_time': v.signout_time.strftime('%H:%M') if v.signout_time else '',
            'created_by': v.created_by or ''
        })

    year_rows = db.session.query(
        func.strftime('%Y', Visit.date)
    ).distinct().order_by(func.strftime('%Y', Visit.date).desc()).all()
    years = [int(r[0]) for r in year_rows if r[0]]

    filters = {
        'q': (request.args.get('q') or '').strip(),
        'status': (request.args.get('status') or '').strip(),
        'purpose': (request.args.get('purpose') or '').strip(),
        'month': (request.args.get('month') or '').strip(),
        'year': (request.args.get('year') or '').strip(),
        'date_from': (request.args.get('date_from') or '').strip(),
        'date_to': (request.args.get('date_to') or '').strip()
    }

    return render_template(
        'admin_reports.html',
        visits=rows,
        filters=filters,
        years=years,
        total=total,
        shown=len(rows)
    )

# ---------------------------------------------------------------- Admin APIs

@app.route('/api/admin/users', methods=['POST'])
def api_create_user():
    gate = require_api_admin_session()
    if gate:
        return gate

    data = request.form
    service_no = clean_form_value(data, 'service_no')
    fullname = normalize_name(clean_form_value(data, 'fullname'))
    password = data.get('password') or ''
    role_id = parse_int_arg(data.get('role_id'))

    if not service_no or not fullname or not password or not role_id:
        return jsonify({'ok': False, 'error': 'missing_required_fields'}), 400

    if len(password) < 6:
        return jsonify({
            'ok': False,
            'error': 'weak_password',
            'message': 'Password must be at least 6 characters.'
        }), 400

    if not db.session.get(Role, role_id):
        return jsonify({'ok': False, 'error': 'invalid_role'}), 400

    if User.query.filter(func.lower(User.service_no) == service_no.lower()).first():
        return jsonify({'ok': False, 'error': 'service_no_exists'}), 409

    phone = digits_only(clean_form_value(data, 'phone'))
    if phone and not valid_phone(phone):
        return jsonify({
            'ok': False,
            'error': 'invalid_phone',
            'message': 'Phone number must contain exactly 11 digits.'
        }), 400

    rank = clean_form_value(data, 'rank')
    if rank and rank not in NCS_RANKS:
        return jsonify({
            'ok': False,
            'error': 'invalid_rank',
            'message': 'Select a rank from the list.'
        }), 400

    user = User(
        service_no=service_no,
        fullname=fullname,
        role_id=role_id,
        rank=clean_form_value(data, 'rank'),
        email=clean_form_value(data, 'email'),
        phone=phone or None,
        location_type=clean_form_value(data, 'location_type'),
        department_id=parse_int_arg(data.get('department_id')),
        unit_id=parse_int_arg(data.get('unit_id')),
        active=True
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({'ok': True, 'user_id': user.id})

@app.route('/api/admin/users/<int:user_id>/update', methods=['POST'])
def api_update_user(user_id):
    gate = require_api_admin_session()
    if gate:
        return gate

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'ok': False, 'error': 'user_not_found'}), 404

    data = request.form
    fullname = normalize_name(clean_form_value(data, 'fullname'))
    role_id = parse_int_arg(data.get('role_id'))

    if not fullname or not role_id:
        return jsonify({'ok': False, 'error': 'missing_required_fields'}), 400

    if not db.session.get(Role, role_id):
        return jsonify({'ok': False, 'error': 'invalid_role'}), 400

    phone = digits_only(clean_form_value(data, 'phone'))
    if phone and not valid_phone(phone):
        return jsonify({
            'ok': False,
            'error': 'invalid_phone',
            'message': 'Phone number must contain exactly 11 digits.'
        }), 400

    rank = clean_form_value(data, 'rank')
    # Accept a rank from the standard list, or the user's existing value so an
    # edit does not force a change to a legacy rank.
    if rank and rank not in NCS_RANKS and rank != user.rank:
        return jsonify({
            'ok': False,
            'error': 'invalid_rank',
            'message': 'Select a rank from the list.'
        }), 400

    # Never let an admin lock themselves out of the admin module.
    if user.id == session.get('user_id'):
        admin_role = Role.query.filter_by(name=ROLE_ADMIN).first()
        if admin_role and role_id != admin_role.id:
            return jsonify({
                'ok': False,
                'error': 'cannot_change_own_role',
                'message': 'You cannot change your own role.'
            }), 400

    user.fullname = fullname
    user.role_id = role_id
    user.rank = clean_form_value(data, 'rank')
    user.email = clean_form_value(data, 'email')
    user.phone = phone or None
    user.location_type = clean_form_value(data, 'location_type')
    user.department_id = parse_int_arg(data.get('department_id'))
    user.unit_id = parse_int_arg(data.get('unit_id'))
    user.updated_at = datetime.utcnow()

    new_password = data.get('password') or ''
    if new_password:
        if len(new_password) < 6:
            return jsonify({
                'ok': False,
                'error': 'weak_password',
                'message': 'Password must be at least 6 characters.'
            }), 400
        user.set_password(new_password)

    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/users/<int:user_id>/toggle', methods=['POST'])
def api_toggle_user(user_id):
    gate = require_api_admin_session()
    if gate:
        return gate

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'ok': False, 'error': 'user_not_found'}), 404

    if user.id == session.get('user_id'):
        return jsonify({
            'ok': False,
            'error': 'cannot_disable_self',
            'message': 'You cannot disable your own account.'
        }), 400

    user.active = not user.active
    db.session.commit()
    return jsonify({'ok': True, 'active': user.active})

@app.route('/api/admin/users/<int:user_id>/delete', methods=['POST'])
def api_delete_user(user_id):
    gate = require_api_admin_session()
    if gate:
        return gate

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'ok': False, 'error': 'user_not_found'}), 404

    if user.id == session.get('user_id'):
        return jsonify({
            'ok': False,
            'error': 'cannot_delete_self',
            'message': 'You cannot delete your own account.'
        }), 400

    db.session.delete(user)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/roles', methods=['POST'])
def api_create_role():
    gate = require_api_admin_session()
    if gate:
        return gate

    data = request.form
    name = clean_form_value(data, 'name')
    if not name:
        return jsonify({'ok': False, 'error': 'missing_required_fields'}), 400

    if Role.query.filter(func.lower(Role.name) == name.lower()).first():
        return jsonify({'ok': False, 'error': 'role_exists'}), 409

    landing = clean_form_value(data, 'landing_endpoint') or 'checkin'
    if landing not in app.view_functions:
        return jsonify({
            'ok': False,
            'error': 'invalid_landing',
            'message': 'Landing endpoint does not exist.'
        }), 400

    role = Role(
        name=name,
        description=clean_form_value(data, 'description'),
        landing_endpoint=landing
    )
    db.session.add(role)
    db.session.commit()
    return jsonify({'ok': True, 'role_id': role.id})

@app.route('/api/admin/roles/<int:role_id>/update', methods=['POST'])
def api_update_role(role_id):
    gate = require_api_admin_session()
    if gate:
        return gate

    role = db.session.get(Role, role_id)
    if not role:
        return jsonify({'ok': False, 'error': 'role_not_found'}), 404

    data = request.form
    name = clean_form_value(data, 'name')
    if not name:
        return jsonify({'ok': False, 'error': 'missing_required_fields'}), 400

    clash = Role.query.filter(
        func.lower(Role.name) == name.lower(), Role.id != role.id
    ).first()
    if clash:
        return jsonify({'ok': False, 'error': 'role_exists'}), 409

    landing = clean_form_value(data, 'landing_endpoint') or 'checkin'
    if landing not in app.view_functions:
        return jsonify({
            'ok': False,
            'error': 'invalid_landing',
            'message': 'Landing endpoint does not exist.'
        }), 400

    role.name = name
    role.description = clean_form_value(data, 'description')
    role.landing_endpoint = landing
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/roles/<int:role_id>/delete', methods=['POST'])
def api_delete_role(role_id):
    gate = require_api_admin_session()
    if gate:
        return gate

    role = db.session.get(Role, role_id)
    if not role:
        return jsonify({'ok': False, 'error': 'role_not_found'}), 404

    if role.name in (ROLE_ADMIN, ROLE_OFFICER):
        return jsonify({
            'ok': False,
            'error': 'protected_role',
            'message': 'Built-in roles cannot be deleted.'
        }), 400

    if User.query.filter_by(role_id=role.id).count():
        return jsonify({
            'ok': False,
            'error': 'role_in_use',
            'message': 'Reassign users before deleting this role.'
        }), 409

    db.session.delete(role)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/locations', methods=['POST'])
def api_create_location():
    gate = require_api_admin_session()
    if gate:
        return gate

    data = request.form
    name = normalize_name(clean_form_value(data, 'name'))
    loc_type = clean_form_value(data, 'type')
    if not name or not loc_type:
        return jsonify({'ok': False, 'error': 'missing_required_fields'}), 400

    if loc_type not in ('department', 'command', 'unit'):
        return jsonify({'ok': False, 'error': 'invalid_type'}), 400

    parent_id = parse_int_arg(data.get('parent_id'))
    if parent_id and not db.session.get(Location, parent_id):
        return jsonify({'ok': False, 'error': 'invalid_parent'}), 400

    location = Location(name=name, type=loc_type, parent_id=parent_id)
    db.session.add(location)
    db.session.commit()
    return jsonify({'ok': True, 'location_id': location.id})

@app.route('/api/admin/locations/<int:location_id>/delete', methods=['POST'])
def api_delete_location(location_id):
    gate = require_api_admin_session()
    if gate:
        return gate

    location = db.session.get(Location, location_id)
    if not location:
        return jsonify({'ok': False, 'error': 'location_not_found'}), 404

    if Location.query.filter_by(parent_id=location.id).count():
        return jsonify({
            'ok': False,
            'error': 'location_has_children',
            'message': 'Remove child locations first.'
        }), 409

    db.session.delete(location)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/stats')
def api_admin_stats():
    gate = require_api_admin_session()
    if gate:
        return gate

    today = date.today()
    return jsonify({
        'ok': True,
        'stats': {
            'visitors_total': Visitor.query.count(),
            'visits_total': Visit.query.count(),
            'visits_today': Visit.query.filter(Visit.date == today).count(),
            'active_visits': Visit.query.filter(Visit.status == 'in').count(),
            'users_total': User.query.count(),
            'users_active': User.query.filter(User.active.is_(True)).count()
        }
    })

@app.route('/visits/today')
def visits_today():
    gate = require_reception_session()
    if gate:
        return gate
    today = date.today()
    visits = Visit.query.filter(Visit.date == today).order_by(Visit.signin_time.desc()).all()
    rows = []
    for v in visits:
        visitor = db.session.get(Visitor, v.visitor_id)
        rows.append({
            'id': v.id,
            'visit_no': v.visit_no,
            'fullname': visitor.fullname if visitor else '',
            'phone': visitor.phone if visitor else '',
            'purpose': v.purpose,
            'host_name': v.host_name or '',
            'destination': v.destination or '',
            'status': v.status,
            'signin_time': v.signin_time.strftime('%H:%M'),
            'signout_time': v.signout_time.strftime('%H:%M') if v.signout_time else '',
            'created_by': v.created_by or '',
            'signed_out_by': v.signed_out_by or ''
        })
    return render_template('visits_today.html', visits=rows)

@app.route('/api/visits')
def list_visits():
    gate = require_api_reception_session()
    if gate:
        return gate

    status = request.args.get('status', '').strip()
    query = Visit.query.order_by(Visit.signin_time.desc())
    if status:
        query = query.filter(Visit.status == status)

    visits = query.limit(150).all()
    return jsonify({'ok': True, 'visits': [visit_to_dict(visit) for visit in visits]})

def parse_date_arg(value):
    value = (value or '').strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None

def parse_int_arg(value):
    value = (value or '').strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None

def build_history_query(args):
    """Build the filtered Visit query used by the history page and its API."""
    query = Visit.query.join(Visitor, Visitor.id == Visit.visitor_id)

    q = (args.get('q') or '').strip()
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Visitor.fullname.ilike(like)) |
            (Visitor.phone.ilike(like)) |
            (Visit.visit_no.ilike(like)) |
            (Visit.host_name.ilike(like)) |
            (Visit.destination.ilike(like))
        )

    status = (args.get('status') or '').strip()
    if status in ('in', 'out'):
        query = query.filter(Visit.status == status)

    purpose = (args.get('purpose') or '').strip()
    if purpose in ('official', 'personal'):
        query = query.filter(Visit.purpose == purpose)

    year = parse_int_arg(args.get('year'))
    if year:
        query = query.filter(func.strftime('%Y', Visit.date) == f"{year:04d}")

    month = parse_int_arg(args.get('month'))
    if month and 1 <= month <= 12:
        query = query.filter(func.strftime('%m', Visit.date) == f"{month:02d}")

    date_from = parse_date_arg(args.get('date_from'))
    if date_from:
        query = query.filter(Visit.date >= date_from)

    date_to = parse_date_arg(args.get('date_to'))
    if date_to:
        query = query.filter(Visit.date <= date_to)

    return query

@app.route('/visits/history')
def visits_history():
    gate = require_reception_session()
    if gate:
        return gate

    filters = {
        'q': (request.args.get('q') or '').strip(),
        'status': (request.args.get('status') or '').strip(),
        'purpose': (request.args.get('purpose') or '').strip(),
        'month': (request.args.get('month') or '').strip(),
        'year': (request.args.get('year') or '').strip(),
        'date_from': (request.args.get('date_from') or '').strip(),
        'date_to': (request.args.get('date_to') or '').strip()
    }

    query = build_history_query(request.args)
    total = query.count()
    visits = query.order_by(Visit.signin_time.desc()).limit(500).all()

    rows = []
    for v in visits:
        visitor = db.session.get(Visitor, v.visitor_id)
        rows.append({
            'visit_no': v.visit_no,
            'fullname': visitor.fullname if visitor else '',
            'phone': visitor.phone if visitor else '',
            'purpose': v.purpose,
            'host_name': v.host_name or '',
            'destination': v.destination or '',
            'status': v.status,
            'date': v.date.strftime('%Y-%m-%d') if v.date else '',
            'signin_time': v.signin_time.strftime('%H:%M') if v.signin_time else '',
            'signout_time': v.signout_time.strftime('%H:%M') if v.signout_time else '',
            'created_by': v.created_by or '',
            'signed_out_by': v.signed_out_by or ''
        })

    # Distinct years present in the data, for the year dropdown.
    year_rows = db.session.query(
        func.strftime('%Y', Visit.date)
    ).distinct().order_by(func.strftime('%Y', Visit.date).desc()).all()
    years = [int(r[0]) for r in year_rows if r[0]]

    summary = {
        'total': total,
        'shown': len(rows),
        'in': sum(1 for r in rows if r['status'] == 'in'),
        'out': sum(1 for r in rows if r['status'] == 'out')
    }

    return render_template(
        'visits_history.html',
        visits=rows,
        filters=filters,
        years=years,
        summary=summary
    )

@app.route('/api/visits/history')
def api_visits_history():
    gate = require_api_reception_session()
    if gate:
        return gate

    query = build_history_query(request.args)
    total = query.count()
    visits = query.order_by(Visit.signin_time.desc()).limit(500).all()
    return jsonify({
        'ok': True,
        'total': total,
        'visits': [visit_to_dict(v) for v in visits]
    })

@app.route('/api/visitor/search')
def search_visitor():
    gate = require_api_reception_session()
    if gate:
        return gate
    q = request.args.get('q', '')
    v = Visitor.query.filter(
        (Visitor.phone.ilike(f"%{q}%")) | (Visitor.email.ilike(f"%{q}%"))
    ).first()
    if not v:
        return jsonify({'found': False})
    return jsonify({
        'found': True,
        'visitor': visitor_to_dict(v),
        'history': visitor_history(v.id)
    })

@app.route('/api/visitors')
def list_visitors():
    gate = require_api_reception_session()
    if gate:
        return gate

    q = request.args.get('q', '').strip()
    query = Visitor.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Visitor.fullname.ilike(like)) |
            (Visitor.phone.ilike(like)) |
            (Visitor.email.ilike(like)) |
            (Visitor.organization.ilike(like)) |
            (Visitor.id_number.ilike(like))
        )

    visitors = query.order_by(Visitor.created_at.desc()).limit(100).all()
    return jsonify({'ok': True, 'visitors': [visitor_to_dict(v) for v in visitors]})

@app.route('/api/visitor/<int:visitor_id>')
def get_visitor(visitor_id):
    gate = require_api_reception_session()
    if gate:
        return gate

    visitor = db.session.get(Visitor, visitor_id)
    if not visitor:
        return jsonify({'ok': False, 'error': 'visitor_not_found'}), 404

    return jsonify({
        'ok': True,
        'visitor': visitor_to_dict(visitor),
        'history': visitor_history(visitor.id)
    })

@app.route('/api/visitor/<int:visitor_id>/update', methods=['POST'])
def update_visitor(visitor_id):
    gate = require_api_reception_session()
    if gate:
        return gate

    visitor = db.session.get(Visitor, visitor_id)
    if not visitor:
        return jsonify({'ok': False, 'error': 'visitor_not_found'}), 404

    data = request.form
    fullname = normalize_name(clean_form_value(data, 'fullname'))
    raw_phone = clean_form_value(data, 'phone')
    phone = digits_only(raw_phone)
    email = clean_form_value(data, 'email')

    if not fullname or not raw_phone:
        return jsonify({'ok': False, 'error': 'missing_required_fields'}), 400

    if not valid_phone(phone):
        return jsonify({
            'ok': False,
            'error': 'invalid_phone',
            'message': 'Phone number must contain exactly 11 digits.'
        }), 400

    phone_owner = Visitor.query.filter(Visitor.phone == phone, Visitor.id != visitor.id).first()
    if phone_owner:
        return jsonify({
            'ok': False,
            'error': 'visitor_already_exists',
            'duplicate_field': 'phone',
            'visitor': visitor_to_dict(phone_owner),
            'history': visitor_history(phone_owner.id)
        }), 409

    if email:
        email_owner = Visitor.query.filter(Visitor.email.ilike(email), Visitor.id != visitor.id).first()
        if email_owner:
            return jsonify({
                'ok': False,
                'error': 'visitor_already_exists',
                'duplicate_field': 'email',
                'visitor': visitor_to_dict(email_owner),
                'history': visitor_history(email_owner.id)
            }), 409

    visitor.fullname = fullname
    visitor.phone = phone
    visitor.email = email
    visitor.gender = clean_form_value(data, 'gender')
    visitor.address = clean_form_value(data, 'address')
    visitor.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'ok': True,
        'visitor': visitor_to_dict(visitor),
        'history': visitor_history(visitor.id)
    })

@app.route('/api/visitor/<int:visitor_id>/photo')
def visitor_photo(visitor_id):
    gate = require_reception_session()
    if gate:
        return gate

    visitor = db.session.get(Visitor, visitor_id)
    if not visitor or not visitor.photo_path or not os.path.exists(visitor.photo_path):
        return jsonify({'ok': False, 'error': 'photo_not_found'}), 404

    return send_file(visitor.photo_path, mimetype='image/jpeg')

@app.route('/api/visitors/rebuild-face-index', methods=['POST'])
def rebuild_face_index():
    gate = require_api_reception_session()
    if gate:
        return gate

    updated = 0
    skipped = 0
    visitors = Visitor.query.filter(Visitor.photo_path.isnot(None)).all()
    for visitor in visitors:
        if not visitor.photo_path or not os.path.exists(visitor.photo_path):
            skipped += 1
            continue
        try:
            stored_img = Image.open(visitor.photo_path).convert('RGB')
            visitor.face_fingerprint = encode_fingerprints(portrait_fingerprints(stored_img))
            updated += 1
        except Exception as e:
            print("Face index rebuild error:", e)
            skipped += 1

    db.session.commit()
    return jsonify({'ok': True, 'updated': updated, 'skipped': skipped})

@app.route('/api/visitor/face-search', methods=['POST'])
def face_search_visitor():
    gate = require_api_reception_session()
    if gate:
        return gate

    photo_data = request.form.get('photo_data')
    portrait_url = portrait_data_url(photo_data)
    img = decode_data_image(photo_data)
    if not img:
        return jsonify({'ok': False, 'error': 'invalid_photo'}), 400

    probe = portrait_fingerprints(img)
    best = None
    best_distance = None

    visitors = Visitor.query.filter(Visitor.photo_path.isnot(None)).all()
    for visitor in visitors:
        try:
            distance = fingerprint_match_distance(probe, visitor.face_fingerprint)
            if distance is None and visitor.photo_path and os.path.exists(visitor.photo_path):
                stored_img = Image.open(visitor.photo_path).convert('RGB')
                stored_fingerprints = portrait_fingerprints(stored_img)
                visitor.face_fingerprint = encode_fingerprints(stored_fingerprints)
                distance = fingerprint_match_distance(probe, visitor.face_fingerprint)

            if distance is None:
                continue
        except Exception as e:
            print("Photo compare error:", e)
            continue

        if best_distance is None or distance < best_distance:
            best = visitor
            best_distance = distance

    if best and best_distance is not None and best_distance <= FINGERPRINT_MATCH_THRESHOLD:
        db.session.commit()
        return jsonify({
            'ok': True,
            'found': True,
            'match_score': match_score(best_distance),
            'portrait': portrait_url,
            'visitor': visitor_to_dict(best),
            'history': visitor_history(best.id)
        })

    return jsonify({
        'ok': True,
        'found': False,
        'match_score': match_score(best_distance),
        'portrait': portrait_url
    })

@app.route('/api/visitor/create', methods=['POST'])
def create_visitor():
    gate = require_api_reception_session()
    if gate:
        return gate
    try:
        data = request.form
        photo_data = data.get('photo_data')
        photo_path = None
        face_fingerprint = None
        fullname = normalize_name(clean_form_value(data, 'fullname'))
        raw_phone = clean_form_value(data, 'phone')
        phone = digits_only(raw_phone)
        email = clean_form_value(data, 'email')

        if not fullname or not raw_phone:
            return jsonify({'ok': False, 'error': 'missing_required_fields'}), 400

        if not valid_phone(phone):
            return jsonify({
                'ok': False,
                'error': 'invalid_phone',
                'message': 'Phone number must contain exactly 11 digits.'
            }), 400

        existing = Visitor.query.filter(Visitor.phone == phone).first()
        duplicate_field = 'phone' if existing else None
        if not existing and email:
            existing = Visitor.query.filter(Visitor.email.ilike(email)).first()
            duplicate_field = 'email' if existing else None

        if existing:
            return jsonify({
                'ok': False,
                'error': 'visitor_already_exists',
                'duplicate_field': duplicate_field,
                'visitor': visitor_to_dict(existing),
                'history': visitor_history(existing.id)
            }), 409

        if photo_data and photo_data.startswith('data:image'):
            try:
                photo_path, face_fingerprint = save_visitor_photo(photo_data)
            except Exception as e:
                print("Photo decode error:", e)
                photo_path = None

        v = Visitor(
            fullname=fullname,
            phone=phone,
            email=email,
            address=clean_form_value(data, 'address'),
            organization=clean_form_value(data, 'organization'),
            id_type=clean_form_value(data, 'id_type'),
            id_number=clean_form_value(data, 'id_number'),
            gender=clean_form_value(data, 'gender'),
            photo_path=photo_path,
            face_fingerprint=face_fingerprint,
            created_by=session.get('desk_officer')
        )
        db.session.add(v)
        db.session.commit()
        return jsonify({'ok': True, 'visitor_id': v.id, 'visitor': visitor_to_dict(v)})
    except IntegrityError:
        db.session.rollback()
        return jsonify({'ok': False, 'error': 'duplicate_visitor'}), 409
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'ok': False, 'error': 'server_error'}), 500

@app.route('/api/visit/create', methods=['POST'])
def create_visit():
    gate = require_api_reception_session()
    if gate:
        return gate
    data = request.form
    try:
        visitor_id = int(data.get('visitor_id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'invalid_visitor'}), 400

    visitor = db.session.get(Visitor, visitor_id)
    if not visitor:
        return jsonify({'ok': False, 'error': 'visitor_not_found'}), 404

    purpose = clean_form_value(data, 'purpose')
    host_name = clean_form_value(data, 'host_name')
    if not purpose:
        return jsonify({'ok': False, 'error': 'missing_visit_fields'}), 400
    if purpose == 'personal' and not host_name:
        return jsonify({'ok': False, 'error': 'missing_host_name'}), 400

    active_visit = active_visit_for_visitor(visitor.id, date.today())
    if active_visit:
        return jsonify({
            'ok': False,
            'error': 'active_visit_exists',
            'message': (
                f"{visitor.fullname} already has an active visit today "
                f"({active_visit.visit_no}). Sign it out before creating a new one."
            ),
            'active_visit': visit_to_dict(active_visit, visitor)
        }), 409

    visit_no = generate_visit_no()
    vi = Visit(
        visitor_id=visitor.id,
        purpose=purpose,
        host_name=host_name,
        destination=clean_form_value(data, 'destination'),
        documents=clean_form_value(data, 'documents') or '',
        group_size=max(1, int(data.get('group_size', 1) or 1)),
        visit_no=visit_no,
        created_by=session.get('desk_officer')
    )
    db.session.add(vi)
    db.session.commit()

    qr_data = f"VISIT:{vi.id}|NO:{visit_no}"
    qr = qrcode.QRCode(version=1, box_size=10, border=3)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    qr_dir = os.path.join(app.static_folder, 'img')
    os.makedirs(qr_dir, exist_ok=True)
    qr_path = os.path.join(qr_dir, f"visit_{vi.id}.png")
    img.save(qr_path)
    vi.qr_path = f"img/visit_{vi.id}.png"
    db.session.commit()

    return jsonify({
        'ok': True,
        'visit_id': vi.id,
        'visit_no': visit_no,
        'qr': vi.qr_path,
        'visit': visit_to_dict(vi, visitor)
    })

@app.route('/api/visit/signout', methods=['POST'])
def signout_visit():
    gate = require_api_reception_session()
    if gate:
        return gate
    visit_no = request.form['visit_no']
    vi = Visit.query.filter_by(visit_no=visit_no, status='in').first()
    if not vi:
        return jsonify({'ok': False, 'error': 'Visit not found or already signed out'})
    vi.status = 'out'
    vi.signout_time = datetime.utcnow()
    vi.signed_out_by = session.get('desk_officer')
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/visit/<int:visit_id>/details')
def visit_details(visit_id):
    """Full visit and visitor detail for the reception details modal."""
    gate = require_api_reception_session()
    if gate:
        return gate

    visit = db.session.get(Visit, visit_id)
    if not visit:
        return jsonify({'ok': False, 'error': 'visit_not_found'}), 404

    visitor = db.session.get(Visitor, visit.visitor_id)

    data = visit_to_dict(visit, visitor)
    data.update({
        'visitor_email': visitor.email if visitor else None,
        'visitor_address': visitor.address if visitor else None,
        'visitor_organization': visitor.organization if visitor else None,
        'visitor_id_type': visitor.id_type if visitor else None,
        'visitor_id_number': visitor.id_number if visitor else None,
        'visitor_gender': visitor.gender if visitor else None,
        'has_photo': bool(visitor and visitor.photo_path),
        'photo_url': url_for('visitor_photo', visitor_id=visitor.id) if visitor and visitor.photo_path else None,
        'qr_url': url_for('static', filename=visit.qr_path) if visit.qr_path else None,
        'previous_visits': Visit.query.filter(
            Visit.visitor_id == visit.visitor_id,
            Visit.id != visit.id
        ).count()
    })

    # Human-readable timestamps for display.
    data['date_display'] = visit.date.strftime('%d %b %Y') if visit.date else None
    data['signin_display'] = visit.signin_time.strftime('%d %b %Y, %H:%M') if visit.signin_time else None
    data['signout_display'] = visit.signout_time.strftime('%d %b %Y, %H:%M') if visit.signout_time else None
    data['created_by_name'] = officer_display_name(visit.created_by)
    data['signed_out_by_name'] = officer_display_name(visit.signed_out_by)

    return jsonify({'ok': True, 'visit': data})

def officer_display_name(service_no):
    """Resolve a stored service number to a readable officer label."""
    if not service_no:
        return None
    user = User.query.filter(func.lower(User.service_no) == service_no.lower()).first()
    if not user:
        return service_no
    parts = [user.rank, user.fullname] if user.rank else [user.fullname]
    return f"{' '.join(parts)} ({user.service_no})"

_ngrok_cleaned = False

def start_ngrok_tunnel(port):
    """Open an ngrok tunnel and register cleanup so the agent does not linger.

    A lingering agent is the usual reason ngrok "stops working": the previous
    run's process keeps the reserved domain claimed, so the next start fails
    with ERR_NGROK_334 ("endpoint is already online"). We therefore disconnect
    any tunnel already registered with the local agent, and always kill the
    agent on exit.
    """
    try:
        from pyngrok import conf, ngrok
        from pyngrok.exception import PyngrokNgrokError
    except ImportError:
        print("Ngrok requested but pyngrok is not installed. Run: pip install pyngrok")
        return None

    auth_token = os.environ.get('NGROK_AUTHTOKEN')
    if auth_token:
        ngrok.set_auth_token(auth_token)

    # Drop tunnels left behind by a previous run of this process.
    try:
        for tunnel in ngrok.get_tunnels():
            ngrok.disconnect(tunnel.public_url)
            print(f"Closed previous tunnel: {tunnel.public_url}")
    except PyngrokNgrokError:
        pass  # No agent running; nothing to clean up.
    except Exception as exc:  # noqa: BLE001
        print(f"Could not inspect existing tunnels: {exc}")

    domain = os.environ.get('NGROK_DOMAIN')
    region = os.environ.get('NGROK_REGION')
    config = conf.PyngrokConfig(region=region) if region else None

    connect_kwargs = {'addr': port, 'proto': 'http'}
    if domain:
        connect_kwargs['domain'] = domain
    if config:
        connect_kwargs['pyngrok_config'] = config

    try:
        public_url = ngrok.connect(**connect_kwargs)
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        print("Ngrok tunnel could not be started.")
        if 'ERR_NGROK_334' in message or 'already online' in message:
            print(
                "  The endpoint is already online, which means another ngrok agent\n"
                "  still holds it. Stop it and try again:\n"
                "      pkill -f ngrok\n"
                "  Or use a different reserved domain via NGROK_DOMAIN."
            )
        elif 'authentication failed' in message.lower() or 'ERR_NGROK_4018' in message:
            print(
                "  Authentication failed. Set a valid token:\n"
                "      export NGROK_AUTHTOKEN=your_token"
            )
        else:
            print(f"  {message[:300]}")
        return None

    # Always release the agent when this process exits, so the next start is clean.
    register_ngrok_cleanup()
    print(f"Ngrok tunnel online: {public_url}")
    return public_url


def _shutdown_ngrok():
    """Disconnect tunnels and stop the agent. Safe to call more than once."""
    global _ngrok_cleaned
    if _ngrok_cleaned:
        return
    _ngrok_cleaned = True
    try:
        from pyngrok import ngrok
    except ImportError:
        return
    try:
        ngrok.disconnect()
    except Exception:  # noqa: BLE001
        pass
    try:
        ngrok.kill()
    except Exception:  # noqa: BLE001
        pass


def register_ngrok_cleanup():
    """Ensure the ngrok agent dies with this process.

    ``atexit`` alone is not enough: it does not run when the process is stopped
    with SIGTERM or SIGINT (Ctrl+C, ``kill``, ``pkill``), which is exactly how a
    server is normally stopped. Installing signal handlers covers those cases.
    """
    atexit.register(_shutdown_ngrok)

    def _handler(signum, frame):
        _shutdown_ngrok()
        # Restore default behaviour and re-raise so the exit code stays correct.
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass  # Not on the main thread, or unsupported platform.


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5100))
    debug = os.environ.get('FLASK_DEBUG', '1').lower() in {'1', 'true', 'yes', 'on'}
    enable_ngrok = os.environ.get('NCS_ENABLE_NGROK', '').lower() in {'1', 'true', 'yes', 'on'}

    # With the reloader, only the child process (WERKZEUG_RUN_MAIN=true) should
    # own the tunnel; the parent would otherwise hold a second agent.
    if enable_ngrok and (not debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true'):
        start_ngrok_tunnel(port)

    app.run(host='0.0.0.0', port=port, debug=debug)
