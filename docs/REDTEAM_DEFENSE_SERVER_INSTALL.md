# RedTeamDefense: Windows Server 설치 및 보안 로깅

이 절차는 **기존 Windows Server에 읽기 전용 보안 점검 도구**를 설치합니다. Windows Server 운영체제, IIS/WAS, Hyper-V, Ubuntu VM 및 웹 서버를 설치하지 않습니다. GitHub Actions는 일회용 검증 환경이며 사용자의 실제 서버가 아닙니다.

- [점검 엔진](../scripts/windows-server/RedTeamDefense-Audit.ps1)
- [설치/상태 확인/제거](../scripts/windows-server/Install-RedTeamDefense.ps1)
- [추가 보안 로깅](../scripts/windows-server/Set-RedTeamDefenseSecurityLogging.ps1)

## 1. 설치 전 준비

1. 승인된 Windows Server(예: 2019/2022/2025)에서 Windows PowerShell 5.1을 관리자 권한으로 엽니다.
2. 백업, 관리 콘솔 접속 경로, 조직 GPO/MDM/EDR 정책을 확인합니다.
3. 검토된 코드를 서버에서 내려받습니다. 인터넷 차단 서버는 검토된 파일을 오프라인으로 전달합니다.
4. 새 PR의 작업 브랜치에만 코드가 존재한다면 main 병합 전에 해당 브랜치를 명시적으로 checkout합니다.

```powershell
git clone https://github.com/koreatest12/codex.git
cd .\codex
```

기존에 clone한 폴더에서는 새로 복제하지 않고 변경사항을 검토한 다음 필요할 때만 `git pull`을 사용하세요.

## 2. 사전 확인 및 설치

**기본 모드는 읽기 전용**입니다. 아래 명령은 실제 설치/설정 변경을 하지 않습니다.

```powershell
.\scripts\windows-server\Install-RedTeamDefense.ps1 -Mode Status
.\scripts\windows-server\Install-RedTeamDefense.ps1 -Mode Install
```

승인된 서버에 설치할 때만 관리자 PowerShell에서 `-Apply`를 명시합니다. 확인 프롬프트가 표시됩니다.

```powershell
.\scripts\windows-server\Install-RedTeamDefense.ps1 -Mode Install -Apply -DailyAt '03:00'
```

설치 내용:

- `%ProgramFiles%\RedTeamDefense\RedTeamDefense-Audit.ps1` — 로컬 점검 프로그램, 관리자/SYSTEM 쓰기 권한
- `%ProgramData%\RedTeamDefense\Reports` — 로컬 HTML·JSON·CSV 보고서
- `%ProgramData%\RedTeamDefense\Backups` — 선택적 보안 정책 변경의 백업
- `\RedTeamDefense\DailyAudit` — 매일 서버 로컬 시간 03:00에 실행되는 예약 작업

작업은 로컬 **SYSTEM** 계정으로 실행하며 **외부 전송, 방화벽 변경, 원격 연결, 서비스 포트 개방, GPO 완화는 하지 않습니다.** 설치된 폴더와 보고서/백업 폴더에는 Administrators·SYSTEM만 접근할 수 있도록 제한합니다.

기존 설치나 데이터 폴더가 이미 존재하면 자동 덮어쓰기/ACL 변경을 거부합니다. 설치가 중단되면 남아 있는 작업/폴더를 관리자가 확인한 뒤 복구하십시오. 스크립트 서명이 필요한 운영 정책이라면 서명된 버전을 사용하고 실행 정책을 우회하지 마세요.

설치 상태 확인:

```powershell
.\scripts\windows-server\Install-RedTeamDefense.ps1 -Mode Status
Get-ScheduledTask -TaskPath '\RedTeamDefense\' -TaskName 'DailyAudit'
Get-ScheduledTaskInfo -TaskPath '\RedTeamDefense\' -TaskName 'DailyAudit'
```

첫 보고서는 예약 시간이 지난 뒤 생성됩니다. 관리자의 승인 아래 수동 시작할 수 있습니다.

```powershell
Start-ScheduledTask -TaskPath '\RedTeamDefense\' -TaskName 'DailyAudit'
```

보고서에는 로그인 실패 IP, 서비스 이름 등이 들어갈 수 있습니다. 보고서나 실제 감사 로그를 GitHub, Pull Request, Actions 아티팩트에 업로드하지 마세요. 별도 보존·백업 정책을 수립하세요.

## 3. 선택적 보안 로깅 적용

설치 자체는 방화벽 프로필, RDP, WinRM, Defender, SMB 및 네트워크 구성을 변경하지 않습니다. 원격 관리가 끊기거나 타사 EDR과 충돌하지 않도록 이 설정들은 관리자가 별도로 검토합니다.

