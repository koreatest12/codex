# 정보보안기사 학습 시스템 (GitHub 통합판)

이 폴더는 `koreatest12/codex`의 **기존** `data/study/security-exam-2027.json` 데이터를 재사용해 동작하는 독립형 로컬 FastAPI 학습 앱입니다.

## 기능

- 필기 5과목 개념 목록 및 학습완료 상태, 과목별 검색
- 자체 제작 객관식 100문항 랜덤 풀이, 서버 채점 및 정답 해설
- 실기 서술형 연습 20문항의 답안 확인 (자동 채점 없음)
- 최신 풀이가 틀린 문항의 오답노트, 메모 및 복습 날짜 저장
- 과목별 진도 및 누적 정답률 표시
- 연결 출처의 제목/발행기관/버전/메모 관리 및 출처 삭제 보호
- 로컬 SQLite 데이터 영속화

**주의:** 위 콘텐츠는 기존 저장소에 수록된 자체 제작 연습자료입니다. 공식 기출문제가 아닙니다. 출처 URL은 참고 링크이며 해설이 기관 공식 설명이라는 의미는 아닙니다. 2027–2029 출제범위 전체를 빠짐없이 다루는 완성 교재는 아닙니다.

## Windows 실행

저장소 루트에서:

```powershell
cd security-study-system
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

브라우저 주소: http://127.0.0.1:8000

Linux에서도 `python3 -m venv .venv`로 가상환경을 만들고 동일하게 실행할 수 있습니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q tests
```

## 안전 및 데이터

- **로컬 개인 전용**입니다. 관리자 인증, HTTPS, 다중 사용자 기능이 없으므로 `0.0.0.0`에 공개하지 마세요.
- 문제은행 입력은 기존 저장소의 `data/study/security-exam-2027.json`을 읽습니다. 해당 파일을 삭제하거나 수정하지 않습니다.
- 공부 기록은 이 폴더의 `data/study.sqlite3`에 보관됩니다. 서버를 종료한 후 DB 파일을 백업하세요. 이 폴더의 `data/`는 Git 추적 대상이 아닙니다.
- 기존 루트 Flask/WebAuthn 서버나 배포 구성은 변경하지 않습니다. 별도 포트에서 직접 실행하는 개인 학습 앱입니다.
- 원래 채팅에서 제공한 35개 개념·45개 문제 ZIP과는 **다른 GitHub 통합 구현**입니다. 이 버전은 저장소의 기존 2027 학습은행을 재사용하므로 문항 구성과 개념 상세 내용이 다릅니다.
