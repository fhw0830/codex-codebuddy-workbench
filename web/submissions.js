(function(root){
 'use strict';
 function create(storage,uuid){
  const sending=new Set();
  const key=id=>'robot-collab:unconfirmed:'+id;
  function reserve(id,payload){
   const fingerprint=JSON.stringify({...payload,client_key:undefined,send_mode:undefined});
   let pending;try{pending=JSON.parse(storage.getItem(key(id))||'[]');}catch{pending=[];}
   if(!Array.isArray(pending))pending=pending?[pending]:[];
   const old=pending.find(item=>item.fingerprint===fingerprint);
   if(old)return {...old,retry:true};
   if(pending.length>=20)throw new Error('这条对话有过多未确认的发送，请先核对已有任务');
   const record={client_key:uuid(),fingerprint};
   // Failure to persist must stop submission, otherwise reload could duplicate it.
   storage.setItem(key(id),JSON.stringify([...pending,record]));return {...record,retry:false};
  }
  function clear(id,clientKey){
   if(!clientKey)return;
   let pending=JSON.parse(storage.getItem(key(id))||'[]');if(!Array.isArray(pending))pending=[pending];
   pending=pending.filter(item=>item.client_key!==clientKey);
   if(pending.length)storage.setItem(key(id),JSON.stringify(pending));else storage.removeItem(key(id));
  }
  return {reserve,clear,isSending:id=>sending.has(id),
   start(id){if(sending.has(id))return false;sending.add(id);return true;},finish:id=>sending.delete(id)};
 }
 function remaining(current,submitted){
  function subtract(values,sent){
   const counts=new Map();for(const item of sent||[]){const key=JSON.stringify(item);counts.set(key,(counts.get(key)||0)+1);}
   return (values||[]).filter(item=>{const key=JSON.stringify(item),count=counts.get(key)||0;if(count){counts.set(key,count-1);return false;}return true;});
  }
  return {...current,text:current.text===submitted.text?'':current.text,
   documents:subtract(current.documents,submitted.documents),uploads:subtract(current.uploads,submitted.uploads)};
 }
 const api={create,remaining};if(typeof module==='object'&&module.exports)module.exports=api;else root.CollabSubmissions=api;
})(typeof window==='object'?window:this);
