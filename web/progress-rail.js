(function(root){
 'use strict';
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const active=s=>['running','inProgress','preparing'].includes(s);
 function select(conversation){
  const messages=(conversation?.messages||[]).filter(m=>m.role==='assistant'&&!m.meta?.deleted),job=conversation?.job;
  const scoped=job?messages.filter(m=>m.meta?.job_id===job.id):messages;
  return scoped.findLast(m=>m.status==='streaming')||scoped.at(-1)||null;
 }
 function tools(message){
  const all=new Map((message?.meta?.tool_events||[]).map(t=>[t.id,t]));
  for(const item of message?.meta?.activity||[])if(item.type==='tool'&&item.tool)all.set(item.tool.id,item.tool);
  return [...all.values()];
 }
 function paths(tool){return [...new Set([tool?.file_path,tool?.path,...(tool?.paths||[]),...(tool?.changes||[]).map(c=>c.path)].filter(Boolean))];}
 function stepFiles(step,records){
  const assigned=records.filter(t=>t.plan_step===step.step).flatMap(paths);
  const explicit=[step.file_path,step.path,...(String(step.step||'').match(/(?:[A-Za-z]:[\\/]|\/?[\w.-]+[\\/])*[\w.-]+\.(?:py|js|ts|tsx|jsx|vue|css|html|json|yaml|yml|md|cpp|hpp|h|sh|ps1)\b/g)||[])];
  return [...new Set([...assigned,...explicit].filter(Boolean))];
 }
 function target(message,step){
  const record=tools(message).find(t=>t.plan_step===step);
  return {message_id:message?.id,tool_id:record?.id,step};
 }
 function html(c,ui,execution){
  if(!c)return '';
  const m=select(c),job=c.job,pending=['queued','running','waiting_input'].includes(job?.status),plan=m?.meta?.plan||[];
  if(!m&&!pending)return '';
  const record=tools(m),business=record.filter(t=>t.type!=='hook'&&!['report_task_plan','coordinate_resources','资源协调','TaskCreate','TaskUpdate','TodoWrite'].includes(t.name)),latest=business.findLast(t=>active(t.status))||business.at(-1);
  const phase=m?.meta?.progress?.phase;
  const waiting=job?.status==='waiting_input'||phase==='waiting_input'||(c.input_requests||[]).some(q=>q.message_id===m?.id&&q.blocking&&['pending','followup','submitted'].includes(q.state));
  const resource=ui.resourceLabel(m);
  const labels={connecting:'正在连接模型',analysis:'正在分析问题',planning:'正在更新步骤',tools:'正在执行工具',reply:'正在生成回复',context:'正在整理上下文'};
  const status=waiting?'等待你回答':resource||(!m?'等待后台开始':m.status==='failed'?'本轮失败':m.status==='interrupted'?'本轮已停止':m.status==='completed'?'本轮回复完成':labels[phase]||'正在处理');
  const current=plan.findIndex(s=>s.status==='in_progress'),done=plan.filter(s=>s.status==='completed').length;
  const total=m?.meta?.total_rounds,round=m?.meta?.round;
  const name=m?({codex:'Codex',codebuddy:'CodeBuddy'}[m.agent]||m.agent):job?.route==='both'?'Codex → CodeBuddy':job?.route==='codebuddy'?'CodeBuddy':'Codex';
  const recent=(m?.meta?.activity||[]).findLast(e=>e.type==='text'&&e.phase!=='final_answer')?.text;
  const action=latest?(execution?.toolLabel(latest)||latest.name||latest.type):'';
  const stateClass=waiting||resource?'waiting':m?.status==='streaming'?'running':m?.status||'queued';
  return `<div class="rail-summary"><div class="rail-owner">${m?ui.avatar(m.agent):''}<strong>${esc(name)}</strong></div><p class="rail-round">${round?`第 ${esc(round)}${total?' / '+esc(total):''} 轮`:'本次任务'}</p><p class="rail-status ${esc(stateClass)}"><span aria-hidden="true"></span>${esc(status)}</p>${plan.length?`<p class="rail-count">已完成 ${done} / ${plan.length} 步</p>`:''}${current>=0?`<p class="rail-now" title="${esc(plan[current].step)}">${esc(plan[current].step)}</p>`:''}<div class="rail-time">${m?ui.replyTiming(m):ui.activeTiming(c)}</div></div><div class="rail-content">${plan.length?`<ol class="rail-stations">${plan.map((step,index)=>{
   const files=stepFiles(step,record),progress=step.status==='in_progress';
   const label=step.status==='completed'?'已完成':progress?waiting?'等待回答':m.status==='streaming'?'进行中':'结束时进行中':'待处理';
   return `<li class="rail-station ${esc(step.status)}" data-rail-step="${esc(step.step)}"${progress?' aria-current="step"':''}><span class="rail-node" aria-hidden="true">${index+1}</span><button type="button" class="rail-step-link" data-rail-message="${esc(m.id)}" data-rail-step-name="${esc(step.step)}" aria-label="定位步骤：${esc(step.step)}">${esc(step.step)}</button>${files.length?`<span class="rail-step-files" title="${esc(files.join('\n'))}">${files.slice(0,2).map(p=>`<span>${esc(p)}</span>`).join('')}${files.length>2?`<small>另 ${files.length-2} 个文件</small>`:''}</span>`:''}<small class="rail-step-time">${esc(label)}${ui.stepTime(step,m)}</small></li>`;
  }).join('')}</ol>`:`<p class="rail-empty">${m?.status==='streaming'?'等待模型提供具体步骤；收到后会实时显示。':pending?'本次任务尚未提供执行步骤。':'这条历史回复没有记录执行计划。'}</p>`}${latest?`<div class="rail-operation"><small>${active(latest.status)?'当前工具':'最近工具'}</small><strong>${esc(action)}</strong>${paths(latest).slice(0,2).map(p=>`<span class="rail-operation-path">${esc(p)}</span>`).join('')}${latest.status==='failed'?'<span class="rail-error">工具失败，展开原记录查看原因</span>':''}</div>`:''}${recent&&m?.status==='streaming'?`<details class="rail-progress-note"><summary>最近进展</summary><p>${esc(String(recent).slice(0,400))}</p></details>`:''}<div class="rail-foot">${m?`<button type="button" class="rail-locate" data-rail-message="${esc(m.id)}"${current>=0?` data-rail-step-name="${esc(plan[current].step)}"`:''}>${current>=0?'定位当前步骤':'定位本轮回复'} ↗</button>`:''}<small>${waiting?'任务保留在这里，等你回答后继续。':'步骤随实际执行更新；回复完成不等于任务已验收。'}</small></div></div>`;
 }
 const api={select,tools,paths,stepFiles,target,html};
 if(typeof module==='object'&&module.exports)module.exports=api;else root.CollabProgressRail=api;
})(typeof window==='object'?window:this);
