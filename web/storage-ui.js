(function(root){
 'use strict';
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const bytes=value=>{let n=Number(value)||0;for(const unit of ['B','KB','MB','GB']){if(n<1024||unit==='GB')return n.toFixed(unit==='B'?0:1)+' '+unit;n/=1024;}};
 function draftUploads(storage){
  const found=new Set();
  for(let i=0;i<storage.length;i++){
   const key=storage.key(i);if(!key?.startsWith('robot-collab:draft:'))continue;
   let draft;try{draft=JSON.parse(storage.getItem(key)||'{}');}catch{throw new Error('有草稿记录无法读取，请先导出或处理该草稿后再清理');}
   for(const ref of draft.uploads||[])if(/^[a-f0-9]{32}$/.test(ref.upload_id||''))found.add(ref.upload_id);
  }
  return [...found];
 }
 function rows(items,kind){
  if(!items?.length)return '<p class="storage-empty">暂无项目</p>';
  return `<label class="storage-select-all"><input type="checkbox" data-storage-all="${kind}">全选本组（${items.length}项）</label><div class="storage-list">${items.map(item=>`<label class="storage-row"><input type="checkbox" data-storage-kind="${kind}" value="${esc(item.id)}"><span><strong>${esc(item.title||item.name||item.relative_path)}</strong><small>${esc(item.relative_path||item.updated||item.created||'')}${item.messages!=null?' · '+Number(item.messages)+' 条消息':''}</small></span>${item.bytes!=null?`<b>${bytes(item.bytes)}</b>`:''}</label>`).join('')}</div>`;
 }
 function install({doc,api,onChanged,toast,storage=root.localStorage}){
  const dialog=doc.getElementById('storage-dialog'),content=doc.getElementById('storage-content'),status=doc.getElementById('storage-status');
  let view=null,tab='garbage',working=false,epoch=0;
  function confirmAction(question,danger){
   const box=doc.getElementById('storage-confirm-dialog'),approve=doc.getElementById('storage-confirm-approve');
   doc.getElementById('storage-confirm-text').textContent=question;
   approve.textContent=danger?'确认永久删除':'确认处理';approve.classList.toggle('storage-danger',danger);
   return new Promise(resolve=>{
    box.onclose=()=>resolve(box.returnValue==='confirmed');
    box.returnValue='';box.showModal();doc.getElementById('storage-confirm-cancel').focus();
   });
  }
  const selected=kind=>[...content.querySelectorAll(`input[data-storage-kind="${kind}"]:checked`)].map(el=>el.value);
  const names=kind=>[...content.querySelectorAll(`input[data-storage-kind="${kind}"]:checked`)].map(el=>el.closest('label').querySelector('strong').textContent);
  function buttons(){
   for(const button of dialog.querySelectorAll('[data-storage-action]')){
    const kind=button.dataset.storageGroup;
    const count=kind?selected(kind).length:1;
    button.disabled=working||!!view?.busy||count<1||count>200;
   }
   doc.getElementById('storage-refresh').disabled=working;
  }
  function render(){
   if(!view)return;
   const disabled=view.busy?'disabled':'';
   content.innerHTML=`<p class="storage-status-note">${view.busy?'有任务执行、排队或等待回答，目前仅可查看。':'每次最多选择200项。永久删除与垃圾清理都需要你再次确认。'}</p>
    <div class="storage-panels">
    <section data-storage-panel="garbage" ${tab==='garbage'?'':'hidden'}><p>预计可清理 <strong>${bytes(view.estimated_bytes)}</strong> · ${view.garbage.length} 项。仅列出超过${view.grace_days}天的未引用附件和未登记压缩原文。</p>${rows(view.garbage,'garbage')}<div class="storage-actions"><button class="secondary-button" data-storage-action="cleanup" data-storage-group="garbage" ${disabled}>清理选中垃圾</button></div></section>
    <section data-storage-panel="conversations" ${tab==='conversations'?'':'hidden'}><p>归档只是隐藏；移入回收区后仍可恢复。含待回答任务的对话不能删除。</p>${rows(view.archived,'conversations')}<div class="storage-actions"><button class="secondary-button" data-storage-action="trash_conversations" data-storage-group="conversations" ${disabled}>移入回收区</button></div></section>
    <section data-storage-panel="files" ${tab==='files'?'':'hidden'}><p>这里只管理网页生成的每日对话和交接文件。其他说明、证据、源码与配置不参与清理。</p>${rows(view.archive_files,'files')}<div class="storage-actions"><button class="secondary-button" data-storage-action="trash_files" data-storage-group="files" ${disabled}>移入文件回收区</button></div></section>
    <section data-storage-panel="trash" ${tab==='trash'?'':'hidden'}><h3>回收的对话</h3>${rows(view.trash,'trash-conversations')}<div class="storage-actions"><button class="secondary-button" data-storage-action="restore_conversations" data-storage-group="trash-conversations" ${disabled}>恢复到归档列表</button><button class="secondary-button storage-danger" data-storage-action="purge_conversations" data-storage-group="trash-conversations" ${disabled}>永久删除选中对话</button></div><p class="section-description">永久删除对话会同时删除其消息、任务、压缩原文与相关事件。共用附件和每日导出文件单独管理。</p><h3>回收的文件</h3>${rows(view.trash_files,'trash-files')}<div class="storage-actions"><button class="secondary-button" data-storage-action="restore_files" data-storage-group="trash-files" ${disabled}>恢复文件</button><button class="secondary-button storage-danger" data-storage-action="purge_files" data-storage-group="trash-files" ${disabled}>永久删除选中文件</button></div><div class="storage-database"><span>数据库及写入日志目前 ${bytes(view.database_bytes)}。删除记录后可整理数据库以归还空闲页，不会删除现有对话。</span><button class="secondary-button" data-storage-action="compact_database" ${disabled}>整理数据库</button></div></section>
    </div><details class="storage-protection"><summary>哪些内容会受到保护？</summary>${view.notes.map(note=>`<p>${esc(note)}</p>`).join('')}</details>`;
   for(const button of dialog.querySelectorAll('[data-storage-tab]'))button.setAttribute('aria-selected',String(button.dataset.storageTab===tab));
   buttons();
  }
  async function inspect(){
   if(working)return;working=true;buttons();const ticket=++epoch;status.textContent='正在核对引用与文件范围…';
   try{const next=await api('/api/storage',{action:'inspect',protected_upload_ids:draftUploads(storage)});if(ticket!==epoch)return;view=next;render();status.textContent='已更新预览，尚未清理或删除任何项目。';}
   catch(error){status.textContent=error.message;status.setAttribute('role','alert');}
   finally{working=false;buttons();}
  }
  async function open(initial='garbage'){tab=initial;if(!dialog.open)dialog.showModal();await inspect();}
  for(const id of ['open-storage','open-storage-side'])doc.getElementById(id)?.addEventListener('click',()=>open(id==='open-storage-side'?'conversations':'garbage'));
  doc.getElementById('close-storage').onclick=()=>dialog.close();
  doc.getElementById('storage-refresh').onclick=inspect;
  dialog.addEventListener('change',event=>{const all=event.target.dataset.storageAll;if(all)for(const checkbox of content.querySelectorAll(`input[data-storage-kind="${all}"]`))checkbox.checked=event.target.checked;buttons();});
  dialog.addEventListener('click',async event=>{
   const picker=event.target.closest('[data-storage-tab]');
   if(picker){tab=picker.dataset.storageTab;for(const panel of content.querySelectorAll('[data-storage-panel]'))panel.hidden=panel.dataset.storagePanel!==tab;for(const b of dialog.querySelectorAll('[data-storage-tab]'))b.setAttribute('aria-selected',String(b===picker));return;}
   const button=event.target.closest('[data-storage-action]');if(!button||working||button.disabled)return;
   const action=button.dataset.storageAction,kind=button.dataset.storageGroup,ids=kind?selected(kind):[];
   const titles=kind?names(kind):[];
   const summary=titles.slice(0,8).map(name=>'• '+name).join('\n')+(titles.length>8?'\n另有 '+(titles.length-8)+' 项':'');
   const irreversible=['cleanup','purge_conversations','purge_files'].includes(action);
   const question=action==='compact_database'?'整理数据库空闲页？不会删除现有对话，整理期间请保持网页开启。':`${irreversible?'永久删除':'处理'}以下 ${ids.length} 项？${irreversible?'此操作无法恢复。':'移入回收区后可恢复。'}\n\n${summary}`;
   working=true;buttons();
   if(action.startsWith('restore')||await confirmAction(question,irreversible)){
    status.textContent='正在处理…';
    try{
     const body={action,ids,protected_upload_ids:draftUploads(storage)};
     if(action==='cleanup'){body.plan_token=view.plan_token;body.confirmation='清理选中垃圾';}
     if(action.startsWith('purge'))body.confirmation='永久删除';
     if(action==='compact_database')body.confirmation='整理数据库';
     const result=await api('/api/storage',body);
     if(onChanged)await onChanged({action,conversation_ids:result.conversation_ids||[]});
     const message=result.message||(result.ok?'操作完成':'部分项目未完成，请重新扫描');
     toast(message,!result.ok);status.textContent=message;
     working=false;await inspect();status.textContent=message;
    }catch(error){working=false;await inspect();status.textContent=error.message;status.setAttribute('role','alert');toast(error.message,true);}
    finally{working=false;buttons();}
   }else{working=false;buttons();}
  });
  return {open};
 }
 const api={bytes,draftUploads,rows,install};
 if(typeof module==='object'&&module.exports)module.exports=api;else root.CollabStorage=api;
})(typeof window==='object'?window:globalThis);
