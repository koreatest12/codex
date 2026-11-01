const $=s=>document.querySelector(s);
let view="dashboard",meta=null,quiz=[],pos=0;
function node(tag,text,cls){const x=document.createElement(tag);if(text!==undefined)x.textContent=text;if(cls)x.className=cls;return x}
function clear(){ $("#content").replaceChildren();$("#toolbar").replaceChildren() }
function card(parent,title,detail){const c=node("article",undefined,"card");c.append(node("h3",title));if(detail)c.append(node("p",detail));parent.append(c);return c}
function button(parent,label,fn,cls=""){const b=node("button",label,cls);b.addEventListener("click",fn);parent.append(b);return b}
function selector(parent,opts,fn){const s=node("select");opts.forEach(([value,label])=>{const o=node("option",label);o.value=value;s.append(o)});s.addEventListener("change",()=>fn(s.value));parent.append(s);return s}
async function api(path,opts){const r=await fetch(path,{...opts,headers:{"Content-Type":"application/json",...(opts?.headers||{})}});
 if(!r.ok){let d={};try{d=await r.json()}catch{}throw new Error(typeof d.detail==="string"?d.detail:"HTTP "+r.status)}return r.json()}
function message(e){alert(e.message||String(e))}
function choose(next){view=next;document.querySelectorAll("nav button").forEach(x=>x.classList.toggle("active",x.dataset.view===next));
 $("#heading").textContent=({dashboard:"학습 대시보드",concepts:"과목별 개념",quiz:"문제은행",written:"실기 연습",wrongbook:"오답노트",sources:"출처 관리"})[next];clear();
 Promise.resolve(({dashboard,concepts,quiz:quizView,written,wrongbook,sources})[next]()).catch(message)}
