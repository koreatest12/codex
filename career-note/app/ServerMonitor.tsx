'use client';
import {useEffect,useRef,useState} from 'react';
import {Activity,RefreshCw,Database,HardDrive,ShieldCheck} from 'lucide-react';
import {reliableGet} from './reliable-fetch';
type Health={ok:boolean,checkedAt:string,session:string,checks:{name:string,status:string,ms:number}[]};
export default function ServerMonitor({expanded,onRecovered}:{expanded:boolean,onRecovered:()=>Promise<void>}){
const [health,setHealth]=useState<Health|null>(null),[busy,setBusy]=useState(false),[state,setState]=useState('점검 중'),[history,setHistory]=useState<{time:string,text:string}[]>([]),[auto,setAuto]=useState(true);
const running=useRef(false),failed=useRef(false),callback=useRef(onRecovered),alive=useRef(true);callback.current=onRecovered;
function log(text:string){if(alive.current)setHistory(h=>[{time:new Date().toLocaleTimeString('ko-KR'),text},...h].slice(0,20))}
async function check(manual=false){if(running.current)return;running.current=true;setBusy(true);try{
if(!navigator.onLine)throw new Error('인터넷 연결 끊김');
const r=await reliableGet('/api/health');if(!r.headers.get('content-type')?.includes('application/json'))throw new Error('로그인 또는 서버 응답 확인 필요');const h=await r.json() as Health;if(!alive.current)return;setHealth(h);
if(!h.ok){if(!failed.current||manual)log('저장소 점검 실패 · 다음 주기에 재점검');failed.current=true;setState('저장소 점검 필요');return;}
if(h.session!=='ok'){setState('로그인 연결 필요');if(manual)log('서버 정상 · 로그인 재연결 필요');return;}
if(manual||failed.current){setState('자료 다시 불러오는 중');await callback.current();log('연결 복구 및 자료 조회 완료');}else if(!health)log('서버·DB·파일 저장소 점검 완료');
failed.current=false;setState('정상');
}catch(e){const text=e instanceof Error?e.message:'연결 오류';if(!failed.current||manual)log(text);failed.current=true;if(alive.current)setState(text);}finally{running.current=false;if(alive.current)setBusy(false)}}
useEffect(()=>{alive.current=true;check();return()=>{alive.current=false}},[]);
useEffect(()=>{if(!auto)return;const timer=setInterval(()=>{if(document.visibilityState==='visible')check()},30000);const resume=()=>{if(document.visibilityState==='visible')check()};window.addEventListener('online',resume);document.addEventListener('visibilitychange',resume);return()=>{clearInterval(timer);window.removeEventListener('online',resume);document.removeEventListener('visibilitychange',resume)}},[auto]);
const good=health?.ok&&health.session==='ok'&&state==='정상';
return <section className={'server-monitor '+(expanded?'expanded':'')}><div className="server-strip"><span className={'status-dot '+(good?'good':'bad')}/><strong>이력서 서버</strong><span role="status">{busy?'상태 점검 중…':state}</span><button className="outline" disabled={busy} onClick={()=>check(true)}><RefreshCw size={14}/> 연결 복구</button></div>{expanded&&<><div className="server-explanation"><h2>서버 상태와 연결 복구</h2><p>현재 서비스는 요청 단위로 실행되는 Cloudflare Workers 서버입니다. 아래 복구는 서버 연결과 자료 조회를 다시 시도하며, 서버 프로세스를 재기동하지 않습니다.</p></div><div className="health-grid">{[{name:'database',label:'이력서 데이터베이스',Icon:Database},{name:'files',label:'첨부파일 저장소',Icon:HardDrive}].map(({name,label,Icon})=>{const c=health?.checks.find(x=>x.name===name);return <div className="health-card" key={name}><Icon size={23}/><h3>{label}</h3><strong>{!c?'확인 전':c.status==='ok'?'정상':'점검 필요'}</strong><small>{c?c.ms+' ms':'—'}</small></div>})}<div className="health-card"><ShieldCheck size={23}/><h3>로그인 연결</h3><strong>{!health?'확인 전':health.session==='ok'?'정상':'재연결 필요'}</strong>{health?.session!=='ok'&&<a href="/signin-with-chatgpt?return_to=%2F" target="_top">ChatGPT 로그인</a>}</div></div><div className="monitor-settings"><label><input type="checkbox" checked={auto} onChange={e=>setAuto(e.target.checked)}/> 화면을 보고 있을 때 30초마다 상태 점검</label><p>일시적인 조회 오류는 최대 2회 재시도합니다. 저장·삭제 요청은 자동 반복하지 않습니다. 편집 중인 내용은 강제로 새로고침하지 않습니다.</p><small>마지막 서버 점검: {health?new Date(health.checkedAt).toLocaleString('ko-KR'):'—'}</small></div><div className="recovery-log"><h3>현재 화면의 점검·복구 기록</h3>{history.map((h,i)=><p key={i}><time>{h.time}</time>{h.text}</p>)}<small>최근 20건 · 화면을 닫으면 이 목록은 초기화됩니다.</small></div></>}</section>}
