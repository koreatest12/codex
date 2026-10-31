# 2027년 정보보안기사 문제은행 120문항 대량 반영 가이드

> **120문항 모두 자체 제작·비공식·초안용.** GitHub에 데이터가 추가되었다고 운영 서버 DB 또는 공개 모의학습에 자동 반영되는 것은 아닙니다.

## 범위·출처·구조

| 구분 | 신규 자료 |
|---|---|
| 필기 시스템 보안 | 20문항 |
| 필기 네트워크 보안 | 20문항 |
| 필기 어플리케이션 보안 | 20문항 |
| 필기 정보보안 일반 | 20문항 |
| 필기 정보보안 관리 및 법규 | 20문항 |
| 실기 서술형 | 20문항 |
| 합계 | **120문항** |

저장: [security-exam-2027.json](../../data/study/security-exam-2027.json). 각 데이터에는 **안정적인 중복 방지 키**(`SEC27-MC-...` 또는 `SEC27-WR-...`), 과목·구분·주제·난이도, 문제와 선택지 또는 모범답안, 해설과 HTTPS 참고 URL이 들어 있다. 원문 출제기준 전체를 복제하거나 공식 문항을 무단 재게시하지 않는다.

- 이 100개 필기 문제는 **개념 정의를 읽고 알맞은 용어를 고르는 자체 연습문제**이며 실제 필기 시험과 동일한 난도·배점·출제빈도를 의미하지 않는다.
- 20개 실기 문항은 설명/점검/계산 연습용 **서술형**이며 자동 채점하지 않는다.
- 사용한 참고 URL은 해당 **기술 분야의 설명 근거**, 공식 기출 원출처가 아니다. 출제기준의 최신 정보는 [KCA](https://www.cq.or.kr/qh_cusgm10_001.do)에서 확인한다.
- 인간 검토 전 상태는 **draft**로 유지하고, 정답·해설의 정확성이 확인된 개별 문항만 모의학습으로 승인한다.

## 1. GitHub에서 검증

```bash
# 프로젝트 루트, 격리된 Python 환경/requirements.txt 설치 후
PYTHONPATH=app python scripts/study-question-import.py \
  --db /tmp/unused-question-bank.db

# dry-run은 파일 존재 여부와 관계없이 DB 파일을 생성하거나 수정하지 않음
PYTHONPATH=app python -m unittest tests/test_study_question_import.py -v
```

**예상 결과:** `validated: 120`, `mode: dry-run`, `inserted: 0`. 실제 출력과 검증이 일치하는지는 해당 커밋의 CI를 확인한다.

## 2. 분리된 개발 DB에 실제 초안 데이터 생성

운영 데이터를 건드리지 않고 처음부터 테스트하려면:

```bash
mkdir -p /tmp/study-bank-2027
python3 scripts/study-question-import.py \
  --seed data/study/security-exam-2027.json \
  --db /tmp/study-bank-2027/questions.db --apply
```

최초 생성된 파일에만 **120문항 draft**가 들어간다. 파일을 재사용해 두 번 적용할 경우 동일 안정 키는 한 번만 들어간다. 기존 DB를 지정하면 반드시 별도 백업 디렉터리가 있어야 적용할 수 있다.

## 3. 기존 Ubuntu WAS의 실제 문제은행 DB에 적용 (명시적 승인 시만)

**전제:** 관리자가 실제 운영 인스턴스 및 백업·복원 가능성을 확인했고, 기존 데이터에 신규 초안 120개를 추가하려는 의사를 결정했다. 아래 명령은 직접 운영 서버에서 실행해야 하며 GitHub Actions에서 원격 실행하지 않는다.

기존 Docker 이미지에 포함된 스크립트와 데이터 파일을 사용할 수 있다. 먼저 확인:

```bash
docker compose ps
docker compose exec -T web sh -c 'test -f /opt/codex-source/data/study/security-exam-2027.json && test -f /opt/codex-source/scripts/study-question-import.py'
```

기본 `/data/question-bank.db`이 이미 있다면 **다른 디렉터리에 백업할 위치를** 준비한다. DB는 기존 Compose 영구 볼륨에 두되 백업은 **별도 안전한 스토리지**에 복제한다.

```bash
# 컨테이너 /data 아래 예시: 나중에 반드시 호스트의 외부 백업 공간으로 복사하고 복원 검증
docker compose exec -u www-data web mkdir -p /data/study-import-backup

# 먼저 변경 없는 dry-run
docker compose exec -u www-data web python3 \
  /opt/codex-source/scripts/study-question-import.py \
  --seed /opt/codex-source/data/study/security-exam-2027.json \
  --db /data/question-bank.db

# 검토·승인 후 초안만 추가하고 적용 전 SQLite 일관성 백업 생성
docker compose exec -u www-data web python3 \
  /opt/codex-source/scripts/study-question-import.py \
  --seed /opt/codex-source/data/study/security-exam-2027.json \
  --db /data/question-bank.db --apply \
  --backup-dir /data/study-import-backup
```

**주의:** 백업은 처음에 동일 Docker 볼륨 안에 놓이므로 단일 장애로 소실될 수 있다. 검증한 후 접근통제된 별도의 호스트/외부 스토리지로 복사해야 한다. 기존 DB가 비어 있거나 없는 경우 파일 생성에 백업은 강제하지 않지만, 운영 환경에서는 별도 백업을 먼저 권장한다.

## 4. 반복 적용과 보안

- 신규 문항의 ID는 **변하지 않는 `key`의 SHA-256 기반**으로 생성. 동일 키를 다시 가져오면 중복 생성하지 않음.
- 기존 문항의 내용·정답·승인 여부·풀이 이력은 **덮어쓰지 않음**. 문항을 보관/승인했어도 재가져오기 시 자동 해제하거나 갱신하지 않음.
- 기존 DB에 적용하려면 `--backup-dir` 필수. 백업명이 이미 존재하면 덮어쓰지 않고 실패하므로 별도 신규 디렉터리를 준비한다.
- 가져오기 전 **120문항 전부 구조/분야/정답/URL 입력 형식**을 검사한다. 내용의 참·거짓과 법규 최신 여부를 기계적으로 확정하는 검사는 아니다.
- CSV/실제 개인정보/사고 로그/비밀키를 이 파일에 혼합해 넣지 않는다. 공개 GitHub 저장소에 운영 DB를 올리지 않는다.
- 모의학습은 `published`만 출제. 개별 답안 검토·수동 승인은 기존 `/study/questions`에서 관리자 WebAuthn 세션 뒤 수행.
- 다른 운영 변경과 함께 사용할 때 `docker compose down -v`를 실행하지 않는다.

## 5. 문제별 재검토 순서

1. 용어 정의와 시험 기준의 연도·과목 위치를 비교한다.
2. 정답과 다른 선택지가 동시에 맞는 해석이 가능한지 검토한다.
3. 출처 URL이 적절한 기술 원문인지, 2027 당시에도 유효한지 검토한다.
4. 서술형 모범답안을 기존 [실기 워크북](2027_PRACTICAL_WORKBOOK.md)과 비교한다.
5. 관리 UI에서 **개별 출제 승인**한 뒤 문제를 풀고 해설의 오해 소지를 기록한다.

연계 자료: [개념 심화판](2027_SYSTEMATIC_EXTENSIONS.md), [기존 문제은행 서버](QUESTION_BANK_SERVER.md), [2027 과목별 대조표](2027_EXAM_CROSSWALK.md).
