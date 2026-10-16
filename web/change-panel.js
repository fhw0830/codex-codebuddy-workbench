(function(root){
 'use strict';
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function collect(conversation,messageId,tools){
  const origin=(conversation.messages||[]).find(m=>m.id===messageId&&!m.meta?.deleted);
  if(!origin)return [];
  const messages=origin.meta?.job_id&&origin.meta?.round
   ?conversation.messages.filter(m=>m.role==='assistant'&&m.meta?.job_id===origin.meta.job_id&&m.meta?.round===origin.meta.round&&!m.meta?.deleted)
   :[origin];
  return messages.flatMap(message=>tools(message).flatMap(tool=>(tool.changes||[]).map((change,index)=>({key:message.id+':'+tool.id+':'+index,message,tool,change,index}))));
 }
 function summary(records,execution){
  return records.reduce((sum,r)=>{const n=execution.counts(r.change);sum.added+=n.added;sum.removed+=n.removed;sum.paths.add(r.change.path||'未记录路径');return sum;},{added:0,removed:0,paths:new Set()});
 }
 function pendingQuestions(conversation){
  const messages=new Set((conversation.messages||[]).filter(m=>m.role==='assistant'&&!m.meta?.deleted).map(m=>m.id));
  return (conversation.input_requests||[]).filter(q=>['pending','followup'].includes(q.state)&&messages.has(q.message_id)&&(!q.conversation_id||q.conversation_id===conversation.id));
 }
 function matchingFile(conversation,message,link,tools,localLinks){
  if(!message)return null;
  function canonical(value,base){
   const path=localLinks.path(value,base);if(!path)return null;
   const absolute=/^(?:[a-z]:\/|\/)/i.test(path);if(!absolute)return null;
   const parts=[];for(const part of path.split('/')){if(part==='.')continue;if(part==='..'){if(parts.length>1)parts.pop();}else parts.push(part);}
   const result=parts.join('/');return /^[a-z]:\//i.test(result)?result.toLowerCase():result;
  }
  const target=canonical(link,message.meta?.workdir||conversation.preferences?.workdir);
  if(!target)return null;
  return collect(conversation,message.id,tools).filter(r=>canonical(r.change.path,r.message.meta?.workdir||conversation.preferences?.workdir)===target).at(-1)||null;
 }
 function recordHTML(record,execution){
  const {change,tool,message,key}=record,n=execution.counts(change);
  const state=({completed:'工具报告已完成',success:'工具报告已完成',failed:'工具报告失败',cancelled:'工具已取消',running:'修改中',inProgress:'修改中'}[tool.status]||'结果待确认');
  const note=change.scope==='snippet'?'编辑片段 · 行号相对片段':change.scope==='submitted'?'提交内容预览 · 未保存修改前全文':'工具记录的文件行号';
  const rows=change.diff?`<div class="change-code-scroll" tabindex="0" aria-label="${esc(change.path||'文件')}的代码差异"><table class="change-code"><thead class="change-sr"><tr><th>原行号</th><th>新行号</th><th>代码</th></tr></thead><tbody>${execution.diffLines(change.diff).map(line=>`<tr class="change-line-${line.kind}"><td>${line.before??''}</td><td>${line.after??''}</td><td><code>${esc(line.text)}</code>${['add','remove','context'].includes(line.kind)?`<button class="change-line-comment" type="button" data-wb-path="${esc(change.path||'未记录路径')}" data-wb-line="${line.after||line.before}" data-wb-side="${line.kind==='remove'?'before':'after'}" data-wb-scope="${esc(change.scope||'file')}" aria-label="针对${line.kind==='remove'?'修改前':'修改后'}第 ${line.after||line.before} 行补充意见">补充</button>`:''}</td></tr>`).join('')}</tbody></table></div>`:`<pre class="change-preview">${esc(change.preview||'这条历史记录未保存差异正文，无法还原修改前后。')}</pre>`;
  return `<details class="change-record" open data-plan-step="change:${esc(key)}" data-change-record="${esc(key)}"><summary><span class="change-file-mark" aria-hidden="true">${esc((change.path||'file').split('.').at(-1).slice(0,5).toUpperCase())}</span><strong>${esc(change.path||'未记录路径')}</strong>${change.diff?`<span class="diff-added">+${n.added}</span><span class="diff-removed">−${n.removed}</span>`:'<span class="change-preview-tag">内容预览</span>'}</summary><div class="change-record-meta"><span>${esc(message.agent==='codex'?'Codex':message.agent==='codebuddy'?'CodeBuddy':message.agent)} · ${esc(state)}</span><button class="text-button" type="button" data-wb-locate="${esc(message.id)}">定位执行记录 ↗</button></div><p class="change-record-note">${esc(note)}${change.truncated?' · 已截断，仅显示保存片段':''}</p>${rows}</details>`;
 }
 function install({doc,conversation,execution,workbench,stable,toast}){
  const panel=doc.getElementById('change-panel'),body=doc.getElementById('change-panel-body'),shell=doc.querySelector('.app-shell');
  const fileSelect=doc.getElementById('change-file-filter'),heading=doc.getElementById('change-panel-title'),expand=doc.getElementById('change-panel-expand');
  const attention=doc.getElementById('change-panel-attention'),review=doc.getElementById('change-panel-review-question');
  let owner=null,source=null,records=[],filter='',trigger=null,signature='',drag=null;
  function close(restore=true){panel.hidden=true;shell.classList.remove('has-change-panel','change-panel-expanded');panel.classList.remove('expanded');expand.setAttribute('aria-pressed','false');expand.textContent='放大';owner=null;source=null;signature='';if(restore&&trigger?.isConnected)trigger.focus({preventScroll:true});}
  function render(preserve=false){
   const snapshot=preserve?stable.capture(body):null;
   const shown=filter?records.filter(r=>(r.change.path||'未记录路径')===filter):records;
   stable.render(body,shown.length?shown.map(r=>recordHTML(r,execution)).join(''):'<p class="change-empty">本轮没有保存文件差异。工具未提供的历史改动无法还原。</p>');
   if(snapshot)stable.restore(body,snapshot);else body.scrollTop=0;
   const stats=summary(records,execution);
   doc.getElementById('change-panel-count').innerHTML=`${stats.paths.size} 个文件 · ${records.length} 次操作 <span class="diff-added">+${stats.added}</span> <span class="diff-removed">−${stats.removed}</span>`;
   const options='<option value="">全部文件</option>'+[...stats.paths].map(path=>`<option value="${esc(path)}">${esc(path)}</option>`).join('');
   if(fileSelect.innerHTML!==options)fileSelect.innerHTML=options;
   fileSelect.value=filter;
  }
  function update(c){
   const pending=pendingQuestions(c);if(attention)attention.hidden=!pending.length;
   if(pending.length&&review){const label=`有 ${pending.length} 条提问待回答 · 返回问题`;if(review.textContent!==label)review.textContent=label;review.dataset.reviewQuestion=pending[0].id;}
   records=collect(c,source,workbench.tools);
   if(filter&&!records.some(r=>(r.change.path||'未记录路径')===filter))filter='';
   const message=c.messages.find(m=>m.id===source),round=message?.meta?.round;
   doc.getElementById('change-panel-source').textContent=(round?'第 '+round+' 轮':'当前回复')+' · '+(c.title||'协作对话');
   const next=JSON.stringify(records.map(r=>[r.key,r.tool.status,r.change]));
   if(next!==signature){signature=next;render(true);}
  }
  function open({messageId,path='',toolId=null,index=null,opener=null}){
   const c=conversation();if(!c)return;
   const isSame=owner===c.id&&source===messageId&&!panel.hidden;
   owner=c.id;source=messageId;trigger=opener||doc.activeElement;filter=path;
   records=collect(c,source,workbench.tools);signature='';panel.hidden=false;shell.classList.add('has-change-panel');update(c);render(isSame);
   const selected=records.find(r=>r.message.id===messageId&&r.tool.id===toolId&&r.index===index);
   const target=selected&&[...body.querySelectorAll('[data-change-record]')].find(el=>el.dataset.changeRecord===selected.key);
   if(target){target.open=true;body.scrollTop=target.offsetTop;}
   heading.focus({preventScroll:true});
  }
  function sync(c){
   if(panel.hidden)return;
   if(c.id!==owner){close(false);return;}
   if(!c.messages.some(m=>m.id===source&&!m.meta?.deleted)){close(false);toast('原始消息已移出当前对话，可从压缩原文查阅');return;}
   update(c);
  }
  doc.getElementById('change-panel-close').onclick=()=>close();
  if(review)review.onclick=()=>{
   const id=review.dataset.reviewQuestion;close(false);
   const target=[...doc.querySelectorAll('[data-question-card]')].find(el=>el.dataset.questionCard===id);
   if(!target){toast('问题位置已更新，请刷新当前对话后查看',true);return;}
   for(let parent=target.parentElement;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;
   target.scrollIntoView({block:'center',behavior:'auto'});target.querySelector('input,textarea,button')?.focus({preventScroll:true});
  };
  fileSelect.onchange=()=>{filter=fileSelect.value;render();};
  expand.onclick=()=>{const wide=panel.classList.toggle('expanded');shell.classList.toggle('change-panel-expanded',wide);expand.setAttribute('aria-pressed',String(wide));expand.textContent=wide?'还原宽度':'放大';};
  panel.addEventListener('click',event=>{if(event.target.closest('[data-wb-line],[data-wb-locate]')&&doc.documentElement.clientWidth<=760)close(false);});
  doc.addEventListener('keydown',event=>{
   if(panel.hidden||doc.querySelector('dialog[open]'))return;
   if(event.key==='Escape'){event.preventDefault();close();}
   if(event.key==='Tab'&&doc.documentElement.clientWidth<=760){
    const items=[...panel.querySelectorAll('button,select,summary,[tabindex]:not([tabindex="-1"])')].filter(el=>!el.disabled&&el.getClientRects().length);
    const first=items[0],last=items.at(-1),current=doc.activeElement;
    if(!items.includes(current)||event.shiftKey&&current===first||!event.shiftKey&&current===last){event.preventDefault();(event.shiftKey?last:first)?.focus();}
   }
  });
  const handle=doc.getElementById('change-panel-resize');
  function width(value){const max=Math.max(360,doc.documentElement.clientWidth-620),n=Math.max(360,Math.min(max,value));doc.documentElement.style.setProperty('--changes-width',`clamp(360px,${n}px,calc(100vw - 620px))`);handle.setAttribute('aria-valuenow',String(Math.round(n)));handle.setAttribute('aria-valuemax',String(max));}
  handle.onpointerdown=event=>{if(event.button!==0)return;drag={x:event.clientX,width:panel.getBoundingClientRect().width};handle.setPointerCapture(event.pointerId);event.preventDefault();};
  handle.onpointermove=event=>{if(drag)width(drag.width+drag.x-event.clientX);};
  handle.onpointerup=handle.onpointercancel=()=>{drag=null;};
  handle.onkeydown=event=>{if(!['ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();width(panel.getBoundingClientRect().width+(event.key==='ArrowLeft'?40:-40));};
  return {open,close,sync};
 }
 const api={collect,summary,pendingQuestions,matchingFile,recordHTML,install};
 if(typeof module==='object'&&module.exports)module.exports=api;else root.CollabChanges=api;
})(typeof window==='object'?window:this);
