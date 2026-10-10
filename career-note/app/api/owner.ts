import {env} from 'cloudflare:workers';
// Dispatch owns and sanitizes authenticated identity headers. Resolve the verified
// site owner's authenticated email to a fixed account key, never use email as a DB key.
export function ownerKey(req:Request){const e=env as any;const email=req.headers.get('oai-authenticated-user-email');if(e.CAREER_OWNER_EMAIL&&e.CAREER_OWNER_KEY&&email?.toLowerCase()===e.CAREER_OWNER_EMAIL.toLowerCase())return e.CAREER_OWNER_KEY as string;return null;}
export function sameOrigin(req:Request){return req.headers.get('origin')===new URL(req.url).origin;}
