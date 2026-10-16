(function(root){
 'use strict';
 const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function diffLines(text){
  let before=null,after=null,oldLeft=0,newLeft=0;
  return String(text||'').split('\n').map(text=>{
   const hunk=text.match(/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/);
   if(hunk){before=Number(hunk[1]);after=Number(hunk[3]);oldLeft=Number(hunk[2]??1);newLeft=Number(hunk[4]??1);return {kind:'hunk',text};}
   if(before===null||oldLeft===0&&newLeft===0)return {kind:'header',text};
   if(text.startsWith('+')&&newLeft>0){newLeft--;return {kind:'add',before:'',after:after++,text};}
   if(text.startsWith('-')&&oldLeft>0){oldLeft--;return {kind:'remove',before:before++,after:'',text};}
   if(text.startsWith(' ')&&oldLeft>0&&newLeft>0){oldLeft--;newLeft--;return {kind:'context',before:before++,after:after++,text};}
   return {kind:'header',text};
  });
 }
 function counts(change){const lines=diffLines(change.diff);return {added:lines.filter(l=>l.kind==='add').length,removed:lines.filter(l=>l.kind==='remove').length};}
 function changesHTML(tool,zoom=true){
  return (tool.changes||[]).map((change,index)=>{
   const n=counts(change),state=['completed','success'].includes(tool.status)?'工具报告已完成':tool.status==='failed'?'修改未成功':'修改中／待确认';
   const note=change.scope==='snippet'?'本次编辑片段；行号相对片段':change.scope==='submitted'?'提交内容，尚无修改前全文':state;
   const rows=change.diff?`<div class="diff-scroll"><table class="diff-table"><tbody>${diffLines(change.diff).map(l=>`<tr class="diff-${l.kind}"><td>${l.before??''}</td><td>${l.after??''}</td><td><code>${esc(l.text)}</code></td></tr>`).join('')}</tbody></table></div>`:`<pre class="write-preview">${esc(change.preview||'工具未提供差异正文')}</pre>`;
   return `<section class="code-change"><div class="diff-heading">${zoom?`<button class="diff-path-button" data-diff-tool="${esc(tool.id)}" data-diff-index="${index}" title="在侧边查看代码变更">${esc(change.path||'代码变更')}</button>`:`<strong>${esc(change.path||'代码变更')}</strong>`}${change.diff?`<span class="diff-added">+${n.added}</span><span class="diff-removed">−${n.removed}</span>`:''}${zoom?`<button class="diff-expand" data-diff-tool="${esc(tool.id)}" data-diff-index="${index}">侧边查看</button>`:''}</div><p class="diff-note">${esc(note)}${change.truncated?' · 显示片段，完整差异超出展示长度':''}</p>${rows}</section>`;
  }).join('');
 }
 function toolLabel(tool){
  if((tool.type==='commandExecution'||tool.name==='Bash'||tool.name==='PowerShell')&&/\brg(?:\s|$)/.test(tool.command||''))return '搜索本地资料';
  return ({Read:'读取文件',Glob:'查找文件',Grep:'搜索内容',Edit:'修改文件',Write:'写入文件',commandExecution:'执行命令',fileChange:'修改文件',mcpToolCall:'调用工具',report_task_plan:'更新步骤',coordinate_resources:'协调资源'}[tool.name]||tool.name||tool.type||'工具');
 }
 function failureReason(tool){
  if(tool.status!=='failed')return '';
  if(/\brg(?:\s|$)/.test(tool.command||'')&&/CommandNotFoundException|not found|无法将.*rg|not recognized/i.test(tool.output||''))return '本机未找到搜索工具 rg';
  return tool.exit_code!==undefined?'命令退出码 '+tool.exit_code:'查看具体错误';
 }
 function routine(tool){return tool.type==='hook'||['资源协调','coordinate_resources','report_task_plan','TaskCreate','TaskUpdate','TodoWrite'].includes(tool.name);}
 function batchSummary(tools){
  const commands=tools.filter(t=>!routine(t)).length;
  const running=tools.filter(t=>['running','inProgress','preparing'].includes(t.status)).length;
  const failed=tools.filter(t=>t.status==='failed').length,cancelled=tools.filter(t=>t.status==='cancelled').length;
  const waiting=tools.filter(t=>['waiting_input','waiting'].includes(t.status)).length;
  const label=commands?`${running?'正在运行':'运行了'} ${commands} 个命令`:`步骤与协调 · ${tools.length} 项更新`;
  return `<span class="command-batch-icon" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1"><rect x="1.5" y="2" width="13" height="12" rx="2"/><path d="m4 5 2 2-2 2m4 1h3"/></svg></span><span class="command-batch-label">${label}</span>${running?`<small class="command-batch-running">${running} 项执行中</small>`:''}${waiting?`<small class="command-batch-waiting">${waiting} 项等待回答</small>`:''}${failed?`<small class="command-batch-failed">${failed} 项失败</small>`:''}${cancelled?`<small>${cancelled} 项已取消</small>`:''}<span class="command-batch-arrow" aria-hidden="true">›</span>`;
 }
 function excerpt(tool){
  const path=tool.path||tool.file_path||(tool.paths||[]).join(' · ')||(tool.changes||[]).map(c=>c.path).join(' · ');
  if(path)return path;
  return String(tool.command||tool.pattern||'').replace(/^.*?\s-(?:NoProfile\s+)?Command\s+/i,'').replace(/[\r\n]+/g,' ').slice(0,400);
 }
 function toolHTML(tool,time=()=> ''){
  const status=({completed:'已完成',success:'已完成',running:'执行中',inProgress:'执行中',preparing:'准备中',failed:'失败',cancelled:'已取消'}[tool.status]||tool.status||'');
  const name=toolLabel(tool),reason=failureReason(tool);
  const timing=typeof tool.elapsed_s==='number'&&tool.elapsed_s>0&&tool.elapsed_s<1&&!['running','inProgress','preparing'].includes(tool.status)?'不足1秒':time(tool);
  const patches=tool.changes||[],hasDiff=patches.some(c=>c.diff),sum=patches.reduce((a,c)=>{const n=counts(c);return {added:a.added+n.added,removed:a.removed+n.removed};},{added:0,removed:0});
  const paths=tool.path||tool.file_path||(tool.paths||[]).join('\n');
  const summary=excerpt(tool),running=['running','inProgress','preparing'].includes(tool.status);
  return `<details class="execution-tool tool-line${tool.status==='failed'?' tool-line-failed':''}${running?' tool-line-running':''}" data-tool-id="${esc(tool.id)}"><summary><span class="tool-line-icon" aria-hidden="true">${running?'◌':tool.status==='failed'?'!':'<svg width=14 height=14 viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1"><rect x="1.5" y="2" width="13" height="12" rx="2"/><path d="m4 5 2 2-2 2m4 1h3"/></svg>'}</span><span class="tool-call-name" title="${esc(tool.name||tool.type)}">${esc(name)}</span><span class="tool-excerpt" title="${esc(summary)}">${esc(reason||summary)}</span>${patches.length?`<span class="change-count">${patches.length} 个文件 ${hasDiff?`<b class="diff-added">+${sum.added}</b> <b class="diff-removed">−${sum.removed}</b>`:'· 提交内容'}</span>`:''}<span class="tool-call-state">${esc(status)} ${timing}</span></summary>${reason?`<p class="tool-failure-reason">${esc(reason)}</p>`:''}<div class="execution-tool-detail">${tool.command?`<div class="tool-detail-heading"><span>Shell</span><button type="button" class="text-button" data-copy-tool="${esc(tool.id)}" aria-label="复制命令">复制</button></div><pre class="tool-command"><code>${esc(tool.command)}</code></pre>`:''}${paths?`<p class="tool-path">${esc(paths)}</p>`:''}${changesHTML(tool)}${tool.type==='fileChange'&&!patches.length?'<p class="diff-note">这条历史记录未保存差异正文。</p>':''}${tool.output?`<pre class="tool-output">${esc(tool.output)}</pre>`:''}${tool.output_truncated?'<small>输出显示前3000字。</small>':''}${tool.exit_code!==undefined?`<small>退出码 ${esc(tool.exit_code)}</small>`:''}</div></details>`;
 }
 function groupHTML(events,time){
  const parts=[];
  for(let i=0;i<events.length;i++){
   const e=events[i];
   if(routine(e.tool)&&e.tool.status!=='failed'){
    const internal=[e];while(i+1<events.length&&routine(events[i+1].tool)&&events[i+1].tool.status!=='failed')internal.push(events[++i]);
    parts.push(`<details class="tool-coordination" data-tool-id="coord-${esc(e.id)}"><summary>步骤与协调 · ${internal.length} 项更新</summary>${internal.map(x=>toolHTML(x.tool,time)).join('')}</details>`);
   }else parts.push(`<div data-activity-id="${esc(e.id)}">${toolHTML(e.tool,time)}</div>`);
  }
  const content=`<div class="tool-lines">${parts.join('')}</div>`;
  if(!events.some(e=>!routine(e.tool)))return content;
  return `<details class="command-batch" data-tool-id="batch-${esc(events[0].id)}"><summary>${batchSummary(events.map(e=>e.tool))}</summary><div class="command-batch-items">${content}</div></details>`;
 }
 function questionIds(message){return (message.meta?.activity||[]).filter(e=>e.type==='question').map(e=>e.question_id);}
 function html(message,renderText,renderQuestion,time,followups=''){
  const events=message.meta?.activity||[];
  if(!events.length)return followups+renderText(message.content||'');
  let point=events.findIndex(e=>e.type==='text'&&e.phase==='final_answer');
  if(point<0)point=message.status==='streaming'?events.length:events.findLastIndex(e=>e.type==='text');
  if(point<0)point=events.length;
  const parts=[];
  for(let index=0;index<events.length;index++){
   if(index===point)parts.push(followups);
   const e=events[index];
   if(e.type==='tool'){
    const group=[e];while(index+1<events.length&&events[index+1].type==='tool'&&index+1!==point)group.push(events[++index]);
    parts.push(`<div class="execution-item" data-activity-id="${esc(e.id)}">${groupHTML(group,time)}</div>`);
   }else parts.push(`<div class="execution-item" data-activity-id="${esc(e.id)}">${e.type==='text'?`<div class="execution-text">${renderText(e.text||'')}</div>`:e.type==='question'?renderQuestion(e.question_id):''}</div>`);
  }
  if(point===events.length)parts.push(followups);
  return `<div class="execution-stream">${parts.join('')}</div>`;
 }
 function retrySource(messages,failedId){
  const index=messages.findIndex(m=>m.id===failedId);if(index<0)return null;
  const failure=messages[index],job=failure.meta?.job_id;
  const eligible=m=>m.role==='user'&&!['steer','answer'].includes(m.meta?.delivery?.mode)&&!m.meta?.deleted;
  const source=job?messages.find(m=>eligible(m)&&m.meta?.job_id===job):messages.slice(0,index).reverse().find(eligible);
  return source?{source,failure}:null;
 }
 const api={diffLines,counts,changesHTML,toolHTML,toolLabel,failureReason,batchSummary,groupHTML,questionIds,html,retrySource};
 if(typeof module==='object'&&module.exports)module.exports=api;else root.CollabExecution=api;
})(typeof window==='object'?window:this);
