import os
from datetime import datetime, timedelta, date
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, flash
from flask_sqlalchemy import SQLAlchemy
from config import Config
import qrcode
import pickle
import face_recognition
import cv2
import time

from flask import request
app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)
from flask_migrate import Migrate

migrate = Migrate(app, db)
# =========================
# Existing Library Models
# =========================

class Student(db.Model):
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    sid = db.Column(db.String(32), unique=True, index=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    fingerprint = db.Column(db.String(120), nullable=True)  # 🔑 NEW
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
    borrow_dt = db.Column(db.DateTime, default=datetime.utcnow)
    due_dt = db.Column(db.DateTime, nullable=False)
    return_dt = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(16), default="BORROWED")  # BORROWED / RETURNED

# =========================
# NEW: Classes Attendance
# =========================

class ClassRoom(db.Model):
    __tablename__ = "classrooms"          # (course/section)
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, index=True, nullable=False)   # e.g. CSE-A-DSA
    name = db.Column(db.String(200), nullable=False)                            # e.g. "DSA - CSE A"
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
    ts = db.Column(db.DateTime, default=datetime.utcnow)
    present = db.Column(db.Boolean, default=True)
    __table_args__ = (db.UniqueConstraint("session_id", "student_sid", name="uq_session_student"),)

# =========================
# NEW: Labs Entry/Exit
# =========================

class Lab(db.Model):
    __tablename__ = "labs"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, index=True, nullable=False)  # e.g. LAB-ML-01
    name = db.Column(db.String(200), nullable=False)                           # e.g. "ML Lab"
    room = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LabLog(db.Model):
    __tablename__ = "lab_logs"
    id = db.Column(db.Integer, primary_key=True)
    lab_id = db.Column(db.Integer, db.ForeignKey("labs.id"), nullable=False)
    student_sid = db.Column(db.String(32), db.ForeignKey("students.sid"), nullable=False)
    action = db.Column(db.String(8), nullable=False)  # ENTRY or EXIT
    ts = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    lab = db.relationship("Lab")

# =========================
# NEW: Hostel Entry/Exit
# =========================

class HostelLog(db.Model):
    __tablename__ = "hostel_logs"
    id = db.Column(db.Integer, primary_key=True)
    gate = db.Column(db.String(80), default="Main Gate")  # simple single gate; editable in UI
    student_sid = db.Column(db.String(32), db.ForeignKey("students.sid"), nullable=False)
    action = db.Column(db.String(8), nullable=False)  # ENTRY or EXIT
    ts = db.Column(db.DateTime, default=datetime.utcnow, index=True)

# =========================
# Helpers
# =========================

def ensure_dirs():
    os.makedirs(app.config["QR_FOLDER"], exist_ok=True)

def save_qr(filename, data):
    ensure_dirs()
    path = os.path.join(app.config["QR_FOLDER"], filename)
    img = qrcode.make(data)
    img.save(path)
    return path

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

def verify_fingerprint(student_sid, fingerprint_input):
    student = Student.query.filter_by(sid=student_sid).first()
    if student and student.fingerprint == fingerprint_input:
        return True
    return False

FACE_DB = "faces.pkl"

def load_faces():
    if os.path.exists(FACE_DB):
        with open(FACE_DB, "rb") as f:
            return pickle.load(f)
    return {}

def save_faces(data):
    with open(FACE_DB, "wb") as f:
        pickle.dump(data, f)

def _capture_face_encoding(timeout=8, process_every_n_frames=2):
    """
    Capture a single face encoding from webcam within `timeout` seconds.
    Returns a 128-d numpy array encoding or None.
    """
    cap = cv2.VideoCapture(0)
    start = time.time()
    frame_count = 0
    encoding = None

    while time.time() - start < timeout:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.1)
            continue
        frame_count += 1
        if frame_count % process_every_n_frames != 0:
            continue

        # face_recognition expects RGB
        rgb = frame[:, :, ::-1]
        encs = face_recognition.face_encodings(rgb)
        if encs:
            encoding = encs[0]
            break

        # optional quick exit (user can press 'q' if running with display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    try:
        cv2.destroyAllWindows()
    except:
        pass
    return encoding


def verify_face(student_sid, timeout=8, tolerance=0.5):
    """
    Verify that a live capture matches the enrolled face for student_sid.
    Returns (True, {"distance": float}) on success,
    or (False, "reason") on failure.
    """
    data = load_faces()
    if student_sid not in data:
        return False, "no_enrolled_face"

    known_enc = data[student_sid]
    captured = _capture_face_encoding(timeout=timeout)
    if captured is None:
        return False, "no_face_detected"

    # compute distance and compare with tolerance
    dist = float(face_recognition.face_distance([known_enc], captured)[0])
    ok = dist <= tolerance
    if ok:
        return True, {"distance": dist}
    return False, {"distance": dist}


# =========================
# Pages (existing + new)
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

# Existing scanner (library)
@app.route("/scan")
def scan():
    return render_template("scan.html")

@app.route("/history")
def history():
    rows = Borrow.query.order_by(Borrow.borrow_dt.desc()).limit(200).all()
    return render_template("history.html", rows=rows)

