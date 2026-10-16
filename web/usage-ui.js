(function(root){
 'use strict';
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const fmt=n=>typeof n==='number'&&Number.isFinite(n)?n.toLocaleString('en-US'):'未上报';
 function credit(meta){
  const selected=String(meta.credit_source||'').startsWith('user_selected_');
  const n=selected?meta.reported_credit:meta.credit;
  if(typeof n==='number'&&n>0)return `${n.toFixed(3).replace(/0+$/,'').replace(/\.$/,'')} 积分${meta.credit_is_partial?'（部分）':''}`;
  return typeof n==='number'?`0 积分${meta.credit_is_partial?'（部分）':''}`:'积分未上报';
 }
 function detail(meta){
  const u=meta.token_usage||{},row=(label,value,cls='')=>`<div class="usage-detail-row ${cls}"><span>${label}</span><b>${fmt(value)}</b></div>`;
  const cache=typeof u.cache_read==='number'&&typeof u.input==='number'&&u.cache_read<=u.input;
  const miss=cache?u.input-u.cache_read:undefined;
  const rate=cache&&u.input>0?(u.cache_read/u.input*100):null;
  const expected=u.expected_requests||0,reported=u.reported_requests||0;
  return `<strong class="usage-detail-title">Token 消耗明细 <span>总计 ${fmt(u.total)}</span></strong>${row('输入',u.input,'usage-primary')}${row('缓存命中',u.cache_read,'usage-sub')}${row('缓存未命中（含写入）',miss,'usage-sub')}${row('缓存写入',u.cache_write,'usage-sub')}${row('输出（含工具调用）',u.output,'usage-primary')}${row('其中推理 Tokens',u.reasoning,'usage-sub')}${rate===null?'':`<div class="usage-cache-rate"><span>缓存命中率</span><b>${rate.toFixed(1)}%</b><meter min="0" max="100" value="${rate}">${rate.toFixed(1)}%</meter></div>`}<p>${u.total===undefined?'这条回复尚未保存实际用量。':u.partial?`当前仅收到部分用量${expected?`（${reported} / ${expected} 次调用）`:''}，总计仍会更新。`:u.scope==='result'?'整条回复的 CLI 汇总用量，包含中间工具调用。':`已累计 ${reported} 次模型调用；流式重复事件不重复计数。`}</p><p>积分和 Tokens 由后台自动提取实际回执；返回 0 时显示 0，未上报不等于免费。自带 API 的服务商费用另计。${u.reasoning===undefined?' 推理细分未上报。':''} 缓存明细以 CLI 报告为准。</p>`;
 }
 function html(message){
  if(message.agent!=='codebuddy')return '';
  const meta=message.meta||{},u=meta.token_usage||{},id='usage-'+message.id;
  return `<span class="reply-credit">${esc(credit(meta))}</span><span class="usage-wrap"><button type="button" class="usage-total" data-usage="${esc(id)}" aria-describedby="${esc(id)}" aria-expanded="false">Tokens: ${fmt(u.total)}${u.partial?' · 部分':''}</button><span class="usage-tooltip" id="${esc(id)}" role="tooltip" popover="manual">${detail(meta)}</span></span>`;
 }
 function install(doc){
  let active=null,button=null,timer=null,pinned=false;
  function close(){if(active){if(active.matches(':popover-open'))active.hidePopover();active.classList.remove('usage-visible');}if(button)button.setAttribute('aria-expanded','false');active=button=null;pinned=false;}
  function show(target){
   clearTimeout(timer);const next=doc.getElementById(target.dataset.usage);if(!next)return;
   if(active!==next){close();active=next;button=target;if(active.showPopover)active.showPopover();else active.classList.add('usage-visible');}
   button.setAttribute('aria-expanded','true');
   const r=button.getBoundingClientRect(),width=Math.min(334,root.innerWidth-24),h=active.getBoundingClientRect().height;
   active.style.width=width+'px';active.style.left=Math.max(12,Math.min(r.left,root.innerWidth-width-12))+'px';
   active.style.top=Math.max(12,r.top-h-10>=12?r.top-h-10:Math.min(r.bottom+10,root.innerHeight-h-12))+'px';
  }
  doc.addEventListener('pointerover',e=>{const b=e.target.closest('[data-usage]');if(b)show(b);else if(e.target.closest('.usage-tooltip'))clearTimeout(timer);});
  doc.addEventListener('pointerout',e=>{if(e.target.closest('.usage-wrap')&&!pinned)timer=setTimeout(close,160);});
  doc.addEventListener('focusin',e=>{const b=e.target.closest('[data-usage]');if(b)show(b);});
  doc.addEventListener('focusout',e=>{if(e.target.closest('.usage-wrap')&&!pinned)timer=setTimeout(close,160);});
  doc.addEventListener('click',e=>{const b=e.target.closest('[data-usage]');if(b){if(pinned&&button===b)close();else{show(b);pinned=true;}}else if(!e.target.closest('.usage-tooltip'))close();});
  doc.addEventListener('keydown',e=>{if(e.key==='Escape')close();});
  root.addEventListener('resize',close);doc.addEventListener('scroll',close,true);
 }
 const api={credit,detail,html};
 if(typeof module==='object'&&module.exports)module.exports=api;else{root.CollabUsage=api;install(document);}
})(typeof window==='object'?window:this);
