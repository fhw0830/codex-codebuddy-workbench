const assert=require('node:assert/strict');
const ui=require('../web/user-input-ui.js');
const message={id:'safe',agent:'codex',role:'assistant',status:'streaming',content:'控制板是什么型号？是否支持断线关阀？'};
let html=ui.html(message);assert.ok(html.includes('提交答案'));assert.ok(html.includes('填写答案'));assert.ok(!html.includes('type="radio"'));
const request={id:'q1',message_id:'safe',transport:'codex',state:'pending',blocking:true,questions:[{id:'hardware',question:'选择 <script>',options:[{label:'A',description:'说明'},{label:'B',description:'另一种'}]}]};
html=ui.html(message,[request]);assert.ok(html.includes('等待你回答'));assert.ok(html.includes('type="radio"'));assert.ok(!html.includes(' checked'));assert.ok(html.includes('&lt;script&gt;'));
request.state='answered';assert.ok(ui.html(message,[request]).includes('答案已提交'));assert.ok(!ui.html(message,[request]).includes('<form'));
assert.equal(ui.proseQuestion('转发模板：\n\n```text\nA.\n\n主板是否支持超时关阀？请提供型号。\n```\n\n资料回传即可。'),null);
console.log('Question cards: explicit options, freeform, no default choice, escaped text and final receipt passed');

assert.equal(require('../web/chat-ui.js').questionTiming({meta:{delivery:{mode:'answer'},timing:{started_at:new Date().toISOString()}}}), '');
