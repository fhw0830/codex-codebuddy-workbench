/* Update existing reading surfaces without replacing open details or selected text. */
(function(root){
  'use strict';
  const cache=new WeakMap();
  const key=node=>node.nodeType===1?(node.getAttribute('data-round-key')||node.getAttribute('data-message')||node.getAttribute('data-activity-id')||node.getAttribute('data-followup-message')||node.getAttribute('data-answer-message')||node.getAttribute('data-tool-id')||node.getAttribute('data-plan-step')||node.getAttribute('data-conversation')||node.getAttribute('data-task')||node.getAttribute('data-question-card')||node.getAttribute('data-question-host')||node.getAttribute('data-question-part')||node.id||null):null;
  const compatible=(a,b)=>a&&a.nodeType===b.nodeType&&(a.nodeType!==1||a.tagName===b.tagName)&&key(a)===key(b);
  function patchNode(current,next){
    if(current.nodeType!==1){
      if(current.nodeValue!==next.nodeValue){
        const before=current.nodeValue||'',after=next.nodeValue||'';
        let prefix=0,suffix=0;
        while(prefix<before.length&&prefix<after.length&&before[prefix]===after[prefix])prefix++;
        while(suffix<before.length-prefix&&suffix<after.length-prefix&&before[before.length-1-suffix]===after[after.length-1-suffix])suffix++;
        current.replaceData(prefix,before.length-prefix-suffix,after.slice(prefix,after.length-suffix));
      }
      return;
    }
    for(const attribute of Array.from(current.attributes)){
      if((current.hasAttribute('popover')&&attribute.name==='style')||(current.hasAttribute('data-usage')&&attribute.name==='aria-expanded'))continue;
      if(current.tagName==='DETAILS'&&attribute.name==='open')continue;
      if(!next.hasAttribute(attribute.name))current.removeAttribute(attribute.name);
    }
    for(const attribute of Array.from(next.attributes)){
      if(current.hasAttribute('data-usage')&&attribute.name==='aria-expanded')continue;
      if(current.tagName==='DETAILS'&&attribute.name==='open')continue;
      if(current.getAttribute(attribute.name)!==attribute.value)current.setAttribute(attribute.name,attribute.value);
    }
    patchChildren(current,next);
  }
  function patchChildren(parent,next){
    const original=Array.from(parent.childNodes),retained=new Set();
    const keyed=new Map(original.filter(key).map(node=>[key(node),node]));
    let cursor=parent.firstChild;
    for(const desired of Array.from(next.childNodes)){
      let current=key(desired)?keyed.get(key(desired)):compatible(cursor,desired)&&!retained.has(cursor)?cursor:null;
      if(!compatible(current,desired))current=null;
      if(!current){current=desired.cloneNode(true);parent.insertBefore(current,cursor);}
      else {if(current!==cursor)parent.insertBefore(current,cursor);patchNode(current,desired);}
      retained.add(current);cursor=current.nextSibling;
    }
    for(const node of original)if(!retained.has(node))node.remove();
  }
  function render(element,html){
    if(cache.get(element)===html)return false;
    const template=element.ownerDocument.createElement('template');template.innerHTML=html;
    patchChildren(element,template.content);cache.set(element,html);return true;
  }
  function capture(scroll){
    const doc=scroll.ownerDocument,selection=doc.getSelection();
    const selected=selection&&!selection.isCollapsed&&scroll.contains(selection.anchorNode);
    const follow=!selected&&scroll.scrollHeight-scroll.scrollTop-scroll.clientHeight<24;
    const top=scroll.getBoundingClientRect().top;
    const anchor=Array.from(scroll.querySelectorAll('.tool-row, .message-body p, .message-body pre, .message-body table, .message-heading, summary')).find(el=>el.getBoundingClientRect().bottom>top+2);
    return {follow,top:scroll.scrollTop,anchor,offset:anchor?.getBoundingClientRect().top};
  }
  function restore(scroll,snapshot){
    if(snapshot.follow){scroll.scrollTop=scroll.scrollHeight;return;}
    scroll.scrollTop=snapshot.anchor?.isConnected?snapshot.top+snapshot.anchor.getBoundingClientRect().top-snapshot.offset:snapshot.top;
  }
  const api={render,capture,restore};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.CollabStableDOM=api;
})(typeof globalThis!=='undefined'?globalThis:this);
