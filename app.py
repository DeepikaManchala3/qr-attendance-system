import os
import re
import base64
import uuid
from io import BytesIO
from datetime import datetime, timedelta, date


from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, flash
from flask_sqlalchemy import SQLAlchemy
from config import Config
import qrcode

# optional libs
try:
    import numpy as np
except Exception:
    np = None

try:
    import face_recognition
except Exception:
    face_recognition = None

from flask_migrate import Migrate

app = Flask(__name__)
app.config.from_object(Config)

# Defaults (override in config if you want)
app.config.setdefault("FACE_FOLDER", os.path.join(os.getcwd(), "face_data"))
app.config.setdefault("OPERATOR_PASSWORD", "admin123")
app.config.setdefault("QR_FOLDER", os.path.join(os.getcwd(), "qrcodes"))

db = SQLAlchemy(app)
migrate = Migrate(app, db)

from sqlalchemy.sql import func

ts = db.Column(db.DateTime, server_default=func.now())


# =========================
# Models
# =========================

class Student(db.Model):
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    sid = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    face_image = db.Column(db.String(200))
    face_encoding_path = db.Column(db.String(200))  # <--- make sure this exists
    face_images_prefix = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Book(db.Model):
    __tablename__ = "books"
    id = db.Column(db.Integer, primary_key=True)
    bid = db.Column(db.String(32), unique=True, index=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(200), nullable=True)
    available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Borrow(db.Model):
    __tablename__ = "borrows"
    id = db.Column(db.Integer, primary_key=True)
    student_sid = db.Column(db.String(32), db.ForeignKey("students.sid"), nullable=False)
    book_bid = db.Column(db.String(32), db.ForeignKey("books.bid"), nullable=False)
    borrow_dt = db.Column(db.DateTime, server_default=func.now(), nullable=True)
    due_dt = db.Column(db.DateTime, nullable=False)
    return_dt = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(16), default="BORROWED")  # BORROWED / RETURNED

# Classes / attendance
class ClassRoom(db.Model):
    __tablename__ = "classrooms"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, index=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    teacher = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AttendanceSession(db.Model):
    __tablename__ = "attendance_sessions"
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classrooms.id"), nullable=False)
    date_ = db.Column(db.Date, default=date.today, index=True)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(16), default="OPEN")  # OPEN / CLOSED
    classroom = db.relationship("ClassRoom")

class AttendanceRecord(db.Model):
    __tablename__ = "attendance_records"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("attendance_sessions.id"), nullable=False)
    student_sid = db.Column(db.String(32), db.ForeignKey("students.sid"), nullable=False)
    ts = db.Column(db.DateTime, server_default=func.now(), nullable=False)  # ← auto DB time
    present = db.Column(db.Boolean, default=True)
    __table_args__ = (db.UniqueConstraint("session_id", "student_sid", name="uq_session_student"),)

# Labs
class Lab(db.Model):
    __tablename__ = "labs"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, index=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    room = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LabLog(db.Model):
    __tablename__ = "lab_logs"
    id = db.Column(db.Integer, primary_key=True)
    lab_id = db.Column(db.Integer, db.ForeignKey("labs.id"), nullable=False)
    student_sid = db.Column(db.String(32), db.ForeignKey("students.sid"), nullable=False)
    action = db.Column(db.String(8), nullable=False)  # ENTRY or EXIT
    ts = db.Column(db.DateTime, server_default=func.now(), nullable=False, index=True)
    lab = db.relationship("Lab")

# Hostel
class HostelLog(db.Model):
    __tablename__ = "hostel_logs"
    id = db.Column(db.Integer, primary_key=True)
    gate = db.Column(db.String(80), default="Main Gate")
    student_sid = db.Column(db.String(32), db.ForeignKey("students.sid"), nullable=False)
    action = db.Column(db.String(8), nullable=False)  # ENTRY or EXIT
    ts = db.Column(db.DateTime, server_default=func.now(), nullable=False, index=True)


# =========================
# Helpers / filesystem
# =========================

def ensure_dirs():
    os.makedirs(app.config["QR_FOLDER"], exist_ok=True)
    os.makedirs(app.config["FACE_FOLDER"], exist_ok=True)

def save_qr(filename, data):
    ensure_dirs()
    path = os.path.join(app.config["QR_FOLDER"], filename)
    img = qrcode.make(data)
    img.save(path)
    return path

