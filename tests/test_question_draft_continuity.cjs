const assert=require('node:assert/strict'),ui=require('../web/user-input-ui.js'),panel=require('../web/change-panel.js');
function fixture({id='q',source='m',question='选择方案？',text='',checked='',focused=false}={}){
 const field={value:text,selectionStart:2,selectionEnd:4,isConnected:true,matches:s=>s==='[data-free-answer]',focus(){this.focused=true;},setSelectionRange(a,b){this.selection=[a,b];}};
 const options=['A','B'].map(value=>({value,checked:checked===value,isConnected:true}));
 const part={dataset:{questionPart:'choice'},contains:el=>el===field||options.includes(el),querySelector:s=>s==='legend'?{textContent:question}:s==='[data-free-answer]'?field:null,querySelectorAll:s=>s==='input:checked'?options.filter(x=>x.checked):options};
 const form={dataset:{answerQuestion:id,sourceMessage:source},querySelectorAll:()=>[part]};
 return {field,options,container:{ownerDocument:{activeElement:focused?field:null},querySelectorAll:()=>[form]}};
}
const old=fixture({text:'用户尚未提交的自由回答',checked:'B',focused:true}),saved=ui.captureDrafts(old.container);old.field.isConnected=false;
const moved=fixture();ui.restoreDrafts(moved.container,saved);assert.equal(moved.field.value,'用户尚未提交的自由回答');assert.equal(moved.options[1].checked,true);assert.equal(moved.options[0].checked,false);assert.equal(moved.field.focused,true);assert.deepEqual(moved.field.selection,[2,4]);
for(const changed of [{id:'different'},{source:'another-message'},{question:'另一个问题？'}]){const next=fixture(changed);ui.restoreDrafts(next.container,saved);assert.equal(next.field.value,'');assert.equal(next.options.some(x=>x.checked),false,'never apply a previous selection to a different question or source');}
assert.doesNotThrow(()=>ui.restoreDrafts({querySelectorAll:()=>[]},saved),'submitted/answered forms are not recreated');
const conversation={id:'c',messages:[{id:'m',role:'assistant'},{id:'deleted',role:'assistant',meta:{deleted:true}}],input_requests:[{id:'q1',message_id:'m',state:'pending'},{id:'q2',message_id:'m',state:'followup'},{id:'q3',message_id:'m',state:'submitted'},{id:'q4',message_id:'m',state:'answered'},{id:'q5',message_id:'deleted',state:'pending'},{id:'q6',message_id:'m',conversation_id:'other',state:'pending'}]};
assert.deepEqual(panel.pendingQuestions(conversation).map(q=>q.id),['q1','q2']);
console.log('Question continuity: timeline relocation retains actual typed values/selection/cursor, rejects different questions/sources, does not recreate submitted forms, and filters review alerts by pending state passed');
