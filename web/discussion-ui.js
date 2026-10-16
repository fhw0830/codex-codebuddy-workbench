(function(root){
 'use strict';
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const names={codex:'Codex',codebuddy:'CodeBuddy'};
 function rootFor(c,id){return (c.messages||[]).find(m=>m.role==='user'&&m.meta?.job_id===id&&!['answer','steer'].includes(m.meta?.delivery?.mode));}
 function context(c,m){
  const id=m.meta?.job_id,source=id?rootFor(c,id):null;
  const job=c.job?.id===id?c.job:null;
  const route=source?.meta?.route||job?.route;
  const total=route&&route!=='both'?1:Number(m.meta?.total_rounds||source?.meta?.rounds||job?.rounds)||null;
  return {accessMode:m.meta?.access_mode,id,round:Number(m.meta?.round)||null,total,route,strategy:source?.meta?.execution_strategy||job?.meta?.execution_strategy};
 }
 function actorState(c,id,round,actor){
  const messages=(c.messages||[]).filter(m=>m.role==='assistant'&&m.meta?.job_id===id&&Number(m.meta?.round)===round&&m.agent===actor&&!m.meta?.deleted);
  const latest=messages.at(-1);
  if(!latest){
   const checkpoint=rootFor(c,id)?.meta?.resume_checkpoint,order=['codex','codebuddy'];
   if(checkpoint&&Number(checkpoint.round)===round&&order.indexOf(actor)<order.indexOf(checkpoint.agent)){
    const original=(c.messages||[]).find(m=>m.role==='assistant'&&m.agent===actor&&Number(m.meta?.round)===round&&m.status==='completed'&&(m.meta?.job_id===checkpoint.source_job_id||m.id===checkpoint.handoff_source_message_id));
    return {state:'completed',label:original?'上次已完成':'本轮未重复执行'};
   }
   return {state:'pending',label:'未开始'};
  }
  if((c.input_requests||[]).some(q=>q.message_id===latest.id&&q.state==='pending'&&q.blocking))return {state:'waiting',label:'等你回答'};
  return {state:latest.status,label:({completed:'回答完成',streaming:'进行中',failed:'本次失败',interrupted:'已停止'}[latest.status]||'待确认')};
 }
 function phase(c,ctx){
  if(ctx.strategy==='discuss_first'&&ctx.round>1&&ctx.accessMode==='discussion')return '继续讨论与复核';
  if(ctx.strategy==='discuss_first')return ctx.round===1?'双方讨论方案':ctx.round===2?'执行方案与复核':'承接意见继续推进';
  if(ctx.route==='both')return ctx.round===1?'Codex 推进 · CodeBuddy 复核':'承接上一轮意见';
  return '单方处理';
 }
 function heading(c,m){
  const ctx=context(c,m);if(!ctx.id||!ctx.round)return '';
  const actors=ctx.route==='both'?['codex','codebuddy']:ctx.route&&names[ctx.route]?[ctx.route]:[...new Set((c.messages||[]).filter(x=>x.meta?.job_id===ctx.id&&Number(x.meta?.round)===ctx.round&&names[x.agent]).map(x=>x.agent))];
  return `<section class="discussion-round" data-round-key="${esc(ctx.id)}:${ctx.round}" aria-label="第 ${ctx.round} 轮${ctx.total?'，共 '+ctx.total+' 轮':''}"><div class="round-title"><strong>第 ${ctx.round} 轮${ctx.total?`<span> / 共 ${ctx.total} 轮</span>`:''}</strong><small>${esc(phase(c,ctx))}</small></div><div class="round-actors">${actors.map((actor,i)=>{const s=actorState(c,ctx.id,ctx.round,actor);return `${i?'<span class="round-arrow" aria-hidden="true">→</span>':''}<span class="round-actor ${actor} ${esc(s.state)}"><span class="round-state-dot" aria-hidden="true"></span><b>${names[actor]}</b><span>${s.label}</span></span>`;}).join('')}</div></section>`;
 }
 function badge(c,m){const ctx=context(c,m);if(!ctx.round)return '';return `<span class="message-round-badge">第 ${ctx.round}${ctx.total?' / '+ctx.total:''} 轮</span>`;}
 function render(c,messages,renderMessage){
  let previous=null;
  return messages.map(m=>{let title='';if(m.role==='user'&&!['answer','steer'].includes(m.meta?.delivery?.mode))previous=null;
   if(m.role==='assistant'&&m.meta?.job_id&&m.meta?.round){const key=m.meta.job_id+':'+m.meta.round;if(key!==previous)title=heading(c,m);previous=key;}
   return title+renderMessage(m);
  }).join('');
 }
 const api={context,actorState,heading,badge,render};if(typeof module==='object'&&module.exports)module.exports=api;else root.CollabDiscussion=api;
})(typeof window==='object'?window:this);
