# Windows Server 업그레이드 준비·검증 가이드 (2026-10 기준)

> **실행 범위:** 이 PR은 **Windows Server 호스트의 운영체제를 실제 업그레이드하지 않습니다.**
> 위험 평가와 읽기 전용 사전 점검, GitHub Actions 구문/기본 동작 검증을 제공하는 문서·스크립트 변경입니다.
> 소유하고 관리하는 운영 서버의 버전, 라이선스, 백업, 역할, 클러스터 유무가 아직 확인되지 않아
> OS 설치/재부팅을 자동화하지 않습니다.

## 1. 현재 WAS와 Windows 호스트의 경계

기존 구성: **Windows Server → Hyper-V → Ubuntu Server VM → Docker Engine/Compose → Flask/Gunicorn/Nginx → SQLite 문제은행**.

- `scripts/windows-server/Invoke-WasUbuntuGuest.ps1 -Action Upgrade`는 **Ubuntu 게스트에서 실행되는 WAS 애플리케이션 업그레이드**를 뜻하며 Windows Server OS 업그레이드가 아닙니다.
- GitHub Actions의 `windows-2022` 실행기는 임시 CI VM입니다. 여기서 통과해도 사용자의 물리/가상 Windows Server 운영 장비를 업데이트하거나 접근하지 않습니다.
- Ubuntu Docker 컨테이너를 Windows Server 컨테이너 런타임에 직접 배포하지 않습니다. **기존 Hyper-V Ubuntu 게스트 구조 유지**.
- VM 신규 생성, SSH 키 재발급, 기존 데이터 볼륨 삭제 등은 업그레이드의 기본 단계가 아닙니다.

## 2. Windows Server OS 지원 경로: 공식 자료 기반

