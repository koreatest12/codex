'use strict';
(function(global){
const MENU=[{name:'떡볶이',icon:'🥘',price:4500,time:4},{name:'김밥',icon:'🍙',price:3500,time:3.5},{name:'라면',icon:'🍜',price:5000,time:4.5},{name:'만두',icon:'🥟',price:6000,time:5,unlock:22000},{name:'햄버거',icon:'🍔',price:8500,time:6,unlock:45000},{name:'피자',icon:'🍕',price:11000,time:7,unlock:75000}];
const DEFS={speed:{name:'조리 도구',max:12,base:12000},storage:{name:'음식 보관 공간',max:6,base:10000},stations:{name:'조리대',max:5,base:18000},seats:{name:'주문 카운터',max:5,base:15000},chef:{name:'주방 직원',max:4,base:22000},waiter:{name:'판매 직원',max:4,base:22000}};
class Engine{
 constructor(random=Math.random){this.random=random;this.settings={stock:true,equip:true,recipe:true,next:true};this.auto=false;this.logs=[];this.serial=0;this.elapsed=0;this.purchaseTimer=0;this.nextWait=0;this.reset();}
 reset(){this.s={day:1,time:120,running:false,paused:false,money:30000,sold:0,total:0,revenue:0,totalRevenue:0,expense:0,missed:0,combo:0,bestCombo:0,rep:80,goal:90000,level:{speed:1,storage:1,stations:1,seats:1,chef:0,waiter:0},unlocked:[true,true,true,false,false,false],stock:[16,16,16,0,0,0],ready:[0,0,0,0,0,0],jobs:[],customers:[],spawn:0,report:null};this.log('새 분식집을 열 준비가 됐어요.');}
 log(text){this.logs.unshift({at:Math.floor(this.elapsed),text});this.logs.length=Math.min(this.logs.length,10);}
 capacity(){return 5+(this.s.level.storage-1)*4;}
 stationCount(){return this.s.level.stations;}
 seats(){return 6+(this.s.level.seats-1)*2;}
 duration(i){return Math.max(.8,MENU[i].time/(1+(this.s.level.speed-1)*.22+this.s.level.chef*.08));}
 cost(k){const d=DEFS[k];return d.base*(this.s.level[k]+(k==='chef'||k==='waiter'?1:0));}
 open(){const s=this.s;if(s.running)return false;const next=!!s.report;if(next){s.day++;s.goal=Math.round(90000*(1+.28*(s.day-1)));}Object.assign(s,{time:120,running:true,paused:false,sold:0,revenue:0,expense:0,missed:0,combo:0,customers:[],spawn:2,report:null});this.nextWait=0;this.spawn();this.spawn();this.log(`${s.day}일차 영업 시작!`);return true;}
 spawn(){const s=this.s;if(!s.running||s.customers.length>=this.seats())return;const available=MENU.map((_,i)=>i).filter(i=>s.unlocked[i]);const food=available[Math.floor(this.random()*available.length)];const vip=this.random()<.12,qty=this.random()<.30?2:1+(s.day>2&&this.random()<.2?2:0);const max=32+Math.min(s.level.waiter*2,8);s.customers.push({id:++this.serial,food,qty,vip,takeaway:this.random()<.3,face:Math.floor(this.random()*6),patience:max,max,age:0});}
 cooking(i){return this.s.jobs.filter(j=>j.food===i).reduce((sum,j)=>sum+j.qty,0);}
 cook(i,bulk=false){const s=this.s;if(!s.running||s.paused||!s.unlocked[i]||s.jobs.filter(j=>j.food===i).length>=this.stationCount())return false;const free=this.capacity()-s.ready[i]-this.cooking(i);const qty=Math.min(bulk?3:1,s.stock[i],free);if(qty<=0)return false;s.stock[i]-=qty;const duration=this.duration(i)*(1+(qty-1)*.18);s.jobs.push({food:i,qty,left:duration,duration});return true;}
 sell(id,automated=false){const s=this.s,c=s.customers.find(c=>c.id===id);if(!c||!s.running||s.paused||s.ready[c.food]<c.qty||(automated&&c.age<2))return false;s.ready[c.food]-=c.qty;s.sold+=c.qty;s.total+=c.qty;s.combo++;s.bestCombo=Math.max(s.bestCombo,s.combo);const base=MENU[c.food].price*c.qty;const tip=Math.round((c.patience/c.max*600*c.qty+Math.min(s.combo,15)*100)*(c.vip?1.7:1)/100)*100;const revenue=base+tip;s.money+=revenue;s.revenue+=revenue;s.totalRevenue+=revenue;s.rep=Math.min(100,s.rep+.6);s.customers=s.customers.filter(x=>x.id!==id);this.log(`${MENU[c.food].name} ${c.qty}그릇 판매 · +₩${revenue.toLocaleString('ko-KR')}${c.vip?' VIP':''}`);return true;}
 restock(i=null){const s=this.s;if(s.paused)return false;const cost=i===null?10000:2500;if(s.money<cost||(i!==null&&!s.unlocked[i]))return false;if(i===null&&!s.unlocked.some((u,j)=>u&&s.stock[j]<120))return false;if(i!==null&&s.stock[i]>=120)return false;s.money-=cost;s.expense+=cost;for(let j=0;j<MENU.length;j++)if(s.unlocked[j]&&(i===null||i===j))s.stock[j]=Math.min(120,s.stock[j]+12);this.log(i===null?'전체 재료 12개씩 보충':MENU[i].name+' 재료 12개 보충');return true;}
 upgrade(k){const s=this.s,d=DEFS[k];if(!d||s.paused||s.level[k]>=d.max||s.money<this.cost(k))return false;const cost=this.cost(k);s.money-=cost;s.expense+=cost;s.level[k]++;this.log(`${d.name} Lv.${s.level[k]} 구매 · ₩${cost.toLocaleString('ko-KR')}`);return true;}
 unlock(i){const s=this.s;if(s.paused||s.unlocked[i]||!MENU[i].unlock||s.money<MENU[i].unlock)return false;s.money-=MENU[i].unlock;s.expense+=MENU[i].unlock;s.unlocked[i]=true;s.stock[i]=12;this.log(MENU[i].name+' 메뉴 해금! 재료 12개 지급');return true;}
 automate(){const s=this.s;if(!s.running||s.paused)return;
 if(this.auto||s.level.waiter>0)for(const c of [...s.customers].sort((a,b)=>a.patience-b.patience))this.sell(c.id,true);
 if(this.auto&&this.settings.stock&&s.unlocked.some((u,i)=>u&&s.stock[i]<=4)&&s.money>=10000)this.restock();
 if(this.auto&&this.purchaseTimer<=0&&s.time>20){const reserve=10000;let bought=false;
  if(this.settings.recipe){const i=s.unlocked.findIndex(u=>!u);if(i>=0&&s.money>=MENU[i].unlock+reserve)bought=this.unlock(i);}
  if(!bought&&this.settings.equip){const keys=Object.keys(DEFS).filter(k=>s.level[k]<DEFS[k].max).sort((a,b)=>this.cost(a)-this.cost(b));for(const k of keys)if(s.money>=this.cost(k)+reserve){bought=this.upgrade(k);break;}}
  if(bought)this.purchaseTimer=3;
 }
 if(this.auto||s.level.chef>0)for(let i=0;i<MENU.length;i++){if(!s.unlocked[i])continue;const demand=s.customers.filter(c=>c.food===i).reduce((n,c)=>n+c.qty,0);const target=Math.min(this.capacity(),Math.max(3,demand+2));while(s.ready[i]+this.cooking(i)<target&&s.jobs.filter(j=>j.food===i).length<this.stationCount()){if(!this.cook(i,true))break;}}
 }
 finish(){const s=this.s;s.running=false;s.time=0;const success=s.revenue>=s.goal;const bonus=success?Math.round(s.goal*.12):0;s.money+=bonus;s.report={day:s.day,sold:s.sold,revenue:s.revenue,expense:s.expense,missed:s.missed,goal:s.goal,success,bonus};this.nextWait=5;this.log(`${s.day}일차 마감 · ${success?'목표 달성! 보너스 ₩'+bonus.toLocaleString('ko-KR'):'다음 날 다시 도전해요.'}`);}
 step(dt){dt=Math.min(Math.max(dt,0),.5);const s=this.s;if(!s.running){if(s.report&&this.auto&&this.settings.next){this.nextWait-=dt;if(this.nextWait<=0)this.open();}return;}if(s.paused)return;this.elapsed+=dt;s.time=Math.max(0,s.time-dt);this.purchaseTimer-=dt;
 for(const j of s.jobs)j.left-=dt;for(const j of s.jobs.filter(j=>j.left<=0))s.ready[j.food]+=j.qty;s.jobs=s.jobs.filter(j=>j.left>0);
 for(const c of s.customers){c.patience-=dt;c.age+=dt;}const lost=s.customers.filter(c=>c.patience<=0);if(lost.length){s.missed+=lost.length;s.rep=Math.max(10,s.rep-lost.length*3);s.combo=0;this.log(`손님 ${lost.length}명이 기다리다 떠났어요.`);}s.customers=s.customers.filter(c=>c.patience>0);
 if(s.time<=0){this.finish();return;}s.spawn-=dt;if(s.spawn<=0){this.spawn();s.spawn=Math.max(1.2,3-(s.day-1)*.1-s.rep*.008);}this.automate();
 }
}
global.RushEngine=Engine;global.RushMenu=MENU;global.RushUpgrades=DEFS;
})(globalThis);
