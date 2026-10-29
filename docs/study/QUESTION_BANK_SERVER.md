# 정보보안기사 문제은행 관리 서버

> 2027.01.01–2029.12.31 출제기준과 연결하는 **자체 제작 문제 관리 도구**. 공식 출제기관과 무관하며 공식 기출·복원문제·공식 답안은 이 서버에 기본 제공하지 않는다.

## 1. 구현 위치와 기존 시스템 보존

- 서버: `app/question_bank.py` — 기존 Flask/Gunicorn/WebAuthn 앱에 등록하는 보호된 API.
- 화면: `/study/questions` — `app/templates/questions.html`, `app/static/questions.js`, `app/static/questions.css`.
- 데이터: 기본 `/data/question-bank.db`, 별도 SQLite 파일. `QUESTION_BANK_DB_PATH`로 경로 변경 가능(선택). 기존 `/data/webauthn.db`, `/data/managed-data.db`, 개인 암호화 보관함을 덮어쓰지 않는다.
- DB 구조는 서비스 시작 시 **테이블이 없을 때만** 생성. 기존 문제는 재시작 후에도 Compose의 `security-data` 볼륨에 남는다.
- 서버 인증은 기존 **FIDO2/WebAuthn 세션**, 선택한 관리자 계정 모드에서는 **관리자 비밀번호 + 보안키**가 모두 필요하다. 관리자 권한의 문제 목록/정답, 모의학습도 모두 인증 뒤에만 접근 가능하다.

**서비스가 GitHub에 추가된 것과 실제 서버가 배포되어 실행 중인 것은 다르다.** GitHub는 소스코드와 CI를 보관하고, 이미 구축된 Ubuntu Docker 서버 또는 Windows Hyper-V의 Ubuntu 게스트에 변경된 이미지를 배포해야 한다.

## 2. 기능

| 기능 | 동작 | 주의 |
|---|---|---|
| 문제 등록 | 필기 객관식(4지선다), 실기 서술형 | 새 문제는 무조건 `draft`, 자체 작성 콘텐츠만 허용 |
| 관리 | 과목·구분·상태 필터, 페이지 조회, 수정 | 수정은 `expected_revision`으로 충돌 감지(409) |
| 문제 승인 | 정확한 정답·출처를 사람이 확인한 뒤 `reviewed=true`와 `published` 명시 | **자동 게시 없음** |
| 삭제 대신 보관 | 문제를 `archived`로 전환 | 기존 풀이 이력과 문제 원본 보존 |
| 모의학습 | `published` 문제에서 1~20개 무작위 선정 | 출제 전에는 정답/해설을 응답에서 제외 |
| 채점 | 객관식 즉시 자동채점, 해설/정답 제공 | 필답형은 자동 채점 없음; 모범답안을 읽고 직접 평가 |
| 오답/통계 | 풀이 이력, 정답·오답·서술형 미평가 집계 | 이 서버는 현재 **단일 관리자 전용**(다중 수강생 서비스 아님) |
| 출처·버전 | 문항별 HTTPS 참고 링크, 과목, 주제, 난이도 기록 | 필기/실기 범위와 실제 출제 가능성은 별개 |

과목 선택: 시스템 보안 / 네트워크 보안 / 어플리케이션 보안 / 정보보안 일반 / 정보보안 관리 및 법규. 실기는 과목 태그를 **학습 분류**로 사용하며, 공식 시험의 실기 과목이 5개라는 뜻이 아니다.

### 상태 흐름

```text
문제 직접 작성 → draft(미공개) → 사람 검토/승인 → published(모의학습 출제)
                                    ↘ archived(보관·출제 제외)
```

`published` 상태에서 내용을 수정할 경우 변경 사항이 즉시 출제될 수 있으므로, **수정 전 먼저 draft로 되돌린 뒤 검토 후 다시 승인**하는 운영 정책을 권장한다. 서버가 모든 내용의 정확성을 자동 검증해 주지는 않는다.

