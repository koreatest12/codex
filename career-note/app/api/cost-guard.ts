import {env} from 'cloudflare:workers';

/** Paid storage is disabled unless the operator explicitly accepts usage costs. */
export function storageCostGuard(): Response | null {
  if ((env as {ENABLE_METERED_STORAGE?: string}).ENABLE_METERED_STORAGE === 'true') return null;
  // A non-retryable response prevents read retries while the cost lock is active.
  return new Response('비용 보호 설정으로 저장소 접근이 중지되었습니다.', {
    status: 403,
    headers: {'Cache-Control': 'private, no-store'},
  });
}