def _b64_to_bytes(data_url):
    # accepts "data:image/png;base64,...."
    if not data_url:
        return None
    m = re.match(r"data:(image/\w+);base64,(.+)", data_url)
    if not m:
        # maybe plain base64
        try:
            return base64.b64decode(data_url)
        except Exception:
            return None
    return base64.b64decode(m.group(2))

def save_face_images_and_encoding(sid, images_dataurls):
    """
    images_dataurls: list of data URLs (base64). Save raw images and attempt to compute face encoding.
    Returns (ok, message, encoding_path_or_none, prefix)
    """
    ensure_dirs()
    prefix = f"{sid}_{uuid.uuid4().hex}"
    saved_paths = []
    for i, d in enumerate(images_dataurls):
        b = _b64_to_bytes(d)
        if not b:
            continue
        fname = f"{prefix}_{i}.png"
        fpath = os.path.join(app.config["FACE_FOLDER"], fname)
        with open(fpath, "wb") as f:
            f.write(b)
        saved_paths.append(fpath)

    if not saved_paths:
        return False, "No valid images received", None, None

    # attempt to compute encoding using face_recognition
    if face_recognition and np:
        # take first face found from each image (if any) and average them
        encs = []
        for p in saved_paths:
            try:
                img = face_recognition.load_image_file(p)
                fcoords = face_recognition.face_locations(img, model="hog")
                if not fcoords:
                    continue
                e = face_recognition.face_encodings(img, known_face_locations=fcoords)
                if e:
                    encs.append(e[0])
            except Exception:
                continue
        if encs:
            # average encodings
            arr = np.array(encs)
            avg = arr.mean(axis=0)
            enc_path = os.path.join(app.config["FACE_FOLDER"], f"{prefix}_enc.npy")
            np.save(enc_path, avg)
            return True, "Saved images and encoding", enc_path, prefix
        else:
            # no encodings found but images saved — still mark enrolled but warn
            return True, "Saved images but no face encoding found (face_recognition couldn't detect)", None, prefix
    else:
        # face_recognition missing — just save images and mark enrolled
        return True, "Saved images (face_recognition not available)", None, prefix

def load_encoding(enc_path):
    if not enc_path or not np:
        return None
    try:
        return np.load(enc_path)
    except Exception:
        return None

def compare_face_encoding(enc_path, image_dataurl, tolerance=0.6):
    """
    Returns (bool, info). enc_path is path to saved .npy encoding.
    """
    if not face_recognition or not np:
        return False, "Face library not available"

    b = _b64_to_bytes(image_dataurl)
    if not b:
        return False, "Invalid image"

    try:
        buf = BytesIO(b)
        img = face_recognition.load_image_file(buf)
    except Exception:
        try:
            img = face_recognition.load_image_file(BytesIO(b))
        except Exception:
            return False, "Cannot read image for verification"

    fcoords = face_recognition.face_locations(img, model="hog")
    if not fcoords:
        return False, "No face detected in provided image"
    try:
        encs = face_recognition.face_encodings(img, known_face_locations=fcoords)
        if not encs:
            return False, "No face encodings found"
        probe = encs[0]
    except Exception:
        return False, "Failed to compute encoding"

    ref = load_encoding(enc_path)
    if ref is None:
        return False, "No reference encoding available"
    dist = np.linalg.norm(ref - probe)
    return (dist <= tolerance), f"distance={float(dist):.4f}"

# =========================
# Demo seed
# =========================

def seed_demo():
    # Students
    if Student.query.count() == 0:
        db.session.add_all([
            Student(sid="STU1001", name="Aarav Kumar", email="aarav@example.com"),
            Student(sid="STU1002", name="Isha Reddy", email="isha@example.com"),
            Student(sid="STU1003", name="Neha Gupta", email="neha@example.com"),
        ])
    # Books
    if Book.query.count() == 0:
        db.session.add_all([
            Book(bid="BK0001", title="Clean Code", author="Robert C. Martin"),
            Book(bid="BK0002", title="Design Patterns", author="GoF"),
            Book(bid="BK0003", title="Introduction to Algorithms", author="CLRS"),
        ])
    # Classes
    if ClassRoom.query.count() == 0:
        db.session.add_all([
            ClassRoom(code="CSE-A-DSA", name="DSA - CSE A", teacher="Prof. Rao"),
            ClassRoom(code="CSE-B-OS", name="Operating Systems - CSE B", teacher="Dr. Iyer"),
        ])
    # Labs
    if Lab.query.count() == 0:
        db.session.add_all([
            Lab(code="LAB-ML-01", name="ML Lab", room="L-301"),
            Lab(code="LAB-NET-02", name="Networks Lab", room="L-208"),
        ])
    db.session.commit()    