로그 설정 도구는 다음 두 옵션만 **명시적 승인 후** 적용합니다.

- `-EnableFailedLogonAudit`: 감사 하위 범주 Logon의 실패(Failure) 감사만 활성화하고 기존 성공(Success) 감사 설정은 유지합니다. 이벤트 4625 탐지에 도움이 될 수 있지만 도메인 GPO/MDM에 의해 덮어써질 수 있습니다.
- `-EnableScriptBlockLogging`: PowerShell의 `EnableScriptBlockLogging=1` 정책을 설정합니다. 이벤트 4104 수집에 유용하지만 스크립트의 **비밀번호·토큰·개인정보도 로그에 남을 수 있으므로** 저장소 권한, 보존, 조직 정책을 먼저 확인하세요.

먼저 상태/계획만 확인합니다.

```powershell
.\scripts\windows-server\Set-RedTeamDefenseSecurityLogging.ps1 -Mode Status
.\scripts\windows-server\Set-RedTeamDefenseSecurityLogging.ps1 -Mode Enable -EnableFailedLogonAudit
.\scripts\windows-server\Set-RedTeamDefenseSecurityLogging.ps1 -Mode Enable -EnableScriptBlockLogging
```

선택 기능 적용 예시(확인 프롬프트 표시):

```powershell
.\scripts\windows-server\Set-RedTeamDefenseSecurityLogging.ps1 -Mode Enable -EnableFailedLogonAudit -Apply
# 둘 다 활성화할 때에만 다음과 같이 실행
.\scripts\windows-server\Set-RedTeamDefenseSecurityLogging.ps1 -Mode Enable -EnableFailedLogonAudit -EnableScriptBlockLogging -Apply
```

정책 변경 **전에** `%ProgramData%\RedTeamDefense\Backups\SecurityLogging-*` 폴더에 다음을 백업합니다.

- `audit-policy-before.csv` — **전체** 감사 정책(시스템·사용자별 정책 포함)
- `script-block-policy-before.json` — 레지스트리 값의 이전 존재 여부/값

실제 정책은 도메인 GPO/MDM 우선순위에 영향을 받으므로 적용 후 `-Mode Status`로 재확인하십시오. 재부팅, 방화벽 규칙 생성, RDP 차단은 수행하지 않습니다.

## 4. 제거 및 원상복구

점검 프로그램 예약 작업과 설치된 사본을 제거할 수 있습니다. **보고서와 정책 백업은 보존**합니다.

```powershell
.\scripts\windows-server\Install-RedTeamDefense.ps1 -Mode Uninstall
.\scripts\windows-server\Install-RedTeamDefense.ps1 -Mode Uninstall -Apply
```

설치 제거는 별도로 적용한 **로그 감사 정책을 원복하지 않습니다.** 사전 백업을 기준으로 변경 관리 절차에 따라 복원합니다.

- PowerShell 로깅: `script-block-policy-before.json`의 `ValueExisted`가 true면 `OldValue`로 되돌리고, false면 이번에 추가한 `EnableScriptBlockLogging` 값만 제거합니다. 도메인 GPO는 변경하지 마세요.
- 로그온 감사: `audit-policy-before.csv`의 내용을 확인합니다. `auditpol /restore` 명령은 **로그온뿐 아니라 전체 감사 정책**을 일괄 복원해 그 이후의 다른 변경까지 덮어쓸 수 있습니다. 반드시 별도 보안 변경 승인 후에만 사용합니다.

```powershell
# 중요: 전체 감사 정책을 덮어쓰므로 검토·승인 전에는 실행하지 마세요.
# auditpol.exe /restore /file:"C:\ProgramData\RedTeamDefense\Backups\SecurityLogging-...\audit-policy-before.csv"
```

## 5. CI 검증과 실제 서버 설치의 구분

[Windows GitHub Actions](../.github/workflows/windows-server-was.yml)에서 스크립트 문법과 **미적용 계획 모드**를 검사합니다. GitHub 러너에 실제 설치, 권한 변경 또는 감사 정책 수정을 수행하지 않습니다. 진짜 운영 서버에서의 설치·실행 성공은 위 상태 확인, 작업 스케줄러 실행 기록, 로컬 보고서로 별도 검증해야 합니다.

Microsoft 공식 참고:
- [ScheduledTasks](https://learn.microsoft.com/powershell/module/scheduledtasks/register-scheduledtask)
- [auditpol set](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/auditpol-set)
- [auditpol backup](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/auditpol-backup)
- [auditpol restore](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/auditpol-restore)
- [PowerShell logging 및 민감정보 유의사항](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_logging)
