# ChatGPT 중심 GitAIOps 시작 안내

## 현재 구성 범위
이 문서는 koreatest12/codex 저장소에서 ChatGPT/Codex로 변경을 분석하고
검증한 뒤 PR로 검토하는 운영 절차를 정의한다.
문서와 AGENTS.md를 추가하는 것만으로 Codex 연결, 자동 리뷰, 상시 감시,
운영 배포 또는 자동 복구가 활성화되지는 않는다.

## 저장소에서 확인한 기반
- Python 서버와 테스트, Java Maven 도구, career-note 웹앱이 함께 있다.
- CI(blank.yml)는 기본 Python 단위 테스트와 셸 문법 검사를 실행한다.
- Latest Linux Image and Container Server는 Python·Java·컨테이너 검증을 수행한다.
- Docker Image CI는 컨테이너를 검증하며 main의 push 또는 수동 실행에서
  GHCR에 이미지를 게시할 수 있다. 이미지 게시와 실제 서버 배포는 구분한다.
- Dependency Review와 Dependabot 설정이 있다.
- career-note는 기존 Python/Docker 검증만으로 검증되었다고 판단하지 않는다.

## 계정에서 완료할 연결
1. ChatGPT/Codex의 클라우드 환경에서 GitHub 저장소 koreatest12/codex를 선택한다.
2. 환경 준비 결과에서 필요한 도구와 의존성, 테스트 결과를 확인한다.
3. Code review 설정에서 이 저장소의 Automatic review를 활성화한다.
   개인 설정의 리뷰 트리거도 확인한다.
4. 테스트 PR에서 리뷰가 실제 게시되는지 확인한다.
   수동 요청은 PR 댓글에 `@codex review`를 입력한다.

GitHub 플러그인에서 저장소를 읽을 수 있다는 사실은 Codex 클라우드 환경이나
자동 리뷰까지 활성화되었다는 증거가 아니다.
이 설정 파일들은 OpenAI API를 호출하지 않으며 API 키를 요구하지 않는다.
서비스 사용 한도와 GitHub Actions 사용량은 각 계정에서 별도로 확인한다.

공식 문서:
- https://learn.chatgpt.com/docs/cloud
- https://learn.chatgpt.com/docs/third-party/github

## 일상 작업
1. ChatGPT에 작업 대상과 기대 결과를 전달한다.
2. Codex가 AGENTS.md를 읽고 작업 브랜치에서 최소 변경을 준비한다.
3. 변경 영역의 테스트를 실행하고 초안 PR에 결과를 기록한다.
4. 해당 커밋에 대한 Actions 결과와 Codex 리뷰를 확인한다.
5. 검토 후 병합한다. main 병합은 기존 이미지 게시 워크플로를 실행할 수 있다.

## CI 실패 분석
ChatGPT에 실패한 GitHub Actions 실행 URL을 전달한다.
분석 시 저장소, 브랜치, 커밋 SHA, 실행 시도, 실패 작업과 단계를 확인한다.
마스킹한 오류를 근거로 코드 오류·환경 문제·의존성 문제·일시적 장애를 구분한다.
필요한 수정만 새 브랜치에 적용하고 동일 조건에서 검증해 PR을 만든다.
원인이 확인되지 않은 상태에서 반복 재실행하거나 운영 서버를 재시작하지 않는다.
공개 PR에는 실제 개인정보나 비밀값이 포함된 로그를 붙이지 않는다.

## 운영 감시·배포 확장에 필요한 정보
- 배포 대상: 개인 PC, 서버 또는 클라우드와 접근 방식
- 운영할 구성 요소: Python 서버, career-note 또는 둘 다
- 상태 확인 주소와 수집할 로그, 보관·마스킹 정책
- 배포 승인 방식, 데이터 백업과 이전 버전 복구 절차

현재는 운영 대상과 접근 정보가 확정되지 않았다.
상시 감시, 서버 변경, 자동 복구는 이 정보를 확인한 다음 별도 구성한다.

## 완료 확인
- [ ] 이 PR의 문서와 작업 규칙을 검토하고 병합했다.
- [ ] Codex 클라우드 환경에 저장소를 연결하고 테스트했다.
- [ ] 테스트 PR에서 Codex 리뷰가 실제로 게시되었다.
- [ ] 변경 영역의 실제 테스트를 실행했다.
- [ ] 운영 대상과 배포·복구 절차를 확인했다.

## GitHub Actions Skipped 수정 — 2026-10-22

워크플로 4개(CI, Dependency Review, Docker Image CI, Latest Linux
Image and Container Server)의 job 단계에 공통으로 있던
`if: ${{ vars.ENABLE_BILLABLE_CI == 'true' }}` 조건 때문에,
저장소 변수가 설정되지 않았을 때 실행이 `Skipped` 처리되었다.
공개 저장소에서 표준 `ubuntu-24.04` GitHub-hosted runner는
무료로 제공되므로 해당 작업 실행 차단 조건을 제거했다.

- 이제 `main` push 및 PR은 관련 워크플로를 실행한다.
  경로 필터가 있는 워크플로는 변경 대상 경로가 포함되어야 자동 실행된다.
- CI는 기존의 "Hello world" 예제가 아닌 Python 테스트와 각 셸 스크립트
  문법 검사로 바뀌었다. Python 테스트 성공은 Java/Node 테스트나
  전체 배포 검증 성공을 의미하지 않는다.
- Docker 이미지 GHCR **게시** 단계는 기존과 동일하게 `main`에서
  수동 `workflow_dispatch` 실행과 `publish_image=true` 승인 조건을 유지한다.
- 저장소가 비공개로 전환되거나 대형 러너를 사용하게 되면 Actions
  요금이 발생할 수 있다. 패키지/아티팩트 저장 공간 정책도 별도 확인한다.
- `Skipped`가 사라진 뒤 `failure`가 나오면 새로 노출된 실제 테스트 실패로
  구분하고 해당 단계 로그에 따라 별도로 수정한다.

관련 GitHub 문서: https://docs.github.com/en/billing/concepts/product-billing/github-actions
