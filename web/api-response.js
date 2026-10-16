(function(root){
 'use strict';
 async function read(response){
  const text=await response.text();
  try{return JSON.parse(text);}
  catch{throw new Error('后台返回异常页面（HTTP '+response.status+'），输入内容已保留，请稍后重试。');}
 }
 const api={read};if(typeof module==='object'&&module.exports)module.exports=api;else root.CollabApiResponse=api;
})(typeof window==='object'?window:this);
