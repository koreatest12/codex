# Datadog Synthetic tests — 키 등록, 실행, 결과 다운로드

이 저장소의 `.github/workflows/datadog-synthetics.yml`은 **선택적 Datadog 외부 테스트**입니다.
Python/Docker/Linux 기본 CI와 분리되어 있으며, Datadog 사용자가 키를 등록한 뒤
**Actions의 Run workflow 또는 GitHub CLI로 수동 실행**합니다. Datadog 계정,
Synthetic 테스트 및 권한이 없으면 실제 테스트는 실행할 수 없습니다.

## 오류 분석과 수정 (2026-10-22)

이전 워크플로는 `push` 및 `pull_request`마다 실행하면서
`DD_API_KEY`/`DD_APP_KEY` 값이 없으면 `Missing API or APP keys`로 실패했습니다.
또한 Node.js 20 기반의 `actions/checkout@v4`, Datadog 액션 `v1.4.0`과
`ubuntu-latest` 러너를 사용했습니다.

- **인증:** 키 미등록 시 명시적 오류와 등록 경로를 출력합니다.
- **Node.js:** `actions/checkout@v7.0.1`, Node.js 24 기반 Datadog
  `v4.1.1`(전체 커밋 SHA로 고정), `actions/upload-artifact@v6` 사용.
- **러너:** `ubuntu-24.04`에 고정해 `ubuntu-latest` 레이블 이전 영향을 피합니다.
- **트리거:** `workflow_dispatch`만 허용해 키가 없는 저장소의
  PR 및 main CI가 매번 실패하지 않도록 합니다. 수동 테스트에서
  키 누락/인증 실패/테스트 실패는 정상적으로 **실패** 처리합니다.
- **다운로드:** 인증키가 아닌, 통과/실패/스킵/미발견 건수 및 실행 결론만
  담은 `datadog-synthetics-summary` Actions artifact를 생성해 7일 보관합니다.
  테스트 원본 응답·URL·키·개인정보는 업로드하지 않습니다.

## 1. Datadog에서 키 생성

1. [Datadog 공식 키 관리 안내](https://docs.datadoghq.com/account_management/api-app-keys/)에 따라
   본인 Datadog 조직의 Organization Settings > API Keys에서 API 키를 생성합니다.
2. Organization Settings > Application Keys에서 **Application Key**를 생성합니다.
   Synthetic 테스트 실행에 필요한 최소 권한만 지정하세요.
3. 발급 직후 값을 안전하게 보관하세요. 특히 One-Time Read 정책이 켜진
   조직의 Application Key 비밀값은 나중에 다시 확인/다운로드할 수 없습니다.

**이 저장소, ChatGPT, GitHub Actions는 Datadog 인증키를 임의로 발급하거나
기존 GitHub Secrets 값으로부터 다운로드할 수 없습니다.** 키가 없으면 Datadog의
권한 있는 계정에서 새로 발급해야 합니다.

## 2. 키를 GitHub Secrets에 안전하게 설치

로컬 PC에서 [GitHub CLI](https://cli.github.com/)를 설치한 후:

```bash
gh auth login
bash scripts/datadog-synthetics.sh install
bash scripts/datadog-synthetics.sh status
```

`install` 명령은 터미널에서 API/Application 키를 **숨김 입력**으로 받아
`koreatest12/codex`의 Actions Secrets `DD_API_KEY`, `DD_APP_KEY`에
stdin으로 안전하게 등록합니다. 키는 Git 작업 파일·프로세스 인자·출력
로그·Actions artifact로 저장하거나 복사하지 않습니다. `status`는
비밀값이 아닌 등록 여부만 보여줍니다. 사용 중인 Datadog site가
`datadoghq.com`이 아니라면 실행 시 site를 지정해야 합니다.

웹 UI로 직접 등록할 수도 있습니다:
[저장소 Settings > Secrets and variables > Actions](https://github.com/koreatest12/codex/settings/secrets/actions)
에서 `New repository secret`을 선택해 두 값을 각각 저장하세요.

> 인증키 파일을 공개 Git 저장소나 PR에 커밋하거나 Actions artifact로
> 내보내지 마세요. GitHub Secrets 원문을 역으로 조회/다운로드하는 기능은
> 제공하지 않습니다.

## 3. Datadog 검사 실행

[GitHub Actions → Run Datadog Synthetic tests](https://github.com/koreatest12/codex/actions/workflows/datadog-synthetics.yml)
에서 **Run workflow**를 누르고, `test_search_query`와 `datadog_site`
입력값을 확인하세요.

또는 로컬에서:

```bash
bash scripts/datadog-synthetics.sh run 'tag:e2e-tests' 'datadoghq.com'
gh run list --repo koreatest12/codex --workflow datadog-synthetics.yml
```

Synthetic 테스트는 해당 조직에 미리 구성되어 있어야 하며,
`tag:e2e-tests`로 조회되는 테스트가 없으면 의도적으로 실패합니다.
사용자 계정/권한/테스트 수에 따라 Datadog 요금이 발생할 수 있습니다.

## 4. 결과 파일 다운로드

실행 상세 화면의 **Artifacts**에서 `datadog-synthetics-summary`를 다운로드합니다.
또는 실제 워크플로 실행 ID를 지정합니다:

```bash
bash scripts/datadog-synthetics.sh download 123456789
# 지정 폴더 사용
bash scripts/datadog-synthetics.sh download 123456789 ./local-datadog-results
```

다운로드되는 `datadog-summary.json`에는 **비밀정보를 제외한 수치 요약만**
있습니다. API/Application 인증키는 다운로드하지 않습니다. 테스트 시작 전
자격 증명 검증에 실패한 경우에는 생성할 결과가 없어 artifact가 없습니다.

## 문제 해결

- `Missing API or APP keys`: `install` 또는 GitHub UI에서 두 Actions
  Secrets를 등록하세요. PR에서 외부 포크로부터 Secrets는 전달되지 않습니다.
- `401` / `403`: Datadog 계정의 키 활성화 상태, 권한, site 선택을 검토하세요.
- `0 tests`: 테스트가 등록되어 있는지, 쿼리 `tag:e2e-tests`가 맞는지 확인하세요.
- `Artifact not found`: 워크플로 실행 ID, 테스트 실행 단계, 7일 만료 여부 확인.
- 예전 실행 로그의 Node.js 20 / Ubuntu 레이블 경고는 이전 워크플로
  실행 기록이며 변경 후에도 과거 로그에서는 그대로 보입니다.

공식 문서:
- [Datadog Synthetics GitHub Action](https://github.com/DataDog/synthetics-ci-github-action)
- [GitHub CLI Secrets](https://cli.github.com/manual/gh_secret_set)
- [GitHub CLI 아티팩트 다운로드](https://cli.github.com/manual/gh_run_download)
