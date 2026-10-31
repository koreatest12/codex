# Windows Server용 WAS 설치 및 GitHub 관리

현재 저장소의 WAS는 **Linux 이미지**입니다: Nginx → Gunicorn → Flask,
FIDO2/WebAuthn, SQLite 암호화 데이터 볼륨. Docker Desktop은 Windows Server
2019·2022·2025에서 공식 지원되는 설치 방식이 아닙니다. Windows Server의
Windows 컨테이너 엔진에서는 이 Linux 이미지를 그대로 실행할 수 없습니다.

**권장 배치:** Windows Server 호스트 → Hyper-V Ubuntu Server 가상 머신 →
게스트 내부 Docker Engine/Compose → 기존 WAS. Windows 호스트에서는 검증된
SSH로 Ubuntu 게스트 관리 명령만 실행합니다. Docker TCP 소켓을 공개하지
않으며 GitHub Actions를 영구 WAS 서버처럼 사용하지 않습니다.

GitHub 코드와 실제 Windows Server 설치는 별개입니다. 이 저장소의 PowerShell
스크립트를 실제 Windows Server에서 실행할 **관리자 권한과 물리/원격 접근**이
필요합니다. 호스트에 무단 방화벽/DNS/포트/VM 설정 변경은 하지 않습니다.

## 2026-10 업그레이드·문제은행 운영 확장

- **Windows OS 업데이트는 자동 수행하지 않습니다.** 실서버 버전과 Hyper-V/클러스터, 백업/복원 검증을 위한 [Windows Server 업그레이드 준비 가이드](WINDOWS_SERVER_UPGRADE_READINESS.md)를 먼저 확인하세요.
- 읽기 전용 진단: `scripts/windows-server/Get-WasUpgradeReadiness.ps1 -AsJson`. OS 설치·VM 변경·재부팅을 하지 않습니다.
- Linux WAS의 `Upgrade` 명령은 **Ubuntu 게스트의 WAS 앱 업데이트**이며 Windows Server 자체의 OS 업데이트가 아닙니다.
- 문제은행 신규 데이터: [120문항 초안·가져오기 가이드](study/2027_BULK_QUESTION_IMPORT.md). GitHub에 파일 추가만으로 실제 운영 DB에 자동 반영되지는 않습니다.

## 1. Windows Server 호스트 사전 점검

관리자 PowerShell에서 다음을 실행합니다 (저장소를 먼저 clone).

```powershell
git clone https://github.com/koreatest12/codex.git
Set-Location .\codex
.\scripts\windows-server\Test-WasHost.ps1
```

Hyper-V 기능이 비활성화되어 있다면 **관리자 승인과 재부팅 계획**을 세운 뒤:

```powershell
Install-WindowsFeature -Name Hyper-V -IncludeManagementTools -Restart
```

이는 서버 역할 설치 및 재시작을 유발할 수 있으므로 운영 중인 다른 워크로드를
확인한 다음 실행해야 합니다. Windows Server 2019·2022·2025에서 Hyper-V를
사용할 수 있지만 물리 서버/중첩 가상화 하드웨어 기능이 필요합니다.
Windows Server 2022·2025는 WSL 2도 지원하나, 이 프로젝트에서는
장기 운영·분리 관리가 쉬운 Hyper-V Ubuntu VM 방식을 기본으로 사용합니다.

## 2. Ubuntu Server VM 준비

공식 Ubuntu Server 24.04 LTS ISO를 신뢰할 수 있는 사이트에서 다운로드하고
공식 SHA-256 해시를 대조하세요. Windows Hyper-V 관리자에서 네트워크 정책에
맞는 가상 스위치를 **관리자가 직접** 선택해 준비합니다. 외부 스위치를
사용하더라도 SSH는 신뢰된 관리망만 허용하고 인터넷에 바로 노출하지 마세요.

먼저 가상 머신 구성 변경을 미리 확인할 수 있습니다.

```powershell
.\scripts\windows-server\New-WasUbuntuVm.ps1 `
  -VMName "CodexWAS" `
  -IsoPath "D:\ISO\ubuntu-24.04-live-server-amd64.iso" `
  -SwitchName "TrustedManagementSwitch" `
  -VmRoot "D:\HyperV" `
  -MemoryGB 4 -CpuCount 2 -DiskGB 60 -WhatIf
```

경로·스위치 이름은 **예시**입니다. 실제 확인된 경로로 바꿔서
`-WhatIf`를 제거하면 새 Generation 2 VM과 가상 디스크를 만듭니다.
실제 설치 ISO가 존재하고 `VmRoot` 디렉터리가 이미 있어야 합니다.
기존 VM 이름/디스크는 절대 덮어쓰지 않습니다. `-StartVM`은 선택 옵션이며
Ubuntu 설치 과정(계정/디스크/SSH 설정)은 Hyper-V 콘솔에서 완료해야 합니다.

Windows 서버에 Docker Desktop을 설치하거나 Windows 컨테이너 모드에서
`ubuntu:latest` 이미지를 실행하지 마세요.

## 3. Ubuntu 게스트에서 SSH·서버 준비

Ubuntu 설치와 게스트 IP 확인 후, Hyper-V 콘솔에서 다음을 준비합니다.

```bash
sudo apt-get update
sudo apt-get install -y git python3 openssh-server
sudo systemctl enable --now ssh
```

Windows 호스트의 사용자 프로필에서 별도 SSH 키 쌍을 생성할 수 있습니다.

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\codex-was" -C "codex-was-admin"
```

