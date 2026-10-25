# WAS 설치·관리 (운영 서버에서 직접 실행)

이 저장소에는 **WAS가 이미 구현**돼 있습니다: Nginx(컨테이너 8080) →
Gunicorn(내부 127.0.0.1:8000) → Flask/WebAuthn. 암호화 저장소는
Compose 관리형 `security-data` Docker 볼륨(`/data`)에 보존합니다.
`scripts/was-manager.py`는 이 기존 구성을 관리하는 **호스트 전용 CLI**입니다.
기존 로그인·암호화 규칙을 우회하는 웹 기반 Docker 관리자 페이지는 만들지 않습니다.

**중요:** GitHub Actions에서 이미지가 빌드돼도 개인 PC/Ubuntu 서버 또는
클라우드 VM에 실제로 설치되는 것은 아닙니다. 실제 호스트의 Docker 권한,
디스크, DNS, TLS 및 FIDO2 실물 키 등록은 별도로 필요합니다.

## 1. 최초 설치 (Ubuntu Server)

Ubuntu 24.04 같은 실제 서버에서 아래 명령을 실행합니다. 이 스크립트는
원격 SSH 접속이나 GitHub Actions를 통해 자동 설치하지 않습니다.

```bash
git clone https://github.com/koreatest12/codex.git
cd codex
sudo python3 scripts/was-manager.py install-docker
python3 scripts/was-manager.py init --rp-id localhost --origin http://localhost:8080
sudo python3 scripts/was-manager.py doctor
sudo python3 scripts/was-manager.py deploy
sudo python3 scripts/was-manager.py health
```

- Windows 10/11 개발 PC라면 Docker Desktop + WSL2의 Linux 터미널을 사용할 수 있지만,
  **Windows Server는 Docker Desktop 공식 지원 대상이 아닙니다.**
  Windows Server에서는 Hyper-V Ubuntu VM 안에서 Docker Engine을 설치해야 합니다.
  전체 절차는 [Windows Server WAS 설치 안내](WINDOWS_SERVER_WAS.md)를 참고하세요.
- 서버에 Docker와 Compose가 이미 작동한다면 설치 명령은 생략합니다.
- `init`은 **신규 서버용**입니다. 기존 `.env`, `secrets/`, DB가 있는
  서버에서는 절대 재실행하지 마세요. 덮어쓰기를 거부합니다.
- `deploy`는 이미지를 빌드하고 서비스를 시작합니다. 기존
  `security-data` 볼륨을 삭제하지 않으며 서비스의 로컬
  `/healthz`가 정상 응답해야 성공으로 처리합니다.
- 새 사용자 등록 시 `http://localhost:8080`에 접속하여 호스트의
  `secrets/webauthn_bootstrap_token`을 로컬에서 확인하고
  **실제 FIDO2 보안키를 등록**해야 합니다. 이 과정은 자동화할 수 없습니다.

다른 컴퓨터/외부에서 접속할 경우 도메인에 맞춘
`--rp-id example.com --origin https://example.com`을 최초 설치 때 지정하고
호스트 앞에 별도의 HTTPS 역방향 프록시를 설치해야 합니다.
외부 주소와 WebAuthn RP ID가 맞아야 합니다. 컨테이너의 기본 포트 바인딩은
**127.0.0.1 전용**입니다. 방화벽 포트나 Docker TCP API를 무단으로 열지 마세요.

## 2. 일상 운영 명령

모든 명령은 저장소 루트에서 실행하며 Docker 접근 권한이 필요합니다.
운영 서버에서 `sudo`로 사용하는 예시입니다.

| 목적 | 명령 |
|---|---|
| 설정·도커 사전 점검 | `sudo python3 scripts/was-manager.py doctor` |
| 초기 생성 (처음 한 번) | `python3 scripts/was-manager.py init` |
| 빌드·배포·헬스 검사 | `sudo python3 scripts/was-manager.py deploy` |
| 기존 이미지로 시작 | `sudo python3 scripts/was-manager.py start` |
| 데이터 보존하고 중지 | `sudo python3 scripts/was-manager.py stop` |
| 서비스만 재시작 | `sudo python3 scripts/was-manager.py restart` |
| 컨테이너·보안 상태 | `sudo python3 scripts/was-manager.py status` |
| 로컬 통신 상태 | `sudo python3 scripts/was-manager.py health` |
| 최근 로그 100줄 | `sudo python3 scripts/was-manager.py logs` |
| 로그 실시간 확인 | `sudo python3 scripts/was-manager.py logs --follow` |
| 안전하게 DB 볼륨 백업 | `sudo python3 scripts/was-manager.py backup` |
| 백업 후 최신 소스 빌드·배포 | `sudo python3 scripts/was-manager.py upgrade` |

