(function(root){
 'use strict';
 const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function proseQuestion(text){const lines=[];let fence=null;for(const line of text.split('\n')){const marker=line.match(/^\s*(`{3,}|~{3,})/);if(marker){const token=marker[1];if(fence===null)fence=token;else if(token[0]===fence[0]&&token.length>=fence.length)fence=null;continue;}if(fence!==null||/^\s*>/.test(line))continue;lines.push(line);}for(const p of lines.join('\n').split('\n\n').slice(-12).reverse()){if(p.length<1001&&/[？?]/.test(p)&&/请确认|请告诉|请提供|你希望|你要|什么型号|是否|能否|是.*吗|需要你/.test(p))return p.trim();}return null;}
 function answersFor(request,messages){return messages.filter(m=>m.role==='user'&&(m.meta?.answer_to===request.id||m.id===request.user_message_id));}
 function inlineAnswerIds(messages,requests){
  const sources=new Set(messages.filter(m=>m.role==='assistant').map(m=>m.id)),ids=new Set();
  for(const r of requests)if(sources.has(r.message_id))for(const m of answersFor(r,messages))ids.add(m.id);
  return ids;
 }
 function answerHTML(request,messages){
  const linked=answersFor(request,messages),values=request.answers||{};
  if(!linked.length&&!Object.keys(values).length)return '';
  const content=Object.keys(values).length?request.questions.map(q=>`<div class="answer-part"><small>${esc(q.question)}</small><p>${esc((values[q.id]||[]).join('；'))}</p></div>`).join(''):linked.map(m=>`<p>${esc(m.content)}</p>`).join('');
  const state=linked.some(m=>m.meta?.delivery?.state==='pending')?'正在送达':request.state==='answered'?'已送达':'已提交';
  return `<div class="question-answer" data-answer-message="${esc(linked[0]?.id||request.id)}"><div class="answer-heading"><span class="answer-avatar" aria-hidden="true">你</span><strong>你的回答</strong><small>${state}</small></div>${content}</div>`;
 }
 function captureDrafts(container){
  const snapshots=new Map(),active=container.ownerDocument.activeElement;
  for(const form of container.querySelectorAll('[data-answer-question]')){
   const parts=new Map();
   for(const part of form.querySelectorAll('[data-question-part]')){
    const field=part.querySelector('[data-free-answer]');
    parts.set(part.dataset.questionPart,{question:part.querySelector('legend')?.textContent||'',text:field?.value||'',selected:[...part.querySelectorAll('input:checked')].map(el=>el.value),
     focused:part.contains(active)?active:null,start:field?.selectionStart,end:field?.selectionEnd});
   }
   snapshots.set(form.dataset.answerQuestion,{source:form.dataset.sourceMessage,parts});
  }
  return snapshots;
 }
 function restoreDrafts(container,snapshots){
  for(const form of container.querySelectorAll('[data-answer-question]')){
   const saved=snapshots.get(form.dataset.answerQuestion);if(!saved||saved.source!==form.dataset.sourceMessage)continue;
   for(const part of form.querySelectorAll('[data-question-part]')){
    const value=saved.parts.get(part.dataset.questionPart);if(!value||value.question!==(part.querySelector('legend')?.textContent||''))continue;
    const field=part.querySelector('[data-free-answer]');if(field&&field.value!==value.text)field.value=value.text;
    const options=[...part.querySelectorAll('input')];for(const option of options)option.checked=value.selected.includes(option.value);
    if(value.focused&&!value.focused.isConnected){
     const target=value.focused.matches('[data-free-answer]')?field:options.find(el=>el.value===value.focused.value);
     target?.focus({preventScroll:true});if(field&&target===field&&typeof value.start==='number')field.setSelectionRange(value.start,value.end);
    }
   }
  }
 }
 function html(message,requests=[],answered={},messages=[],options={}){
  if(message.role!=='assistant')return '';
  let items=requests.filter(r=>r.message_id===message.id);
  const prose=options.allowProse===false?null:proseQuestion(message.content||'');
  if(!items.length&&prose)items=[{id:'text-'+message.id,message_id:message.id,state:answered[message.id]===prose?'answered':'followup',transport:'text',questions:[{id:'text',question:prose,options:[]}]}];
  return items.map(r=>{
   const terminal=['answered','cancelled','submitted'].includes(r.state);
   return `<section class="question-card" data-question-card="${esc(r.id)}"><div class="question-heading"><strong>${['pending','followup'].includes(r.state)&&r.blocking?'等待你回答':r.state==='answered'?'答案已提交':r.state==='submitted'?'答案正在送达':r.state==='cancelled'?'原任务已停止':'回复这个问题'}</strong><small>${r.transport==='text'?'文字提问':esc(message.agent)}</small></div>${terminal?`<div class="asked-questions">${r.questions.map(q=>`<p>${esc(q.question)}</p>`).join('')}</div><p class="question-receipt">${r.state==='answered'?'已保留你的答案。':r.state==='submitted'?'正在回传，勿重复提交。':'如需继续，请在输入框明确发起。'}</p>`:`<form data-answer-question="${esc(r.id)}" data-source-message="${esc(message.id)}">${r.questions.map(q=>`<fieldset data-question-part="${esc(q.id)}"><legend>${esc(q.question)}</legend>${(q.options||[]).map(o=>`<label class="question-option"><input type="${q.multi_select?'checkbox':'radio'}" name="${esc(r.id+q.id)}" value="${esc(o.label)}"><span><strong>${esc(o.label)}</strong>${o.description?`<small>${esc(o.description)}</small>`:''}</span></label>`).join('')}<textarea data-free-answer rows="2" maxlength="4000" aria-label="${esc(q.question)} · 自己的答案" placeholder="${q.options?.length?'也可以填写自己的答案':'在这里填写答案'}"></textarea></fieldset>`).join('')}<div class="question-actions"><small>${r.state==='followup'?'问题会保留，等你实际回答后续接原任务。':'提交后继续当前任务，不会默认选择。'}</small><button type="submit" class="small-button">提交答案</button></div></form>`}${answerHTML(r,messages)}</section>`;
  }).join('');
 }
 root.CollabUserInput={html,proseQuestion,inlineAnswerIds,answersFor,captureDrafts,restoreDrafts,discussionFirst:text=>/(?:(?:第一轮|第1轮|首轮).*?(?:讨论|评审)|(?:先)?(?:讨论|评审)[一1]轮).*?(?:第二轮|第2轮|次轮).*?(?:操作|执行|动手|修改|开始做)/s.test(text)};
 if(typeof module!=='undefined'&&module.exports)module.exports=root.CollabUserInput;
})(typeof globalThis!=='undefined'?globalThis:this);
