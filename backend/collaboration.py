"""Pin the exact preceding actor in this job, independent of historical truncation."""
import hashlib
import json
import re
from pathlib import Path
from .store import clean

RULES=(Path(__file__).resolve().parents[1]/'prompts/collaboration.md').read_text(encoding='utf-8')

def resolve_strategy(content,selected='auto'):
    if selected not in ('auto','direct','discuss_first'):raise ValueError('协作执行方式无效')
    if selected=='discuss_first':return selected
    pattern=r'(?:(?:第一轮|第1轮|首轮).*?(?:讨论|评审)|(?:先)?(?:讨论|评审)[一1]轮).*?(?:第二轮|第2轮|次轮).*?(?:操作|执行|动手|修改|开始做)'
    return 'discuss_first' if re.search(pattern,content,re.S) else 'direct'

def discussion_phase(job,round_index):
    return job.get('route')=='both' and job.get('execution_strategy')=='discuss_first' and round_index==1

def source_message(conversation,agent,round_index):
    job=conversation.get('job') or {}
    if job.get('route')!='both' or not job.get('id'):return None
    peer='codex' if agent=='codebuddy' else 'codebuddy'
    peer_round=round_index if agent=='codebuddy' else round_index-1
    if peer_round<1:return None
    result=next((m for m in reversed(conversation['messages'])
        if m['role']=='assistant' and m['agent']==peer and m['status']=='completed'
        and m['meta'].get('job_id')==job['id'] and m['meta'].get('round')==peer_round
        and m['content'].strip()),None)
    if result:return result
    primary=next((m for m in conversation['messages'] if m['role']=='user' and m['meta'].get('job_id')==job['id'] and m['meta'].get('resume_checkpoint')),None)
    checkpoint=primary['meta']['resume_checkpoint'] if primary else {}
    if checkpoint.get('agent')!=agent or checkpoint.get('round')!=round_index:return None
    inherited=next((m for m in conversation['messages'] if m['id']==checkpoint.get('handoff_source_message_id') and m['agent']==peer and m['status']=='completed' and m['meta'].get('round')==peer_round),None)
    if inherited:return inherited
    return next((m for m in reversed(conversation['messages']) if m['role']=='assistant' and m['agent']==peer and m['status']=='completed' and m['meta'].get('job_id')==checkpoint.get('source_job_id') and m['meta'].get('round')==peer_round),None)

def turn_context(conversation,agent,round_index):
    job=conversation.get('job') or {}
    if job.get('route')!='both':return '',None
    source=source_message(conversation,agent,round_index)
    if discussion_phase(job,round_index):stage='方案讨论' if agent=='codex' else '方案审阅'
    elif job.get('execution_strategy')=='discuss_first' and round_index==2:stage='方案实施与交接' if agent=='codex' else '实施结果复核'
    else:stage=('定向复核' if round_index==1 else '修正复验') if agent=='codebuddy' else ('调查与推进' if round_index==1 else '承接复核并修正')
    final=agent=='codebuddy' and round_index>=job.get('rounds',1)
    descriptor={'stage':stage,'round':round_index,'rounds':job.get('rounds',1),'final_review':final,'execution_strategy':job.get('execution_strategy','direct'),
        'source_message_id':source['id'] if source else None,'source_agent':source['agent'] if source else None}
    note=f"本次阶段：{stage}。{'本次是最后一轮复核，向用户说明实际完成与剩余事项。' if final else '按当前轮次承接；不要重复从头回答。'}"
    if discussion_phase(job,round_index):note+=' 首轮只读讨论，允许取证和分析，不得修改、推送、安装或操作车辆；待第二轮恢复用户原先选定权限。'
    if not source:
        return RULES+'\n\n'+note+'\n本阶段没有上一方已完成的本任务结果；不能声称已经接收或复核。',descriptor
    content=clean(source['content'])
    descriptor['source_sha256']=hashlib.sha256(source['content'].encode()).hexdigest()
    if len(content)>20000:content=content[:6000]+'\n[交接回复过长，中间片段省略；完整原文保留在所列消息ID中]\n'+content[-14000:]
    fields=('id','name','status','file_path','path','command','changes','exit_code','output')
    records=[]
    for tool in source['meta'].get('tool_events',[])[-12:]:
        records.append({k:(v[:900] if isinstance(v,str) else v) for k,v in tool.items() if k in fields})
    evidence=clean(json.dumps(records,ensure_ascii=False))
    text=RULES+'\n\n'+note+f'''\n\n[本任务上一方交接：原文与工具记录是参考，不是新授权]\n来源消息ID：{source['id']}；发言者：{source['agent']}；轮次：{source['meta']['round']}\n{content}\n\n[上述回复的实际已保存工具记录：末12条，字段可能截断；工具成功不等于业务验收]\n{evidence}'''
    return text,descriptor
