from flask import Flask, render_template, request, jsonify, redirect, send_file, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, date
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
import qrcode
from PIL import Image, ImageOps
import os
import base64
import uuid
from io import BytesIO

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
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
    if session.get('desk_officer'):
        return redirect(url_for('checkin'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    service_no = (
        request.form.get('service_no')
        or request.form.get('officer_name')
        or ''
    ).strip()
    password = request.form.get('password') or request.form.get('access_code') or ''
    expected_code = os.environ.get('DESK_OFFICER_CODE', 'NCS-1234')

    if service_no and password == expected_code:
        session['desk_officer'] = service_no
        return redirect(url_for('checkin'))

    return render_template(
        'login.html',
        error='Invalid service number or password.',
        service_no=service_no
    ), 401

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

def require_officer_session():
    if not session.get('desk_officer'):
        return redirect(url_for('index'))
    return None

def require_api_officer_session():
    if not session.get('desk_officer'):
        return jsonify({'ok': False, 'error': 'login_required'}), 401
    return None

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

def image_fingerprint(img):
    gray = ImageOps.grayscale(img.resize((9, 8), Image.Resampling.LANCZOS))
    pixels = list(gray.getdata())
    bits = []
    for row in range(8):
        start = row * 9
        for col in range(8):
            bits.append(1 if pixels[start + col] > pixels[start + col + 1] else 0)
    return bits

def average_fingerprint(img):
    gray = ImageOps.grayscale(img.resize((8, 8), Image.Resampling.LANCZOS))
    pixels = list(gray.getdata())
    avg = sum(pixels) / len(pixels)
    return [pixel >= avg for pixel in pixels]

def center_fingerprint(img):
    width, height = img.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    crop = img.crop((left, top, left + side, top + side))
    return average_fingerprint(crop)

def fingerprint_distance(left, right):
    return sum(1 for a, b in zip(left, right) if a != b)

def encode_fingerprint(bits):
    return ''.join('1' if bit else '0' for bit in bits)

def decode_fingerprint(value):
    if not value:
        return None
    if '|' in value:
        return [
            [char == '1' for char in part]
            for part in value.split('|')
            if part
        ]
    return [char == '1' for char in value]

def portrait_fingerprints(img):
    portrait = make_professional_portrait(img)
    return [
        image_fingerprint(portrait),
        average_fingerprint(portrait),
        center_fingerprint(portrait)
    ]

def encode_fingerprints(fingerprints):
    return '|'.join(encode_fingerprint(bits) for bits in fingerprints)

def fingerprint_match_distance(probe_fingerprints, stored_value):
    stored = decode_fingerprint(stored_value)
    if not stored:
        return None

    if stored and isinstance(stored[0], bool):
        stored = [stored]

    distances = []
    for probe in probe_fingerprints:
        for candidate in stored:
            if len(probe) == len(candidate):
                distances.append(fingerprint_distance(probe, candidate))
    return min(distances) if distances else None

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
    return full_path, encode_fingerprints([
        image_fingerprint(portrait),
        average_fingerprint(portrait),
        center_fingerprint(portrait)
    ])

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
    gate = require_officer_session()
    if gate:
        return gate
    return render_template('checkin.html')

@app.route('/admin')
def admin():
    gate = require_officer_session()
    if gate:
        return gate
    return render_template('admin.html')

@app.route('/visits/today')
def visits_today():
    gate = require_officer_session()
    if gate:
        return gate
    today = date.today()
    visits = Visit.query.filter(Visit.date == today).order_by(Visit.signin_time.desc()).all()
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
            'signin_time': v.signin_time.strftime('%H:%M'),
            'signout_time': v.signout_time.strftime('%H:%M') if v.signout_time else '',
            'created_by': v.created_by or '',
            'signed_out_by': v.signed_out_by or ''
        })
    return render_template('visits_today.html', visits=rows)

@app.route('/api/visits')
def list_visits():
    gate = require_api_officer_session()
    if gate:
        return gate

    status = request.args.get('status', '').strip()
    query = Visit.query.order_by(Visit.signin_time.desc())
    if status:
        query = query.filter(Visit.status == status)

    visits = query.limit(150).all()
    return jsonify({'ok': True, 'visits': [visit_to_dict(visit) for visit in visits]})

