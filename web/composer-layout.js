/* Measure an off-screen copy; never collapse the focused textarea to measure it. */
(function(root){
 'use strict';
 const mirrors=new WeakMap();
 const properties=['fontFamily','fontSize','fontWeight','fontStyle','lineHeight','letterSpacing','wordSpacing','textIndent','textTransform','tabSize','paddingTop','paddingBottom','paddingLeft','paddingRight','borderTopWidth','borderBottomWidth','borderLeftWidth','borderRightWidth','borderStyle','boxSizing','whiteSpace','overflowWrap','wordBreak','scrollbarGutter'];
 function measure(input){
  let cached=mirrors.get(input);
  if(!cached){const mirror=input.ownerDocument.createElement('textarea');mirror.rows=1;mirror.tabIndex=-1;mirror.setAttribute('aria-hidden','true');mirror.setAttribute('inert','');
   mirror.style.cssText='position:fixed;left:-10000px;top:0;visibility:hidden;pointer-events:none;height:0;min-height:0;max-height:none;overflow:hidden;resize:none;contain:layout style;';
   input.ownerDocument.body.append(mirror);cached={mirror};mirrors.set(input,cached);}
  const style=getComputedStyle(input),width=input.getBoundingClientRect().width;
  const signature=[width,input.value,...properties.map(p=>style[p])].join('\u0000');
  if(signature===cached.signature)return cached.height;
  for(const property of properties)cached.mirror.style[property]=style[property];
  cached.mirror.style.width=width+'px';cached.mirror.value=input.value;
  cached.height=Math.ceil(cached.mirror.scrollHeight+(parseFloat(style.borderTopWidth)||0)+(parseFloat(style.borderBottomWidth)||0));cached.signature=signature;
  return cached.height;
 }
 function resize(input,manual,maximum){
  const minimum=parseFloat(getComputedStyle(input).minHeight)||52;
  const max=Math.floor(maximum),height=Math.min(max,Math.max(minimum,Math.round(manual),measure(input)));
  const target=height+'px',limit=max+'px';
  if(input.style.maxHeight!==limit)input.style.maxHeight=limit;
  if(input.style.height!==target)input.style.height=target;
  return height;
 }
 root.CollabComposerLayout={measure,resize};
})(typeof globalThis==='object'?globalThis:this);