## 3. 실제 배포 순서

기존 WebAuthn 서버를 안전하게 운영 중이라는 전제이다. 운영 데이터 백업 후 병합/배포한다.

```bash
# Ubuntu의 실제 서버에서 저장소를 최신으로 동기화
git pull --ff-only origin main

# 현재 컨테이너 구성을 확인하고 기존 볼륨을 유지
docker compose ps
docker compose config

# 기존 시크릿과 .env는 보존한 상태에서 이미지만 재빌드
docker compose up -d --build

# 기존 애플리케이션 상태(간단한 헬스체크)
curl -fsS http://127.0.0.1:8080/healthz
```

서비스 시작 URL: 기존 설정의 `WEBAUTHN_ORIGIN` + `/study/questions`. 예: 로컬 환경이라면 `http://localhost:8080/study/questions`; **외부 접속은 인증서가 유효한 HTTPS**를 사용한다. 먼저 기존 `/` 화면에서 FIDO2 인증을 마쳐야 한다.

> 운영 서버, 도메인, 실행 호스트의 설정은 이 저장소에만으로 확정되지 않는다. GitHub PR을 만들어도 서버가 자동으로 시작하지 않으며, 운영 중인 인스턴스에서 실제 명령을 실행한 것으로 주장하지 않는다.

### Windows Server 사용

이 저장소에는 Windows Hyper-V + Ubuntu 게스트 배포 지원 문서 `docs/WINDOWS_SERVER_WAS.md`가 있다. **Windows 호스트에 이 Flask 서버를 직접 GitHub가 설치하는 구조가 아니다.** Ubuntu 게스트의 Docker Compose 서비스에서 업데이트한다. 운영 인증정보·SSH 키·Docker 데이터 볼륨은 보존한다.

## 4. 보호 API 명세

모든 API는 기존 인증된 웹브라우저의 **동일 출처** 요청이 기본이다. JSON을 변경하는 POST/PATCH/DELETE는 서버가 발급한 CSRF 헤더가 필요하다.

| 메서드 | 경로 | 결과 |
|---|---|---|
| GET | `/api/questions/session` | 과목 목록·CSRF 토큰(로그인 후) |
| GET | `/api/questions?exam_part=필기&subject=시스템 보안&status=draft&limit=20&offset=0` | 관리자용 문항 목록(정답 포함), 합계 |
| POST | `/api/questions` | 1개 새 문제 **초안 생성** |
| GET | `/api/questions/{id}` | 1문항 전체 조회 |
| PATCH | `/api/questions/{id}` | 검증된 필드 변경·버전 충돌 검사 |
| DELETE | `/api/questions/{id}` | **소프트 보관**, 실제 데이터/풀이 이력 삭제 아님 |
| GET | `/api/questions/practice?exam_part=필기&limit=10` | 공개 승인된 문제만, **정답/해설 제외** |
| POST | `/api/questions/attempts` | 답안 제출, 객관식 채점 또는 서술형 모범답안 |
| POST | `/api/questions/attempts/{attempt_id}/review` | 서술형 자가 평가(`is_correct` bool) |
| GET | `/api/questions/attempts` | 개인 풀이 이력(최근 50개)과 전체 통계 |

변경 요청 필수 헤더:
```text
Content-Type: application/json
X-Question-CSRF: <인증된 세션의 /api/questions/session 응답 csrf_token>
```

예시(참고용 · **브라우저 UI 사용 권장**):
```json
{
  "exam_part": "필기",
  "subject": "어플리케이션 보안",
  "kind": "multiple_choice",
  "topic": "OWASP API1",
  "prompt": "다른 사용자의 객체를 조회하지 못하도록 하는 서버 통제는?",
  "options": [
    "객체별 서버측 인가 확인",
    "화면의 글꼴 변경",
    "DNS 조회 주기 증가",
    "HTTP 압축 활성화"
  ],
  "correct_index": 0,
  "model_answer": "",
  "explanation": "객체 소유자와 공유 정책을 서버에서 검사해야 합니다.",
  "source_url": "https://api-security.owasp.org/editions/2023/en/0x11-t10/",
  "difficulty": 2
}
```

