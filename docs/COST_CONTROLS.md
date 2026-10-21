# 비용 발생 방지 기본값

GitHub Actions의 모든 현재 작업은 저장소 변수 `ENABLE_BILLABLE_CI`가
정확히 `true`일 때만 실행됩니다. 미설정·빈 값·그 외 값은 runner 실행을
차단합니다. 보안 의존성 검토도 포함하므로 CI를 끈 동안에는 로컬에서
테스트와 의존성 감사를 실행해야 합니다.

주간 컨테이너 빌드는 제거했습니다. CI를 허용해도 GHCR 게시는 main에서
수동 실행하면서 `publish_image`를 선택한 경우에만 진행합니다.
Actions 캐시 업로드는 제거했으며 중복 실행 취소와 작업 시간 제한을 적용합니다.
이미 실행 중인 작업이나 기존 이미지·캐시는 이 변경으로 삭제되지 않습니다.

Career Note의 30초 자동 상태 점검은 기본적으로 꺼집니다. 사용자가 켜면
반복 호출이 다시 발생합니다. 미인증 상태 점검은 D1/R2에 접근하기 전에
401로 거부합니다. 모든 API의 D1/R2 접근은 `ENABLE_METERED_STORAGE`가 정확히 문자열 `true`일
때만 허용합니다. 기본값은 403 차단이며 자동 재시도하지 않습니다.
이 기본값에서는 소유자도 조회·저장·업로드·문서 생성·상태 점검을 할 수 없습니다.
운영자가 사용 비용을 허용할 때만 Workers 환경 변수로 명시적으로 켜야 합니다.
기존 자료는 삭제하지 않습니다.

이 설정은 비용 발생 경로를 줄이는 코드 정책이며 계정의 과금 상한이 아닙니다.
Cloudflare Workers 요청 자체, D1/R2 사용·기존 저장량, GitHub의 기존
스토리지, Codex 이용료는 별도 과금 대상일 수 있습니다. 비용을 엄격히
차단하려면 각 서비스에서 실제 사용 중인 요금제와 하드 지출 제한을 확인하고,
하드 제한을 지원하지 않는 유료 서비스를 중지해야 합니다. 예산 알림만으로는
자동 결제가 차단되지 않습니다. 이 작업은 계정 요금제·운영 배포를 변경하지 않습니다.

로컬 검증:

```bash
cd career-note
pnpm test:security
node --test tests/health-cost-guard.test.mjs
```

## 로컬 배포 검증 (2026-10-17)

다음 명령으로 프로덕션 산출물을 로컬 Workers에 실행했습니다.
실제 Cloudflare 배포나 원격 D1/R2 접근은 수행하지 않습니다.

```bash
cd /workspace/codex/career-note
pnpm build
mkdir -p .sites-runtime/xdg-config
XDG_CONFIG_HOME="$PWD/.sites-runtime/xdg-config" pnpm start
```

`XDG_CONFIG_HOME`은 이 클라우드 환경에서 읽기 전용인 사용자 설정 경로 대신
무시된 로컬 경로를 Wrangler가 사용하도록 합니다.

검증 결과: 화면 GET은 200, `/api/health` GET, `/api/records` GET/POST/DELETE,
`/api/files` GET/POST, `/api/generate` POST는 모두 비용 보호 응답 403입니다.
비용 차단 테스트 3개, 의존성 보안 테스트 6개, TypeScript 검사가 통과했습니다.
현재 빌드 산출물에는 저장소 과금 허용 변수가 설정되어 있지 않습니다.
GitHub 계정 변수와 실제 배포의 Workers 변수는 확인하지 못했으므로
원격 환경에서 같은 차단이 적용되었다는 근거는 아닙니다.