# =========================
# Pages
# =========================

@app.route("/")
def home():
    total_books = Book.query.count()
    available = Book.query.filter_by(available=True).count()
    total_students = Student.query.count()
    borrowed = Borrow.query.filter_by(status="BORROWED").count()

    # New stats for dashboard
    today = date.today()
    open_sessions = AttendanceSession.query.filter_by(status="OPEN").count()
    sessions_today = AttendanceSession.query.filter_by(date_=today).count()
    lab_entries_today = LabLog.query.filter(db.func.date(LabLog.ts) == today, LabLog.action == "ENTRY").count()
    hostel_entries_today = HostelLog.query.filter(db.func.date(HostelLog.ts) == today, HostelLog.action == "ENTRY").count()

    return render_template(
        "index.html",
        total_books=total_books,
        available=available,
        total_students=total_students,
        borrowed=borrowed,
        open_sessions=open_sessions,
        sessions_today=sessions_today,
        lab_entries_today=lab_entries_today,
        hostel_entries_today=hostel_entries_today
    )

@app.route("/admin")
def admin():
    return render_template("admin.html")

@app.route("/books")
def books():
    q = request.args.get("q", "").strip()
    qry = Book.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(db.or_(Book.title.ilike(like), Book.author.ilike(like), Book.bid.ilike(like)))
    items = qry.order_by(Book.created_at.desc()).all()
    return render_template("books.html", books=items, q=q)

@app.route("/students")
def students():
    q = request.args.get("q", "").strip()
    qry = Student.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(db.or_(Student.name.ilike(like), Student.sid.ilike(like)))
    items = qry.order_by(Student.created_at.desc()).all()
    return render_template("students.html", students=items, q=q)

@app.route("/scan")
def scan():
    return render_template("scan.html")

@app.route("/history")
def history():
    rows = Borrow.query.order_by(Borrow.borrow_dt.desc()).limit(200).all()
    return render_template("history.html", rows=rows)

@app.route("/classes")
def classes():
    items = ClassRoom.query.order_by(ClassRoom.created_at.desc()).all()
    return render_template("classes.html", classes=items)

@app.route("/attendance")
def attendance():
    classes = ClassRoom.query.order_by(ClassRoom.name.asc()).all()
    recent = AttendanceSession.query.order_by(AttendanceSession.start_time.desc()).limit(20).all()
    return render_template("attendance.html", classes=classes, recent=recent)

@app.route("/labs")
def labs_page():
    labs = Lab.query.order_by(Lab.name.asc()).all()
    recent = LabLog.query.order_by(LabLog.ts.desc()).limit(50).all()
    return render_template("labs.html", labs=labs, recent=recent)

@app.route("/hostel")
def hostel_page():
    recent = HostelLog.query.order_by(HostelLog.ts.desc()).limit(10).all()
    return render_template("hostel.html", recent=recent)

@app.route("/labdetail")
def labdetail():
    items = Lab.query.order_by(Lab.created_at.desc()).all()
    return render_template("labdetail.html", labdetail=items)

# =========================
# Admin actions
# =========================


@app.route("/admin/initdb")
def initdb():
    db.create_all()
    seed_demo()
    flash("Database initialized and demo data added.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/add-book", methods=["POST"])
def add_book():
    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    bid = request.form.get("bid", "").strip() or f"BK{str(int(datetime.utcnow().timestamp()))[-6:]}"
    if not title:
        flash("Title is required.", "danger")
        return redirect(url_for("books"))
    if Book.query.filter_by(bid=bid).first():
        flash("Book ID already exists.", "danger")
        return redirect(url_for("books"))
    book = Book(bid=bid, title=title, author=author, available=True)
    db.session.add(book)
    db.session.commit()
    save_qr(f"book_{bid}.png", f"BOOK:{bid}")
    flash(f"Book '{title}' added. QR generated.", "success")
    return redirect(url_for("books"))

