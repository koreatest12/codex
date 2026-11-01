"""Local-only security exam study UI over the repository's original 2027 question bank."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BANK = Path(os.getenv("STUDY_QUESTION_BANK", str(REPO / "data/study/security-exam-2027.json")))
DB = Path(os.getenv("STUDY_DB_PATH", str(HERE / "data" / "study.sqlite3")))
app = FastAPI(title="정보보안기사 학습 시스템", version="1.0")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def items():
    return json.loads(BANK.read_text(encoding="utf-8"))["items"]


def concepts():
    by_topic = {}
    for item in items():
        key = item["subject"] + "::" + item["topic"]
        if key not in by_topic:
            by_topic[key] = {
                "key": key, "subject": item["subject"], "topic": item["topic"],
                "summary": item.get("explanation", ""), "source_url": item.get("source_url", ""),
                "description": item.get("model_answer") or item.get("explanation", ""),
            }
    return by_topic


@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript("""
          CREATE TABLE IF NOT EXISTS progress (
            key TEXT PRIMARY KEY, done INTEGER NOT NULL, updated_at TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, question_key TEXT NOT NULL,
            selected INTEGER NOT NULL, correct INTEGER NOT NULL, created_at TEXT NOT NULL
          );
          CREATE INDEX IF NOT EXISTS idx_attempt_question ON attempts(question_key,id);
          CREATE TABLE IF NOT EXISTS wrong_notes (
            question_key TEXT PRIMARY KEY, memo TEXT NOT NULL DEFAULT '',
            review_date TEXT NOT NULL DEFAULT ''
          );
          CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL, publisher TEXT NOT NULL DEFAULT '',
            version TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT ''
          );
        """)
        for url in sorted({i.get("source_url", "") for i in items()} - {""}):
            conn.execute("INSERT OR IGNORE INTO sources(url,title,publisher) VALUES(?,?,?)",
                         (url, urlparse(url).netloc, "기존 학습자료에 기록된 참고 URL"))
        conn.commit()
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class Progress(BaseModel):
    done: bool


class Answer(BaseModel):
    question_key: str = Field(min_length=1)
    selected: int = Field(ge=0, le=9)


class Note(BaseModel):
    memo: str = Field(default="", max_length=3000)
    review_date: str = Field(default="", max_length=20)


class Source(BaseModel):
    url: str = Field(min_length=7, max_length=500)
    title: str = Field(min_length=2, max_length=200)
    publisher: str = Field(default="", max_length=150)
    version: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=1000)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        p = urlparse(value)
        if p.scheme not in ("https", "http") or not p.netloc or p.username or p.password:
            raise ValueError("http/https URL만 허용됩니다.")
        return value


@app.get("/")
def home():
    return FileResponse(HERE / "static/index.html")


@app.get("/health")
def health():
    with connect() as c:
        c.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/api/meta")
def meta():
    bank = items()
    subjects = list(dict.fromkeys(x["subject"] for x in bank))
    return {
        "subjects": subjects, "questions": sum(x["kind"] == "multiple_choice" for x in bank),
        "written": sum(x["kind"] == "written" for x in bank),
        "concepts": len(concepts()), "period": "2027-01-01 ~ 2029-12-31",
        "notice": "자체 제작 학습용 문제이며 공식 기출문제가 아닙니다."
    }


@app.get("/api/concepts")
def get_concepts(subject: str = ""):
    with connect() as c:
        complete = {r["key"] for r in c.execute("SELECT key FROM progress WHERE done=1")}
    return [{**v, "done": k in complete} for k, v in concepts().items()
            if not subject or v["subject"] == subject]


@app.post("/api/progress")
def save_progress(key: str, data: Progress):
    if key not in concepts():
        raise HTTPException(404, "학습 개념을 찾지 못했습니다.")
    with connect() as c:
        c.execute("INSERT INTO progress(key,done,updated_at) VALUES(?,?,?) "
                  "ON CONFLICT(key) DO UPDATE SET done=excluded.done,updated_at=excluded.updated_at",
                  (key, int(data.done), timestamp()))
    return {"saved": True, "done": data.done}


def question_bank():
    return {i["key"]: i for i in items() if i["kind"] == "multiple_choice"}


@app.get("/api/quiz")
def quiz(subject: str = "", count: int = Query(10, ge=1, le=100), mode: str = Query("all", pattern="^(all|wrong)$")):
    import random
    bank = question_bank()
    wrong = None
    if mode == "wrong":
        wrong = {a["question_key"] for a in wrong_attempts()}
    eligible = [q for q in bank.values()
                if (not subject or q["subject"] == subject) and (wrong is None or q["key"] in wrong)]
    random.shuffle(eligible)
    return {
        "available": len(eligible),
        "questions": [{"key": q["key"], "subject": q["subject"], "topic": q["topic"],
                       "prompt": q["prompt"], "options": q["options"], "difficulty": q["difficulty"]}
                      for q in eligible[:count]],
    }


@app.post("/api/answers")
def answer(data: Answer):
    q = question_bank().get(data.question_key)
    if not q:
        raise HTTPException(404, "문제를 찾지 못했습니다.")
    if data.selected >= len(q["options"]):
        raise HTTPException(422, "유효하지 않은 보기입니다.")
    correct = data.selected == q["correct_index"]
    with connect() as c:
        c.execute("INSERT INTO attempts(question_key,selected,correct,created_at) VALUES(?,?,?,?)",
                  (data.question_key, data.selected, int(correct), timestamp()))
    return {
        "correct": correct, "correct_index": q["correct_index"],
        "explanation": q["explanation"], "source_url": q.get("source_url", ""),
    }


def wrong_attempts():
    with connect() as c:
        return [dict(r) for r in c.execute("""
            SELECT a.question_key,a.selected,a.created_at,n.memo,n.review_date
            FROM attempts a
            LEFT JOIN wrong_notes n ON n.question_key=a.question_key
            WHERE a.id=(SELECT MAX(id) FROM attempts WHERE question_key=a.question_key)
              AND a.correct=0 ORDER BY a.id DESC
        """)]


@app.get("/api/wrongbook")
def wrongbook():
    bank = question_bank()
    return [{**a, "topic": bank[a["question_key"]]["topic"],
             "subject": bank[a["question_key"]]["subject"],
             "prompt": bank[a["question_key"]]["prompt"]}
            for a in wrong_attempts() if a["question_key"] in bank]


@app.put("/api/wrongbook/{key}")
def save_note(key: str, note: Note):
    if key not in question_bank():
        raise HTTPException(404, "문제를 찾지 못했습니다.")
    with connect() as c:
        c.execute("INSERT INTO wrong_notes(question_key,memo,review_date) VALUES(?,?,?) "
                  "ON CONFLICT(question_key) DO UPDATE SET memo=excluded.memo,review_date=excluded.review_date",
                  (key, note.memo, note.review_date))
    return {"saved": True}


@app.get("/api/analytics")
def analytics():
    all_concepts = concepts()
    all_questions = question_bank()
    with connect() as c:
        done = {r[0] for r in c.execute("SELECT key FROM progress WHERE done=1")}
        stats = {r["question_key"]: dict(r) for r in c.execute("""
          SELECT a.question_key,COUNT(*) AS attempts,SUM(correct) AS correct
          FROM attempts a GROUP BY a.question_key
        """)}
    result = []
    subjects = list(dict.fromkeys(x["subject"] for x in items()))
    for sub in subjects:
        unit = [x for x in all_concepts.values() if x["subject"] == sub]
        qkeys = [q["key"] for q in all_questions.values() if q["subject"] == sub]
        tries = sum(stats.get(k, {}).get("attempts", 0) for k in qkeys)
        correct = sum(stats.get(k, {}).get("correct", 0) for k in qkeys)
        result.append({
            "subject": sub, "total": len(unit),
            "done": sum(x["key"] in done for x in unit),
            "questions": len(qkeys), "attempts": tries, "correct": correct,
            "accuracy": round(100 * correct / tries) if tries else None,
        })
    return {"subjects": result, "total_done": len(done),
            "total_concepts": len(all_concepts), "wrong_count": len(wrong_attempts())}


@app.get("/api/sources")
def sources():
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM sources ORDER BY id")]


@app.post("/api/sources", status_code=201)
def create_source(payload: Source):
    with connect() as c:
        try:
            cur = c.execute("INSERT INTO sources(url,title,publisher,version,notes) VALUES(?,?,?,?,?)",
                            (payload.url,payload.title,payload.publisher,payload.version,payload.notes))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "중복 URL입니다.")
        return {"id": cur.lastrowid}


@app.put("/api/sources/{source_id}")
def update_source(source_id: int, payload: Source):
    with connect() as c:
        try:
            cur = c.execute("UPDATE sources SET url=?,title=?,publisher=?,version=?,notes=? WHERE id=?",
                            (payload.url,payload.title,payload.publisher,payload.version,payload.notes,source_id))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "중복 URL입니다.")
        if not cur.rowcount:
            raise HTTPException(404, "출처를 찾지 못했습니다.")
    return {"saved": True}


@app.delete("/api/sources/{source_id}")
def delete_source(source_id: int):
    with connect() as c:
        row = c.execute("SELECT url FROM sources WHERE id=?", (source_id,)).fetchone()
        if not row:
            raise HTTPException(404, "출처를 찾지 못했습니다.")
        if row["url"] in {x.get("source_url") for x in items()}:
            raise HTTPException(409, "기존 문항에 연결된 출처는 삭제할 수 없습니다.")
        c.execute("DELETE FROM sources WHERE id=?", (source_id,))
    return {"deleted": True}


@app.get("/api/written")
def written(subject: str = ""):
    return [{"key": x["key"], "subject": x["subject"], "prompt": x["prompt"],
             "model_answer": x.get("model_answer", ""), "explanation": x.get("explanation", ""),
             "source_url": x.get("source_url", "")}
            for x in items() if x["kind"] == "written" and (not subject or x["subject"] == subject)]


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    return response
