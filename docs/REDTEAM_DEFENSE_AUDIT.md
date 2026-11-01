# RedTeamDefense-Audit (Windows)

저장소: `koreatest12/codex`  
소스 코드: [`scripts/windows-server/RedTeamDefense-Audit.ps1`](../scripts/windows-server/RedTeamDefense-Audit.ps1)

로컬 Windows PC/서버의 레드팀 공격 대비 상태를 점검하는 **읽기 전용** PowerShell 도구입니다.

Windows Server에 **예약 작업으로 설치**하거나 **선택적 감사 로깅 정책**을 적용하려면 [서버 설치 및 보안 설정 가이드](REDTEAM_DEFENSE_SERVER_INSTALL.md)를 참고하세요. 기존 단발 점검 기능은 그대로 유지됩니다.

## 지원 및 범위
- Windows 10/11 및 Windows Server의 해당 PowerShell 모듈을 지원하는 환경에서 사용
- Windows PowerShell 5.1 또는 호환 PowerShell 7 (운영체제/모듈에 따라 일부 점검은 `UNKNOWN`)
- Windows 방화벽 활성화, Microsoft Defender 실시간 보호, RDP 및 NLA, SMBv1 서버 프로토콜, PowerShell 스크립트 블록 로깅 정책, 로컬 TCP 대기 포트(22, 445, 3389, 5985, 5986), 최근 Security 4625 및 System 7045 이벤트 점검
- 관리자로 실행하면 Security 이벤트 로그 읽기 성공 가능성이 높아집니다. 관리자 권한 없이도 일부 항목을 점검할 수 있습니다.

## 실행

1. GitHub 저장소를 내려받거나 업데이트합니다: `git clone https://github.com/koreatest12/codex.git` (기존 복제본은 `git pull`을 사용).
2. 저장소 루트 디렉터리에서 **Windows PowerShell**을 열고 아래 명령을 입력합니다. 실행 정책을 시스템 전체에서 변경할 필요가 없습니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows-server\RedTeamDefense-Audit.ps1" -LookbackHours 24 -FailedLogonThreshold 5
```

- 보안 이벤트 로그 조회가 필요하면 **관리자 권한으로 실행한 Windows PowerShell**에서 위 명령을 사용합니다.
- PowerShell의 현재 경로는 저장소 루트(`codex`)여야 합니다. 다른 위치에서 실행한다면 `-File`에 스크립트의 전체 경로를 지정하세요.
- 실행 전 스크립트 내용을 확인하세요. 사용자 본인 또는 허가받은 Windows 시스템에만 사용하세요.
- `-ExecutionPolicy Bypass`는 위 명령으로 시작한 PowerShell 프로세스에만 적용됩니다. 조직 정책에 따라 차단될 수 있습니다.

## GitHub와 실제 Windows 실행의 구분

GitHub에는 점검 프로그램 **소스 코드만 저장**합니다. 저장소에 파일을 추가하거나 PR을 병합해도 실제 Windows PC·서버에서 자동 실행되지는 않습니다. 실행 결과(로그인 실패 기록, IP 주소, 서비스 이름)가 담긴 HTML/JSON/CSV 보고서는 개인정보나 운영 정보가 될 수 있으므로 **Git에 커밋하지 마세요**.

## 산출물
`%USERPROFILE%\RedTeamDefense-Reports` 폴더에 타임스탬프가 포함된 보고서 3개가 생성됩니다.
- HTML: 사람이 읽기 쉬운 점검 보고서
- JSON: 자동화·추가 분석용
- CSV: 엑셀 등에서 필터링하기 편한 표

보고서에는 IP 주소와 서비스 이름이 들어갈 수 있으므로 외부 공유에 주의하세요. 이 도구는 네트워크를 외부로 호출하지 않습니다.

## 판정 해석
- **PASS**: 확인한 설정 또는 상태가 기준에 부합
- **WARN**: 우선 확인할 위험 신호. 실제 침해를 뜻하지 않음
- **REVIEW**: 조직의 정책·업무 용도에 따라 판단해야 함
- **UNKNOWN**: 접근 권한 부족 또는 조회 실패 등으로 판단 불가

## 한계
- 침입 방지 솔루션(EDR/IPS), 전체 취약점 스캐너, 실시간 24시간 감시, 공격 차단 기능이 아닙니다.
- TCP 수신 대기 상태가 외부 인터넷으로 노출된다는 뜻은 아닙니다.
- 이벤트 로그 기록이 활성화되어 있지 않거나 로그가 보관되지 않았으면 침해 흔적을 놓칠 수 있습니다.
- Microsoft Defender가 비활성화되어 있어도 승인된 타사 보안 제품이 보호 중일 수 있습니다.
- RDP 사용 자체가 곧 취약점은 아닙니다.
- 서비스 설치 및 로그인 실패에는 정상 관리 작업도 포함됩니다.

## 참고 자료 (Microsoft Learn)
- https://learn.microsoft.com/powershell/module/netsecurity/get-netfirewallprofile
- https://learn.microsoft.com/powershell/module/defender/get-mpcomputerstatus
- https://learn.microsoft.com/powershell/module/smbshare/get-smbserverconfiguration
- https://learn.microsoft.com/powershell/module/nettcpip/get-nettcpconnection
- https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/plan/Appendix-L--Events-to-Monitor