마이크로소프트 [Windows Server upgrade path](https://learn.microsoft.com/en-us/windows-server/get-started/install-upgrade-migrate)에 따르면 **비클러스터** 서버는 설치 매체를 통한 다음 경로가 명시되어 있습니다.

| 현재 Windows Server | 계획할 수 있는 대상 | 조건 |
|---|---|---|
| 2019 | 2022 또는 2025 | 라이선스, 하드웨어·서버 역할 지원, 드라이버 검토 |
| 2022 | 2025 | 백업/롤백·역할 호환성·유지보수 창 확인 |
| 2025 | 2025 후속 빌드/보안 업데이트 | 설치 매체와 지원 채널·에디션 확인 |

지원 경로 목록이 **현장 장비에서 업그레이드가 무조건 가능하다**는 뜻은 아닙니다. 도메인 컨트롤러, 클러스터, OEM 드라이버, VM 이동, Windows Update 경로는 별도 제약이 있습니다. **특히 클러스터 OS 롤링 업그레이드는 한 버전씩 진행**하므로 위 비클러스터 표를 클러스터에 적용하지 않습니다.

- 공식: [Plan Your Windows Server Upgrade](https://learn.microsoft.com/en-us/windows-server/get-started/install-upgrade-migrate)
- 공식: [Perform an in-place upgrade](https://learn.microsoft.com/en-us/windows-server/get-started/upgrade-in-place)
- 공식: [Cluster OS Rolling Upgrade](https://learn.microsoft.com/en-us/windows-server/failover-clustering/cluster-operating-system-rolling-upgrade)

## 3. 운영 변경이 없는 업그레이드 사전 진단

관리자 또는 적절한 조회 권한으로 Windows 호스트의 **PowerShell 5.1 이상**에서:

```powershell
Set-Location C:\path\to\codex  # 실제로 복제한 프로젝트 경로로 교체
.\scripts\windows-server\Test-WasHost.ps1
.\scripts\windows-server\Get-WasUpgradeReadiness.ps1
.\scripts\windows-server\Get-WasUpgradeReadiness.ps1 -AsJson
```

`Get-WasUpgradeReadiness.ps1` 수집 항목:

| 항목 | 의도 |
|---|---|
| OS 설명, 버전, 빌드 번호 | 지원 업그레이드 경로 조회 |
| 물리 메모리, 시스템 드라이브 남은 공간 | 용량·다운타임 검토 자료 |
| Hyper-V 역할 설치 여부, 실행 중 VM 수 | Linux WAS 의존성 확인 |
| 체크포인트 수 | 백업으로 오인되지 않도록 확인 |
| Failover Clustering 역할 설치 여부 | 클러스터 절차가 필요한지 추가 확인 |
| 일부 재부팅 대기 레지스트리 표시 | 선행 재부팅/패치 검토 자료 |

**민감값 보호:** 호스트명/VM명/도메인/IP/사용자명/개인키를 출력하지 않습니다. 진단 항목만으로 시스템 준비 여부를 확정할 수는 없습니다. 클러스터 역할 설치만으로 실제 클러스터 가입 여부가 확정되지 않으므로 별도 관리 도구에서 확인해야 합니다.

**구문 검증:** `.github/workflows/windows-server-was.yml`은 Windows 2022 GitHub CI 러너에서 새 스크립트를 **실행 전에 파싱**하고 `-AsJson` 보고서를 읽어 기본 필드를 검증합니다. VM 생성·OS 업그레이드는 수행하지 않습니다.

## 4. 업그레이드 준비 게이트

- [ ] Windows Server **실제 버전·에디션·설치 유형(Desktop Experience / Server Core)** 확인
- [ ] CPU·메모리·디스크·스토리지 드라이버·BIOS/UEFI·TPM/보안 부팅 호환성 검토
- [ ] 라이선스·설치 매체(공식 SHA-256 확인)·작동 중 서버 역할/기능 호환성 확인
- [ ] 도메인 컨트롤러/클러스터 노드 여부 및 역할별 전용 업그레이드 경로 확인
- [ ] Hyper-V 호스트의 **모든 VM 및 가상 디스크 경로** 확인, 정지/마이그레이션 및 가동중단 창 확보
- [ ] **호스트 전체 백업 + Hyper-V VM 내보내기/복원 테스트 + Ubuntu 애플리케이션 SQLite 일관성 백업 + 별도 파일형 보안키 백업** 확인
- [ ] Windows 방화벽·네트워크 인터페이스·가상 스위치·라우팅·RDP/SSH 접근 경로 백업 및 되돌리기 계획
- [ ] Windows Updates/다른 서비스 재시작 영향·보안 제품 호환성·유지보수 담당자 승인
- [ ] 서비스 복구 지표(`/healthz`, WebAuthn 로그인, 문제은행 읽기/쓰기·정답 비노출, 백업 데이터 무결성)와 실패 시 복구 담당자 지정

**Hyper-V 체크포인트는 독립된 백업을 대체하지 않습니다.** 파일을 가져오거나 삭제/정리하지 않습니다. 운영 서버 데이터에는 실제 보안키 크리덴셜, 암호화 키, 개인 답안이 존재할 수 있으므로 GitHub 업로드 금지.

## 5. 실행 절차의 경계

승인된 관리자가 위 점검과 역할 호환성을 완료한 뒤 Microsoft의 [공식 인플레이스 업그레이드 절차](https://learn.microsoft.com/en-us/windows-server/get-started/upgrade-in-place)를 선택할 수 있습니다.

1. 유지보수 창 공지 및 백업 복원 실험; VM/게스트 서비스 보호 조치.
2. 해당 Windows Server 역할·클러스터·배포 경로에 적합한 설치 매체/업데이트 확인.
3. **물리/원격 콘솔에서 수동으로** 업그레이드 및 재부팅 수행(본 저장소의 스크립트는 OS 설치를 실행하지 않음).
4. 재부팅 후 Windows 에디션·빌드, Hyper-V 가상 스위치/VM 부팅, Ubuntu SSH 및 Docker/Compose 상태 검사.
5. WebAuthn 보안키 로그인 및 `/healthz`, 문제은행 데이터/문항 수, 필기 채점·실기 이력, 실습 승인 상태 검증.
6. 오류가 발생하면 임의 초기화·데이터볼륨 삭제 대신 문서화된 백업/이미지 복구 계획 적용.

## 6. 문제은행 120문항 추가 데이터와 연결

새 데이터: `data/study/security-exam-2027.json` (필기 5과목 100문항, 실기 20문항). 해당 파일을 운영 SQLite에 **자동으로 게시하지 않습니다.**

- 독립적으로 시험하려면 [2027 문제은행 대량 반영 가이드](study/2027_BULK_QUESTION_IMPORT.md)를 참고합니다.
- `scripts/study-question-import.py` 기본 실행은 **건수/형식 검사만** 하고 실제 DB를 수정하지 않습니다.
- `--apply` 명시 시에도 모든 신규 문항은 **초안(draft)** 상태로만 저장합니다.
- 저장한 문제를 `published`로 변경하는 것은 정답·해설·출처를 관리자가 검토한 경우에 한정합니다.

## 7. 구분해야 할 세 가지 검증

1. **GitHub CI 통과:** 배포 대상 서버의 Windows OS/보안 상태를 보장하지 않음.
2. **운영 서버 업그레이드 적합:** 읽기 전용 점검과 담당자의 역할·백업·라이선스 검토가 필요.
3. **배포 성공:** 실제 운영 서버에 접속해서 OS와 Hyper-V, Ubuntu WAS, 시험문제 DB/인증의 기능을 확인해야 증명됨.

담당자 승인이나 운영 서버 연결이 없으므로 이 문서만 추가한 시점에는 2·3이 완료됐다고 표시하지 않습니다.
