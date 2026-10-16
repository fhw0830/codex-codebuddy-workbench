(function(root){
  'use strict';
  function applyDelta(message,payload){
    if(!message||message.id!==payload.id||message.conversation_id!==payload.conversation_id||message.status!=='streaming')return {kind:'ignore'};
    const text=message.content||'',base=payload.base_length,delta=payload.delta;
    if(!Number.isInteger(base)||typeof delta!=='string')return {kind:'reload'};
    if(text.length===base)return {kind:'update',content:text+delta};
    if(text.length>=base+delta.length&&text.slice(base,base+delta.length)===delta)return {kind:'ignore'};
    return {kind:'reload'};
  }
  function mergeMessages(current,next){
    const existing=new Map((current||[]).map(m=>[m.id,m]));
    return next.map(m=>{const old=existing.get(m.id);return old?.status==='streaming'&&m.status==='streaming'&&(old.content||'').length>(m.content||'').length?{...m,content:old.content}:m;});
  }
  const api={applyDelta,mergeMessages};
  if(typeof module==='object'&&module.exports)module.exports=api;else root.CollabStream=api;
})(typeof window==='object'?window:this);
