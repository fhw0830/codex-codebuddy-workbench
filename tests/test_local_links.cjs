'use strict';
const assert=require('node:assert/strict');
const links=require('../web/local-links.js');
const md=require('../web/vendor/markdown-it.min.js')({html:false});links.install(md);
for(const href of ['D:/资料/方案.md','/D:/资料/方案.md','file:///D:/资料/方案.md','D%3A/资料/方案.md']){
 assert.equal(links.path(href),'D:/资料/方案.md');
 const html=md.render('[方案](<'+href+'>)');assert.match(html,/data-local-reference=/);assert.match(html,/href="#"/);
}
assert.equal(links.path('方案.md','D:/资料'),'D:/资料/方案.md');
assert.equal(links.path('/D:/资料/方案.md:12'),'D:/资料/方案.md');
for(const href of ['https://example.com/file.md','javascript:alert(1)','data:text/html,x','file://server/share/file.md','//server/share.md'])assert.equal(links.path(href),null);
assert.match(md.render('[网站](https://example.com/file.md)'),/href="https:\/\/example.com\/file.md"/);
assert.doesNotMatch(md.render('[危险](javascript:alert(1))'),/href=/);
console.log('Local links: Windows, escaped, file URI, relative paths and unsafe schemes passed');
