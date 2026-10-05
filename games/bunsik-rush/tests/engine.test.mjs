import {readFileSync} from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
const c=vm.createContext({console,Math});vm.runInContext(readFileSync('../../app/static/bunsik-rush/engine.js','utf8'),c);const E=c.RushEngine;
// Deterministic random: reproducible traffic, multiple menu choices and VIPs.
function rng(seed){return()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;}}
const e=new E(rng(1));e.open();const first=e.s.customers[0];e.s.ready[first.food]=5;assert.equal(e.sell(first.id,true),false);first.age=2;assert.equal(e.sell(first.id,true),true);
e.s.money=500000;e.upgrade('stations');e.upgrade('storage');assert.equal(e.cook(0,true),true);assert.equal(e.cook(0,true),true);assert.equal(e.cook(0,true),false);assert.ok(e.cooking(0)<=e.capacity());const time=e.s.time;e.s.paused=true;e.step(.5);assert.equal(e.s.time,time);assert.equal(e.upgrade('speed'),false);e.s.paused=false;
assert.equal(e.unlock(3),true);assert.equal(e.s.stock[3],12);assert.equal(e.unlock(3),false);
for(let seed=1;seed<=10;seed++){const game=new E(rng(seed));game.auto=true;game.open();for(let n=0;n<5000;n++){game.step(.1);const s=game.s;assert.ok(s.money>=0);assert.ok(s.customers.length<=game.seats());for(let i=0;i<6;i++){assert.ok(s.stock[i]>=0);assert.ok(s.ready[i]+game.cooking(i)<=game.capacity());}assert.ok(s.level.speed<=12);}assert.ok(game.s.day>=4);assert.ok(game.s.total>150);assert.ok(game.s.unlocked.every(Boolean));}
const off=new E(rng(9));off.auto=true;off.settings={stock:false,equip:false,recipe:false,next:false};off.open();for(let n=0;n<1300;n++)off.step(.1);assert.equal(off.s.day,1);assert.equal(off.s.running,false);assert.equal(off.s.level.speed,1);assert.equal(off.s.unlocked[3],false);
const manual=new E(rng(10));manual.open();manual.s.money=60000;manual.upgrade('chef');manual.upgrade('waiter');for(let n=0;n<1000;n++)manual.step(.1);assert.ok(manual.s.sold>0);assert.equal(manual.auto,false);
console.log('PASS: multi-bowl orders, parallel cooking, limits, 10 automatic multi-day games, purchasing toggles, staff, pause');
