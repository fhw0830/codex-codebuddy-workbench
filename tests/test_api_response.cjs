const assert=require('node:assert/strict');
const {read}=require('../web/api-response.js');
(async()=>{
 assert.deepEqual(await read({status:200,text:async()=>' {"id":"ok"} '}),{id:'ok'});
 assert.deepEqual(await read({status:403,text:async()=>' {"error":"expired"} '}),{error:'expired'});
 await assert.rejects(()=>read({status:400,text:async()=>'<!DOCTYPE HTML><h1>Bad request</h1>'}),/HTTP 400.*输入内容已保留/);
 await assert.rejects(()=>read({status:502,text:async()=>''}),/HTTP 502/);
 console.log('API responses: valid JSON, expired session, HTML and empty error pages passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
