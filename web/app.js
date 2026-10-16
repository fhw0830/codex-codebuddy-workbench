'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<span class="icon" data-icon="${esc(name)}"></span>`;
const answeredQuestions={};
const submissions=CollabSubmissions.create(localStorage,()=>crypto.randomUUID());
let changePanel=null;
const state = {csrf:'',id:null,conv:null,health:{},connection:'connecting',archived:false,route:'both',documents:[],uploads:[],docCatalog:[],preview:null,sending:false,selectEpoch:0};
const md = window.markdownit({html:false,linkify:true,breaks:true});
CollabLocalLinks.install(md);
md.renderer.rules.image = tokens => `<span class="reference-tag">${esc(tokens.map(t=>t.content).join(''))}</span>`;
const fence = md.renderer.rules.fence.bind(md.renderer.rules);
md.renderer.rules.fence = (...args) => fence(...args).replace('<pre>', '<pre><button class="copy-code" type="button">复制代码</button>');
const timeText = value => value ? new Date(value).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}) : '';
const dateText = value => value ? new Date(value).toLocaleString('zh-CN',{hour12:false}) : '未取得';
const label = agent => ({user:'你',codex:'Codex',codebuddy:'CodeBuddy'}[agent] || agent);
const busy = () => ['queued','running','waiting_input'].includes(state.conv?.job?.status);
let toastSequence=0;
function toast(text,error=false){
 const sequence=++toastSequence,box=document.createElement('div'),message=document.createElement('span'),close=document.createElement('button');
 box.className='toast'+(error?' error':'');if(error)box.setAttribute('role','alert');
 message.textContent=text;message.title=text;close.className='toast-close';close.type='button';close.setAttribute('aria-label','关闭提示');close.innerHTML=icon('x');
 const dismiss=()=>{if(sequence!==toastSequence)return;$('toasts').replaceChildren();$('save-note').classList.remove('hidden');};
 close.onclick=dismiss;box.append(message,close);$('toasts').replaceChildren(box);$('save-note').classList.add('hidden');
 if(!error)setTimeout(dismiss,5000);
}
async function api(path,body,retry=true,options={}){
  const response=await fetch(path,{signal:options.signal,method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json','X-Collab-Token':state.csrf},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await CollabApiResponse.read(response);
  if(response.status===403 && retry && body!==undefined){const boot=await api('/api/bootstrap');state.csrf=boot.csrf;return api(path,body,false);}
  if(!response.ok){const error=new Error(data.error||'请求失败');error.status=response.status;throw error;}return data;
}
function guard(fn){return async (...args)=>{try{await fn(...args);}catch(error){toast(error.message,true);}};}
function draftKey(id){return 'robot-collab:draft:'+id;}
function saveDraft(){if(!state.id)return;try{localStorage.setItem(draftKey(state.id),JSON.stringify({text:$('message-input').value,route:state.route,rounds:$('rounds').value,execution_strategy:$('execution-strategy').value,manual_height:composerManualHeight,documents:state.documents,uploads:state.uploads}));}catch{toast('草稿超过浏览器保存容量；可先发送或导出附件',true);}}
function restoreDraft(id){let draft={};try{draft=JSON.parse(localStorage.getItem(draftKey(id))||'{}');}catch{};$('message-input').value=draft.text||'';state.route=draft.route||'both';$('execution-strategy').value=draft.execution_strategy||'auto';composerManualHeight=Math.max(52,Number(draft.manual_height)||60);$('message-input').style.height=composerManualHeight+'px';$('rounds').value=draft.rounds||'1';state.documents=draft.documents||[];state.uploads=draft.uploads||[];renderRoute();renderAttachments();}
function renderRoute(){document.querySelectorAll('[data-route]').forEach(el=>el.classList.toggle('selected',el.dataset.route===state.route));$('rounds').disabled=state.route!=='both';$('execution-strategy').classList.toggle('hidden',state.route!=='both'||!state.capabilities?.phased_execution);}
async function loadList(options={}){const q=$('conversation-search').value;let list=await api('/api/conversations?archived='+(state.archived?'1':'0')+'&q='+encodeURIComponent(q),undefined,true,options);$('waiting-count').textContent=list.filter(c=>c.waiting_input).length;$('waiting-filter').setAttribute('aria-pressed',String(!!state.attentionOnly));if(state.attentionOnly)list=list.filter(c=>c.waiting_input);CollabStableDOM.render($('conversation-list'),list.length?list.map(c=>`<button class="conversation-row ${c.id===state.id?'selected':''}" data-conversation="${c.id}">${c.busy&&!c.waiting_input?'<span class="generation-spinner" role="img" aria-label="正在生成"></span>':icon('chat-circle-text')}<span><strong>${esc(c.title)}</strong><small>${c.waiting_input?'等待回答 · ':c.busy?'正在生成 · ':''}${dateText(c.updated).replace(/:\d\d$/,'')}</small></span></button>`).join(''):'<div class="empty-nav">没有找到相关对话</div>');$('conversation-list-label').textContent=state.archived?'已归档对话':'最近对话';}
async function selectConversation(id,options={}){saveDraft();const epoch=++state.selectEpoch;const item=await api('/api/conversations/'+id,undefined,true,options);if(epoch!==state.selectEpoch)return;state.id=id;state.conv=item;localStorage.setItem('robot-collab:last-conversation',id);const typed=options.preserveInput?$('message-input').value:'';restoreDraft(id);if(typed){$('message-input').value=typed;saveDraft();}renderConversation();await loadList(options);closeOverlays();$('message-scroll').scrollTop=$('message-scroll').scrollHeight;}
let conversationRefreshRunning=false,conversationRefreshAgain=false;
async function refreshConversation(options={}){
 if(!state.id)return;
 if(conversationRefreshRunning){conversationRefreshAgain=true;return;}
 conversationRefreshRunning=true;
 const id=state.id;
 try{const c=await api('/api/conversations/'+id,undefined,true,options);if(id!==state.id)return;
 const scroll=$('message-scroll'),position=CollabStableDOM.capture(scroll);
 c.messages=CollabStream.mergeMessages(state.conv?.messages,c.messages);state.conv=c;
 renderConversation();CollabStableDOM.restore(scroll,position);
 }finally{conversationRefreshRunning=false;if(conversationRefreshAgain){conversationRefreshAgain=false;scheduleRefresh();}}
}
function welcome(){return `<div class="welcome"><div class="welcome-monogram">${CollabChatUI.avatar('codex')}${CollabChatUI.avatar('codebuddy')}</div><h2>从同一份<span>需求</span>开始。</h2><p>把问题、证据和讨论放在同一处。让 Codex 提出判断，CodeBuddy 独立复核，再把明确的结论接下去。</p><div class="welcome-prompts"><button class="welcome-prompt" data-prompt="我们先讨论异常重启后的任务恢复机制。请根据我随后提供的日志与交接材料核对事实，先给方案，不修改代码。">讨论异常重启后的任务恢复${icon('arrow-right')}</button><button class="welcome-prompt" data-prompt="请核对咖啡厅巡航反复绕障的需求：站点持续被占10秒后，使用模式2去站点之后线路上的第1米；障碍提前移开则服务原站。先列出需要验证的场景，不修改代码。">核对巡航反复绕障的遗漏场景${icon('arrow-right')}</button><button class="welcome-prompt" data-prompt="这是协作通道测试，请两方分别只回复“已收到，协作通道正常”，不要调用工具。">验证双方的真实对话通道${icon('arrow-right')}</button></div></div>`;}
function questionHTML(message,onlyId=null){
 const requests=state.conv?.input_requests||[],markers=CollabExecution.questionIds(message);
 const selected=onlyId?requests.filter(q=>q.id===onlyId):requests.filter(q=>!markers.includes(q.id));
 return CollabUserInput.html(message,selected,answeredQuestions,state.conv?.messages||[],{allowProse:!onlyId&&!markers.length&&!requests.some(q=>q.message_id===message.id)});
}
function messageBodyHTML(message){
 const followups=message.role==='assistant'?CollabFollowup.html(state.conv?.messages||[],message,text=>md.render(text),CollabChatUI.avatar):'';
 if(message.role==='assistant'&&message.meta?.activity?.length)return CollabExecution.html(message,text=>md.render(text),id=>questionHTML(message,id),tool=>CollabChatUI.measuredTime(tool,message.status==='streaming'&&['running','inProgress'].includes(tool.status)),followups);
 return message.content?followups+md.render(message.content):followups+'<div class="reply-placeholder"><span></span><span></span><span></span>正在思考</div>';
}
function messageHTML(m){const model=m.meta?.requestModelName||m.meta?.model||m.meta?.requested_model||'';const credit=m.meta?.credit;const refs=m.meta?.references||[];const footer=m.role==='assistant'?`<div class="message-footer"><button class="icon-button" data-copy-message="${m.id}" aria-label="复制回复">${icon('copy')}</button><span>${m.status==='completed'?'已完成':m.status==='streaming'?'生成中':m.status==='interrupted'?'已停止':'生成失败'}</span>${CollabChatUI.replyTiming(m)}${CollabUsage.html(m)}${m.status==='failed'?`<button class="text-button" data-retry-message="${m.id}">重新编辑发送</button>`:''}</div>`:'';return `<article class="message ${m.role} ${m.status}" data-message="${m.id}"><div class="message-heading">${CollabChatUI.avatar(m.agent)}<strong>${label(m.agent)}</strong>${model?`<span class="model-tag" title="${esc(model)}">${esc(model)}</span>`:''}${m.agent==='codex'&&m.meta?.requested_reasoning_effort?`<span class="model-tag" title="本次请求的思考强度">思考：${esc(effortLabel(m.meta.requested_reasoning_effort))}</span>`:''}${m.meta?.access_mode?`<span class="model-tag">${m.meta.access_mode==='full'?'完全访问':m.meta.access_mode==='read_only'?'首轮只读':'仅讨论'}</span>`:''}${m.role==='assistant'?CollabDiscussion.badge(state.conv,m):''}<time>${timeText(m.created)}</time></div>${m.role==='assistant'?CollabChatUI.resourceWait(m)+CollabChatUI.planDisclosure(m):''}<div class="message-body markdown">${messageBodyHTML(m)}</div><div class="message-questions" data-question-host="${m.id}">${questionHTML(m)}</div>${toolTraceHTML(m)}${m.role==='user'?(m.meta?.resume_checkpoint?`<div class="delivery-badge">从 ${esc(label(m.meta.resume_checkpoint.agent))} 第 ${Number(m.meta.resume_checkpoint.round)||1} 轮检查点续接 · 先核验已有结果</div>`:'')+CollabChatUI.delivery(m,state.capabilities?.queue_actions===true)+CollabChatUI.questionTiming(m):''}${refs.length?`<div class="reference-list">${refs.map((r,i)=>`<button class="reference-tag" data-reference-message="${m.id}" data-reference-index="${i}" title="查看附件 · SHA256 ${esc(r.sha256)}">${esc(r.name)}</button>`).join('')}</div>`:''}${m.status==='failed'&&/500\s+internal server error/i.test(m.content||'')?'<aside class="model-failure-notice"><strong>模型请求返回 500</strong><p>本次回答未完成，前面的工具记录仍保留。重试前先核对已执行内容，避免重复修改。</p></aside>':''}${m.meta?.error&&m.content!==m.meta.error?`<div class="message-footer error-label">${esc(m.meta.error)}</div>`:''}${footer}${m.role==='assistant'?CollabWorkbench.extras(state.conv,m,CollabExecution,CollabChatUI,state.capabilities?.workbench_inspection===true):''}</article>`;}
function renderConversation(){const c=state.conv;if(!c)return;const questionDrafts=CollabUserInput.captureDrafts?.($('messages'))||new Map();const inlineAnswers=CollabUserInput.inlineAnswerIds(c.messages,c.input_requests||[]);for(const id of CollabFollowup.inlineIds(c.messages))inlineAnswers.add(id);$('conversation-title').textContent=c.title;$('conversation-subtitle').textContent=c.archived?'已归档 · 可恢复后继续':c.preferences?.access_mode==='full'?'完全访问 · 可读写本地文件、执行命令和使用SSH':'仅讨论 · 不执行工具或文件修改';CollabStableDOM.render($('messages'),compressionHTML(c)+(c.messages.some(m=>!m.meta?.deleted)?CollabDiscussion.render(c,c.messages.filter(m=>!m.meta?.deleted&&!inlineAnswers.has(m.id)),messageHTML):welcome()));CollabUserInput.restoreDrafts?.($('messages'),questionDrafts);renderTaskFlow();$('archive-chat').title=c.archived?'恢复当前对话':'归档当前对话';$('archive-chat').setAttribute('aria-label',$('archive-chat').title);$('archive-chat').innerHTML=icon(c.archived?'arrow-counter-clockwise':'archive');$('send-message').classList.toggle('hidden',busy()&&!state.capabilities?.queue);$('queue-hint').classList.toggle('hidden',!busy()||!state.capabilities?.queue);$('send-message').setAttribute('aria-label',busy()&&state.capabilities?.queue?'排队发送':'发送消息');$('stop-generation').classList.toggle('hidden',!busy());$('send-message').disabled=submissions.isSending(state.id)||isAttachmentBusy()||!!c.archived||state.connection!=='connected';$('message-input').disabled=!!c.archived;$('active-progress').classList.toggle('hidden',!busy());CollabStableDOM.render($('active-progress'),busy()?CollabComposerProgress.html(c,CollabChatUI,CollabDiscussion):'');$('brief-preview').textContent=c.brief||'把目标和不能遗漏的要求固定在这里，切换模型也会保留。';$('brief-preview').classList.toggle('has-brief',!!c.brief);renderModels();renderEffort();renderPermission();renderTasks();$('conversation-credit').textContent=c.reported_credits>0?c.credit_sum.toFixed(3).replace(/0+$/,'').replace(/\.$/,''):'—';renderUsage();sizeComposer();changePanel?.sync(c);}
function renderModels(){for(const name of ['codex','codebuddy']){const health=state.health[name]||{};const models=health.models||[];const selected=state.conv?.preferences?.[name+'_model'];const select=$(name+'-model');CollabStableDOM.render(select,models.length?models.map(m=>`<option value="${esc(m.id)}" ${m.id===selected?'selected':''}>${esc(m.name)}</option>`).join(''):`<option value="${esc(selected||'')}">${esc(selected||'连接中…')}</option>`);if(selected && !models.some(m=>m.id===selected) && models.length && !Array.from(select.options).some(o=>o.value===selected))select.insertAdjacentHTML('afterbegin',`<option value="${esc(selected)}" selected>${esc(selected)} · 待刷新</option>`);select.disabled=!state.id||!models.length;const pending=state.conv?.messages?.findLast(m=>m.status==='streaming');$(name+'-agent-state').textContent=pending?.agent===name?'正在回答':health.ready?'后台就绪':health.error?'暂不可用':'正在连接';$(name+'-status').className='status-dot'+(pending?.agent===name?' busy':health.ready?' ready':'');}}
function renderTasks(){const tasks=state.conv?.tasks||[];$('task-count').textContent=tasks.filter(t=>t.status==='done').length+' / '+tasks.length;CollabStableDOM.render($('task-list'),tasks.length?tasks.map(t=>`<div class="task-row ${t.status}" data-task="${t.id}"><button class="task-check ${t.status==='done'?'done':''}" data-task-toggle="${t.id}" aria-label="${t.status==='done'?'重新打开任务':'标记任务完成'}">${t.status==='done'?icon('check'):''}</button><div class="task-info"><strong>${esc(t.title)}</strong><div class="task-controls"><select data-task-status="${t.id}" aria-label="任务状态">${[['todo','待处理'],['active','进行中'],['blocked','有阻塞'],['done','已完成']].map(([id,name])=>`<option value="${id}" ${t.status===id?'selected':''}>${name}</option>`).join('')}</select><select data-task-owner="${t.id}" aria-label="任务负责人">${[['user','我'],['codex','Codex'],['codebuddy','CodeBuddy']].map(([id,name])=>`<option value="${id}" ${t.owner===id?'selected':''}>${name}</option>`).join('')}</select></div></div><button class="task-remove" data-task-delete="${t.id}" aria-label="删除任务">${icon('x')}</button></div>`).join(''):'<div class="empty-tasks">先添加需要推进的一件事。</div>');}
function renderAttachments(){const all=[...state.documents.map(d=>({...d,kind:'document'})),...state.uploads.map((u,index)=>({...u,kind:'upload',index}))];$('attachment-chips').classList.toggle('hidden',!all.length);$('attachment-chips').innerHTML=all.map(a=>`<div class="attachment-chip">${icon('file-text')}<button class="attachment-preview-button" data-preview-attachment="${a.kind==='document'?'doc:'+esc(a.id):'upload:'+a.index}" title="预览附件">${esc(a.name)}${a.upload_id&&a.preview_url?' · 图片':''}</button><button class="icon-button" data-remove-attachment="${a.kind==='document'?'doc:'+esc(a.id):'upload:'+a.index}" aria-label="移除附件">${icon('x')}</button></div>`).join('');}
function quotaWindows(){const quota=state.health.quota?.data;const buckets=quota?.rateLimitsByLimitId|| (quota?.rateLimits?{codex:quota.rateLimits}:{});return Object.entries(buckets).flatMap(([id,bucket])=>['primary','secondary'].map(key=>({bucket:id,name:bucket.limitName||id,key,...(bucket[key]||{})})).filter(w=>typeof w.usedPercent==='number'));}
function windowLabel(mins){if(mins===10080)return '周窗口';if(mins===1440)return '日窗口';if(mins && mins%60===0)return (mins/60)+' 小时窗口';return mins?mins+' 分钟窗口':'额度窗口';}
function renderUsage(){const windows=quotaWindows();const first=windows[0];if(first){const remaining=Math.max(0,Math.min(100,100-first.usedPercent));$('quota-mini').textContent='剩余 '+remaining+'%';$('quota-mini-bar').style.width=remaining+'%';$('quota-mini-note').textContent=windowLabel(first.windowDurationMins)+' · 已用 '+first.usedPercent+'%';}else{$('quota-mini').textContent=state.health.quota?.error?'未取得':'读取中';$('quota-mini-bar').style.width='0%';}$('usage-content').innerHTML=`<div class="usage-heading">Codex · 账号共享额度</div>${windows.length?windows.map(w=>{const remaining=Math.max(0,Math.min(100,100-w.usedPercent));return `<div class="usage-window"><div class="usage-window-heading"><strong>${esc(w.name)} / ${windowLabel(w.windowDurationMins)}</strong><span>${remaining}% 剩余</span></div><div class="usage-bar"><span style="width:${remaining}%"></span></div><p>已用 ${w.usedPercent}% · ${w.resetsAt?'重置时间 '+dateText(w.resetsAt*1000):'重置时间未提供'}</p></div>`;}).join(''):`<p class="usage-note">${esc(state.health.quota?.error||'正在读取官方额度接口')}</p>`}${state.health.quota?.error&&windows.length?`<p class="usage-note error-label">刷新失败；上方保留最近一次成功查询的数据。</p>`:''}<div class="usage-heading">CodeBuddy · 本对话实际报告的积分</div><div class="usage-credits"><span>累计消耗</span><strong>${state.conv?.reported_credits?(state.conv.credit_sum).toFixed(3).replace(/0+$/,'').replace(/\.$/,''):'—'}</strong></div><p class="usage-note">${state.conv?.partial_credit_replies?state.conv.partial_credit_replies+' 条工具任务仅报告部分积分；此处不是这些任务的完整总消耗。':state.conv?.unreported_credits?state.conv.unreported_credits+' 条回复没有报告积分；未按零计费。':'仅汇总本网页当前对话的实际 credit 字段，刷新页面不会重复累计。'}</p><div class="usage-heading">CodeBuddy · 账号总余额</div><p class="usage-note">目前未取得可用的后台余额接口。<a href="https://copilot.tencent.com/profile/" target="_blank" rel="noopener noreferrer">查看官方账户用量 ${icon('arrow-square-out')}</a></p>`;$('quota-updated').textContent='查询时间：'+dateText(state.health.quota?.updated);}
function renderHealth(){if(state.connection!=='connected'){renderConnectionState();renderModels();renderEffort();renderUsage();return;}const c=state.health.codex?.ready,b=state.health.codebuddy?.ready;const pill=$('connection-pill');pill.className='connection-pill '+(c&&b?'ready':state.health.updated?'error':'');pill.innerHTML=`<span></span>${c&&b?'本地后台就绪':state.health.refreshing||!state.health.updated?'连接中':'部分连接不可用'}`;$('settings-connection').textContent=`Codex：${c?'接口就绪':state.health.codex?.error||'连接中'}；CodeBuddy：${b?'CLI就绪':state.health.codebuddy?.error||'连接中'}`;renderModels();renderEffort();renderUsage();}
async function loadDocuments(q=$('document-search').value){const docs=await api('/api/documents?q='+encodeURIComponent(q));state.docCatalog=docs;$('document-list').innerHTML=docs.length?docs.map(d=>`<button class="document-item" data-document="${esc(d.id)}">${icon('file-text')}<span><strong>${esc(d.name.replace(/\.md$/,''))}</strong><small>${esc(d.group)} · ${(d.bytes/1024).toFixed(1)} KB</small></span></button>`).join(''):'<p class="section-description">没有找到相关文件。</p>';}
function setTab(tab){document.querySelectorAll('[data-tab]').forEach(el=>{const selected=el.dataset.tab===tab;el.classList.toggle('selected',selected);el.setAttribute('aria-selected',selected);});for(const name of ['tasks','documents','handoff'])$('tab-'+name).classList.toggle('hidden',tab!==name);if(tab==='documents')guard(loadDocuments)();}
function showPanel(){if(innerWidth<=1250){$('context-panel').classList.add('open');$('mobile-scrim').classList.remove('hidden');}else{document.querySelector('.app-shell').classList.remove('panel-hidden');} }
function closeOverlays(){$('sidebar').classList.remove('open');$('context-panel').classList.remove('open');$('mobile-scrim').classList.add('hidden');}
function fillDraft(text){$('message-input').value=text;sizeComposer();saveDraft();$('message-input').focus();}
function finishSubmittedDraft(id,submitted){
 if(state.id===id){
  const next=CollabSubmissions.remaining({text:$('message-input').value,documents:state.documents,uploads:state.uploads},submitted);
  $('message-input').value=next.text;state.documents=next.documents;state.uploads=next.uploads;renderAttachments();saveDraft();return;
 }
 let draft;try{draft=JSON.parse(localStorage.getItem(draftKey(id))||'null');}catch{}
 if(draft)localStorage.setItem(draftKey(id),JSON.stringify(CollabSubmissions.remaining(draft,submitted)));
}
async function sendMessage(){
 if(state.connection!=='connected')throw new Error('正在自动连接后台，连接恢复后再发送；输入内容已保留');
 if(isAttachmentBusy())throw new Error('这条对话的附件正在读取，请稍后再发送');
 const id=state.id;if(!id||submissions.isSending(id))return;
 if(busy()&&!state.capabilities?.queue)throw new Error('后台更新尚未加载，请等待当前回答完成');
 const raw=$('message-input').value,content=raw.trim();if(!content){toast('先写下你要讨论的问题');return;}
 if(state.route==='both'&&state.capabilities?.phased_execution&&($('execution-strategy').value==='discuss_first'||CollabUserInput.discussionFirst(content))&&Number($('rounds').value)<2){$('rounds').value='2';toast('已按先讨论再执行使用2轮');}
 const submitted=JSON.parse(JSON.stringify({text:raw,documents:state.documents,uploads:state.uploads}));
 const request={conversation_id:id,content,route:state.route,rounds:Number($('rounds').value),execution_strategy:$('execution-strategy').value,documents:state.documents.map(d=>d.id),attachments:state.uploads,send_mode:busy()?'queue':'send'};
 if(!submissions.start(id))return;$('send-message').disabled=true;saveDraft();let accepted=false,reservation;
 try{
  reservation=submissions.reserve(id,request);request.client_key=reservation.client_key;
  let result;
  if(reservation.retry){const receipt=await api('/api/submission?conversation_id='+encodeURIComponent(id)+'&client_key='+encodeURIComponent(request.client_key));if(receipt.found)result=receipt.job;}
  if(!result)result=await api('/api/messages',request);
  accepted=true;submissions.clear(id,reservation.client_key);finishSubmittedDraft(id,submitted);
  toast(reservation.retry?'已核对发送结果，同一任务没有重复创建':request.send_mode==='queue'?'已排队，当前回答结束后继续':'已发送');
  try{if(state.id===id)await refreshConversation();await loadList();}
  catch{toast('任务已收到，执行状态正在重新同步');void reconnect.wake();}
 }catch(error){
  if(!accepted&&error.status>=400&&error.status<500){submissions.clear(id,reservation?.client_key);throw error;}
  if(!accepted)throw new Error('暂未确认发送结果，输入已保留；再次点击会先核验同一任务，不会另建重复任务。');
  throw error;
 }finally{submissions.finish(id);if(state.conv)renderConversation();}
}
function editDialog(title,value,labelText,save,owner=false){$('edit-title').textContent=title;$('edit-label').textContent=labelText;$('edit-value').value=value;$('edit-value').maxLength=(title.includes('需求')||title.includes('消息'))?16000:300;$('task-owner-field').classList.toggle('hidden',!owner);$('task-owner').value='user';const handler=guard(async event=>{event.preventDefault();if(event.submitter?.value==='cancel'){$('edit-dialog').close();return;}const text=$('edit-value').value.trim();if(!text && !title.includes('需求'))return;await save(text,$('task-owner').value);$('edit-dialog').close();$('edit-form').removeEventListener('submit',handler);await refreshConversation();await loadList();});$('edit-form').onsubmit=handler;$('edit-dialog').showModal();$('edit-value').focus();}
async function createConversation(){saveDraft();state.archived=false;$('conversation-search').value='';const item=await api('/api/conversations',{});await selectConversation(item.id);$('message-input').focus();}
async function viewDocument(id){state.preview={id};const doc=await api('/api/document?id='+encodeURIComponent(id));if(state.preview?.id!==id)return;state.preview=doc;$('attach-document').classList.remove('hidden');$('document-title').textContent=doc.name;$('document-group').textContent=doc.id.split('/')[0];$('document-preview').innerHTML=md.render(doc.content);$('document-dialog').showModal();}
function debounce(fn,ms=250){let timer;return(...args)=>{clearTimeout(timer);timer=setTimeout(()=>guard(fn)(...args),ms);};}
let refreshTimer;
function scheduleRefresh(){if(refreshTimer)return;refreshTimer=setTimeout(()=>{refreshTimer=null;guard(async()=>{await refreshConversation();await loadList();})();},120);}
function connectEvents(after){const stream=new EventSource('/api/events?after='+after);stream.onmessage=event=>{const data=JSON.parse(event.data);if(data.kind==='message_delta'){applyStreamDelta(data.payload);return;}if(data.kind==='health')guard(async()=>{state.health=(await api('/api/health')).health;renderHealth();})();else if(data.kind==='storage')guard(()=>refreshAfterStorage(data.payload))();else if(data.kind==='archive'){if(data.payload.conversation_id===state.id){$('handoff-path').textContent='最近保存：'+data.payload.path;$('handoff-path').classList.remove('hidden');}}else scheduleRefresh();};return stream;}

$('new-chat').onclick=guard(createConversation);$('nav-chat').onclick=closeOverlays;
$('conversation-list').onclick=guard(async event=>{const row=event.target.closest('[data-conversation]');if(row)await selectConversation(row.dataset.conversation);});
$('conversation-search').oninput=debounce(loadList);$('toggle-archived').onclick=guard(async()=>{state.archived=!state.archived;await loadList();});
$('rename-chat').onclick=()=>editDialog('重命名对话',state.conv?.title||'','对话名称',text=>api('/api/conversations/'+state.id,{title:text}));
$('archive-chat').onclick=guard(async()=>{if(busy())throw new Error('请先停止当前生成，再归档对话');await api('/api/conversations/'+state.id,{archived:!state.conv.archived});await refreshConversation();await loadList();});
$('fork-chat').onclick=guard(async()=>{if(busy())throw new Error('旧对话正在生成；先等待或停止，再携带完整记录续接');const c=await api('/api/conversations/'+state.id+'/fork',{});state.archived=false;await selectConversation(c.id);toast('已携带固定需求、旧记录和未完成任务续接');});
$('export-chat').onclick=()=>{if(state.id)location.href='/api/export?id='+state.id;};$('export-json').onclick=()=>{if(state.id)location.href='/api/export?id='+state.id+'&format=json';};
$('edit-brief').onclick=()=>editDialog('编辑固定需求',state.conv?.brief||'','目标、范围、不可遗漏的要求',text=>api('/api/conversations/'+state.id,{brief:text}));
$('add-task').onclick=()=>editDialog('添加任务','','任务内容',(title,owner)=>api('/api/tasks',{conversation_id:state.id,title,owner}),true);
$('task-list').onclick=guard(async event=>{const toggle=event.target.closest('[data-task-toggle]'),remove=event.target.closest('[data-task-delete]');if(toggle){const task=state.conv.tasks.find(t=>t.id===toggle.dataset.taskToggle);await api('/api/tasks/'+task.id,{status:task.status==='done'?'todo':'done'});await refreshConversation();}if(remove){await api('/api/tasks/'+remove.dataset.taskDelete,{delete:true});await refreshConversation();}});
$('task-list').onchange=guard(async event=>{const t=event.target;if(t.dataset.taskStatus)await api('/api/tasks/'+t.dataset.taskStatus,{status:t.value});if(t.dataset.taskOwner)await api('/api/tasks/'+t.dataset.taskOwner,{owner:t.value});await refreshConversation();});
$('send-message').onclick=guard(sendMessage);$('stop-generation').onclick=guard(async()=>{await api('/api/jobs/'+state.conv.job.id+'/stop',{});toast('正在停止当前生成');});
$('message-input').oninput=()=>{sizeComposer();debouncedDraft();};$('message-input').onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&event.keyCode!==229){event.preventDefault();guard(sendMessage)();}};
document.querySelectorAll('[data-route]').forEach(el=>el.onclick=()=>{state.route=el.dataset.route;renderRoute();saveDraft();});$('rounds').onchange=saveDraft;
document.querySelectorAll('[data-tab]').forEach(el=>el.onclick=()=>setTab(el.dataset.tab));
$('codex-effort').onchange=guard(async event=>{await api('/api/conversations/'+state.id,{preferences:{codex_effort:event.target.value}});await refreshConversation();toast('本对话的思考强度已保存，下一次发送生效');});
for(const name of ['codex','codebuddy'])$(name+'-model').onchange=guard(async event=>{await api('/api/conversations/'+state.id,{preferences:{[name+'_model']:event.target.value}});await refreshConversation();toast('这条对话的模型选择已保存');});
$('messages').onclick=guard(async event=>{const copyTool=event.target.closest('[data-copy-tool]');if(copyTool){const m=state.conv.messages.find(x=>x.id===copyTool.closest('[data-message]')?.dataset.message);const tool=(m?.meta?.activity||[]).find(x=>x.type==='tool'&&x.tool?.id===copyTool.dataset.copyTool)?.tool||(m?.meta?.tool_events||[]).find(x=>x.id===copyTool.dataset.copyTool);if(tool?.command){await navigator.clipboard.writeText(tool.command);toast('命令已复制');}return;}const expand=event.target.closest('[data-diff-tool]');if(expand){const m=state.conv.messages.find(x=>x.id===expand.closest('[data-message]')?.dataset.message);const tool=(m?.meta?.activity||[]).find(x=>x.type==='tool'&&x.tool?.id===expand.dataset.diffTool)?.tool||(m?.meta?.tool_events||[]).find(x=>x.id===expand.dataset.diffTool);const change=tool?.changes?.[Number(expand.dataset.diffIndex)];if(change)changePanel.open({messageId:m.id,path:change.path||'未记录路径',toolId:tool.id,index:Number(expand.dataset.diffIndex),opener:expand});return;}const localLink=event.target.closest('[data-local-reference]');if(localLink){event.preventDefault();const message=state.conv.messages.find(m=>m.id===localLink.closest('[data-message]')?.dataset.message);const path=CollabLocalLinks.path(localLink.dataset.localReference,message?.meta?.workdir||state.conv.preferences?.workdir);if(!path)throw new Error('缺少文件的完整本地路径');const recorded=CollabChanges.matchingFile(state.conv,message,localLink.dataset.localReference,CollabWorkbench.tools,CollabLocalLinks);if(recorded)changePanel.open({messageId:message.id,path:recorded.change.path||'未记录路径',toolId:recorded.tool.id,index:recorded.index,opener:localLink});else await previewLocal(path);return;}const action=event.target.closest('[data-queue-action]');if(action){
 const conversation_id=state.id,message_id=action.dataset.queueMessage,operation=action.dataset.queueAction;
 const message=state.conv.messages.find(m=>m.id===message_id);
 if(operation==='edit'){editDialog('编辑排队消息',message.content,'只修改这条排队消息，不打断当前回答',content=>api('/api/queued-message',{conversation_id,message_id,action:'edit',content}));return;}
 action.disabled=true;try{await api('/api/queued-message',{conversation_id,message_id,action:operation});toast(operation==='guide'?'正在引导当前任务；以实际送达状态为准':'已删除排队消息');await refreshConversation();}catch(error){action.disabled=false;throw error;}return;
 }const queued=event.target.closest('[data-cancel-queue]');if(queued){await api('/api/jobs/'+queued.dataset.cancelQueue+'/stop',{});await refreshConversation();return;}const reference=event.target.closest('[data-reference-message]');if(reference){const message=state.conv.messages.find(m=>m.id===reference.dataset.referenceMessage);const doc=message?.meta?.references?.[Number(reference.dataset.referenceIndex)];if(doc)openAttachmentPreview(doc);return;}const prompt=event.target.closest('[data-prompt]'),copy=event.target.closest('[data-copy-message]'),retry=event.target.closest('[data-retry-message]'),code=event.target.closest('.copy-code');if(prompt)fillDraft(prompt.dataset.prompt);if(copy){const m=state.conv.messages.find(m=>m.id===copy.dataset.copyMessage);await navigator.clipboard.writeText(m.content);toast('回复已复制');}if(code){await navigator.clipboard.writeText(code.closest('pre').querySelector('code').textContent);toast('代码已复制');}if(retry){const matched=CollabExecution.retrySource(state.conv.messages,retry.dataset.retryMessage);if(!matched)throw new Error('原任务已不在当前记录中，请从原文归档核对后继续');const {source,failure}=matched;state.route=failure.agent;$('rounds').value='1';state.documents=[];state.uploads=[];for(const ref of source.meta?.references||[]){if(ref.id&&!ref.uploaded&&!ref.upload_id)state.documents.push({id:ref.id,name:ref.name});else state.uploads.push({...ref});}renderRoute();renderAttachments();fillDraft(source.content);toast('已带回这次失败任务的原始要求和附件；仅选择失败方，请核对后发送');}});