`logs --tail 250`처럼 출력 범위를 제한할 수 있습니다. 로그에는
민감한 요청 메타데이터가 포함될 수 있으므로 공개 GitHub 이슈에
원문을 그대로 붙이지 마세요.

## 3. 인증·관리 기능

- 브라우저 내 기존 관리자 UI: FIDO2 보안키 등록/로그인, 두 번째 보안키 추가,
  개인 정보 금고, 암호화 데이터 조회/변경, 서버 최종 운영 상태
- 선택적으로 비밀번호 + FIDO2 모두 필요한 관리자 계정 사용:
  `python3 scripts/setup-admin-account.py --username admin`
  (계정 비밀번호는 대화형 로컬 터미널에 한 번만 표시됨)
- `secrets/admin_account`이 있으면 관리자 계정용 Compose overlay가
  자동으로 선택됩니다. 기존 설치를 **임의로 계정 모드로 전환하지 않습니다**.
- BIFF Java 21 계획 도구는 기존 Docker 이미지에 포함되어 있고,
  `scripts/data-manager.py`로 버전 관리형 공개 자료를 처리합니다.
- 별도 `career-note/`는 Node.js/pnpm/Cloudflare 기반 앱입니다.
  이 Flask WAS를 설치한다고 `career-note` 서비스가 자동 배포되지는
  않습니다. 각각의 배포 대상, 인증, DB 및 비용 정책을 유지해야 합니다.

## 4. 백업, 업데이트 및 복구

`backup`은 Compose 서비스가 실행 중일 때 **먼저 중지**한 다음
프로젝트의 기존 데이터 볼륨을 읽기 전용으로 마운트하여 tar.gz를
`backups/`에 생성합니다. 이후 서비스는 정상·실패 여부와 관계없이
재시작을 시도합니다. 백업에 실패해도 볼륨은 지우지 않습니다.

- `backups/`는 Git과 Docker 이미지에서 제외됩니다.
- 출력 파일은 호스트에 개인적으로 보관하며 **암호화된 외부 저장소에**
  복제하세요. tar.gz 자체는 암호화 파일이 아닙니다.
- `secrets/data_encryption_key` 및 관련 비밀키 파일은 백업에
  포함되지 않습니다. 별도로 안전하게 백업·복구해야 합니다.
- 스크립트에는 `docker compose down -v`, `docker volume rm`,
  디스크 포맷, 자동 복원 기능을 넣지 않았습니다.
- 복원은 **관리자가 호스트에서 수동으로**, 현재 컨테이너를 중지하고
  새 빈 데이터 볼륨에 검증된 아카이브를 복원한 다음 동일한
  암호화 키/인증 설정을 사용하는 방식으로 수행하세요.
  기존 볼륨에 백업을 바로 풀어 덮어쓰지 마세요.
- `upgrade`는 백업 성공 후 빌드·재생성합니다. 최신 이미지에 문제가
  있으면 이전 커밋/이미지를 검토하고 **같은 데이터 볼륨을 보존**하여
  복구해야 합니다. 자동 무검증 롤백은 하지 않습니다.

`health`는 Nginx에서 Flask까지의 경로만 검사하며 로그인 완료,
외부 HTTPS 접속, 저장소의 모든 자료, 또는 서버의 24시간 운영을
보장하지 않습니다. 내부 운영 정보 `/api/system/status`는
WebAuthn 인증 후에만 확인할 수 있습니다.

## 5. 검증 및 한계

GitHub CI에서는 `tests/test_was_manager.py`가 Docker 없이
CLI의 비밀키 덮어쓰기 금지, 경로 검증, 실패 시 서비스 재시작,
데이터 볼륨 삭제 방지를 시험합니다. Docker Image CI와
Latest Linux Image and Container Server는 실제 **일회성 CI 컨테이너**의
빌드, 테스트, WebAuthn 인증 게이트를 추가 검증합니다.

CI의 일회성 Docker 호스트는 사용자의 개인 서버가 아닙니다.
실제 운영 인스턴스 설치가 완료됐다고 기록하려면 본인 호스트에서
`deploy`, `health`, 보안키 등록 및 운영 백업까지 확인해야 합니다.

추가 참고: [Docker 운영 문서](DOCKER_OPERATIONS.md),
[보안 정책](../SECURITY.md), [GitAIOps](GITAIOPS.md).
