const assert=require('node:assert/strict');
const {create}=require('../web/reconnect.js');
function fixture(synchronize){
 const timers=new Map(),states=[],streams=[];let id=0;
 const controller=create({synchronize,onState:(...row)=>states.push(row),
  createStream(){const s={closed:false,close(){this.closed=true;}};streams.push(s);return s;},
  setTimeout(fn,ms){timers.set(++id,{fn,ms});return id;},clearTimeout(id){timers.delete(id);}});
 async function tick(ms){const entry=[...timers].find(([,t])=>t.ms===ms);assert.ok(entry,'missing '+ms+'ms timer');timers.delete(entry[0]);entry[1].fn();await Promise.resolve();await Promise.resolve();}
 return {controller,timers,states,streams,tick};
}
(async()=>{
 let probes=0;
 const f=fixture(async()=>{if(++probes<3)throw Error('offline');});
 await f.controller.start();assert.deepEqual(f.states.at(-1),['reconnecting',1000]);
 await f.tick(1000);assert.deepEqual(f.states.at(-1),['reconnecting',2000]);
 await f.tick(2000);assert.equal(f.streams.length,1);f.streams[0].onopen();assert.equal(f.states.at(-1)[0],'connected');
 const old=f.streams[0];old.onerror();assert.ok(old.closed);assert.deepEqual(f.states.at(-1),['reconnecting',1000]);
 await f.tick(1000);f.streams[1].onopen();const count=f.timers.size;old.onerror();assert.equal(f.timers.size,count);
 const before=f.states.length;await f.controller.wake();assert.equal(f.states.length,before,'healthy wake must not flash connecting');
 assert.ok(f.streams[1].closed);f.streams[2].onopen();f.controller.stop();assert.equal(f.timers.size,0);
 let resolve;const pending=fixture(()=>new Promise(r=>resolve=r));
 const first=pending.controller.start();await pending.controller.wake();await pending.controller.wake();
 assert.equal(pending.streams.length,0);resolve();await first;assert.equal(pending.streams.length,1);pending.controller.stop();
 const timeout=fixture(signal=>new Promise((r,reject)=>signal.addEventListener('abort',()=>reject(Error('aborted')))));
 const waiting=timeout.controller.start();await timeout.tick(10000);await waiting;
 assert.deepEqual(timeout.states.at(-1),['reconnecting',1000]);timeout.controller.stop();
 const failed=fixture(async()=>{throw Error('offline');});await failed.controller.start();
 for(const delay of [1000,2000,4000,8000,10000,10000])await failed.tick(delay);
 assert.deepEqual(failed.states.at(-1),['reconnecting',10000]);failed.controller.stop();
 console.log('Reconnect: initial failure, recovery, stream loss, capped backoff, timeout, single flight and healthy wake passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