document.addEventListener('click',event=>{const button=event.target.closest('[data-open-round-changes]');if(button)changePanel.open({messageId:button.dataset.openRoundChanges,path:button.dataset.changePath||'',opener:button});});
$('document-preview').onclick=guard(async event=>{const code=event.target.closest('.copy-code');if(code){await navigator.clipboard.writeText(code.closest('pre').querySelector('code').textContent);toast('代码已复制');}});
$('nav-documents').onclick=()=>{showPanel();setTab('documents');$('document-search').value='';guard(()=>loadDocuments(''))();};
$('nav-handoffs').onclick=()=>{showPanel();setTab('documents');$('document-search').value='网页交接';guard(()=>loadDocuments('网页交接'))();};
$('document-search').oninput=debounce(()=>loadDocuments());$('document-list').onclick=guard(async event=>{const doc=event.target.closest('[data-document]');if(doc)await viewDocument(doc.dataset.document);});
$('close-document').onclick=()=>$('document-dialog').close();$('attach-document').onclick=()=>{const d=state.preview;if(!state.documents.some(item=>item.id===d.id))state.documents.push({id:d.id,name:d.name});renderAttachments();saveDraft();$('document-dialog').close();toast('已引用，发送时会一并提供给模型');};
$('attachment-chips').onclick=guard(async event=>{const preview=event.target.closest('[data-preview-attachment]');if(preview){await previewAttachment(preview.dataset.previewAttachment);return;}const button=event.target.closest('[data-remove-attachment]');if(!button)return;const value=button.dataset.removeAttachment;if(value.startsWith('doc:'))state.documents=state.documents.filter(d=>d.id!==value.slice(4));else state.uploads.splice(Number(value.slice(7)),1);renderAttachments();saveDraft();});
$('upload-button').onclick=()=>$('file-input').click();
$('file-input').onchange=guard(async event=>{const files=[...event.target.files];event.target.value='';await addFiles(files);});