# ---------- NEW: Classes pages ----------
@app.route("/classes")
def classes():
    items = ClassRoom.query.order_by(ClassRoom.created_at.desc()).all()
    return render_template("classes.html", classes=items)

@app.route("/attendance")
def attendance():
    classes = ClassRoom.query.order_by(ClassRoom.name.asc()).all()
    recent = AttendanceSession.query.order_by(AttendanceSession.start_time.desc()).limit(20).all()
    return render_template("attendance.html", classes=classes, recent=recent)

# ---------- NEW: Labs page ----------
@app.route("/labs")
def labs_page():
    labs = Lab.query.order_by(Lab.name.asc()).all()
    recent = LabLog.query.order_by(LabLog.ts.desc()).limit(50).all()
    return render_template("labs.html", labs=labs, recent=recent)

# ---------- NEW: Hostel page ----------
@app.route("/hostel")
def hostel_page():
    recent = HostelLog.query.order_by(HostelLog.ts.desc()).limit(100).all()
    return render_template("hostel.html", recent=recent)

# =========================
# Admin Actions (existing)
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
    fingerprint = request.form.get("fingerprint", "").strip() or f"fp_{int(datetime.utcnow().timestamp())}"
    sid = request.form.get("sid", "").strip() or f"STU{str(int(datetime.utcnow().timestamp()))[-6:]}"
    
    if not name:
        flash("Name is required.", "danger")
        return redirect(url_for("students"))
    if Student.query.filter_by(sid=sid).first():
        flash("Student ID already exists.", "danger")
        return redirect(url_for("students"))
    
    student = Student(sid=sid, name=name, email=email, fingerprint=fingerprint)
    db.session.add(student)
    db.session.commit()
    
    save_qr(f"student_{sid}.png", f"STUDENT:{sid}")
    flash(f"Student '{name}' added. QR + Fingerprint registered ✅", "success")
    return redirect(url_for("students"))

# ---------- NEW: Admin add class / lab ----------
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
# JSON APIs (existing + new)
# =========================

@app.route("/api/student/<sid>")
def api_student(sid):
    s = Student.query.filter_by(sid=sid).first()
    if not s:
        return jsonify({"ok": False, "error": "Student not found"}), 404
    return jsonify({"ok": True, "student": {"sid": s.sid, "name": s.name, "email": s.email}})

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
    fingerprint = data.get("fingerprint")  # 🔑 NEW

    s = Student.query.filter_by(sid=sid).first()
    b = Book.query.filter_by(bid=bid).first()
    if not s or not b:
        return jsonify({"ok": False, "error": "Invalid student or book"}), 400
    if not b.available:
        return jsonify({"ok": False, "error": "Book already borrowed"}), 409
    if not verify_fingerprint(sid, fingerprint):
        return jsonify({"ok": False, "error": "Fingerprint mismatch"}), 403

    # Face verification
    face_ok, face_info = verify_face(sid)
    if not face_ok:
        return jsonify({"ok": False, "error": "Face verification failed", "detail": face_info}), 403

    due = datetime.utcnow() + timedelta(days=int(data.get("days", 14)))
    rec = Borrow(student_sid=s.sid, book_bid=b.bid, due_dt=due, status="BORROWED")
    b.available = False
    db.session.add(rec)
    db.session.commit()
    return jsonify({"ok": True, "message": "Borrowed", "due_dt": due.isoformat(), "face": face_info})


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

# ---------- NEW: Attendance APIs ----------

@app.route("/api/attendance/start", methods=["POST"])
def api_attendance_start():
    data = request.get_json(force=True)
    class_id = int(data.get("class_id"))
    # Close any open session for same class today
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
    fingerprint = data.get("fingerprint")  # 🔑 NEW

    ses = AttendanceSession.query.get(session_id)
    s = Student.query.filter_by(sid=sid).first()
    if not ses or ses.status != "OPEN":
        return jsonify({"ok": False, "error": "Session closed or missing"}), 400
    if not s:
        return jsonify({"ok": False, "error": "Student not found"}), 404
    if not verify_fingerprint(sid, fingerprint):
        return jsonify({"ok": False, "error": "Fingerprint mismatch"}), 403

    # Face verification (live capture)
    face_ok, face_info = verify_face(sid)
    if not face_ok:
        return jsonify({"ok": False, "error": "Face verification failed", "detail": face_info}), 403

    rec = AttendanceRecord.query.filter_by(session_id=session_id, student_sid=sid).first()
    if not rec:
        rec = AttendanceRecord(session_id=session_id, student_sid=sid, present=True)
        db.session.add(rec)
        db.session.commit()
        return jsonify({"ok": True, "marked": True, "msg": "Present marked", "face": face_info})
    else:
        return jsonify({"ok": True, "marked": False, "msg": "Already marked", "face": face_info})


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

# ---------- NEW: Labs APIs ----------

