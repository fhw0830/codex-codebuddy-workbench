(function(root){
 'use strict';
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const names={codex:'Codex',codebuddy:'CodeBuddy'};
 function tools(m){const result=new Map((m.meta?.tool_events||[]).map((t,i)=>[t.id||i,t]));for(const e of m.meta?.activity||[])if(e.type==='tool')result.set(e.tool.id,e.tool);return [...result.values()];}
 function handoff(c,m){
  const next=(c.messages||[]).filter(x=>x.meta?.collaboration?.source_message_id===m.id&&!x.meta?.deleted).at(-1),source=m.meta?.collaboration?.source_message_id;
  if(!next&&!source)return '';
  const peer=next?names[next.agent]:names[m.meta.collaboration.source_agent];
  const state=next?({streaming:'正在复核',completed:'复核回复完成',failed:'复核中断',interrupted:'复核已停止'}[next.status]||'待接续'):'本轮承接上一方交接';
  const progress=next?.meta?.plan||[];
  return `<details class="wb-handoff" id="wb-handoff-${esc(m.id)}"><summary><span>${next?'交给 '+esc(peer):'承接 '+esc(peer||'上一方')}</span><span>${esc(state)}</span></summary><div class="wb-handoff-body"><p>来源已绑定到实际消息${m.meta?.collaboration?.source_sha256?'，并保存原文校验值':''}。回复完成与任务验收分别记录。</p>${progress.length?`<ol>${progress.map(s=>`<li><span>${esc(s.step)}</span><small>${s.status==='completed'?'已完成':s.status==='in_progress'?'进行中':'待处理'}</small></li>`).join('')}</ol>`:''}<button type="button" class="text-button" data-wb-locate="${esc(next?.id||source)}">${next?'查看复核回复':'查看上一方交接'} ↗</button></div></details>`;
 }
 function context(c,m){
  const r=m.meta?.context_manifest;
  const questions=new Set((c.input_requests||[]).filter(q=>q.message_id===m.id).map(q=>q.id));
  const supplements=(c.messages||[]).filter(x=>(x.meta?.in_reply_to===m.id||questions.has(x.meta?.answer_to))&&x.meta?.delivery?.state==='accepted'&&!x.meta?.deleted);
  if(!r)return '<p class="wb-muted">这条历史回复没有保存输入快照，无法补推断模型收到的内容。</p>';
  const refs=r.references||[],known=new Map((c.messages||[]).map(x=>[x.id,x]));
  return `<p class="wb-muted">记录于模型调用前。中途补充以送达回执为准，不含隐藏思考。</p><dl class="wb-facts"><div><dt>本轮输入</dt><dd>${r.prompt_chars.toLocaleString()} 字符 · 约 ${r.estimated_tokens.toLocaleString()} Tokens（估算）</dd></div><div><dt>历史消息</dt><dd>${r.history_message_ids.length} 条实际进入本轮输入</dd></div><div><dt>旧对话摘要</dt><dd>${r.summary_id?'已包含 · '+esc(r.summary_id.slice(0,8)):'本轮没有引用摘要'}</dd></div><div><dt>交接来源</dt><dd>${r.handoff_source_message_id?`<button class="text-button" data-wb-locate="${esc(r.handoff_source_message_id)}">查看实际交接</button>`:'本轮无上一方交接'}</dd></div></dl>${supplements.length?`<div class="wb-subsection">本轮已送达的中途补充${supplements.map(s=>`<p>${esc(s.content)}</p>`).join('')}</div>`:''}${refs.length?`<ul class="wb-reference-receipts">${refs.map(f=>`<li><strong>${esc(f.name)}</strong><small>${f.kind==='image'?(f.vision_sent?'图片已通过视觉输入传入':'视觉内容未传入此模型'):f.start!=null?`片段 ${esc(f.start)}–${esc(f.end)} / ${esc(f.total_chars??'未知')} 字符`:`本轮附带 ${f.included_chars} 字符`}${f.extraction_note?' · '+esc(f.extraction_note):''}</small></li>`).join('')}</ul>`:''}<details class="wb-subdetails"><summary>查看实际历史来源与校验值</summary><ul>${r.history_message_ids.map(id=>`<li>${known.has(id)?`<button class="text-button" data-wb-locate="${esc(id)}">${esc(names[known.get(id).agent]||'你')} · ${esc(known.get(id).content.slice(0,42))}</button>`:esc(id)+' · 原文已归档'}</li>`).join('')}</ul><code>${esc(r.prompt_sha256)}</code></details>`;
 }
 function changes(c,m,execution){
  const messages=m.meta?.job_id&&m.meta?.round?c.messages.filter(x=>x.role==='assistant'&&x.meta?.job_id===m.meta?.job_id&&x.meta?.round===m.meta?.round&&!x.meta?.deleted):[m];
  const records=messages.flatMap(x=>tools(x).filter(t=>t.changes?.length).map(t=>({message:x,tool:t})));
  const files=new Map();
  for(const record of records)for(const change of record.tool.changes){const path=change.path||'未记录路径';if(!files.has(path))files.set(path,[]);files.get(path).push({...record,change});}
  if(!files.size)return '<p class="wb-muted">本轮没有保存文件差异；工具未提供的改动不会推测补齐。</p>';
  return `<button class="secondary-button wb-open-changes" type="button" data-open-round-changes="${esc(m.id)}">在侧边查看本轮改动 ↗</button><p class="wb-muted">本轮共 ${files.size} 个文件。增删为已保存操作累计，可能包含重复编辑，不代表最终 Git 净差异。</p>${[...files].map(([path,rows])=>{
   const count=rows.reduce((a,r)=>{const n=execution.counts(r.change);return {added:a.added+n.added,removed:a.removed+n.removed};},{added:0,removed:0}),hasDiff=rows.some(r=>r.change.diff);
   return `<details class="wb-file" data-plan-step="wb-file:${esc(m.id+path)}"><summary><span>${esc(path)}</span><small>${rows.length} 次操作${hasDiff?` · <b class="diff-added">+${count.added}</b> <b class="diff-removed">−${count.removed}</b>`:' · 无完整差异'}</small></summary><button class="text-button" type="button" data-open-round-changes="${esc(m.id)}" data-change-path="${esc(path)}">在侧边查看此文件 ↗</button>${rows.map(r=>`<div class="wb-patch"><p class="wb-muted">${esc(names[r.message.agent])} · ${r.tool.status==='completed'?'工具报告已完成':r.tool.status==='failed'?'工具报告失败':'结果待确认'} · ${r.change.scope==='snippet'?'行号相对编辑片段':'按工具原记录'}</p>${r.change.diff?`<div class="diff-scroll"><table class="diff-table"><tbody>${execution.diffLines(r.change.diff).map(line=>`<tr class="diff-${line.kind}"><td>${line.before??''}</td><td>${line.after??''}</td><td><code>${esc(line.text)}</code>${['add','remove','context'].includes(line.kind)?`<button type="button" class="wb-line-feedback" data-wb-path="${esc(path)}" data-wb-line="${line.after||line.before}" data-wb-scope="${esc(r.change.scope||'file')}" aria-label="针对 ${esc(path)} ${line.after||line.before} 行补充意见">补充</button>`:''}</td></tr>`).join('')}</tbody></table></div>`:`<pre>${esc(r.change.preview||'未提供差异正文')}</pre>`}<button class="text-button" data-wb-locate="${esc(r.message.id)}">定位原始执行记录 ↗</button></div>`).join('')}</details>`;
  }).join('')}`;
 }
 function runtime(r,m,ui){
  const phase={connecting:'等待模型连接',analysis:'模型正在分析',planning:'更新执行计划',tools:'执行工具',reply:'正在输出回复',context:'整理上下文',waiting_input:'等待你回答'}[r?.phase]||'等待新进展';
  if(!r||r.message_id!==m?.id)return `<p class="wb-muted">${m?.status==='streaming'?'正在读取后台运行状态；历史记录不会被当成当前进程。':'这轮执行已结束，运行信息以保存的记录为准。'}</p>`;
  return `<dl class="wb-facts"><div><dt>后台进程</dt><dd>${r.process_alive===true?'仍在运行':r.process_alive===false?'进程已退出':'未提供进程状态'}</dd></div><div><dt>当前阶段</dt><dd>${r.waiting_for_resource?'等待同一资源释放':esc(phase)}</dd></div><div><dt>最近进展</dt><dd>${r.last_event_at?`<span data-wb-age="${esc(r.last_event_at)}">${esc(r.last_event_at)}</span>`:'未记录时间'}</dd></div></dl>${r.active_tools?.length?`<ul>${r.active_tools.map(t=>`<li>${esc(t.name||'工具')} · ${ui.measuredTime(t,!!t.started_at)}</li>`).join('')}</ul>`:'<p class="wb-muted">当前没有报告执行中的工具；暂无输出不等于任务已停止。</p>'}<p class="wb-muted">后台采样：${esc(r.checked_at)}；本栏每 5 秒同步。</p>`;
 }
 function extras(c,m,execution,ui,enabled){
  if(m.role!=='assistant')return '';
  const failed=['failed','interrupted'].includes(m.status);
  const continuation=(c.messages||[]).find(x=>x.role==='user'&&x.meta?.resume_checkpoint?.source_message_id===m.id);
  return `${handoff(c,m)}<div class="wb-inspectors">${failed&&enabled?continuation?`<button class="text-button" data-wb-locate="${esc(continuation.id)}">已续接 · 查看任务</button>`:`<button class="wb-resume text-button" data-wb-resume="${esc(m.id)}">从未完成处继续</button>`:''}<details id="wb-context-${esc(m.id)}" name="wb-inspect-${esc(m.id)}"><summary>本轮上下文</summary><div class="wb-inspector-body">${context(c,m)}</div></details><details id="wb-changes-${esc(m.id)}" name="wb-inspect-${esc(m.id)}"><summary>本轮改动</summary><div class="wb-inspector-body">${changes(c,m,execution)}</div></details>${m.status==='streaming'?`<details id="wb-runtime-${esc(m.id)}" name="wb-inspect-${esc(m.id)}"><summary>运行情况</summary><div class="wb-inspector-body" data-wb-runtime="${esc(m.id)}">${runtime(c.runtime,m,ui)}</div></details>`:''}</div>`;
 }
 function updateAges(doc){for(const el of doc.querySelectorAll('[data-wb-age]')){const age=Math.max(0,Math.floor((Date.now()-Date.parse(el.dataset.wbAge))/1000));el.textContent=Number.isFinite(age)?(age<60?age+' 秒前':Math.floor(age/60)+' 分 '+age%60+' 秒前'):'时间未记录';}}
 function install(options){
  const {doc,api,conversation,refresh,toast,ui,stable,saveDraft}=options;
  doc.addEventListener('click',async event=>{
   const resume=event.target.closest('[data-wb-resume]'),locate=event.target.closest('[data-wb-locate]'),feedback=event.target.closest('[data-wb-line]');
   try{
    if(resume){resume.disabled=true;await api('/api/resume',{conversation_id:conversation().id,message_id:resume.dataset.wbResume});await refresh();toast('已从原任务检查点续接，先核验已有执行结果');}
    if(locate){const target=doc.querySelector(`[data-message="${CSS.escape(locate.dataset.wbLocate)}"]`);if(target)target.scrollIntoView({block:'start',behavior:'auto'});else toast('原消息已归档，可从压缩原文查阅');}
    if(feedback){const input=doc.getElementById('message-input');input.value+=(input.value?'\n':'')+`针对 ${feedback.dataset.wbPath} 第 ${feedback.dataset.wbLine} 行${feedback.dataset.wbSide==='before'?'（修改前行号）':''}${feedback.dataset.wbScope==='snippet'?'（编辑片段相对行号）':''}：`;input.focus();input.dispatchEvent(new Event('input',{bubbles:true}));saveDraft();toast('已放入输入框，补充意见后发送');}
   }catch(error){toast(error.message,true);}finally{if(resume?.isConnected)resume.disabled=false;}
  });
  doc.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();const sidebar=doc.getElementById('sidebar');sidebar?.classList.add('open');const input=doc.getElementById('conversation-search');input.focus();input.select();}});
  let pending=false;
  const poll=async()=>{const c=conversation();if(pending||doc.hidden||!c?.id||!['running','waiting_input'].includes(c.job?.status))return;pending=true;const id=c.id;try{const data=await api('/api/runtime?conversation_id='+encodeURIComponent(id));const current=conversation();if(current?.id!==id)return;current.runtime=data;for(const el of doc.querySelectorAll('[data-wb-runtime]')){const m=current.messages.find(x=>x.id===el.dataset.wbRuntime);stable.render(el,runtime(data,m,ui));}updateAges(doc);}catch{}finally{pending=false;}};
  setInterval(poll,5000);setInterval(()=>updateAges(doc),1000);doc.addEventListener('toggle',e=>{if(e.target.matches?.('[id^="wb-runtime-"]')&&e.target.open)void poll();if(e.target.open&&e.target.parentElement?.classList.contains('wb-inspectors'))requestAnimationFrame(()=>{if(e.target.isConnected&&e.target.open)e.target.scrollIntoView({block:'nearest',behavior:'auto'});});},true);
 }
 const api={tools,handoff,context,changes,runtime,extras,install};if(typeof module==='object'&&module.exports)module.exports=api;else root.CollabWorkbench=api;
})(typeof window==='object'?window:this);