document.querySelectorAll('[data-template]').forEach(el=>el.onclick=()=>{fillDraft(el.dataset.template);if(innerWidth<=1250)closeOverlays();});
$('save-handoff').onclick=guard(async()=>{const result=await api('/api/handoff',{conversation_id:state.id});$('handoff-path').textContent='交接文件已保存：'+result.path;$('handoff-path').classList.remove('hidden');toast('交接文件已写入今日 Codex 文件夹');});
$('daily-autosave').onchange=guard(async event=>{await api('/api/settings',{daily_autosave:event.target.checked});toast(event.target.checked?'每日归档已开启':'每日归档已关闭；本地对话仍保存');});
$('theme-toggle').onclick=()=>{const dark=document.documentElement.dataset.theme!=='dark';document.documentElement.dataset.theme=dark?'dark':'light';localStorage.setItem('robot-collab:theme',dark?'dark':'light');$('theme-toggle').innerHTML=icon(dark?'sun':'moon');};
$('panel-toggle').onclick=()=>{if(innerWidth<=1250){if($('context-panel').classList.contains('open'))closeOverlays();else showPanel();}else document.querySelector('.app-shell').classList.toggle('panel-hidden');};
$('panel-close').onclick=closeOverlays;$('mobile-menu').onclick=()=>{$('sidebar').classList.toggle('open');$('mobile-scrim').classList.toggle('hidden',!$('sidebar').classList.contains('open'));};$('mobile-scrim').onclick=closeOverlays;
$('open-settings').onclick=()=>$('settings-dialog').showModal();$('close-settings').onclick=()=>$('settings-dialog').close();
function openUsage(){renderUsage();$('usage-dialog').showModal();}$('open-usage').onclick=openUsage;$('credits-footer').onclick=openUsage;$('close-usage').onclick=()=>$('usage-dialog').close();
const refreshHealth=guard(async()=>{await api('/api/health/refresh',{});state.health.refreshing=true;renderHealth();toast('正在刷新接口、模型列表和官方额度');});$('refresh-usage').onclick=refreshHealth;$('refresh-connections').onclick=refreshHealth;
window.addEventListener('beforeunload',saveDraft);document.addEventListener('keydown',event=>{if(event.key==='Escape')closeOverlays();if(event.altKey&&event.key.toLowerCase()==='n'&&!document.querySelector('dialog[open]')){event.preventDefault();guard(createConversation)();}});
window.addEventListener('resize',()=>{if(innerWidth>1250)closeOverlays();});
const uploadBusyChats=new Set();
function isAttachmentBusy(id=state.id){return uploadBusyChats.has(id);}
function fileData(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('文件读取失败'));reader.readAsDataURL(file);});}
async function addFiles(files){if(!state.id)return;const id=state.id;if(isAttachmentBusy(id))throw new Error('这条对话正在读取上一批文件，请稍候');let count=state.uploads.length;uploadBusyChats.add(id);$('send-message').disabled=true;try{for(const file of files){if(count>=4){toast('每轮最多4份附件',true);break;}if(file.size>20*1024*1024){toast(file.name+' 超过20 MB，请选取较小文件',true);continue;}try{toast('正在读取 '+file.name);const doc=await api('/api/uploads',{name:file.name,data:await fileData(file)});if(!doc.attachable)throw new Error(doc.reason||'未提取到可引用内容');const attachment={...doc,content:doc.content};if(state.id===id){state.uploads.push(attachment);renderAttachments();saveDraft();}else{let draft={};try{draft=JSON.parse(localStorage.getItem(draftKey(id))||'{}');}catch{};draft.uploads=[...(draft.uploads||[]),attachment];localStorage.setItem(draftKey(id),JSON.stringify(draft));}count++;toast(file.name+(doc.kind==='image'?' 已添加；图片请选择Codex查看':doc.partial?' 已添加当前片段，点击附件查看读取范围':' 已添加，点击附件可预览'));}catch(error){toast(file.name+'：'+error.message,true);}}}finally{uploadBusyChats.delete(id);if(state.conv)renderConversation();}}
function openAttachmentPreview(doc){$('document-title').textContent=doc.name;$('document-group').textContent=doc.kind==='image'?'图片 · 当前支持Codex查看':doc.total_chars!==undefined?`当前片段 ${doc.start+1}–${doc.end}/${doc.total_chars} 字符 · ${doc.extraction_note||''}`:'已引用的文本内容';$('document-preview').innerHTML=doc.preview_url?`<img class="uploaded-image" src="${esc(doc.preview_url)}" alt="${esc(doc.name)}">`:`<pre><button class="copy-code" type="button">复制代码</button><code>${esc(doc.content||'')}</code></pre>`;$('attach-document').classList.add('hidden');$('document-dialog').showModal();}
async function previewAttachment(value){if(value.startsWith('doc:')){$('attach-document').classList.remove('hidden');await viewDocument(value.slice(4));return;}const doc=state.uploads[Number(value.slice(7))];if(doc)openAttachmentPreview(doc);}
const fileDrop=CollabDrop.controller(files=>guard(()=>addFiles(files))(),show=>document.body.classList.toggle('file-dragging',show));
for(const [name,handler] of Object.entries(fileDrop))document.addEventListener(name,handler);
function renderPermission(){const prefs=state.conv?.preferences||{};$('access-mode').value=prefs.access_mode||'discussion';$('access-mode').disabled=!state.id;$('workdir-label').textContent=prefs.workdir||'工作目录';}
function toolTraceHTML(message){
 if(message.meta?.activity?.length)return '';
 const tools=message.meta?.tool_events||[];if(!tools.length)return '';
 return `<details class="tool-trace legacy-tool-history command-batch"><summary>${CollabExecution.batchSummary?CollabExecution.batchSummary(tools):`工具执行 · ${tools.length} 条历史记录`}</summary><div class="legacy-tool-stream command-batch-items"><p class="legacy-order-note">历史记录未保存文字与工具的穿插位置，以下按已保存的工具顺序展示。</p>${tools.map(tool=>CollabExecution.toolHTML(tool,t=>CollabChatUI.measuredTime(t,message.status==='streaming'&&['running','inProgress'].includes(t.status)))).join('')}</div></details>`;
}
$('access-mode').onchange=guard(async event=>{await api('/api/conversations/'+state.id,{preferences:{access_mode:event.target.value}});await refreshConversation();toast('本对话权限已保存，下一次发送生效');});
$('edit-workdir').onclick=()=>editDialog('更换工作目录',state.conv?.preferences?.workdir||'','工作目录完整路径',value=>api('/api/conversations/'+state.id,{preferences:{workdir:value}}));
function effortLabel(effort){return ({none:'关闭',minimal:'最低',low:'低',medium:'中',high:'高',xhigh:'很高',max:'最高',ultra:'极高'}[effort]||effort)+'（'+effort+'）';}
function renderEffort(){const select=$('codex-effort'),prefs=state.conv?.preferences;const model=state.health.codex?.models?.find(m=>m.id===prefs?.codex_model);const options=model?.reasoningEfforts||[];CollabStableDOM.render(select,options.length?options.map(e=>`<option value="${esc(e.reasoningEffort)}" title="${esc(e.description||'')}" ${e.reasoningEffort===prefs?.codex_effort?'selected':''}>${esc(effortLabel(e.reasoningEffort))}</option>`).join(''):`<option>${esc(prefs?.codex_effort?effortLabel(prefs.codex_effort):'读取中…')}</option>`);select.disabled=!state.id||!options.length;}
const paintQueue=new Set();let paintFrame=0;
function applyStreamDelta(payload){
 if(payload.conversation_id!==state.id)return;
 const message=state.conv?.messages?.find(m=>m.id===payload.id);if(!message){scheduleRefresh();return;}
 const result=CollabStream.applyDelta(message,payload);if(result.kind==='reload'){scheduleRefresh();return;}if(result.kind!=='update')return;
 message.content=result.content;paintQueue.add(message.id);if(paintFrame)return;
 paintFrame=setTimeout(()=>{paintFrame=0;const scroll=$('message-scroll'),position=CollabStableDOM.capture(scroll);
 for(const id of paintQueue){const current=state.conv?.messages?.find(m=>m.id===id);const article=document.querySelector(`[data-message="${CSS.escape(id)}"]`);
 if(current?.status==='streaming'&&article){CollabStableDOM.render(article.querySelector('.message-body'),messageBodyHTML(current));CollabStableDOM.render(article.querySelector('.message-questions'),questionHTML(current));}}
 paintQueue.clear();CollabStableDOM.restore(scroll,position);},80);
}
let localListing={path:'',parent:null},localPreview=null,localEpoch=0;
async function loadLocal(path=$('local-path').value){const epoch=++localEpoch;$('local-status').textContent='正在读取文件夹…';const item=await api('/api/local/files?path='+encodeURIComponent(path)+'&q='+encodeURIComponent($('local-search').value)+'&recursive='+($('local-recursive').checked?'1':'0'));if(epoch!==localEpoch)return;localListing=item;$('local-path').value=item.path;$('local-up').disabled=item.parent===null;$('local-list').innerHTML=item.entries.length?item.entries.map(e=>`<button class="local-file" data-local-path="${esc(e.path)}" data-local-directory="${e.directory?'1':'0'}">${icon(e.directory?'folder-open':'file-text')}<span><strong>${esc(e.name)}</strong><small>${esc(e.directory?'文件夹':(e.bytes/1024).toFixed(1)+' KB'+(e.protected?' · 凭据内容不引用':''))}</small></span></button>`).join(''):'<p class="section-description">没有匹配文件。</p>';$('local-status').textContent=(item.path||'本机磁盘')+' · '+item.entries.length+' 项'+(item.limited?' · 本次结果达到上限，请进入更具体的文件夹再查找':'')+($('local-recursive').checked&&$('local-search').value?' · 搜索当前目录及最多3层子目录':'');}
async function previewLocal(path,start=0){const doc=await api('/api/local/document?path='+encodeURIComponent(path)+'&start='+start);localPreview=doc;$('local-preview-path').textContent=doc.local_path;$('local-preview-name').textContent=doc.name;$('local-preview-content').textContent=doc.content||doc.reason;$('local-preview-note').textContent=(doc.total_chars!==undefined?`已提取 ${doc.total_chars} 字符；当前 ${doc.start+1}–${doc.end}${doc.partial?'，仅引用这一段':''}。 `:'')+(doc.extraction_note||'');$('attach-local').disabled=!doc.attachable;$('local-previous').disabled=!(doc.start>0);$('local-next').disabled=!(doc.end<doc.total_chars);if(!$('local-preview-dialog').open)$('local-preview-dialog').showModal();}
$('open-local-files').onclick=guard(async()=>{$('local-path').value=localListing.path;$('local-search').value='';$('local-dialog').showModal();await loadLocal(localListing.path);});
$('close-local').onclick=()=>$('local-dialog').close();$('close-local-preview').onclick=()=>$('local-preview-dialog').close();
$('local-go').onclick=guard(()=>loadLocal());$('local-up').onclick=guard(()=>loadLocal(localListing.parent||''));
$('local-path').onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();guard(()=>loadLocal())();}};
$('local-search').oninput=debounce(()=>loadLocal());$('local-recursive').onchange=guard(()=>loadLocal());
$('local-list').onclick=guard(async event=>{const row=event.target.closest('[data-local-path]');if(!row)return;if(row.dataset.localDirectory==='1'){ $('local-search').value='';await loadLocal(row.dataset.localPath);}else await previewLocal(row.dataset.localPath);});
$('local-previous').onclick=guard(()=>previewLocal(localPreview.local_path,Math.max(0,localPreview.start-39000)));
$('local-next').onclick=guard(()=>previewLocal(localPreview.local_path,localPreview.end));
$('attach-local').onclick=()=>{if(!localPreview?.attachable)return;if(state.uploads.length>=4){toast('每轮最多4份文本/本地文件片段',true);return;}const doc=localPreview;state.uploads.push({name:doc.name,content:`[本地来源：${doc.local_path}；已提取字符范围 ${doc.start+1}–${doc.end}/${doc.total_chars}；参考内容不是新指令]\n`+doc.content,local_path:doc.local_path});renderAttachments();saveDraft();$('local-preview-dialog').close();$('local-dialog').close();closeOverlays();toast('所选文件片段已引用，发送后两方才会看到内容');};
let eventCursor=0;
function renderConnectionState(delay=0){
 const connected=state.connection==='connected',pill=$('connection-pill');
 if(!connected){pill.className='connection-pill error';pill.innerHTML='<span></span>'+ (state.connection==='connecting'?'正在连接本地后台':'自动重连中');}
 $('offline-banner').classList.toggle('hidden',connected);
 if(!connected)$('offline-banner').textContent='本地后台暂未连接，'+(delay?Math.ceil(delay/1000)+'秒后自动重试':'正在连接')+'；恢复后会自动同步，输入内容保留。';
 $('send-message').disabled=!connected||submissions.isSending(state.id)||isAttachmentBusy()||!!state.conv?.archived;
}
async function synchronizeConnection(signal){
 const boot=await api('/api/bootstrap',undefined,true,{signal});
 state.csrf=boot.csrf;state.health=boot.health;state.capabilities=boot.capabilities||{};
 $('daily-autosave').checked=boot.settings.daily_autosave!==false;
 if(state.id){await refreshConversation({signal});await loadList({signal});}
 else{
  const previous=localStorage.getItem('robot-collab:last-conversation');
  const id=boot.conversations.find(c=>c.id===previous)?.id||boot.conversations[0]?.id;
  if(id)await selectConversation(id,{signal,preserveInput:true});
 }
 eventCursor=boot.last_event;
}
const reconnect=CollabReconnect.create({
 synchronize:synchronizeConnection,
 createStream:()=>connectEvents(eventCursor),
 onState:(phase,delay)=>{state.connection=phase;renderConnectionState(delay);if(phase==='connected')renderHealth();}
});
function init(){
 const theme=localStorage.getItem('robot-collab:theme');if(theme){document.documentElement.dataset.theme=theme;$('theme-toggle').innerHTML=icon(theme==='dark'?'sun':'moon');}
 void reconnect.start();
 window.addEventListener('online',()=>void reconnect.wake());
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)void reconnect.wake();});
 window.addEventListener('pagehide',event=>{if(!event.persisted)reconnect.stop();});
 window.addEventListener('pageshow',event=>{if(event.persisted)void reconnect.wake();});
 setInterval(()=>{if(document.hidden)return;for(const el of document.querySelectorAll('[data-live-duration]')){const value=CollabChatUI.duration(Number(el.dataset.accumulated||0)+(Date.now()-Date.parse(el.dataset.liveDuration))/1000);if(el.textContent!==value)el.textContent=value;}},1000);
 setInterval(()=>{if(!document.hidden&&state.connection==='connected'&&state.health.updated&&Date.now()-new Date(state.health.updated).getTime()>300000&&!state.health.refreshing)guard(refreshHealth)();},60000);
}
init();

