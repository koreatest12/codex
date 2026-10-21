import os
import time
import logging
import math
from pathlib import Path
from functools import wraps
from collections import deque
from typing import Callable, Any
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------
# 1. 감사 로깅(Audit Logging) 설정
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("mcp_security_audit.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SecureMCP")

# ---------------------------------------------------------
# 2. 보안 및 과금 방지 설정 (Configuration)
# ---------------------------------------------------------
class SecurityAndBillingConfig:
    # [과금 방지 1] 분당 최대 호출 횟수 (에이전트 무한 루프 방지)
    MAX_CALLS_PER_MINUTE: int = 15

    # [과금 방지 2] 일일 최대 허용 예산 (단위: USD)
    DAILY_BUDGET_USD: float = 5.00

    # [과금 방지 3] 반환 데이터 최대 글자 수 (LLM 입력 토큰 과금 폭발 방지)
    MAX_RESPONSE_CHARS: int = 3000  # 약 750~1000 토큰 수준으로 제한

    # [보안 1] 파일 접근이 허용된 안전한 샌드박스 디렉토리
    SAFE_BASE_DIR: Path = Path("./safe_workspace").resolve()

    # [보안 2] 입력값 내 차단할 위험 패턴 (명령어 인젝션 및 경로 조작 방지)
    BLOCKED_PATTERNS: list[str] = ["../", "..\\", "/etc/", "C:\\Windows", "rm -rf", "sudo", ";", "&&", "|"]

# 샌드박스 폴더 자동 생성
SecurityAndBillingConfig.SAFE_BASE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------
# 3. 과금 및 트래픽 가드 (Rate Limiter & Budget Tracker)
# ---------------------------------------------------------
class BillingAndSecurityGuard:
    def __init__(self, config: SecurityAndBillingConfig):
        self.config = config
        self.call_timestamps: deque = deque()
        self.accumulated_cost_usd: float = 0.0
        self.day_start_time: float = time.time()

    def _reset_daily_budget_if_needed(self):
        """24시간 경과 시 일일 누적 과금액 초기화"""
        now = time.time()
        if now - self.day_start_time >= 86400:  # 24시간(초)
            logger.info(f"일일 예산 주기가 초기화되었습니다. (이전 누적액: ${self.accumulated_cost_usd:.4f})")
            self.accumulated_cost_usd = 0.0
            self.day_start_time = now

    def verify_rate_limit(self):
        """분당 호출 횟수(Sliding Window) 검증"""
        now = time.time()
        # 60초가 지난 호출 기록 제거
        while self.call_timestamps and now - self.call_timestamps[0] > 60.0:
            self.call_timestamps.popleft()

        if len(self.call_timestamps) >= self.config.MAX_CALLS_PER_MINUTE:
            logger.warning("[과금 차단] Rate Limit 초과! 에이전트 무한 루프가 의심됩니다.")
            raise RuntimeError(
                f"Rate Limit 초과: 분당 최대 {self.config.MAX_CALLS_PER_MINUTE}회만 호출할 수 있습니다. 잠시 후 다시 시도하세요."
            )
        self.call_timestamps.append(now)

    def verify_and_charge_budget(self, estimated_cost_usd: float):
        """일일 예산 한도 검증 및 비용 누적"""
        if not math.isfinite(estimated_cost_usd) or estimated_cost_usd < 0:
            raise ValueError("Estimated cost must be finite and non-negative")
        self._reset_daily_budget_if_needed()
        if self.accumulated_cost_usd + estimated_cost_usd > self.config.DAILY_BUDGET_USD:
            logger.critical(
                f"[과금 차단] 일일 예산 한도 초과! (현재: ${self.accumulated_cost_usd:.4f}, 한도: ${self.config.DAILY_BUDGET_USD:.2f})"
            )
            raise RuntimeError(
                f"과금 보호 작동: 일일 예산 한도(${self.config.DAILY_BUDGET_USD:.2f})에 도달하여 도구 실행이 차단되었습니다."
            )
        self.accumulated_cost_usd += estimated_cost_usd
        logger.info(f"비용 차감: +${estimated_cost_usd:.4f} (오늘 누적: ${self.accumulated_cost_usd:.4f} / ${self.config.DAILY_BUDGET_USD:.2f})")

    def sanitize_inputs(self, args: tuple, kwargs: dict):
        """모든 입력 파라미터에 대해 위험 문자열 검사"""
        all_inputs = [str(a) for a in args] + [str(v) for v in kwargs.values()]
        for val in all_inputs:
            for pattern in self.config.BLOCKED_PATTERNS:
                if pattern.lower() in val.lower():
                    logger.error("[보안 차단] 허용되지 않는 입력 패턴 감지")
                    raise ValueError(f"보안 정책 위반: 허용되지 않는 문자 또는 패턴('{pattern}')이 포함되어 있습니다.")

    def validate_safe_path(self, target_path: str) -> Path:
        """Path Traversal 원천 차단 (지정된 샌드박스 내부인지 검증)"""
        resolved_path = (self.config.SAFE_BASE_DIR / target_path).resolve()
        if not resolved_path.is_relative_to(self.config.SAFE_BASE_DIR):
            logger.error("[보안 차단] 샌드박스 외부 접근 시도")
            raise PermissionError("보안 정책 위반: 허용된 작업 디렉토리 외부의 파일에는 접근할 수 없습니다.")
        return resolved_path

    def truncate_output(self, result: Any) -> str:
        """반환 데이터가 너무 클 경우 LLM 입력 토큰 비용 폭증을 막기 위해 잘라냄"""
        result_str = str(result)
        if len(result_str) > self.config.MAX_RESPONSE_CHARS:
            logger.warning(
                f"[토큰 과금 방지] 응답 크기({len(result_str)}자)가 한도를 초과하여 {self.config.MAX_RESPONSE_CHARS}자로 절단합니다."
            )
            suffix = "\n...[응답이 절단되었습니다]..."
            limit = self.config.MAX_RESPONSE_CHARS
            if limit <= len(suffix):
                return suffix[:limit]
            return result_str[:limit - len(suffix)] + suffix
        return result_str