@app.route("/api/labs/log", methods=["POST"])
def api_labs_log():
    data = request.get_json(force=True)
    lab_id = int(data.get("lab_id"))
    sid = data.get("sid")
    fingerprint = data.get("fingerprint")  # 🔑 NEW
    action = data.get("action")

    lab = Lab.query.get(lab_id)
    s = Student.query.filter_by(sid=sid).first()
    if not lab or not s:
        return jsonify({"ok": False, "error": "Invalid lab or student"}), 400
    if not verify_fingerprint(sid, fingerprint):
        return jsonify({"ok": False, "error": "Fingerprint mismatch"}), 403

    # Face verification
    face_ok, face_info = verify_face(sid)
    if not face_ok:
        return jsonify({"ok": False, "error": "Face verification failed", "detail": face_info}), 403

    if action == "TOGGLE":
        last = LabLog.query.filter(LabLog.lab_id == lab_id, LabLog.student_sid == sid).order_by(LabLog.ts.desc()).first()
        action = "EXIT" if (last and last.action == "ENTRY") else "ENTRY"
    log = LabLog(lab_id=lab_id, student_sid=sid, action=action)
    db.session.add(log)
    db.session.commit()
    return jsonify({"ok": True, "action": action, "ts": log.ts.isoformat(), "face": face_info})


@app.route("/api/labs/stats/<int:lab_id>")
def api_labs_stats(lab_id):
    # Estimate "currently inside" by last action per student
    last_actions = db.session.query(
        LabLog.student_sid, db.func.max(LabLog.id).label("maxid")
    ).filter(LabLog.lab_id == lab_id).group_by(LabLog.student_sid).subquery()

    rows = db.session.query(LabLog).join(
        last_actions, LabLog.id == last_actions.c.maxid
    ).all()

    inside = sum(1 for r in rows if r.action == "ENTRY")
    return jsonify({"ok": True, "inside": inside})

# ---------- NEW: Hostel APIs ----------

@app.route("/api/hostel/log", methods=["POST"])
def api_hostel_log():
    data = request.get_json(force=True)
    sid = data.get("sid")
    fingerprint = data.get("fingerprint")  # 🔑 NEW
    action = data.get("action")
    gate = (data.get("gate") or "Main Gate").strip()

    s = Student.query.filter_by(sid=sid).first()
    if not s:
        return jsonify({"ok": False, "error": "Student not found"}), 404
    if not verify_fingerprint(sid, fingerprint):
        return jsonify({"ok": False, "error": "Fingerprint mismatch"}), 403

    # Face verification
    face_ok, face_info = verify_face(sid)
    if not face_ok:
        return jsonify({"ok": False, "error": "Face verification failed", "detail": face_info}), 403

    if action == "TOGGLE":
        last = HostelLog.query.filter_by(student_sid=sid).order_by(HostelLog.ts.desc()).first()
        action = "EXIT" if (last and last.action == "ENTRY") else "ENTRY"
    log = HostelLog(student_sid=sid, action=action, gate=gate)
    db.session.add(log)
    db.session.commit()
    return jsonify({"ok": True, "action": action, "ts": log.ts.isoformat(), "gate": gate, "face": face_info})

@app.route("/enroll_face", methods=["GET", "POST"])
def enroll_face():
    if request.method == "POST":
        student_id = request.form["student_id"].strip()
        if not student_id:
            flash("Student ID required", "danger")
            return redirect(url_for("enroll_face"))

        enc = _capture_face_encoding(timeout=8)
        if enc is None:
            flash("⚠️ No face detected — try again", "danger")
            return redirect(url_for("enroll_face"))

        data = load_faces()
        data[student_id] = enc
        save_faces(data)
        flash(f"✅ Face enrolled for Student {student_id}", "success")
        return redirect(url_for("enroll_face"))

    students = Student.query.all()
    return render_template("enroll_face.html", students=students)


@app.route("/api/face/verify", methods=["POST"])
def face_verify():
    sid = request.form.get("sid")
    file = request.files.get("face")
    if not sid or not file:
        return jsonify({"ok": False, "error": "Missing student or image"})

    # Load uploaded frame
    npimg = np.frombuffer(file.read(), np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    # TODO: Load student's enrolled face encoding from DB/storage
    # Example: student_face_encoding = pickle.load(open(f"faces/{sid}.pkl","rb"))

    # Extract face encoding from uploaded frame
    face_locations = face_recognition.face_locations(frame)
    if not face_locations:
        return jsonify({"ok": False, "error": "No face detected"})

    face_encodings = face_recognition.face_encodings(frame, face_locations)
    if not face_encodings:
        return jsonify({"ok": False, "error": "Could not encode face"})

    uploaded_encoding = face_encodings[0]

    # Compare with stored encoding
    match = face_recognition.compare_faces([student_face_encoding], uploaded_encoding)[0]
    if match:
        return jsonify({"ok": True, "msg": "Face verified"})
    else:
        return jsonify({"ok": False, "error": "Face mismatch"})
# =========================
# Main
# =========================

if __name__ == "__main__":
    ensure_dirs()
    with app.app_context():
        db.create_all()
        seed_demo()
        # Generate QRs for any missing students/books (library stays intact)
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