@app.route("/admin/add-student", methods=["POST"])
def add_student():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    sid = request.form.get("sid", "").strip() or f"STU{str(int(datetime.utcnow().timestamp()))[-6:]}"
    if not name:
        flash("Name is required.", "danger")
        return redirect(url_for("students"))
    if Student.query.filter_by(sid=sid).first():
        flash("Student ID already exists.", "danger")
        return redirect(url_for("students"))

    # create student; face_image defaults to None
    student = Student(sid=sid, name=name, email=email, face_image=None, face_encoding_path=None, face_images_prefix=None)
    db.session.add(student)
    db.session.commit()

    save_qr(f"student_{sid}.png", f"STUDENT:{sid}")
    flash(f"Student '{name}' added ✅ (QR generated). Enroll face separately.", "success")
    return redirect(url_for("students"))

@app.route("/admin/add-class", methods=["POST"])
def add_class():
    code = request.form.get("code", "").strip() or f"CLS{str(int(datetime.utcnow().timestamp()))[-5:]}"
    name = request.form.get("name", "").strip()
    teacher = request.form.get("teacher", "").strip()
    if not name:
        flash("Class name is required.", "danger")
        return redirect(url_for("classes"))
    if ClassRoom.query.filter_by(code=code).first():
        flash("Class code already exists.", "danger")
        return redirect(url_for("classes"))
    db.session.add(ClassRoom(code=code, name=name, teacher=teacher))
    db.session.commit()
    flash("Class added.", "success")
    return redirect(url_for("classes"))

@app.route("/admin/add-lab", methods=["POST"])
def add_lab():
    code = request.form.get("code", "").strip() or f"LAB{str(int(datetime.utcnow().timestamp()))[-5:]}"
    name = request.form.get("name", "").strip()
    room = request.form.get("room", "").strip()
    if not name:
        flash("Lab name is required.", "danger")
        return redirect(url_for("labs_page"))
    if Lab.query.filter_by(code=code).first():
        flash("Lab code already exists.", "danger")
        return redirect(url_for("labs_page"))
    db.session.add(Lab(code=code, name=name, room=room))
    db.session.commit()
    flash("Lab added.", "success")
    return redirect(url_for("labs_page"))

@app.route("/qrcodes/<path:filename>")
def qrcodes(filename):
    return send_from_directory(app.config["QR_FOLDER"], filename)

# =========================
# JSON APIs (library unchanged, fixed minor bugs)
# =========================

@app.route("/api/student/<sid>")
def api_student(sid):
    s = Student.query.filter_by(sid=sid).first()
    if not s:
        return jsonify({"ok": False, "error": "Student not found"}), 404
    return jsonify({"ok": True, "student": {
        "sid": s.sid,
        "name": s.name,
        "email": s.email,
        "face_image": s.face_image,
        "face_enrolled": bool(s.face_image)
    }})


@app.route("/api/book/<bid>")
def api_book(bid):
    b = Book.query.filter_by(bid=bid).first()
    if not b:
        return jsonify({"ok": False, "error": "Book not found"}), 404
    return jsonify({"ok": True, "book": {"bid": b.bid, "title": b.title, "author": b.author, "available": b.available}})

@app.route("/api/borrow", methods=["POST"])
def api_borrow():
    data = request.get_json(force=True)
    sid = data.get("sid")
    bid = data.get("bid")

    s = Student.query.filter_by(sid=sid).first()
    b = Book.query.filter_by(bid=bid).first()
    if not s or not b:
        return jsonify({"ok": False, "error": "Invalid student or book"}), 400
    if not b.available:
        return jsonify({"ok": False, "error": "Book already borrowed"}), 409

    due = datetime.utcnow() + timedelta(days=int(data.get("days", 14)))
    rec = Borrow(student_sid=s.sid, book_bid=b.bid, due_dt=due, status="BORROWED")
    b.available = False
    db.session.add(rec)
    db.session.commit()
    return jsonify({"ok": True, "message": "Borrowed", "due_dt": due.isoformat()})

@app.route("/api/return", methods=["POST"])
def api_return():
    data = request.get_json(force=True)
    bid = data.get("bid")
    b = Book.query.filter_by(bid=bid).first()
    if not b:
        return jsonify({"ok": False, "error": "Book not found"}), 404
    rec = Borrow.query.filter_by(book_bid=bid, status="BORROWED").order_by(Borrow.borrow_dt.desc()).first()
    if not rec:
        return jsonify({"ok": False, "error": "No active borrow for this book"}), 409
    rec.status = "RETURNED"
    rec.return_dt = datetime.utcnow()
    b.available = True
    db.session.commit()
    return jsonify({"ok": True, "message": "Returned", "return_dt": rec.return_dt.isoformat()})

