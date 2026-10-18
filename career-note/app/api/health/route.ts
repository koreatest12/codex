import {storageCostGuard} from '../cost-guard';
import {env} from 'cloudflare:workers';
import {ownerKey} from '../owner';
async function probe(name:string,operation:()=>Promise<unknown>){const start=Date.now();let timer:ReturnType<typeof setTimeout>|undefined;try{await Promise.race([operation(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('timeout')),4000)})]);return {name,status:'ok',ms:Date.now()-start};}catch{return {name,status:'error',ms:Date.now()-start};}finally{if(timer)clearTimeout(timer)}}
// Reject unauthenticated requests before metered D1/R2 operations.
export async function GET(req:Request){const blocked=storageCostGuard();if(blocked)return blocked;if(!ownerKey(req))return new Response('Unauthorized',{status:401,headers:{'Cache-Control':'private, no-store'}});const checks=await Promise.all([
probe('database',()=>env.DB!.prepare('SELECT id FROM entries LIMIT 1').first()),
probe('files',()=>env.BUCKET!.head('__imported__/completed-v2'))
]);const ok=checks.every(c=>c.status==='ok');return Response.json({ok,checkedAt:new Date().toISOString(),checks,session:ownerKey(req)?'ok':'login_required',runtime:'Cloudflare Workers',recovery:'retry-and-reconnect',processRestartSupported:false},{status:ok?200:503,headers:{'Cache-Control':'private, no-store'}});}
