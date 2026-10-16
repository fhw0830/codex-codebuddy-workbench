"""Minimal stdio MCP: ask only the active local web task's human user."""
import json
import os
import sys
import time
import urllib.request

# MCP stdio is UTF-8, independent of the Windows console code page.
sys.stdin.reconfigure(encoding='utf-8',errors='strict')
sys.stdout.reconfigure(encoding='utf-8',errors='strict')

URL=os.environ['COLLAB_QUESTION_URL'];TOKEN=os.environ['COLLAB_QUESTION_TOKEN']
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
boot=json.load(opener.open(URL+'/api/bootstrap',timeout=5))

def bridge(body):
    request=urllib.request.Request(URL+'/api/question-bridge',data=json.dumps({**body,'token':TOKEN},ensure_ascii=False).encode(),
        headers={'Content-Type':'application/json','X-Collab-Token':boot['csrf']})
    return json.load(opener.open(request,timeout=10))

RESOURCE_TOKEN=os.environ.get('COLLAB_RESOURCE_TOKEN')
RESOURCE_URL=os.environ.get('COLLAB_RESOURCE_URL',URL)

def coordinate(body):
    request=urllib.request.Request(RESOURCE_URL+'/api/resource-bridge',data=json.dumps({**body,'token':RESOURCE_TOKEN}).encode(),headers={'Content-Type':'application/json','X-Collab-Token':boot['csrf']})
    return json.load(opener.open(request,timeout=10))

SCHEMA={'type':'object','properties':{'questions':{'type':'array','minItems':1,'maxItems':3,'items':{'type':'object','properties':{
    'id':{'type':'string'},'question':{'type':'string'},'options':{'type':'array','items':{'type':'object','properties':{'label':{'type':'string'},'description':{'type':'string'}},'required':['label']}}},'required':['question']}}},'required':['questions']}
for line in sys.stdin:
    event={}
    try:
        event=json.loads(line);method=event.get('method');id=event.get('id')
        if id is None:continue
        if method=='initialize':result={'protocolVersion':event.get('params',{}).get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'collab_web','version':'1'}}
        elif method=='ping':result={}
        elif method=='tools/list':
            tools=[{'name':'ask_web_user','description':'向当前网页用户提问并等待实际答案，支持选项及自由填写。不能默认选择；不执行任何工程或车辆动作。','inputSchema':SCHEMA}]
            if RESOURCE_TOKEN:
                from resource_runtime import COORDINATE_TOOL
                tools.append({'name':COORDINATE_TOOL['name'],'description':COORDINATE_TOOL['description'],'inputSchema':COORDINATE_TOOL['inputSchema']})
            result={'tools':tools}
        elif method=='tools/call' and event.get('params',{}).get('name')=='ask_web_user':
            args=event['params'].get('arguments') or {}
            question=bridge({'action':'open','questions':args.get('questions',[])})
            while True:
                answer=bridge({'action':'poll','question_id':question['id']})
                if answer['state']=='answered':break
                if answer['state']=='closed':raise RuntimeError('提问已结束，未收到有效回答')
                time.sleep(.25)
            result={'content':[{'type':'text','text':json.dumps({'answers':answer['answers']},ensure_ascii=False)}]}
        elif method=='tools/call' and event.get('params',{}).get('name')=='coordinate_resources' and RESOURCE_TOKEN:
            answer=coordinate(event['params'].get('arguments') or {})
            while answer['state']=='waiting':
                time.sleep(.25);answer=coordinate({'action':'poll','id':answer['id']})
            result={'content':[{'type':'text','text':json.dumps(answer,ensure_ascii=False)}],'isError':answer['state'] not in ('acquired','released')}
        else:raise ValueError('Unsupported interaction')
        response={'jsonrpc':'2.0','id':id,'result':result}
    except Exception as exc:
        response={'jsonrpc':'2.0','id':event.get('id') if isinstance(event,dict) else None,'error':{'code':-32603,'message':str(exc)[:500]}}
    sys.stdout.write(json.dumps(response,ensure_ascii=False)+'\n');sys.stdout.flush()
