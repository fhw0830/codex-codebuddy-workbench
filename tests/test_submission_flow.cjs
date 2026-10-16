const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const Submissions=require('../web/submissions.js'),Execution=require('../web/execution-ui.js');
const src=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const send=src.slice(src.indexOf('function finishSubmittedDraft('),src.indexOf('function editDialog('));
const add=src.slice(src.indexOf('async function addFiles('),src.indexOf('function openAttachmentPreview('));
function storage(){const map=new Map();return {getItem:k=>map.get(k)||null,setItem:(k,v)=>map.set(k,v),removeItem:k=>map.delete(k)};}
function context(api,localStorage=storage()){
 const elements=new Map(),$=id=>{if(!elements.has(id))elements.set(id,{value:'',disabled:false,scrollTop:0,scrollHeight:0});return elements.get(id);};
 $('message-input').value='任务A';$('rounds').value='1';$('execution-strategy').value='auto';
 const state={id:'A',conv:{},connection:'connected',route:'codex',capabilities:{queue:true},documents:[],uploads:[]},busyUploads=new Set(),notices=[];
 const ctx={state,$,api,submissions:Submissions.create(localStorage,crypto.randomUUID),CollabSubmissions:Submissions,crypto,
  isAttachmentBusy:(id=state.id)=>busyUploads.has(id),uploadBusyChats:busyUploads,localStorage,busy:()=>true,
  draftKey:id=>'draft:'+id,toast:text=>notices.push(text),renderAttachments:()=>{},fileData:async()=>'',
  refreshConversation:async()=>{},loadList:async()=>{},reconnect:{wake:()=>{}},notices};
 ctx.saveDraft=()=>localStorage.setItem(ctx.draftKey(state.id),JSON.stringify({text:$('message-input').value,documents:state.documents,uploads:state.uploads}));
 ctx.renderConversation=()=>{$('send-message').disabled=ctx.submissions.isSending(state.id)||ctx.isAttachmentBusy();};
 vm.createContext(ctx);vm.runInContext(send+add,ctx);return ctx;
}
async function flush(){await new Promise(setImmediate);}
(async()=>{
 const accepted=new Map(),shared=storage();let posts=0,reads=0;
 const api=async(path,body)=>{
  if(path.startsWith('/api/submission?')){reads++;const key=new URL('http://fixture'+path).searchParams.get('client_key');return {found:accepted.has(key),job:accepted.get(key)};}
  posts++;accepted.set(body.client_key,{id:'job'});if(posts===1)throw Error('response lost');return {id:'job'};
 };
 const first=context(api,shared);await assert.rejects(()=>vm.runInContext('sendMessage()',first),/先核验/);
 const reload=context(api,shared);await vm.runInContext('sendMessage()',reload);assert.equal(posts,1);assert.equal(reads,1);assert.equal(reload.$('message-input').value,'');
 reload.$('message-input').value='任务A';await vm.runInContext('sendMessage()',reload);assert.equal(posts,2,'intentional new send after acknowledgement remains allowed');
 let finish;const typing=context(()=>new Promise(r=>finish=r));typing.state.documents=[{id:'old'}];typing.state.uploads=[{name:'old.txt'}];
 const pending=vm.runInContext('sendMessage()',typing);typing.$('message-input').value='下一条草稿';typing.state.documents.push({id:'new'});typing.state.uploads.push({name:'new.txt'});
 finish({id:'ok'});await pending;assert.equal(typing.$('message-input').value,'下一条草稿');assert.equal(typing.state.documents[0].id,'new');assert.equal(typing.state.uploads[0].name,'new.txt');
 let releaseA;const separate=context((path,body)=>body.conversation_id==='A'?new Promise(r=>releaseA=r):Promise.resolve({id:'B'}));
 const taskA=vm.runInContext('sendMessage()',separate);separate.state.id='B';separate.$('message-input').value='任务B';separate.renderConversation();assert.equal(separate.$('send-message').disabled,false);
 await vm.runInContext('sendMessage()',separate);releaseA({id:'A'});await taskA;
 let finishUpload;const upload=context(()=>new Promise(r=>finishUpload=r));
 const reading=vm.runInContext("addFiles([{name:'fixture.txt',size:1}])",upload);await flush();upload.state.id='B';upload.renderConversation();assert.equal(upload.$('send-message').disabled,false);
 finishUpload({attachable:true,name:'fixture.txt',content:'test'});await reading;assert.equal(upload.$('send-message').disabled,false);assert.equal(JSON.parse(upload.localStorage.getItem('draft:A')).uploads.length,1);
 const q=storage(),manager=Submissions.create(q,crypto.randomUUID),one=manager.reserve('A',{content:'one'}),two=manager.reserve('A',{content:'two'});
 manager.clear('A',two.client_key);assert.equal(manager.reserve('A',{content:'one'}).client_key,one.client_key);
 const failed={id:'f',role:'assistant',agent:'codex',meta:{job_id:'jobA'}},root={id:'a',role:'user',content:'原任务A',meta:{job_id:'jobA'}};
 assert.equal(Execution.retrySource([root,failed,{id:'b',role:'user',content:'任务B'}],'f').source.id,'a');
 assert.equal(Execution.retrySource([failed,{id:'b',role:'user',content:'任务B'}],'f'),null);
 console.log('Submission regressions: lost acknowledgement/reload, intended repeats, new drafts/attachments, independent chats, upload switching and correct retry root passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