guard = BillingAndSecurityGuard(SecurityAndBillingConfig())


# ---------------------------------------------------------
# 4. 보안 및 과금 데코레이터 정의
# ---------------------------------------------------------
def secure_and_budget_guard(estimated_cost_usd: float = 0.001):
    """
    모든 MCP Tool에 적용하는 데코레이터.
    - estimated_cost_usd: 해당 도구가 1회 실행될 때 예상되는 외부 API 비용 또는 리소스 비용
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            tool_name = func.__name__
            logger.info("도구 실행 요청: %s", tool_name)
            try:
                # 1. 입력값 보안 검증
                guard.sanitize_inputs(args, kwargs)
                # 2. 분당 호출 빈도 제한 확인
                guard.verify_rate_limit()
                # 3. 일일 예산 한도 확인 및 차감
                guard.verify_and_charge_budget(estimated_cost_usd)

                # 4. 실제 도구 로직 실행
                raw_result = func(*args, **kwargs)

                # 5. 출력 크기 제한 (LLM 컨텍스트 토큰 과금 방지)
                safe_result = guard.truncate_output(raw_result)
                return safe_result

            except Exception as e:
                logger.error("도구 실행 실패 (%s): %s", tool_name, type(e).__name__)
                # 에러 메시지를 명확히 반환하여 에이전트가 무의미한 재시도(무한 루프)를 하지 않도록 유도
                return f"[실행 거부됨] {type(e).__name__} (재시도하지 마십시오)"
        return wrapper
    return decorator


# ---------------------------------------------------------
# 5. MCP 서버 및 도구(Tools) 등록
# ---------------------------------------------------------
mcp = FastMCP("Secure-Billing-Protected-MCP")

@mcp.tool()
@secure_and_budget_guard(estimated_cost_usd=0.005)  # 예: 1회 파일 읽기 시 $0.005 책정
def read_workspace_file(filename: str) -> str:
    """안전한 작업 공간(safe_workspace) 내부의 텍스트 파일을 읽습니다."""
    safe_file_path = guard.validate_safe_path(filename)

    if not safe_file_path.exists():
        return f"파일을 찾을 수 없습니다: {filename}"

    with safe_file_path.open(encoding="utf-8") as handle:
        return handle.read(guard.config.MAX_RESPONSE_CHARS + 1)


@mcp.tool()
@secure_and_budget_guard(estimated_cost_usd=0.05)  # 예: 유료 외부 API 호출 시 회당 $0.05 책정
def call_paid_external_api(query: str) -> str:
    """과금이 발생하는 외부 유료 검색/데이터 API를 호출하는 예시 도구입니다."""
    # 실제 외부 API 호출 로직이 들어갈 자리 (예: requests.get / 유료 DB 쿼리 등)
    simulated_large_response = f"'{query}'에 대한 검색 결과입니다.\n" + ("상세 데이터 라인...\n" * 500)
    return simulated_large_response


@mcp.tool()
def get_budget_status() -> str:
    """현재 누적 과금액과 잔여 한도를 조회합니다. (비용 미차감)"""
    guard._reset_daily_budget_if_needed()
    remaining = max(0.0, SecurityAndBillingConfig.DAILY_BUDGET_USD - guard.accumulated_cost_usd)
    return (
        f"- 현재 누적 사용액: ${guard.accumulated_cost_usd:.4f}\n"
        f"- 일일 예산 한도: ${SecurityAndBillingConfig.DAILY_BUDGET_USD:.2f}\n"
        f"- 잔여 예산: ${remaining:.4f}"
    )

if __name__ == "__main__":
    logger.info("보안 및 과금 방지 MCP 서버가 시작되었습니다.")
    mcp.run()
