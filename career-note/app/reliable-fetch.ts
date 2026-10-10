/** Read-only retries. Never replay a write automatically. */
export async function reliableGet(url:string, fetcher:typeof fetch=fetch, delay:(ms:number)=>Promise<void>=ms=>new Promise(r=>setTimeout(r,ms))){
for(let attempt=0;attempt<3;attempt++){
 const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),8000);
 try{const response=await fetcher(url,{method:'GET',credentials:'same-origin',cache:'no-store',signal:controller.signal});
 if(![408,429,500,502,503,504].includes(response.status)||attempt===2)return response;
 }catch(e){if(attempt===2)throw new Error('서버 연결 시간이 초과되었거나 네트워크 연결이 끊겼습니다.');}
 finally{clearTimeout(timer)}
 await delay(attempt===0?1000:2500);
}
throw new Error('서버 연결 실패');
}
