(function(root){
 'use strict';
 function target(messages,message){
  if(message.role!=='user'||message.meta?.deleted||message.meta?.delivery?.mode!=='steer')return null;
  if(!['accepted','pending'].includes(message.meta.delivery.state))return null;
  const explicit=message.meta?.in_reply_to;
  if(explicit)return messages.find(m=>m.id===explicit&&m.role==='assistant'&&m.meta?.job_id===message.meta.job_id)||null;
  // Old records retain task and actor, but not an exact text span: preserve that limit.
  const before=messages.slice(0,messages.findIndex(m=>m.id===message.id));
  return before.findLast(m=>m.role==='assistant'&&!m.meta?.deleted&&m.meta?.job_id===message.meta.job_id&&(!message.meta.delivery.agent||m.agent===message.meta.delivery.agent))||null;
 }
 function forMessage(messages,message){return messages.filter(m=>target(messages,m)?.id===message.id);}
 function inlineIds(messages){return new Set(messages.filter(m=>target(messages,m)).map(m=>m.id));}
 function html(messages,message,renderText,avatar){
  const updates=forMessage(messages,message);if(!updates.length)return '';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  return `<section class="followup-thread" aria-label="这轮回复的中途补充">${updates.map(m=>`<div class="followup-message" data-followup-message="${esc(m.id)}"><div class="followup-heading">${avatar('user')}<strong>你的中途补充</strong><small>${m.meta.delivery.state==='pending'?'等待送达':'已送达本轮'}</small></div><div class="followup-body">${renderText(m.content||'')}</div></div>`).join('')}<div class="followup-reply-label">${message.status==='streaming'?'本轮继续回复将在下面显示':'以下是接收这些补充的本轮完整回复'}</div></section>`;
 }
 const api={target,forMessage,inlineIds,html};if(typeof module==='object'&&module.exports)module.exports=api;else root.CollabFollowup=api;
})(typeof window==='object'?window:this);