function renderTaskFlow(){$('task-flow').classList.add('hidden');}

function syncAvailableHeight(){const root=document.documentElement;root.style.setProperty('--available-height',window.innerHeight+'px');root.style.setProperty('--flow-height',Math.max(70,Math.min(140,Math.round(window.innerHeight*.3)))+'px');root.classList.toggle('short-viewport',window.innerHeight<600);}
window.addEventListener('resize',syncAvailableHeight,{passive:true});syncAvailableHeight();

CollabComposerProgress.install($('active-progress'));
CollabWorkbench.install({doc:document,api,conversation:()=>state.conv,refresh:refreshConversation,toast,ui:CollabChatUI,stable:CollabStableDOM,saveDraft});
$('waiting-filter').onclick=guard(async()=>{state.attentionOnly=!state.attentionOnly;await loadList();});
 $('active-progress').onclick=event=>{const button=event.target.closest('[data-show-plan]');if(!button)return;const plan=document.querySelector(`[data-message="${CSS.escape(button.dataset.showPlan)}"] .message-plan`);if(plan){if(plan.tagName==='DETAILS')plan.open=true;plan.scrollIntoView({behavior:'auto',block:'start'});}};

const debouncedDraft=debounce(saveDraft,250);
let composerManualHeight=60;
function composerMinimum(){return parseFloat(getComputedStyle($('message-input')).minHeight)||52;}
function composerMaximum(){
 const el=$('message-input'),main=document.querySelector('.main-panel');
 const extras=main.querySelector('.topbar').offsetHeight+main.querySelector('.conversation-header').offsetHeight+$('composer').offsetHeight-el.offsetHeight+40;
 return Math.max(composerMinimum(),Math.min(Math.round(window.innerHeight*.5),window.innerHeight-extras-Math.min(140,Math.round(window.innerHeight*.28))));
}
function sizeComposer(){
 CollabComposerLayout.resize($('message-input'),composerManualHeight,composerMaximum());
}
const resizeHandle=$('composer-resize-handle');let resizing=null;
resizeHandle.onpointerdown=event=>{if(event.button!==0)return;resizing={y:event.clientY,height:$('message-input').clientHeight};resizeHandle.setPointerCapture(event.pointerId);document.body.classList.add('composer-resizing');event.preventDefault();};
resizeHandle.onpointermove=event=>{if(!resizing)return;composerManualHeight=Math.max(52,Math.min(composerMaximum(),resizing.height+resizing.y-event.clientY));sizeComposer();};
function finishComposerResize(){resizing=null;document.body.classList.remove('composer-resizing');saveDraft();}
resizeHandle.onpointerup=finishComposerResize;resizeHandle.onpointercancel=finishComposerResize;
resizeHandle.onkeydown=event=>{if(!['ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();composerManualHeight=Math.max(52,Math.min(composerMaximum(),$('message-input').clientHeight+(event.key==='ArrowUp'?24:-24)));sizeComposer();saveDraft();};
function compressionHTML(c){
 const latest=c.compactions?.at(-1);if(!latest)return c.compression?.state==='failed'?'<p class="compression-note">自动整理未完成，旧对话原文已保留。</p>':'';
 const count=c.compactions.reduce((sum,item)=>sum+(item.meta?.message_count||0),0);
 return `<details class="compression-note" id="compression-summary"><summary>已自动压缩 ${count} 条旧消息 · 查看摘要</summary><div class="markdown">${md.render(latest.summary)}</div><small class="wb-compaction-metrics">${latest.meta?.original_estimated_tokens!=null?`压缩部分约 ${latest.meta.original_estimated_tokens.toLocaleString()} → ${latest.meta.summary_estimated_tokens.toLocaleString()} Tokens（估算），保留 ${latest.meta.retained_message_count} 条近期消息`:`旧摘要版本 · 未记录 Tokens 估算`} · 摘要 ${esc(latest.id.slice(0,8))}</small><div class="compression-archives">${c.compactions.map(item=>`<a href="/api/compaction/archive?id=${encodeURIComponent(item.id)}">原文归档 · ${dateText(item.created)}</a>`).join('')}</div></details>`;
}
$('execution-strategy').onchange=()=>{if($('execution-strategy').value==='discuss_first'&&Number($('rounds').value)<2){$('rounds').value='2';toast('首轮讨论需要两轮，已切换为2轮');}saveDraft();};
window.addEventListener('resize',sizeComposer);
let composerWidth=0;new ResizeObserver(entries=>{const width=entries[0].contentRect.width;if(Math.abs(width-composerWidth)>1){composerWidth=width;requestAnimationFrame(sizeComposer);}debouncedDraft();}).observe($('message-input'));
$('messages').addEventListener('submit',guard(async event=>{
 const form=event.target.closest('[data-answer-question]');if(!form)return;event.preventDefault();
 const answers={};for(const part of form.querySelectorAll('[data-question-part]')){const free=part.querySelector('[data-free-answer]').value.trim(),selected=Array.from(part.querySelectorAll('input:checked')).map(el=>el.value);if(!free&&!selected.length)throw new Error('请先选择或填写自己的答案');answers[part.dataset.questionPart]=free?[free]:selected;}
 const button=form.querySelector('[type=submit]');button.disabled=true;
 try{const source=state.conv.messages.find(m=>m.id===form.dataset.sourceMessage);
 if(state.capabilities?.user_questions){await api('/api/answers',{conversation_id:state.id,question_id:form.dataset.answerQuestion,message_id:source.id,answers});}
 else{const text='回答 '+source.agent+' 的问题：'+CollabUserInput.proseQuestion(source.content)+'\n答案：'+Object.values(answers).flat().join('；');const root=state.conv.messages.find(m=>m.role==='user'&&m.meta?.job_id===source.meta?.job_id&&m.meta?.delivery?.mode!=='steer');if(busy()&&state.conv.job?.id===source.meta?.job_id)await api('/api/steer',{conversation_id:state.id,content:text,client_key:'answer:'+source.id});else await api('/api/messages',{conversation_id:state.id,content:'继续原任务：'+(root?.content||'')+'\n'+text,route:root?.meta?.route||source.agent,rounds:root?.meta?.rounds||1,send_mode:'queue',client_key:'answer:'+source.id});}
 answeredQuestions[source.id]=CollabUserInput.proseQuestion(source.content);toast('答案已提交，继续处理原任务');await refreshConversation();
 }catch(error){button.disabled=false;throw error;}
}));

let storageNavigation=null;
async function refreshAfterStorage(change={}){
 if(storageNavigation)return storageNavigation;
 storageNavigation=(async()=>{
  const removed=change.conversation_ids||[];
  if(change.action==='purge_conversations')for(const id of removed)localStorage.removeItem(draftKey(id));
  if(removed.includes(state.id)){
   if(change.action!=='purge_conversations')saveDraft();
   state.id=null;state.conv=null;++state.selectEpoch;
   const visible=await api('/api/conversations?archived='+(state.archived?'1':'0'));
   if(visible.length)await selectConversation(visible[0].id);
   else{state.archived=false;const recent=await api('/api/conversations');if(recent.length)await selectConversation(recent[0].id);else await createConversation();}
  }else await loadList();
 })().finally(()=>{storageNavigation=null;});
 return storageNavigation;
}
CollabStorage.install({doc:document,api,onChanged:refreshAfterStorage,toast});

changePanel=CollabChanges.install({doc:document,conversation:()=>state.conv,execution:CollabExecution,workbench:CollabWorkbench,stable:CollabStableDOM,toast});
