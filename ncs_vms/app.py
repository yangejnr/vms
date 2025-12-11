from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, date
from sqlalchemy import func
import qrcode
from PIL import Image
import os
import base64
import uuid

app = Flask(__name__)
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
    photo_path = db.Column(db.String(200), nullable=True)         # stored image file or path
    finger_template = db.Column(db.LargeBinary, nullable=True)    # for future fingerprint
    voice_sample_path = db.Column(db.String(200), nullable=True)  # for future voice sample
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(db.Integer, db.ForeignKey('visitor.id'))
    visit_no = db.Column(db.String(30), unique=True)
    date = db.Column(db.Date, default=date.today)
    purpose = db.Column(db.String(20))  # 'official','personal'
    documents = db.Column(db.Text)
    group_size = db.Column(db.Integer, default=1)
    status = db.Column(db.String(10), default='in')  # 'in','out'
    signin_time = db.Column(db.DateTime, default=datetime.utcnow)
    signout_time = db.Column(db.DateTime, nullable=True)
    qr_path = db.Column(db.String(200), nullable=True)
    synced = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

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
    return render_template('checkin.html')

@app.route('/checkin')
def checkin():
    return render_template('checkin.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/visits/today')
def visits_today():
    today = date.today()
    visits = Visit.query.filter(Visit.date == today).order_by(Visit.signin_time.desc()).all()
    rows = []
    for v in visits:
        visitor = Visitor.query.get(v.visitor_id)
        rows.append({
            'visit_no': v.visit_no,
            'fullname': visitor.fullname if visitor else '',
            'phone': visitor.phone if visitor else '',
            'purpose': v.purpose,
            'status': v.status,
            'signin_time': v.signin_time.strftime('%H:%M'),
            'signout_time': v.signout_time.strftime('%H:%M') if v.signout_time else ''
        })
    return render_template('visits_today.html', visits=rows)

@app.route('/api/visitor/search')
def search_visitor():
    q = request.args.get('q', '')
    v = Visitor.query.filter(
        (Visitor.phone.ilike(f"%{q}%")) | (Visitor.email.ilike(f"%{q}%"))
    ).first()
    if not v:
        return jsonify({'found': False})
    visits = Visit.query.filter_by(visitor_id=v.id).order_by(Visit.signin_time.desc()).all()
    history = [{
        'visit_no': vi.visit_no,
        'date': vi.date.isoformat(),
        'purpose': vi.purpose,
        'status': vi.status
    } for vi in visits]
    return jsonify({
        'found': True,
        'visitor': {
            'id': v.id,
            'fullname': v.fullname,
            'phone': v.phone,
            'email': v.email,
            'address': v.address,
            'photo_path': v.photo_path,
        },
        'history': history
    })

@app.route('/api/visitor/create', methods=['POST'])
def create_visitor():
    try:
        data = request.form
        photo_data = data.get('photo_data')
        photo_path = None

        # Only try to decode if there is a data URL
        if photo_data and photo_data.startswith('data:image'):
            try:
                header, b64data = photo_data.split(',', 1)
                img_bytes = base64.b64decode(b64data)
                photos_dir = os.path.join(app.instance_path, 'photos')
                os.makedirs(photos_dir, exist_ok=True)
                filename = f"visitor_{uuid.uuid4().hex}.jpg"
                full_path = os.path.join(photos_dir, filename)
                with open(full_path, 'wb') as f:
                    f.write(img_bytes)
                photo_path = full_path
            except Exception as e:
                print("Photo decode error:", e)
                photo_path = None

        v = Visitor(
            fullname=data['fullname'],
            phone=data['phone'],
            email=data.get('email') or None,
            address=data.get('address') or None,
            photo_path=photo_path
        )
        db.session.add(v)
        db.session.commit()
        return jsonify({'ok': True, 'visitor_id': v.id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'ok': False, 'error': 'server_error'}), 500

@app.route('/api/visit/create', methods=['POST'])
def create_visit():
    data = request.form
    visit_no = generate_visit_no()
    vi = Visit(
        visitor_id=data['visitor_id'],
        purpose=data['purpose'],
        documents=data.get('documents') or '',
        group_size=int(data.get('group_size', 1)),
        visit_no=visit_no
    )
    db.session.add(vi)
    db.session.commit()

    qr_data = f"VISIT:{vi.id}|NO:{visit_no}"
    qr = qrcode.QRCode(version=1, box_size=10, border=3)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    qr_dir = os.path.join('ncs_vms', 'static', 'img')
    os.makedirs(qr_dir, exist_ok=True)
    qr_path = os.path.join(qr_dir, f"visit_{vi.id}.png")
    img.save(qr_path)
    vi.qr_path = f"img/visit_{vi.id}.png"
    db.session.commit()

    return jsonify({'ok': True, 'visit_id': vi.id, 'visit_no': visit_no, 'qr': vi.qr_path})

@app.route('/api/visit/signout', methods=['POST'])
def signout_visit():
    visit_no = request.form['visit_no']
    vi = Visit.query.filter_by(visit_no=visit_no, status='in').first()
    if not vi:
        return jsonify({'ok': False, 'error': 'Visit not found or already signed out'})
    vi.status = 'out'
    vi.signout_time = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5100, debug=True)