@app.route("/api/history/<sid>")
def api_history(sid):
    rows = Borrow.query.filter_by(student_sid=sid).order_by(Borrow.borrow_dt.desc()).all()
    payload = []
    for r in rows:
        payload.append({
            "book_bid": r.book_bid,
            "borrow_dt": r.borrow_dt.isoformat(),
            "due_dt": r.due_dt.isoformat(),
            "return_dt": r.return_dt.isoformat() if r.return_dt else None,
            "status": r.status
        })
    return jsonify({"ok": True, "history": payload})

# =========================
# Face enrolment / verification / operator-stop (modified)
# =========================

@app.route("/api/face/enroll", methods=["POST"])
def api_face_enroll():
    if not app.config.get("FACE_ENABLED_GLOBAL", True):
        return jsonify({"ok": False, "error": "Face recognition globally disabled"}), 403

    data = request.get_json(force=True)
    sid = data.get("sid")
    frames = data.get("frames") or []  # <-- changed from "images" to "frames"

    s = Student.query.filter_by(sid=sid).first()
    if not s:
        return jsonify({"ok": False, "error": "Student not found"}), 404

    ok, msg, enc_path, prefix = save_face_images_and_encoding(sid, frames)  # <-- use frames
    if not ok:
        return jsonify({"ok": False, "error": msg}), 400

    if prefix:
        primary_img = os.path.join(app.config["FACE_FOLDER"], f"{prefix}_0.png")
        if os.path.exists(primary_img):
            s.face_image = primary_img
    if enc_path:
        s.face_encoding_path = enc_path
    if prefix:
        s.face_images_prefix = prefix

    db.session.commit()
    return jsonify({"ok": True, "msg": msg})


@app.route("/api/face/verify", methods=["POST"])
def api_face_verify():
    if not app.config.get("FACE_ENABLED_GLOBAL", True):
        return jsonify({"ok": True, "msg": "Face recognition globally disabled; verification skipped"})

    data = request.get_json(force=True)
    sid = data.get("sid")
    image = data.get("image")

    s = Student.query.filter_by(sid=sid).first()
    if not s:
        return jsonify({"ok": False, "error": "Student not found"}), 404
    if not s.face_image:
        return jsonify({"ok": False, "error": "Student has no enrolled face"}), 400
    if not image:
        return jsonify({"ok": False, "error": "No image provided for verification"}), 400

    try:
        # Load reference encoding (from file if available)
        if s.face_encoding_path and os.path.exists(s.face_encoding_path):
            ref_enc = np.load(s.face_encoding_path)
        else:
            ref_img = face_recognition.load_image_file(s.face_image)
            ref_locs = face_recognition.face_locations(ref_img, model="hog")
            if not ref_locs:
                return jsonify({"ok": False, "error": "No face detected in enrolled image"}), 400
            ref_encs = face_recognition.face_encodings(ref_img, known_face_locations=ref_locs)
            if not ref_encs:
                return jsonify({"ok": False, "error": "No face encoding in enrolled image"}), 400
            ref_enc = ref_encs[0]

        # Process live/probe image
        b = _b64_to_bytes(image)
        buf = BytesIO(b)
        probe_img = face_recognition.load_image_file(buf)
        probe_locs = face_recognition.face_locations(probe_img, model="hog")
        if not probe_locs:
            return jsonify({"ok": False, "error": "No face detected in provided image"}), 400
        probe_encs = face_recognition.face_encodings(probe_img, known_face_locations=probe_locs)
        if not probe_encs:
            return jsonify({"ok": False, "error": "No encoding in provided image"}), 400
        probe_enc = probe_encs[0]

        # 🔒 Strict matching for ONLY this student
        dist = np.linalg.norm(ref_enc - probe_enc)
        tol = 0.5  # stricter tolerance to reduce false positives
        if dist <= tol:
            return jsonify({"ok": True, "msg": f"Face matched (distance={float(dist):.4f})"})
        else:
            return jsonify({"ok": False, "error": f"Face mismatch (distance={float(dist):.4f})"}), 400

    except Exception as e:
        return jsonify({"ok": False, "error": f"Verification failed: {str(e)}"}), 500



