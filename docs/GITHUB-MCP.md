# GitHub MCP 서버 연결 (VS Code)

이 저장소의 `.vscode/mcp.json`은 GitHub가 운영하는 **공식 원격 GitHub MCP 서버**를 VS Code 작업 공간에 등록하는 설정입니다.
서버 주소는 `https://api.githubcopilot.com/mcp/`입니다. 별도 Docker 컨테이너 또는 토큰을 저장소에 배포하지 않습니다.

## 처음 연결할 때

1. GitHub 계정으로 로그인 가능한 최신 VS Code에서 이 저장소 폴더를 엽니다.
2. **MCP: List Servers** 명령을 실행하고 `github` 서버를 선택합니다.
3. 서버를 시작하고 **Auth / Sign in** 안내에 따라 GitHub OAuth 인증을 완료합니다. 필요한 권한만 승인합니다.
4. Copilot Chat의 Agent 모드에서 도구 목록을 열어 GitHub 서버 도구가 표시되는지 확인합니다.
5. 도구를 읽기 전용으로 먼저 시험합니다. 예: `koreatest12/codex` 저장소의 공개 README 조회.

서버 설정이 커밋되었다고 사용자 인증이 완료되거나 MCP 서비스가 GitHub Actions에서 실행되는 것은 아닙니다.
VS Code에서 실행·인증해야 실제 도구를 사용할 수 있습니다. 다른 MCP 클라이언트(예: Codex CLI)는 해당 클라이언트의 별도 MCP 설정과 인증 절차를 따릅니다.
ChatGPT의 GitHub 연결 역시 로컬 VS Code MCP 인증과는 별개입니다.

## 보안

- GitHub PAT, OAuth 액세스 토큰, 개인 인증키를 `.vscode/mcp.json`, 커밋, PR 또는 Actions 로그에 넣지 마세요.
- 권한이 있는 저장소에 대해서만 도구를 사용하고, 쓰기/병합/배포는 각 작업의 승인 절차를 유지하세요.
- 작업 공간을 열 때 MCP 서버 실행/신뢰에 관한 VS Code 안내를 확인하세요.

공식 참고 문서:
- [GitHub MCP Server](https://github.com/github/github-mcp-server)
- [GitHub Docs: MCP와 Copilot Chat](https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp-in-your-ide/extend-copilot-chat-with-mcp?tool=vscode)
- [VS Code MCP 설정](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)
