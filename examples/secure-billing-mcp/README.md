# MCP 보안·예산 가드 테스트 예제

사용자가 제공한 코드를 별도의 로컬 실험으로 보관합니다. 기존 Flask 서버와
Career Note에 연결하지 않으며, GitHub Actions나 운영 배포를 추가하지 않습니다.
`call_paid_external_api`는 문자열을 생성하는 모의 도구로 실제 API 요청은 없습니다.

원본에서 경로 접두어 검사 우회, 인자·예외의 로그 노출, 잘림 안내문을 포함한
응답 길이 초과를 보완했습니다. 음수·NaN·무한대 비용도 거부하고 파일 읽기량을 제한합니다.

## 실행과 테스트

저장소 루트에서:

```bash
python3 -m venv /workspace/.venvs/secure-billing-mcp
/workspace/.venvs/secure-billing-mcp/bin/python -m pip install -r examples/secure-billing-mcp/requirements.txt
cd examples/secure-billing-mcp
PYTHONDONTWRITEBYTECODE=1 /workspace/.venvs/secure-billing-mcp/bin/python -m unittest -v
/workspace/.venvs/secure-billing-mcp/bin/python server.py
```

서버는 기본 stdio 전송을 사용합니다. 감사 로그와 `safe_workspace`는 실행한
디렉터리에 생성되며 Git에서 제외됩니다. 실제 파일을 넣기 전에는 민감정보를
반환할 수 있는 도구임을 고려하세요. 보안키 인증 서버는 아닙니다.

## 과금·보안 한계

- 기본 일일 5달러와 도구별 비용은 예시 추정치이며 실제 청구액이 아닙니다.
  파일 읽기에 실제로 0.005달러가 청구된다는 의미도 아닙니다.
- 예산·호출 기록은 프로세스 메모리에만 보관됩니다. 재시작 시 초기화되며
  동시 호출·다중 프로세스의 원자적 예산 예약을 보장하지 않습니다.
- 응답 길이는 글자 수 제한이며 토큰·실제 LLM 이용료의 상한이 아닙니다.
- 클라이언트가 재시도 거부 안내를 지킨다는 보장이 없습니다.
- 경로 검사는 심볼릭 링크 변경과 파일 열기 사이의 경쟁까지 차단하지 않습니다.
  다른 프로세스가 작업 폴더를 수정할 수 있는 운영 환경에 사용하지 마세요.
- 호스팅·Codex·클라이언트 LLM 비용은 이 서버가 차단하지 않습니다.

실제 유료 API와 연결하지 않은 로컬 테스트 전용이며, 운영 인증이나 과금 차단
시스템으로 검증된 코드가 아닙니다. GitHub 업로드와 외부 운영 배포는 별개입니다.

## 검증 결과

MCP SDK 1.30.0에서 단위 테스트 9개가 통과했습니다. 실제 stdio 클라이언트로
서버 프로세스를 시작해 초기화, 도구 3개 조회, 예산 상태 및 모의 API 호출도
성공했습니다. 테스트 중 실제 외부 유료 API 호출은 수행하지 않았습니다.