@app.route("/api/face/stop", methods=["POST"])
def api_face_stop():
    """
    Operator override to skip face verification for a given SID.
    Expects JSON: { sid: "...", password: "..." }
    """
    data = request.get_json(force=True)
    sid = data.get("sid")
    password = data.get("password") or ""
    if password != app.config["OPERATOR_PASSWORD"]:
        return jsonify({"ok": False, "error": "Invalid operator password"}), 403
    return jsonify({"ok": True, "msg": "Operator override accepted"})

# =========================
# Cooldown trackers (in-memory)
# =========================
COOLDOWN_SECONDS = 30
_attendance_cooldowns = {}   # key: session_id|sid  => timestamp (ms)
_lab_cooldowns = {}          # key: lab_id|sid => timestamp
_hostel_cooldowns = {}       # key: sid => timestamp

def _is_cooled(last_dict, key):
    now = datetime.utcnow().timestamp()
    ts = last_dict.get(key)
    if ts and (now - ts) < COOLDOWN_SECONDS:
        return False  # not allowed (still cooling)
    last_dict[key] = now
    return True

# =========================
# Attendance APIs (class)
# =========================

@app.route("/api/attendance/start", methods=["POST"])
def api_attendance_start():
    data = request.get_json(force=True)
    class_id = int(data.get("class_id"))
    open_existing = AttendanceSession.query.filter_by(class_id=class_id, date_=date.today(), status="OPEN").first()
    if open_existing:
        return jsonify({"ok": True, "session_id": open_existing.id, "message": "Session already open"})
    ses = AttendanceSession(class_id=class_id, date_=date.today(), status="OPEN")
    db.session.add(ses)
    db.session.commit()
    return jsonify({"ok": True, "session_id": ses.id})

@app.route("/api/attendance/stop", methods=["POST"])
def api_attendance_stop():
    data = request.get_json(force=True)
    session_id = int(data.get("session_id"))
    ses = AttendanceSession.query.get(session_id)
    if not ses:
        return jsonify({"ok": False, "error": "Session not found"}), 404
    ses.status = "CLOSED"
    ses.end_time = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/api/attendance/mark", methods=["POST"])
def api_attendance_mark():
    data = request.get_json(force=True)
    session_id = int(data.get("session_id"))
    sid = data.get("sid")

    ses = AttendanceSession.query.get(session_id)
    s = Student.query.filter_by(sid=sid).first()
    if not ses or ses.status != "OPEN":
        return jsonify({"ok": False, "error": "Session closed or missing"}), 400
    if not s:
        return jsonify({"ok": False, "error": "Student not found"}), 404

    # cooldown key per session+sid
    key = f"{session_id}|{sid}"
    if not _is_cooled(_attendance_cooldowns, key):
        return jsonify({"ok": True, "marked": False, "msg": "Ignored (cooldown)"})

    rec = AttendanceRecord.query.filter_by(session_id=session_id, student_sid=sid).first()
    if not rec:
        rec = AttendanceRecord(session_id=session_id, student_sid=sid, present=True)
        db.session.add(rec)
        db.session.commit()
        return jsonify({"ok": True, "marked": True, "msg": "Present marked" })
    else:
        return jsonify({"ok": True, "marked": False, "msg": "Already marked"})

@app.route("/api/attendance/session/<int:session_id>")
def api_attendance_session(session_id):
    ses = AttendanceSession.query.get(session_id)
    if not ses:
        return jsonify({"ok": False, "error": "Session not found"}), 404
    records = AttendanceRecord.query.filter_by(session_id=session_id).order_by(AttendanceRecord.ts.asc()).all()
    data = {
        "id": ses.id,
        "class": {"id": ses.classroom.id, "code": ses.classroom.code, "name": ses.classroom.name},
        "date": ses.date_.isoformat(),
        "status": ses.status,
        "count": len(records),
        "records": [{"sid": r.student_sid, "ts": r.ts.isoformat()} for r in records]
    }
    return jsonify({"ok": True, "session": data})

# =========================
# Labs APIs
# =========================