**이 예시는 자체 제작 문제**이며 실제 시험 기출이 아니다. 상태를 `published`로 즉시 생성하는 요청은 거부한다. 기존 문제를 출제 승인할 때만 `PATCH {"status":"published","expected_revision":1,"reviewed":true}`를 보낸다.

## 5. 저장·보안·백업

- 서버 인증 전에는 관리 화면, 문제 API, 풀이 API 모두 403. 관리자 계정이나 키 인증을 우회하는 공개 등록 경로가 없다.
- JSON 쓰기는 세션 CSRF 토큰을 검증하고, `Origin`이 있으면 서버에 설정된 신뢰 가능한 출처와 일치하는지 검사한다.
- 응답은 기존 서버의 `Cache-Control: no-store`, CSP, SameSite=Strict 쿠키 및 HTTPS 설정을 따른다.
- 모든 DB 쿼리는 매개변수 사용. 입력은 길이·형식·시험 구분·난이도를 검사한다. 현재 문제 텍스트/서술 답안은 **별도 AES 암호화를 적용하지 않는다**. 따라서 개인정보, 비밀번호, 액세스 토큰, 실제 사고 증거, 민감 자료를 입력하지 않는다.
- 문제은행 DB의 **SQLite WAL 파일까지 고려한 일관된 백업**을 수행한다. 운영 중 단순히 DB 파일만 복사하는 것은 피하고, 애플리케이션 정지 중 백업하거나 SQLite `backup()` API를 사용한다. 관리자가 접근 가능한 보안 위치에 보관하고 복원 테스트를 한다.
- **중요:** `docker compose down -v`는 기존 보안키/개인 데이터 볼륨을 포함해 데이터 삭제 위험이 있으므로 사용하지 않는다.
- GitHub Actions와 소스에는 실제 학습 기록, 개인 답안, 인증 토큰, DB 파일을 커밋하지 않는다.
- 단일 관리자 전용 첫 버전이므로 수강생별 계정, 외부 공개 시험, 온라인 동시응시, 정식 출제 승인 결재는 아직 미구현이다.

## 6. 검증

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=app python -m unittest tests/test_question_bank.py -v
# 저장소 전체 테스트:
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=app python -m unittest discover -s tests -v
```

CI는 `.github/workflows/blank.yml`의 Python 테스트로 수행한다. 포함된 테스트는 인증·CSRF·초안/승인·정답 비노출·객관식 채점·서술형 자가평가·버전 충돌·보관·재시작 시 DB 연결을 다룬다. 운영 서버 실제 배포 검증은 별도다.

## 7. 학습 근거

- [2027–2029 출제기준 대응표](./2027_EXAM_CROSSWALK.md)
- [신규 심화 학습자료](./2027_ADVANCED_SECURITY.md)
- [실기 연습 워크북](./2027_PRACTICAL_WORKBOOK.md)
- [통합 학습 가이드](./2027_STUDY_GUIDE.md)
- [한국방송통신전파진흥원 출제기준](https://www.cq.or.kr/qh_cusgm10_001.do)
- [OWASP API Security Top 10:2023](https://api-security.owasp.org/editions/2023/en/0x11-t10/)
- [NIST SP 800-207 Zero Trust](https://csrc.nist.gov/pubs/sp/800/207/final)

**문제 콘텐츠는 기본으로 비어 있다.** 오인·저작권 문제를 피하기 위해 기존 PDF의 문장을 자동 추출하거나 공식 기출로 게시하지 않는다. 관리자가 검증한 자체 문제를 입력하고 직접 승인한 뒤에만 모의학습에 출제된다.