@app.route('/api/visitor/search')
def search_visitor():
    gate = require_api_officer_session()
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
    gate = require_api_officer_session()
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
    gate = require_api_officer_session()
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
    gate = require_api_officer_session()
    if gate:
        return gate

    visitor = db.session.get(Visitor, visitor_id)
    if not visitor:
        return jsonify({'ok': False, 'error': 'visitor_not_found'}), 404

    data = request.form
    fullname = clean_form_value(data, 'fullname')
    phone = clean_form_value(data, 'phone')
    email = clean_form_value(data, 'email')

    if not fullname or not phone:
        return jsonify({'ok': False, 'error': 'missing_required_fields'}), 400

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
    gate = require_officer_session()
    if gate:
        return gate

    visitor = db.session.get(Visitor, visitor_id)
    if not visitor or not visitor.photo_path or not os.path.exists(visitor.photo_path):
        return jsonify({'ok': False, 'error': 'photo_not_found'}), 404

    return send_file(visitor.photo_path, mimetype='image/jpeg')

@app.route('/api/visitors/rebuild-face-index', methods=['POST'])
def rebuild_face_index():
    gate = require_api_officer_session()
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
    gate = require_api_officer_session()
    if gate:
        return gate

    photo_data = request.form.get('photo_data')
    portrait_url = portrait_data_url(photo_data)
    img = decode_data_image(photo_data)
    if not img:
        return jsonify({'ok': False, 'error': 'invalid_photo'}), 400

    probe = portrait_fingerprints(img)
    best = None
    best_distance = 65

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

        if distance < best_distance:
            best = visitor
            best_distance = distance

    if best and best_distance <= 30:
        db.session.commit()
        return jsonify({
            'ok': True,
            'found': True,
            'match_score': max(0, round((64 - best_distance) / 64, 2)),
            'portrait': portrait_url,
            'visitor': visitor_to_dict(best),
            'history': visitor_history(best.id)
        })

    return jsonify({
        'ok': True,
        'found': False,
        'match_score': max(0, round((64 - best_distance) / 64, 2)) if best else 0,
        'portrait': portrait_url
    })

@app.route('/api/visitor/create', methods=['POST'])
def create_visitor():
    gate = require_api_officer_session()
    if gate:
        return gate
    try:
        data = request.form
        photo_data = data.get('photo_data')
        photo_path = None
        face_fingerprint = None
        fullname = clean_form_value(data, 'fullname')
        phone = clean_form_value(data, 'phone')
        email = clean_form_value(data, 'email')

        if not fullname or not phone:
            return jsonify({'ok': False, 'error': 'missing_required_fields'}), 400

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
    gate = require_api_officer_session()
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
    gate = require_api_officer_session()
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

def start_ngrok_tunnel(port):
    try:
        from pyngrok import conf, ngrok
    except ImportError:
        print("Ngrok requested but pyngrok is not installed. Run: pip install pyngrok")
        return

    auth_token = os.environ.get('NGROK_AUTHTOKEN')
    if auth_token:
        ngrok.set_auth_token(auth_token)

    domain = os.environ.get('NGROK_DOMAIN')
    region = os.environ.get('NGROK_REGION')
    config = conf.PyngrokConfig(region=region) if region else None

    connect_kwargs = {'addr': port, 'proto': 'http'}
    if domain:
        connect_kwargs['domain'] = domain
    if config:
        connect_kwargs['pyngrok_config'] = config

    public_url = ngrok.connect(**connect_kwargs)
    print(f"Ngrok tunnel online: {public_url}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5100))
    debug = os.environ.get('FLASK_DEBUG', '1').lower() in {'1', 'true', 'yes', 'on'}
    enable_ngrok = os.environ.get('NCS_ENABLE_NGROK', '').lower() in {'1', 'true', 'yes', 'on'}

    if enable_ngrok and (not debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true'):
        start_ngrok_tunnel(port)

    app.run(host='0.0.0.0', port=port, debug=debug)