@app.route("/api/labs/log", methods=["POST"])
def api_labs_log():
    data = request.get_json(force=True)
    lab_id = int(data.get("lab_id"))
    sid = data.get("sid")
    action = data.get("action")

    lab = Lab.query.get(lab_id)
    s = Student.query.filter_by(sid=sid).first()
    if not lab or not s:
        return jsonify({"ok": False, "error": "Invalid lab or student"}), 400

    # cooldown key per lab+sid
    key = f"{lab_id}|{sid}"
    if not _is_cooled(_lab_cooldowns, key):
        return jsonify({"ok": True, "action": None, "ts": datetime.utcnow().isoformat(), "msg": "Ignored (cooldown)"})

    if action == "TOGGLE":
        last = LabLog.query.filter(LabLog.lab_id == lab_id, LabLog.student_sid == sid).order_by(LabLog.ts.desc()).first()
        action = "EXIT" if (last and last.action == "ENTRY") else "ENTRY"
    log = LabLog(lab_id=lab_id, student_sid=sid, action=action) 
    db.session.add(log)
    db.session.commit()
    return jsonify({"ok": True, "action": action, "ts": log.ts.isoformat()})
 

@app.route("/api/labs/stats/<int:lab_id>")
def api_labs_stats(lab_id):
    last_actions = db.session.query(
        LabLog.student_sid, db.func.max(LabLog.id).label("maxid")
    ).filter(LabLog.lab_id == lab_id).group_by(LabLog.student_sid).subquery()

    rows = db.session.query(LabLog).join(
        last_actions, LabLog.id == last_actions.c.maxid
    ).all()

    inside = sum(1 for r in rows if r.action == "ENTRY")
    return jsonify({"ok": True, "inside": inside})

# =========================
# Hostel APIs
# =========================

@app.route("/api/hostel/log", methods=["POST"])
def hostel_log():
    data = request.get_json()
    sid = data.get("sid")
    action = data.get("action")
    gate = data.get("gate", "Main Gate")

    if not sid or not action:
        return jsonify({"ok": False, "error": "Missing sid or action"})

    log = HostelLog(student_sid=sid, action=action, gate=gate, ts=datetime.utcnow())
    db.session.add(log)
    db.session.commit()
    return jsonify({
        "ok": True,
        "sid": sid,
        "action": action,
        "gate": gate,
        "ts": log.ts.isoformat()
    })

@app.route("/api/hostel/recent")
def hostel_recent():
    logs = HostelLog.query.order_by(HostelLog.ts.desc()).limit(10).all()
    return jsonify({
        "logs": [
            {
                "sid": l.student_sid,
                "action": l.action,
                "gate": l.gate,
                "ts": l.ts.isoformat()
            } for l in logs
        ]
    })

@app.route("/api/hostel/logs")
def hostel_logs():
    logs = HostelLog.query.order_by(HostelLog.ts.desc()).all()
    return jsonify({
        "logs": [
            {
                "sid": l.student_sid,
                "action": l.action,
                "gate": l.gate,
                "ts": l.ts.isoformat()
            } for l in logs
        ]
    })

# =========================
# Global Face Recognition Control (Admin)
# =========================

# default setting
app.config.setdefault("FACE_ENABLED_GLOBAL", True)

@app.route("/api/admin/face-status")
def api_face_status():
    """Return whether face recognition is enabled globally."""
    return jsonify({
        "ok": True,
        "enabled": bool(app.config.get("FACE_ENABLED_GLOBAL", True))
    })

@app.route("/api/admin/face-toggle", methods=["POST"])
def api_face_toggle():
    """Toggle face recognition globally (admin control)."""
    data = request.get_json(force=True)
    enabled = bool(data.get("enabled", True))

    # (Optional) Protect with operator password if you want stricter control
    password = data.get("password")
    if password and password != app.config["OPERATOR_PASSWORD"]:
        return jsonify({"ok": False, "error": "Invalid operator password"}), 403

    app.config["FACE_ENABLED_GLOBAL"] = enabled
    return jsonify({"ok": True, "enabled": enabled})


# =========================
# Main
# =========================

if __name__ == "__main__":
    ensure_dirs()
    with app.app_context():
        db.create_all()
        seed_demo()
        # Generate QRs for any missing students/books
        for s in Student.query.all():
            fname = f"student_{s.sid}.png"
            fpath = os.path.join(app.config["QR_FOLDER"], fname)
            if not os.path.exists(fpath):
                save_qr(fname, f"STUDENT:{s.sid}")
        for b in Book.query.all():
            fname = f"book_{b.bid}.png"
            fpath = os.path.join(app.config["QR_FOLDER"], fname)
            if not os.path.exists(fpath):
                save_qr(fname, f"BOOK:{b.bid}")
    app.run(debug=True, host="0.0.0.0", port=5000)
