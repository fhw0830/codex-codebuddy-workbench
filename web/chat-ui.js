(function(root){
  'use strict';
  const escape = value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const roles={user:{name:'你',icon:'user-circle'},codex:{name:'Codex',icon:'robot'},codebuddy:{name:'CodeBuddy',icon:'chat-circle-text'}};
  function duration(value){const seconds=Math.max(0,Math.floor(Number(value)||0));if(seconds<60)return `${seconds} 秒`;return `${Math.floor(seconds/60)} 分 ${seconds%60} 秒`;}
  function measuredTime(t,live=false){if(live&&t.started_at&&Number.isFinite(Date.parse(t.started_at)))return `<span data-live-duration="${escape(t.started_at)}" data-accumulated="${Number(t.accumulated_s)||0}">${duration((Number(t.accumulated_s)||0)+(Date.now()-Date.parse(t.started_at))/1000)}</span>`;return typeof t.elapsed_s==='number'?duration(t.elapsed_s):'未记录用时';}
  function replyTiming(message){if(message.status==='streaming')return `<span class="reply-elapsed" title="本轮从开始生成起计时，含等待">已用 ${measuredTime({started_at:message.created},true)}</span>`;return typeof message.meta?.elapsed_s==='number'?`<span>${duration(message.meta.elapsed_s)}</span>`:'';}
  function activeTiming(conversation){
   const job=conversation?.job;if(!job)return '';
   const user=(conversation.messages||[]).find(m=>m.role==='user'&&m.meta?.job_id===job.id&&!['steer','answer'].includes(m.meta?.delivery?.mode));
   if(!user)return '';
   const timing=user.meta?.timing;
   const queued=job.status==='queued',waiting=job.status==='waiting_input';
   const value=queued?measuredTime({started_at:job.created||user.created},true):timing?measuredTime(timing,!waiting&&!timing.finished_at):measuredTime({started_at:user.created},true);
   return `<span class="active-progress-clock" aria-label="本任务计时" aria-live="off" title="本次任务用时，包含任务内等待；重启续接沿用已记录用时">${queued?'排队':'已用'} <span class="timer-number">${value}</span></span>`;
  }
  function questionTiming(message){if(['answer','steer'].includes(message.meta?.delivery?.mode))return '';const t=message.meta?.timing;const d=message.meta?.delivery;if(!t){return d?.state==='queued'&&message.created?`<div class="question-timing">排队等待 · ${measuredTime({started_at:message.created},true)}</div>`:'';}const live=!t.finished_at&&!['failed','interrupted','completed'].includes(t.status);const label=t.status==='failed'?'失败前处理':t.status==='interrupted'?'停止前处理':live?'正在处理':'处理耗时';return `<div class="question-timing"><span>${label} · ${measuredTime(t,live)}</span><span>排队等待 · ${typeof t.wait_s==='number'?duration(t.wait_s):'未记录用时'}</span></div>`;}
  function stepTime(step,message){if(step.status==='pending'&&step.elapsed_s==null)return '';return ` · ${measuredTime(step,message.status==='streaming'&&step.timing_live===true)}`;}
  function planDisclosure(message){
    const plan=message.meta?.plan||[];if(!plan.length)return flow(message);
    if(message.status!=='streaming')return `<details class="message-plan plan-history" data-plan-message="${escape(message.id||'current')}"><summary>本轮步骤 · 已完成 ${plan.filter(s=>s.status==='completed').length} / ${plan.length} 步</summary>${flow(message)}</details>`;
    return `<div class="message-plan plan-live" data-plan-message="${escape(message.id||'current')}" aria-label="任务步骤，直接显示">${flow(message)}</div>`;
  }
  function avatar(agent){const role=roles[agent]||roles.user;return `<span class="agent-avatar ${roles[agent]?agent:'user'}" role="img" aria-label="${role.name}头像"><span class="icon" data-icon="${role.icon}" aria-hidden="true"></span></span>`;}
  function delivery(message,actions=false){const d=message.meta?.delivery;if(!d)return '';const labels={queued:'排队中 · 当前回答结束后继续',waiting:'等待你回答',pending:'正在补充当前任务',accepted:'已补充当前任务',cancelled:'已取消排队',failed:'补充未送达',interrupted:'服务中断 · 未自动重发',started:d.mode==='queue'?'任务已开始':null};const label=labels[d.state];if(!label)return '';return `<div class="delivery-badge ${escape(d.state)}">${escape(label)}${d.reason?`<span title="${escape(d.reason)}"> · ${escape(d.reason)}</span>`:''}${d.state==='queued'?(actions?`<span class="queue-actions"><button class="text-button" data-queue-action="guide" data-queue-message="${escape(message.id)}">引导当前任务</button><button class="text-button" data-queue-action="edit" data-queue-message="${escape(message.id)}">编辑</button><button class="text-button" data-queue-action="delete" data-queue-message="${escape(message.id)}">删除</button></span>`:`<button class="text-button" data-cancel-queue="${escape(message.meta.job_id)}">取消排队</button>`):''}</div>`;}
  function resourceLabel(message){const wait=message?.meta?.resource_wait;if(wait?.state!=='waiting')return '';const names=(wait.resources||[]).map(r=>{if(r.startsWith('robot:'))return '机器人 '+r.slice(6);let parts=r.slice(5).split(/[\\/]/).filter(Boolean);if(parts.at(-1)==='.git')parts.pop();return '项目 '+(parts.at(-1)||r.slice(5));});return '等待同一资源：'+names.join('、');}
  function resourceWait(message){const label=resourceLabel(message);return label?`<div class="resource-wait" role="status"><strong>${escape(label)}</strong><span>另一对话正在操作；该操作尚未执行，其他对话可以继续回答。</span></div>`:'';}
  function flow(message){
    if(!message)return '';
    const plan=message.meta?.plan||[];
    const names={connecting:'正在连接模型',analysis:'正在分析问题',planning:'正在更新执行计划',tools:'正在执行工具',reply:'正在生成回复',context:'正在整理上下文',completed:'回答已完成'};
    const phase=message.meta?.progress?.phase;
    const tools=message.meta?.tool_events||[];
    const active=tools.findLast(t=>['running','preparing'].includes(t.status));
    const latest=active||tools.at(-1);
    const action=latest?[root.CollabExecution?.toolLabel(latest)||({commandExecution:'执行命令',report_task_plan:'更新步骤',coordinate_resources:'协调资源'}[latest.name]||latest.name),latest.file_path||latest.path||''].filter(Boolean).join(' · '):'';
    const status=message.status==='failed'?'执行失败':message.status==='interrupted'?'已停止':message.status==='completed'?'回答已完成':names[phase]||'正在处理';
    const who=roles[message.agent]?.name||message.agent;
    const title=`${who} · 第 ${message.meta?.round||1} 轮 · ${status}`;
    if(!plan.length)return message.status==='streaming'?`<section class="task-flow compact" aria-label="当前任务进度"><div class="flow-heading"><strong>${escape(title)}</strong><span>${tools.length?'工具 '+tools.length+' 次':'等待实际执行计划'}</span></div>${action?`<p class="flow-action" title="${escape(action)}">${escape(action)}</p>`:''}</section>`:'';
    const statusLabels={pending:'待处理',in_progress:message.status==='streaming'?'进行中':'结束时进行中',completed:'已完成'};
    return `<section class="task-flow" aria-label="当前任务执行计划"><div class="flow-heading"><strong>${escape(title)}</strong><span>${plan.filter(s=>s.status==='completed').length} / ${plan.length} 步</span></div><div class="metro-track" role="list">${plan.map((step,index)=>`<div class="metro-station ${['pending','in_progress','completed'].includes(step.status)?step.status:'pending'}" data-plan-step="${escape(step.step)}" role="listitem" title="${escape(step.step)} · ${statusLabels[step.status]||'待处理'}"><span class="metro-node" aria-hidden="true">${index+1}</span><span class="metro-label">${escape(step.step)}</span><small>${statusLabels[step.status]||'待处理'}${stepTime(step,message)}</small></div>`).join('')}</div>${action?`<p class="flow-action" title="${escape(action)}">${escape(action)}</p>`:''}<small class="flow-note">执行计划由模型实际更新；工具详情可点开查看。</small></section>`;
  }
  const api={resourceLabel,resourceWait,avatar,delivery,flow,duration,measuredTime,questionTiming,stepTime,planDisclosure,replyTiming,activeTiming};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.CollabChatUI=api;
})(typeof globalThis!=='undefined'?globalThis:this);