생성된 **공개키만** Ubuntu 계정의 `~/.ssh/authorized_keys`에 등록하고,
키 파일은 안전하게 보관합니다. 개인키, 비밀번호, 부트스트랩 토큰을
GitHub, PR, Actions Secrets 덤프, 로그 또는 이 대화에 올리지 마세요.

Ubuntu의 실제 SSH 호스트키 지문을 **VM 콘솔 등 독립적인 경로**로
검증한 후 Windows 호스트에서 최초 SSH 연결을 수락하세요.
이후 관리 스크립트는 `StrictHostKeyChecking=yes`와
공개키 로그인을 요구하며 미검증 호스트키를 자동 수락하지 않습니다.

## 4. Windows PowerShell에서 Ubuntu WAS 구축·관리

다음 예시는 Ubuntu 관리 계정이 `ubuntu`, VM의 사설 IP 주소가
`192.0.2.10`, SSH 키가 `~\.ssh\codex-was`라고 가정한
**치환용 예시**입니다. `192.0.2.10`은 문서용 주소이며 실제 서버가 아닙니다.

```powershell
$was = ".\scripts\windows-server\Invoke-WasUbuntuGuest.ps1"
$vmIp = "192.0.2.10"       # 실제 Ubuntu VM의 주소로 변경
$key = "$env:USERPROFILE\.ssh\codex-was"

# Ubuntu VM으로 GitHub 저장소 복제 (기존 ~/codex 있으면 거부)
& $was -Action Clone -LinuxHost $vmIp -LinuxUser ubuntu -IdentityFile $key

# Ubuntu VM 내부에 Linux Docker Engine 설치
& $was -Action InstallDocker -LinuxHost $vmIp -LinuxUser ubuntu -IdentityFile $key

# 신규 설치에 한 번만: 암호화 키/로컬 WebAuthn 설정 생성
& $was -Action InitLocal -LinuxHost $vmIp -LinuxUser ubuntu -IdentityFile $key

# 점검, 배포, 헬스 확인
& $was -Action Doctor -LinuxHost $vmIp -LinuxUser ubuntu -IdentityFile $key
& $was -Action Deploy -LinuxHost $vmIp -LinuxUser ubuntu -IdentityFile $key
& $was -Action Health -LinuxHost $vmIp -LinuxUser ubuntu -IdentityFile $key

# Windows 호스트 브라우저로 localhost:8080 접속할 때만 사용
& $was -Action Tunnel -LinuxHost $vmIp -LinuxUser ubuntu -IdentityFile $key
```

`Tunnel`은 Windows 호스트의 `127.0.0.1:8080`을 Ubuntu 게스트의
`127.0.0.1:8080`으로 포워딩합니다. 이것은 공개 서비스나 영구 자동
접속 구성이 아니며, 터널 프로세스가 종료되면 접속도 종료됩니다.
터널을 연 **해당 Windows 머신의 브라우저**에서
`http://localhost:8080`에 접속해 WebAuthn 보안키를 등록하세요.

`InitLocal`은 최초 설치 한 번만 실행하세요. 기존 시스템의
`.env`, `secrets/`, Docker 영구 볼륨은 덮어쓰지 마세요.
도메인/외부 사용자가 필요한 경우 최초 생성부터 별도 HTTPS 도메인,
RP ID, TLS 프록시 및 인증서가 필요합니다. 터널과 localhost 설정만으로
다른 컴퓨터에서 안전하게 접속하도록 구성되지는 않습니다.

같은 호출에서 `-Action`을 `Start`, `Stop`, `Restart`, `Status`,
`Health`, `Backup`, `Upgrade`로 바꿔 관리합니다. (`Logs`는 현재 Windows SSH 스크립트 허용 목록에 없습니다.)
`Backup`은 **Ubuntu VM 내부**의 `~/codex/backups/`에 저장되며
GitHub에 업로드하지 않습니다. 저장 데이터와 별도로 암호화 키도
안전하게 백업해야 합니다. `Upgrade`는 Ubuntu 게스트에 현재
체크아웃된 소스 버전을 기준으로 백업 후 빌드합니다. GitHub 최신
커밋으로 코드를 가져오는 별도 승인과 검토 절차는 관리자가 수행합니다.

Ubuntu VM의 Docker 데몬 권한은 관리자급 권한입니다. 원격 Docker API를
열지 않았고, SSH를 통한 허용 명령만 실행합니다. Windows Server 측
RDP/SSH, 파일 백업, 방화벽은 기존 운영 정책을 따라야 합니다.

## 5. GitHub Actions의 Windows 검증

`.github/workflows/windows-server-was.yml`은 Windows 호스팅 실행기에서
PowerShell 파일의 **구문**, 기본 호스트 사전 점검, 악성 호스트명 거부를
확인합니다. 다른 Linux CI는 Flask WebAuthn과 Docker 이미지를 검사합니다.
GitHub 실행기는 일회성이므로 Windows Server에 VM을 지속 생성하거나
사용자의 운영 서버에 비밀키를 설치하지 않습니다.

참고:
- Docker Desktop의 Windows Server 미지원: https://docs.docker.com/desktop/setup/install/windows-install/
- Windows Server WSL 2 설치: https://learn.microsoft.com/en-us/windows/wsl/install-on-server
- Hyper-V Linux VM 지원: https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/Supported-Linux-and-FreeBSD-virtual-machines-for-Hyper-V-on-Windows
- Ubuntu VM 지원 기능: https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/Supported-Ubuntu-virtual-machines-on-Hyper-V
- 기존 WAS 설치: [WAS_MANAGEMENT.md](WAS_MANAGEMENT.md)
