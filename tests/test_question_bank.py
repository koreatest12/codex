"""API regression coverage with an isolated temporary question-bank database.

The session marker here emulates an already-verified authentication result;
cryptographic WebAuthn verification remains in tests/test_server_admin.py.
"""
import tempfile
import unittest
from pathlib import Path

from flask import Flask, session
from question_bank import QuestionBank, install_question_bank


class QuestionBankServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(__file__).resolve().parents[1] / "app" / "templates"
        self.app = Flask(__name__, template_folder=str(folder))
        self.app.secret_key = "isolated-test-session-secret"
        self.app.config.update(TESTING=True, QUESTION_ALLOWED_ORIGIN="http://localhost")
        self.bank = install_question_bank(
            self.app, lambda: session.get("webauthn_passed") is True,
            Path(self.temp.name) / "question-bank.db"
        )
        self.client = self.app.test_client()

    def authenticate(self):
        with self.client.session_transaction() as current:
            current["webauthn_passed"] = True
        response = self.client.get("/api/questions/session")
        self.assertEqual(200, response.status_code)
        return response.get_json()["csrf_token"]

    def send(self, method, path, payload, token):
        return self.client.open(path, method=method, json=payload,
                                headers={"X-Question-CSRF": token})

    @staticmethod
    def multiple():
        return {
            "exam_part": "필기",
            "subject": "어플리케이션 보안",
            "kind": "multiple_choice",
            "topic": "객체 수준 인가",
            "prompt": "다른 사용자 소유의 문서를 읽지 못하도록 하는 서버 통제는?",
            "options": ["서버 측 객체 인가", "화면 색상 변경", "DNS 캐시 증가", "압축률 향상"],
            "correct_index": 0,
            "model_answer": "",
            "explanation": "서버는 매 요청마다 자원 소유자와 허용된 접근 주체를 확인해야 합니다.",
            "source_url": "https://api-security.owasp.org/editions/2023/en/0x11-t10/",
            "difficulty": 2,
        }

    @staticmethod
    def written():
        return {
            "exam_part": "실기",
            "subject": "네트워크 보안",
            "kind": "written",
            "topic": "클라우드 VPC",
            "prompt": "클라우드 보안 그룹과 NACL의 차이를 서술하시오.",
            "options": [],
            "correct_index": None,
            "model_answer": "보안 그룹은 리소스에 적용하는 상태 저장 규칙, NACL은 서브넷 수준 상태 비저장 규칙입니다.",
            "explanation": "네트워크 경로, 인바운드/아웃바운드 정책과 상태 저장 여부를 구분합니다.",
            "source_url": "https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html",
            "difficulty": 3,
        }

    def test_authentication_and_csrf_gate(self):
        self.assertEqual(403, self.client.get("/api/questions").status_code)
        self.assertEqual(403, self.client.get("/study/questions").status_code)
        self.assertEqual(403, self.client.get("/api/questions/session").status_code)
        self.assertEqual(403, self.client.post("/api/questions", json=self.multiple()).status_code)
        token = self.authenticate()
        self.assertEqual(200, self.client.get("/study/questions").status_code)
        self.assertEqual(403, self.client.post("/api/questions", json=self.multiple()).status_code)
        self.assertEqual(415, self.client.post("/api/questions", data="text",
                                             headers={"X-Question-CSRF": token}).status_code)
        self.assertEqual(403, self.client.post("/api/questions", json=self.multiple(),
            headers={"X-Question-CSRF": token, "Origin": "https://untrusted.example"}).status_code)
        self.assertEqual(201, self.send("POST", "/api/questions", self.multiple(), token).status_code)

    def test_draft_review_publish_practice_and_scoring(self):
        token = self.authenticate()
        created = self.send("POST", "/api/questions", self.multiple(), token)
        self.assertEqual(201, created.status_code)
        question = created.get_json()
        self.assertEqual("draft", question["status"])
        self.assertEqual("self-authored", question["source_type"])
        self.assertEqual([], self.client.get("/api/questions/practice").get_json()["items"])
        url = "/api/questions/" + question["id"]
        denied = self.send("PATCH", url, {"status": "published",
                                            "expected_revision": 1}, token)
        self.assertEqual(400, denied.status_code)
        approved = self.send("PATCH", url, {"status": "published",
                                              "expected_revision": 1,
                                              "reviewed": True}, token)
        self.assertEqual(200, approved.status_code)
        self.assertEqual(2, approved.get_json()["revision"])
        practice = self.client.get("/api/questions/practice?exam_part=필기&limit=5")
        self.assertEqual(1, len(practice.get_json()["items"]))
        listed = practice.get_json()["items"][0]
        for hidden in ("correct_index", "model_answer", "explanation"):
            self.assertNotIn(hidden, listed)
        # Editing an approved question must not silently publish unreviewed text,
        # even if the same PATCH claims reviewed=true.
        changed = self.send("PATCH", url, {
            "expected_revision": 2, "status": "published", "reviewed": True,
            "prompt": "다른 사용자의 문서에 대한 접근을 막는 서버 통제는 무엇인가요?"
        }, token)
        self.assertEqual(200, changed.status_code)
        self.assertEqual("draft", changed.get_json()["status"])
        self.assertEqual([], self.client.get("/api/questions/practice").get_json()["items"])
        reapproved = self.send("PATCH", url, {
            "expected_revision": 3, "status": "published", "reviewed": True
        }, token)
        self.assertEqual("published", reapproved.get_json()["status"])
        result = self.send("POST", "/api/questions/attempts", {
            "question_id": question["id"], "selected_choice": 2
        }, token)
        self.assertEqual(201, result.status_code)
        self.assertFalse(result.get_json()["is_correct"])
        self.assertEqual(0, result.get_json()["correct_index"])
        stats = self.client.get("/api/questions/attempts").get_json()["stats"]
        self.assertEqual(1, stats["total"])
        self.assertEqual(0, stats["correct"])

    def test_revision_conflicts_archive_and_invalid_input(self):
        token = self.authenticate()
        invalid = self.multiple()
        invalid["correct_index"] = True
        self.assertEqual(400, self.send("POST", "/api/questions", invalid, token).status_code)
        invalid = self.multiple()
        invalid["status"] = "published"
        self.assertEqual(400, self.send("POST", "/api/questions", invalid, token).status_code)
        invalid = self.multiple()
        invalid["source_url"] = "file:///etc/passwd"
        self.assertEqual(400, self.send("POST", "/api/questions", invalid, token).status_code)
        question = self.send("POST", "/api/questions", self.multiple(), token).get_json()
        path = "/api/questions/" + question["id"]
        update = self.send("PATCH", path, {"topic": "API1:2023",
                                         "expected_revision": 1}, token)
        self.assertEqual(200, update.status_code)
        self.assertEqual(409, self.send("PATCH", path, {
            "topic": "stale", "expected_revision": 1
        }, token).status_code)
        archive = self.send("DELETE", path, {"expected_revision": 2}, token)
        self.assertEqual(200, archive.status_code)
        self.assertEqual("archived", archive.get_json()["status"])
        self.assertEqual(0, self.client.get("/api/questions/practice").get_json()["items"].__len__())
        self.assertEqual(400, self.client.get("/api/questions?status=published%27%20OR%201=1").status_code)

    def test_written_requires_manual_review(self):
        token = self.authenticate()
        question = self.send("POST", "/api/questions", self.written(), token).get_json()
        self.send("PATCH", "/api/questions/" + question["id"],
                  {"expected_revision": 1, "reviewed": True, "status": "published"}, token)
        response = self.send("POST", "/api/questions/attempts", {
            "question_id": question["id"], "written_response": "SG는 상태 저장입니다."
        }, token)
        self.assertEqual(201, response.status_code)
        answer = response.get_json()
        self.assertIsNone(answer["is_correct"])
        self.assertTrue(answer["manual_review_required"])
        self.assertIn("NACL", answer["model_answer"])
        self.assertEqual(1, self.client.get("/api/questions/attempts").get_json()["stats"]["ungraded"])
        review = self.send("POST", "/api/questions/attempts/" +
                           str(answer["attempt_id"]) + "/review", {"is_correct": False}, token)
        self.assertEqual(200, review.status_code)
        self.assertEqual(0, self.client.get("/api/questions/attempts").get_json()["stats"]["ungraded"])
        self.assertEqual(400, self.send("POST", "/api/questions/attempts/" +
                           str(answer["attempt_id"]) + "/review", {"is_correct": "yes"}, token).status_code)

    def test_persistence_across_connections(self):
        token = self.authenticate()
        self.send("POST", "/api/questions", self.multiple(), token)
        other = QuestionBank(Path(self.temp.name) / "question-bank.db")
        other.init_schema()
        self.assertEqual(1, other.list()["total"])
        self.assertEqual(1, self.client.get("/api/questions").get_json()["total"])


if __name__ == "__main__":
    unittest.main()
