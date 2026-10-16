"""Human answers are explicit input; no default choice or silent approval."""
import queue
import re
import threading
from .store import clean, uid

def normalize_questions(rows):
    result=[]
    for index,row in enumerate(rows[:3]):
        if row.get('isSecret'):raise ValueError('凭据问题请通过本机登录界面处理，不在聊天卡片收集')
        question=clean(row.get('question','')).strip()[:2000]
        if not question:continue
        options=[]
        for option in (row.get('options') or [])[:6]:
            label=clean(option.get('label') if isinstance(option,dict) else option).strip()[:200]
            if label:options.append({'label':label,'description':clean(option.get('description',''))[:500] if isinstance(option,dict) else ''})
        result.append({'id':str(row.get('id') or index)[:100],'question':question,'options':options,'multi_select':bool(row.get('multiSelect'))})
    if not result:raise ValueError('提问缺少问题正文')
    if len({q['id'] for q in result})!=len(result):raise ValueError('问题ID不能重复')
    return result

def validate_answers(questions,answers):
    result={}
    for question in questions:
        value=answers.get(question['id'])
        if isinstance(value,str):value=[value]
        if not isinstance(value,list) or not value:raise ValueError('请回答每个问题，也可以填写自己的答案')
        values=[clean(v).strip() for v in value if isinstance(v,str)]
        if not values or any(not v or len(v)>4000 for v in values):raise ValueError('答案须为1至4000字')
        result[question['id']]=values
    return result

def text_question(content):
    # Ordinary prose can offer a reply card, but cannot block or fabricate options.
    lines=[];fence=None
    for line in content.splitlines():
        marker=re.match(r'^\s*(`{3,}|~{3,})',line)
        if marker:
            token=marker.group(1)
            if fence is None:fence=token
            elif token[0]==fence[0] and len(token)>=len(fence):fence=None
            continue
        if fence is not None or re.match(r'^\s*>',line):continue
        lines.append(line)
    paragraphs=[p.strip() for p in '\n'.join(lines).split('\n\n') if p.strip()]
    for paragraph in reversed(paragraphs[-12:]):
        if len(paragraph)>1000 or paragraph.startswith('```'):continue
        if ('？' in paragraph or '?' in paragraph) and re.search(r'请确认|请告诉|请提供|你希望|你要|什么型号|是否|能否|是.*吗|需要你',paragraph):
            return [{'id':'text','question':paragraph,'options':[]}]
    return None

class QuestionBroker:
    def __init__(self,changed):
        self.changed=changed;self.pending={};self.keys={};self.queue=queue.Queue();self.lock=threading.RLock();self.closed=False
        self.bridge=None

    @property
    def has_blocking(self):
        with self.lock:return any(item['request']['blocking'] for item in self.pending.values())

    def bridge_answer(self,id):
        with self.lock:
            item=self.pending.get(id)
            if not item:return {'state':'closed'}
            if not item['submitted']:return {'state':'pending'}
            values=item['request']['answers']
        self.ack(id);return {'state':'answered','answers':values}

    def open(self,key,rows,blocking=True,transport='codex'):
        with self.lock:
            if self.closed:raise ValueError('当前提问会话已结束')
            if key in self.keys:return self.keys[key]
            id=uid();request={'id':id,'questions':normalize_questions(rows),'state':'pending','blocking':blocking,'transport':transport}
            self.pending[id]={'key':key,'request':request,'submitted':False};self.keys[key]=id
        self.changed(request);return id

    def submit(self,id,answers):
        with self.lock:
            item=self.pending.get(id)
            if self.closed or not item or item['submitted']:return False
            values=validate_answers(item['request']['questions'],answers)
            item['submitted']=True;item['request'].update(state='submitted',answers=values)
            self.queue.put((id,item['key'],values))
        self.changed(item['request']);return True

    def drain(self):
        while True:
            try:yield self.queue.get_nowait()
            except queue.Empty:return

    def ack(self,id):
        with self.lock:
            item=self.pending.pop(id,None)
        if item:self.changed({**item['request'],'state':'answered'})

    def dismiss(self,id):
        with self.lock:item=self.pending.pop(id,None)
        if item:self.changed({**item['request'],'state':'followup'})

    def close(self,completed=False,preserve=False):
        with self.lock:
            self.closed=True;items=list(self.pending.values());self.pending.clear()
        for item in items:self.changed({**item['request'],'state':'followup' if completed or preserve else 'cancelled'})