function subjSelect(fn){return selector($("#toolbar"),[["","전체 과목"],...meta.subjects.map(s=>[s,s])],fn)}
async function dashboard(){const a=await api("/api/analytics");const grid=node("div",undefined,"grid");$("#content").append(grid);
const total=a.subjects.reduce((n,s)=>n+s.attempts,0),hit=a.subjects.reduce((n,s)=>n+s.correct,0);
[["개념 학습",a.total_done+"/"+a.total_concepts],["누적 정답률",total?Math.round(hit/total*100)+"%":"미응시"],["오답 문제",String(a.wrong_count)],["문제 풀이",total+"회"]].forEach(([k,v])=>{const c=card(grid,k);c.append(node("p",v,"metric"))});
a.subjects.forEach(s=>card($("#content"),s.subject,"진도 "+s.done+"/"+s.total+" · 객관식 "+s.questions+"문제 · 정답률 "+(s.accuracy===null?"미응시":s.accuracy+"%")))}
async function concepts(subject=""){clear();subjSelect(concepts);const all=await api("/api/concepts?subject="+encodeURIComponent(subject));
all.forEach(x=>{const c=card($("#content"),x.topic,x.subject+" · "+x.summary);c.append(node("pre",x.description));
if(x.source_url){const a=node("a",x.source_url,"link");a.href=x.source_url;a.target="_blank";a.rel="noopener noreferrer";c.append(a)}
const label=node("label");const chk=document.createElement("input");chk.type="checkbox";chk.checked=x.done;chk.addEventListener("change",async()=>{try{await api("/api/progress?key="+encodeURIComponent(x.key),{method:"POST",body:JSON.stringify({done:chk.checked})})}catch(e){chk.checked=!chk.checked;message(e)}});label.append(chk,"완료");c.append(node("p"),label)})}
async function quizView(subject=""){clear();subjSelect(quizView);selector($("#toolbar"),[["all","전체 문제"],["wrong","틀린 문제만"]],m=>$("#toolbar").dataset.mode=m);
button($("#toolbar"),"문제 시작",async()=>{const mode=$("#toolbar").dataset.mode||"all";const data=await api("/api/quiz?subject="+encodeURIComponent(subject)+"&mode="+mode+"&count=20");
quiz=data.questions;pos=0;renderQuiz()},"primary");$("#content").append(node("p","과목과 문제 유형을 선택하고 문제 시작을 누르세요."))}
function renderQuiz(){const el=$("#content");el.replaceChildren();if(pos>=quiz.length){el.append(node("h3",quiz.length?"문제 풀이를 마쳤습니다.":"해당 조건의 문제가 없습니다."));return}
const q=quiz[pos],c=card(el,"문제 "+(pos+1)+" / "+quiz.length,q.subject+" · "+q.topic);c.append(node("pre",q.prompt));
const ans=node("div",undefined,"answers");c.append(ans);
q.options.forEach((choice,i)=>button(ans,(i+1)+". "+choice,async()=>{try{const res=await api("/api/answers",{method:"POST",body:JSON.stringify({question_key:q.key,selected:i})});
ans.querySelectorAll("button").forEach(b=>b.disabled=true);const d=card(el,res.correct?"정답입니다":"오답입니다",res.explanation);
d.classList.add(res.correct?"correct":"wrong");d.append(node("p","정답: "+q.options[res.correct_index]));
if(res.source_url){const a=node("a","참고 출처 확인");a.href=res.source_url;a.target="_blank";a.rel="noopener noreferrer";d.append(a)}
button(el,"다음 문제",()=>{pos++;renderQuiz()},"primary")}catch(e){message(e)}})))}
async function written(subject=""){clear();subjSelect(written);const all=await api("/api/written?subject="+encodeURIComponent(subject));all.forEach(x=>{const c=card($("#content"),x.subject+" · 실기",x.prompt);
const t=node("textarea");t.placeholder="직접 답안을 작성해 보세요 (서버에 저장되지 않음)";c.append(t);
button(c,"모범답안 확인",()=>{if(c.querySelector(".sample"))return;const d=node("p",x.model_answer+"\n"+x.explanation,"sample");d.style.whiteSpace="pre-wrap";c.append(d)})})}
async function wrongbook(){const rows=await api("/api/wrongbook");if(!rows.length){$("#content").append(node("p","현재 복습할 오답이 없습니다."));return}
rows.forEach(x=>{const c=card($("#content"),x.topic,x.subject+" · "+x.prompt);c.append(node("p","마지막 오답: "+x.created_at));
const t=node("textarea");t.value=x.memo||"";t.placeholder="틀린 이유·복습 메모";c.append(t);
const date=node("input");date.type="date";date.value=x.review_date||"";c.append(date);
button(c,"메모 저장",async()=>{try{await api("/api/wrongbook/"+encodeURIComponent(x.question_key),{method:"PUT",body:JSON.stringify({memo:t.value,review_date:date.value})});alert("저장했습니다.")}catch(e){message(e)}})})}
async function sources(){const list=await api("/api/sources");const c=card($("#content"),"새 출처 등록");
const fields={};["title","url","publisher","version","notes"].forEach(k=>{const input=node("input");input.placeholder=({title:"자료명",url:"https://...",publisher:"발행기관",version:"발행연도/버전",notes:"검증 메모"})[k];fields[k]=input;c.append(input)});
button(c,"출처 추가",async()=>{try{await api("/api/sources",{method:"POST",body:JSON.stringify(Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.value]))) });clear();sources()}catch(e){message(e)}},"primary");
list.forEach(s=>{const x=card($("#content"),s.title,s.publisher+" · "+s.version+" · "+s.notes);const a=node("a",s.url,"link");a.href=s.url;a.target="_blank";a.rel="noopener noreferrer";x.append(a);
button(x,"수정",async()=>{const title=prompt("자료명",s.title);if(title===null)return;
const notes=prompt("검증 메모",s.notes);if(notes===null)return;try{await api("/api/sources/"+s.id,{method:"PUT",body:JSON.stringify({...s,title,notes})});clear();sources()}catch(e){message(e)}});
button(x,"삭제",async()=>{if(!confirm("이 출처를 삭제할까요?"))return;try{await api("/api/sources/"+s.id,{method:"DELETE"});clear();sources()}catch(e){message(e)}})})}
document.querySelectorAll("nav button").forEach(b=>b.addEventListener("click",()=>choose(b.dataset.view)));
api("/api/meta").then(x=>{meta=x;choose("dashboard")}).catch(message);
