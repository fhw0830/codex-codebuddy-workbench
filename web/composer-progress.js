(function(root){
 'use strict';
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const phases={connecting:'正在连接模型',analysis:'正在分析问题',planning:'正在更新步骤',tools:'正在执行工具',reply:'正在生成回复',context:'正在整理上下文'};
 function select(c){
  if(!c?.job||c.job.status==='queued')return null;
  const messages=(c.messages||[]).filter(m=>m.role==='assistant'&&!m.meta?.deleted&&m.meta?.job_id===c.job.id);
  return messages.findLast(m=>m.status==='streaming')||messages.at(-1)||null;
 }
 function shortStep(value){const text=String(value||'未命名步骤').trim(),clause=text.split(/[，,；;。\n]/)[0]||text;return Array.from(clause).length>16?Array.from(clause).slice(0,16).join('')+'…':clause;}
 function html(c,ui,discussion){
  if(!['queued','running','waiting_input'].includes(c?.job?.status))return '';
  const m=select(c),job=c.job,plan=Array.isArray(m?.meta?.plan)?m.meta.plan:[];
  const waiting=job.status==='waiting_input'||(c.input_requests||[]).some(q=>q.message_id===m?.id&&q.blocking&&['pending','followup','submitted'].includes(q.state));
  const resource=ui.resourceLabel(m),done=plan.filter(s=>s.status==='completed').length,current=plan.find(s=>s.status==='in_progress');
  const ctx=m?discussion.context(c,m):{},owner=m?({codex:'Codex',codebuddy:'CodeBuddy'}[m.agent]||m.agent):job.route==='both'?'Codex → CodeBuddy':job.route==='codebuddy'?'CodeBuddy':'Codex';
  const status=c.compression?.state==='running'?'正在自动整理旧对话':waiting?'等待你回答':resource||(!m?job.status==='queued'?'排队等待':'等待后台开始':m.status==='failed'?'本轮失败':m.status==='interrupted'?'本轮已停止':m.status==='completed'?'正在交接下一方':phases[m.meta?.progress?.phase]||'正在处理');
  const label=step=>step.status==='completed'?'已完成':step.status==='in_progress'?waiting?'等待回答':resource?'等待资源':m.status==='streaming'?'进行中':'结束时进行中':'待处理';
  const timingMessage=waiting||resource?{...m,status:'waiting'}:m;
  const stepClock=current?ui.stepTime(current,timingMessage).replace(/^ · /,''):'';
  const clock=current?`<small>本步用时</small><strong>${stepClock||'未记录用时'}</strong>`:`<small>本任务用时</small>${ui.activeTiming(c)}`;
  const round=ctx.round?`第 ${ctx.round}${ctx.total?' / '+ctx.total:''} 轮`:'本次任务';
  const header=`<span class="cp-owner"><strong>${esc(owner)}</strong><small>${esc(round)}</small><small>${plan.length?`已完成 ${done} / ${plan.length} 步`:esc(status)}</small></span>`;
  const stations=plan.length?`<span class="cp-stations" role="list" aria-label="实际任务步骤" tabindex="0" style="--cp-columns:${plan.length}">${plan.map((step,index)=>{
   const state=['completed','in_progress'].includes(step.status)?step.status:'pending';
   return `<span class="cp-station ${state}${index===plan.length-1?' cp-row-end':''}" role="listitem" data-plan-step="${esc(step.step)}"${state==='in_progress'?' aria-current="step"':''} title="${esc(step.step)} · ${esc(label(step))}"><span class="cp-node" aria-hidden="true">${index+1}</span><span class="cp-step-name">${esc(shortStep(step.step))}</span><small class="cp-step-status">${esc(label(step))}</small></span>`;
  }).join('')}</span>`:`<span class="cp-no-plan">${!waiting&&job.status!=='queued'?'<span class="generation-spinner" aria-hidden="true"></span>':''}<span>${esc(status)}<small>${job.status==='queued'?'当前对话回答结束后继续':'收到模型执行计划后显示具体步骤'}</small></span></span>`;
  const summary=header+stations+`<span class="cp-clock">${clock}${plan.length?'<span class="cp-chevron" aria-hidden="true">⌃</span>':''}</span>`;
  if(!plan.length)return `<div class="cp-progress-summary cp-without-plan">${summary}</div>`;
  return `<details class="cp-progress" id="cp-progress-${esc(job.id)}-${esc(m.id)}"><summary class="cp-progress-summary" aria-label="${esc(owner)} ${esc(round)}，已完成 ${done} / ${plan.length} 步，展开执行详情">${summary}</summary><section class="cp-progress-detail" aria-label="本轮执行详情"><div class="cp-detail-heading"><strong>本轮执行步骤</strong><span>${esc(status)}</span></div><ol>${plan.map((step,index)=>`<li><span class="cp-detail-number ${esc(step.status)}">${index+1}</span><span>${esc(step.step)}</span><small>${esc(label(step))}${ui.stepTime(step,timingMessage)}</small></li>`).join('')}</ol><div class="wb-runtime-panel" data-wb-runtime="${esc(m.id)}">${typeof CollabWorkbench!=='undefined'?CollabWorkbench.runtime(c.runtime,m,ui):''}</div><div class="cp-detail-footer"><small>步骤随实际执行更新</small><button type="button" class="text-button" data-show-plan="${esc(m.id)}">定位本轮对话 ↗</button></div></section></details>`;
 }
 function install(element){
  element.addEventListener('keydown',event=>{if(event.key!=='Escape')return;const detail=element.querySelector('details[open]');if(detail){detail.open=false;detail.querySelector('summary').focus({preventScroll:true});event.preventDefault();}});
  element.ownerDocument.addEventListener('pointerdown',event=>{if(!element.contains(event.target))for(const d of element.querySelectorAll('details[open]'))d.open=false;});
  element.addEventListener('click',event=>{if(event.target.closest('[data-show-plan]'))for(const d of element.querySelectorAll('details[open]'))d.open=false;});
 }
 const api={select,shortStep,html,install};
 if(typeof module==='object'&&module.exports)module.exports=api;else root.CollabComposerProgress=api;
})(typeof window==='object'?window:this);
