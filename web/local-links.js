(function(root){
 'use strict';
 function decode(value){try{return decodeURIComponent(value);}catch{return value;}}
 function path(value,base=''){
  let raw=String(value||'').trim();
  if(/^file:\/\//i.test(raw)){
   if(!/^file:\/\/\//i.test(raw))return null;raw=raw.replace(/^file:\/\/\//i,'/');
  }else if(/^[a-z][a-z0-9+.-]*:/i.test(raw)&&!/^\/?[a-z]:[\\/]/i.test(raw))return null;
  raw=decode(raw).replace(/(?:#L?\d+(?:-L?\d+)?|:\d+(?::\d+)?)$/,'');
  if(/^\/[a-z]:[\\/]/i.test(raw))raw=raw.slice(1);
  if(/^(?:\\\\|\/\/)/.test(raw)||raw.includes('\0'))return null;
  if(/^[a-z]:[\\/]/i.test(raw))return raw.replace(/\\/g,'/');
  if(raw.startsWith('/')&&/\.[a-z0-9_-]{1,12}$/i.test(raw))return raw;
  if(raw.includes('?')||raw.includes('#')||! /\.[a-z0-9_-]{1,12}$/i.test(raw))return null;
  if(!base)return raw;
  if(!/^(?:[a-z]:[\\/]|\/)/i.test(base))return null;
  return base.replace(/\\/g,'/').replace(/\/$/,'')+'/'+raw.replace(/\\/g,'/');
 }
 function install(md){
  const valid=md.validateLink.bind(md),render=md.renderer.rules.link_open;
  md.validateLink=value=>Boolean(path(value))||valid(value);
  md.renderer.rules.link_open=(tokens,index,options,env,self)=>{
   const token=tokens[index],raw=token.attrGet('href');
   if(path(raw)){token.attrSet('data-local-reference',raw);token.attrSet('href','#');token.attrSet('title','点击预览本地文件');}
   return render?render(tokens,index,options,env,self):self.renderToken(tokens,index,options);
  };
 }
 const api={path,install};root.CollabLocalLinks=api;
 if(typeof module==='object'&&module.exports)module.exports=api;
})(typeof window==='object'?window:globalThis);
