const assert=require('node:assert/strict'),ui=require('../web/usage-ui.js'),tools=require('../web/execution-ui.js');
assert.equal(ui.credit({credit:0}),'0 积分');
assert.equal(ui.credit({credit_mode:'free'}),'积分未上报');
assert.equal(ui.credit({credit_mode:'external'}),'积分未上报');
assert.equal(ui.credit({}),'积分未上报');
assert.equal(ui.credit({credit:2,credit_mode:'free'}),'2 积分');
const html=ui.html({id:'x',agent:'codebuddy',meta:{credit:0,token_usage:{total:3449,input:3414,output:35,cache_read:0,cache_write:3414,scope:'result'}}});
assert.match(html,/Tokens: 3,449/);assert.match(html,/缓存命中率/);assert.match(html,/未上报/);assert.match(html,/role="tooltip"/);assert.match(html,/popover="manual"/);
assert.match(ui.detail({credit_mode:'external'}),/服务商费用另计/);
assert.match(ui.html({id:'<script>',agent:'codebuddy'}),/&lt;script&gt;/);
const group=tools.groupHTML([{id:'1',tool:{id:'a',name:'Read',path:'demo.py',status:'completed'}},{id:'2',tool:{id:'b',name:'Bash',command:'echo test',status:'completed'}},{id:'3',tool:{id:'c',name:'TaskUpdate',status:'completed'}}],()=> '不足1秒');
assert.match(group,/tool-line/);assert.match(group,/demo.py/);assert.doesNotMatch(group,/execution-tool-group/);assert.match(group,/步骤与协调/);assert.doesNotMatch(group,/<details[^>]+\sopen/);
console.log('Usage and thin tools: totals, zero, unknown, billing basis, escaping, disclosure and ordered rows passed');

assert.equal(ui.credit({credit:0,credit_mode:'free',credit_source:'user_selected_free'}),'积分未上报');
assert.equal(ui.credit({credit:0,reported_credit:0,credit_source:'user_selected_external'}),'0 积分');
assert.equal(ui.credit({credit:0,reported_credit:1.5,credit_source:'user_selected_free'}),'1.5 积分');
