"""Authenticated, opt-in publishing question bank for Security Engineer exam study.

Shares the existing WebAuthn session gate. Uses its own persistent SQLite file
under /data; never migrates the credential or private vault databases.
"""
import hmac
import json
import secrets
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

from flask import Blueprint, jsonify, render_template, request, session

SUBJECTS = (
    "시스템 보안",
    "네트워크 보안",
    "어플리케이션 보안",
    "정보보안 일반",
    "정보보안 관리 및 법규",
)
PARTS = ("필기", "실기")
KINDS = ("multiple_choice", "written")
STATUSES = ("draft", "published", "archived")
FIELDS = ("exam_part", "subject", "kind", "topic", "prompt", "options",
          "correct_index", "model_answer", "explanation", "source_url", "difficulty")


class QuestionError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _text(value, field, maximum, minimum=0):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise QuestionError(f"{field} must be {minimum}-{maximum} characters")
    return value.strip()


def _normalize(payload):
    if not isinstance(payload, dict) or set(payload) - set(FIELDS):
        raise QuestionError("invalid question fields")
    part = payload.get("exam_part")
    subject = payload.get("subject")
    kind = payload.get("kind")
    if part not in PARTS or subject not in SUBJECTS or kind not in KINDS:
        raise QuestionError("invalid exam_part, subject or kind")
    if (part == "필기" and kind != "multiple_choice") or (part == "실기" and kind != "written"):
        raise QuestionError("필기 is multiple_choice and 실기 is written")
    topic = _text(payload.get("topic"), "topic", 100, 1)
    prompt = _text(payload.get("prompt"), "prompt", 3000, 8)
    explanation = _text(payload.get("explanation"), "explanation", 5000, 1)
    source_url = _text(payload.get("source_url", ""), "source_url", 500)
    if source_url:
        parsed = urlsplit(source_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise QuestionError("source_url must use HTTPS without credentials")
    difficulty = payload.get("difficulty", 3)
    if type(difficulty) is not int or not 1 <= difficulty <= 5:
        raise QuestionError("difficulty must be an integer from 1 to 5")
    options = payload.get("options", [])
    correct_index = payload.get("correct_index")
    model_answer = payload.get("model_answer", "")
    if kind == "multiple_choice":
        if not isinstance(options, list) or len(options) != 4:
            raise QuestionError("multiple_choice requires exactly four options")
        options = [_text(opt, "option", 500, 1) for opt in options]
        if len(set(options)) != 4:
            raise QuestionError("options must be distinct")
        if type(correct_index) is not int or correct_index not in range(4):
            raise QuestionError("correct_index must be 0-3")
        if model_answer not in ("", None):
            raise QuestionError("model_answer is only for written questions")
        model_answer = ""
    else:
        if options not in ([], None) or correct_index is not None:
            raise QuestionError("written questions cannot have choices")
        options = []
        correct_index = None
        model_answer = _text(model_answer, "model_answer", 4000, 1)
    return {
        "exam_part": part, "subject": subject, "kind": kind, "topic": topic,
        "prompt": prompt, "options": options, "correct_index": correct_index,
        "model_answer": model_answer, "explanation": explanation,
        "source_url": source_url, "difficulty": difficulty,
    }


class QuestionBank:
    def __init__(self, db_path):
        self.path = Path(db_path)

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def init_schema(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS questions (
                    id TEXT PRIMARY KEY,
                    exam_part TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    correct_index INTEGER,
                    model_answer TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'self-authored',
                    difficulty INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    revision INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_exam_questions
                    ON questions (status, exam_part, subject);
                CREATE TABLE IF NOT EXISTS question_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id TEXT NOT NULL REFERENCES questions(id),
                    question_revision INTEGER NOT NULL,
                    answer_text TEXT NOT NULL,
                    is_correct INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_exam_attempts
                    ON question_attempts (created_at, id);
            """)

    @staticmethod
    def serialize(row, public=False):
        item = dict(row)
        if "options_json" in item:
            item["options"] = json.loads(item.pop("options_json"))
        if public:
            for field in ("correct_index", "model_answer", "explanation"):
                item.pop(field, None)
        return item

    def get(self, question_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if row is None:
            raise QuestionError("question not found", 404)
        return self.serialize(row)

    def list(self, part=None, subject=None, status=None, limit=25, offset=0):
        where, args = [], []
        for field, value in (("exam_part", part), ("subject", subject), ("status", status)):
            if value:
                where.append(f"{field} = ?")
                args.append(value)
        clause = " WHERE " + " AND ".join(where) if where else ""
        with self.connect() as db:
            total = db.execute("SELECT COUNT(*) FROM questions" + clause, args).fetchone()[0]
            rows = db.execute(
                "SELECT * FROM questions" + clause +
                " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (*args, limit, offset),
            ).fetchall()
        return {"total": total, "items": [self.serialize(r) for r in rows]}

    def create(self, payload):
        if not isinstance(payload, dict) or any(
            key in payload for key in ("status", "source_type", "id", "revision")
        ):
            raise QuestionError("new questions must be created as drafts")
        item = _normalize(payload)
        question_id = secrets.token_hex(12)
        with self.connect() as db:
            db.execute("""
                INSERT INTO questions
                  (id, exam_part, subject, kind, topic, prompt, options_json,
                   correct_index, model_answer, explanation, source_url, difficulty)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                question_id, item["exam_part"], item["subject"], item["kind"],
                item["topic"], item["prompt"], json.dumps(item["options"], ensure_ascii=False),
                item["correct_index"], item["model_answer"], item["explanation"],
                item["source_url"], item["difficulty"],
            ))
        return self.get(question_id)

    def modify(self, question_id, payload, archive=False):
        if not isinstance(payload, dict) or type(payload.get("expected_revision")) is not int:
            raise QuestionError("expected_revision integer is required", 428)
        previous = self.get(question_id)
        if previous["revision"] != payload["expected_revision"]:
            raise QuestionError("revision conflict", 409)
        allowed = set(FIELDS) | {"expected_revision", "status", "reviewed"}
        if set(payload) - allowed:
            raise QuestionError("unknown update fields")
        fields = {name: previous[name] for name in FIELDS}
        fields.update({name: payload[name] for name in FIELDS if name in payload})
        item = _normalize(fields)
        status = "archived" if archive else payload.get("status", previous["status"])
        if status not in STATUSES:
            raise QuestionError("invalid status")
        if status == "published" and previous["status"] != "published" and payload.get("reviewed") is not True:
            raise QuestionError("publishing requires reviewed=true and human review")
        with self.connect() as db:
            cursor = db.execute("""
                UPDATE questions SET exam_part=?, subject=?, kind=?, topic=?, prompt=?,
                    options_json=?, correct_index=?, model_answer=?, explanation=?,
                    source_url=?, difficulty=?, status=?, revision=revision+1,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND revision=?
            """, (
                item["exam_part"], item["subject"], item["kind"], item["topic"],
                item["prompt"], json.dumps(item["options"], ensure_ascii=False),
                item["correct_index"], item["model_answer"], item["explanation"],
                item["source_url"], item["difficulty"], status, question_id,
                payload["expected_revision"],
            ))
            if cursor.rowcount == 0:
                raise QuestionError("revision conflict", 409)
        return self.get(question_id)

    def practice(self, part=None, subject=None, limit=10):
        filters = ["status='published'"]
        args = []
        if part:
            filters.append("exam_part=?")
            args.append(part)
        if subject:
            filters.append("subject=?")
            args.append(subject)
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM questions WHERE " + " AND ".join(filters) +
                " ORDER BY RANDOM() LIMIT ?", (*args, limit)
            ).fetchall()
        return [self.serialize(row, public=True) for row in rows]

    def answer(self, payload):
        if not isinstance(payload, dict):
            raise QuestionError("JSON object required")
        question_id = payload.get("question_id")
        if not isinstance(question_id, str) or len(question_id) > 64:
            raise QuestionError("invalid question_id")
        question = self.get(question_id)
        if question["status"] != "published":
            raise QuestionError("question is not published", 404)
        if question["kind"] == "multiple_choice":
            choice = payload.get("selected_choice")
            if type(choice) is not int or choice not in range(4) or set(payload) != {"question_id", "selected_choice"}:
                raise QuestionError("selected_choice must be 0-3")
            correct = choice == question["correct_index"]
            answer_text = str(choice)
        else:
            if set(payload) != {"question_id", "written_response"}:
                raise QuestionError("written_response is required")
            answer_text = _text(payload.get("written_response"), "written_response", 4000, 1)
            correct = None  # Written answers require human/self-assessment.
        with self.connect() as db:
            cursor = db.execute("""
                INSERT INTO question_attempts
                    (question_id, question_revision, answer_text, is_correct)
                VALUES (?, ?, ?, ?)
            """, (
                question_id, question["revision"], answer_text,
                None if correct is None else int(correct),
            ))
            attempt_id = cursor.lastrowid
        return {
            "attempt_id": attempt_id, "is_correct": correct,
            "correct_index": question["correct_index"] if correct is not None else None,
            "model_answer": question["model_answer"] if correct is None else None,
            "explanation": question["explanation"], "manual_review_required": correct is None,
        }

    def review(self, attempt_id, payload):
        if not isinstance(payload, dict) or set(payload) != {"is_correct"} or type(payload.get("is_correct")) is not bool:
            raise QuestionError("is_correct boolean required")
        with self.connect() as db:
            row = db.execute("""
                SELECT a.id, q.kind FROM question_attempts a
                JOIN questions q ON a.question_id = q.id WHERE a.id=?
            """, (attempt_id,)).fetchone()
            if row is None:
                raise QuestionError("attempt not found", 404)
            if row["kind"] != "written":
                raise QuestionError("only written attempts can be reviewed")
            db.execute("UPDATE question_attempts SET is_correct=? WHERE id=?",
                       (int(payload["is_correct"]), attempt_id))
        return {"ok": True, "attempt_id": attempt_id, "is_correct": payload["is_correct"]}

    def history(self, limit=50):
        with self.connect() as db:
            rows = db.execute("""
                SELECT a.id, a.question_id, q.exam_part, q.subject, q.topic,
                       a.question_revision, a.is_correct, a.created_at
                FROM question_attempts a JOIN questions q ON q.id=a.question_id
                ORDER BY a.id DESC LIMIT ?
            """, (limit,)).fetchall()
            counts = db.execute("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END) AS correct,
                       SUM(CASE WHEN is_correct IS NULL THEN 1 ELSE 0 END) AS ungraded
                FROM question_attempts
            """).fetchone()
        return {
            "items": [dict(row) for row in rows],
            "stats": {"total": counts["total"], "correct": counts["correct"] or 0,
                      "ungraded": counts["ungraded"] or 0},
        }


def install_question_bank(app, authenticated, db_path):
    """Register routes and initialize independent SQLite storage."""
    bank = QuestionBank(db_path)
    bank.init_schema()
    bp = Blueprint("question_bank", __name__)

    @bp.errorhandler(QuestionError)
    def question_error(exc):
        return jsonify({"error": str(exc)}), exc.status

    @bp.before_request
    def question_security():
        if not authenticated():
            return jsonify({"error": "WebAuthn authentication required"}), 403
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not request.is_json:
                return jsonify({"error": "JSON required"}), 415
            expected = session.get("question_csrf_token", "")
            supplied = request.headers.get("X-Question-CSRF", "")
            if not expected or not supplied or not hmac.compare_digest(expected, supplied):
                return jsonify({"error": "CSRF token required"}), 403
            origin = request.headers.get("Origin")
            configured = app.config.get("QUESTION_ALLOWED_ORIGIN")
            if origin and configured and origin.rstrip("/") != configured.rstrip("/"):
                return jsonify({"error": "request origin not allowed"}), 403
        return None

    @bp.get("/study/questions")
    def questions_page():
        return render_template("questions.html")

    @bp.get("/api/questions/session")
    def question_session():
        if "question_csrf_token" not in session:
            session["question_csrf_token"] = secrets.token_urlsafe(32)
        return jsonify({
            "csrf_token": session["question_csrf_token"],
            "subjects": SUBJECTS, "parts": PARTS,
            "disclaimer": "자체 제작 학습문제이며 공식 기출문제가 아닙니다.",
        })

    @bp.get("/api/questions")
    def question_list():
        part = request.args.get("exam_part") or None
        subject = request.args.get("subject") or None
        status = request.args.get("status") or None
        if part and part not in PARTS or subject and subject not in SUBJECTS or status and status not in STATUSES:
            raise QuestionError("invalid filter")
        limit, offset = request.args.get("limit", "25"), request.args.get("offset", "0")
        if not limit.isdecimal() or not offset.isdecimal():
            raise QuestionError("invalid pagination")
        if not 1 <= int(limit) <= 100 or int(offset) > 1000000:
            raise QuestionError("pagination outside allowed range")
        return jsonify(bank.list(part, subject, status, int(limit), int(offset)))

    @bp.post("/api/questions")
    def question_create():
        return jsonify(bank.create(request.get_json(silent=True))), 201

    @bp.get("/api/questions/practice")
    def question_practice():
        part = request.args.get("exam_part") or None
        subject = request.args.get("subject") or None
        limit = request.args.get("limit", "10")
        if part and part not in PARTS or subject and subject not in SUBJECTS:
            raise QuestionError("invalid filter")
        if not limit.isdecimal() or not 1 <= int(limit) <= 20:
            raise QuestionError("practice limit must be 1-20")
        return jsonify({"items": bank.practice(part, subject, int(limit))})

    @bp.get("/api/questions/attempts")
    def question_history():
        return jsonify(bank.history())

    @bp.post("/api/questions/attempts")
    def question_attempt():
        return jsonify(bank.answer(request.get_json(silent=True))), 201

    @bp.post("/api/questions/attempts/<int:attempt_id>/review")
    def question_review(attempt_id):
        return jsonify(bank.review(attempt_id, request.get_json(silent=True)))

    @bp.get("/api/questions/<question_id>")
    def question_get(question_id):
        return jsonify(bank.get(question_id))

    @bp.patch("/api/questions/<question_id>")
    def question_patch(question_id):
        return jsonify(bank.modify(question_id, request.get_json(silent=True)))

    @bp.delete("/api/questions/<question_id>")
    def question_archive(question_id):
        return jsonify(bank.modify(question_id, request.get_json(silent=True), archive=True))

    app.register_blueprint(bp)
    return bank
