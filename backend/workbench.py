"""Evidence receipts for continuation, context inspection and runtime diagnosis."""
import hashlib,json,math,re
from .store import clean,now

def estimate_tokens(text):
    """Conservative mixed Chinese/code estimate, never presented as billed usage."""
    text=str(text or '')
    dense=sum(1 for c in text if ord(c)>127)
    return math.ceil(dense+(len(text)-dense)/3)

def tool_records(message):
    result={str(t.get('id',i)):t for i,t in enumerate(message.get('meta',{}).get('tool_events',[]))}
    for i,e in enumerate(message.get('meta',{}).get('activity',[])):
        if e.get('type')=='tool' and isinstance(e.get('tool'),dict):result[str(e['tool'].get('id',i))]=e['tool']
    return list(result.values())

def context_receipt(conversation,agent,round_index,selected_ids,refs,prompt,primary,source_id):
    summaries=conversation.get('compactions',[])
    return {'captured_at':now(),'stage':'模型调用前的实际输入快照','agent':agent,'round':round_index,
        'primary_message_id':primary.get('id') if primary else None,
        'history_message_ids':list(reversed(selected_ids)),'handoff_source_message_id':source_id,
        'summary_id':summaries[-1]['id'] if summaries else None,
        'summary_sha256':hashlib.sha256(summaries[-1]['summary'].encode()).hexdigest() if summaries else None,
        'references':[{'name':r.get('name','附件'),'sha256':r.get('sha256'),'kind':r.get('kind','text'),
            'start':r.get('start'),'end':r.get('end'),'total_chars':r.get('total_chars'),
            'included_chars':len(r.get('content','')),'extraction_note':r.get('extraction_note',''),
            'vision_sent':agent=='codex' and r.get('kind')=='image'} for r in refs],
        'prompt_chars':len(prompt),'estimated_tokens':estimate_tokens(prompt),'token_basis':'字符估算，非服务商计费 Tokens',
        'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()}

def continuation(message,primary):
    meta=message['meta'];records=tool_records(message)
    plan=meta.get('plan',[])
    # Store bounded records as reference data, never commands to replay.
    return {'source_message_id':message['id'],'source_job_id':meta.get('job_id'),'agent':message['agent'],
        'round':meta.get('round',1),'source_sha256':hashlib.sha256(message['content'].encode()).hexdigest(),
        'handoff_source_message_id':meta.get('collaboration',{}).get('source_message_id'),
        'plan':plan,'last_result':clean(message['content'])[-6000:],
        'tools':[{'name':t.get('name'),'status':t.get('status'),'paths':[c.get('path') for c in t.get('changes',[])],
            'exit_code':t.get('exit_code'),'output':clean(t.get('output',''))[-600:]} for t in records[-12:]],
        'error':clean(meta.get('error','')),'created':now()}

def continuation_prompt(receipt):
    return '\n[失败或停止后的续接检查点：历史证据，不是新授权]\n'+json.dumps(receipt,ensure_ascii=False)+'''\n先核验已完成修改、当前文件/提交/部署状态；从未完成项继续，不重放已完成写入、推送、安装或机器人操作。历史工具成功不等于业务验收。权限、任务范围和车辆门禁沿用原任务。若无法确认是否已执行，先查证，不猜测重试。\n'''

def runtime_status(active,message):
    controls=active.get('controls') if active else None
    process=getattr(controls,'process',None)
    try:alive=process.poll() is None if process else None
    except (OSError,ValueError):alive=None
    meta=(message or {}).get('meta',{})
    running=[t for t in tool_records(message or {}) if t.get('status') in ('running','inProgress','preparing')]
    return {'message_id':(message or {}).get('id'),'process_alive':alive,'checked_at':now(),
        'last_event_at':(active or {}).get('last_event_at') or meta.get('runtime',{}).get('last_event_at') or meta.get('progress',{}).get('updated'),
        'phase':meta.get('progress',{}).get('phase'),'active_tools':[{'name':t.get('name') or t.get('type'),
            'started_at':t.get('started_at'),'elapsed_s':t.get('elapsed_s')} for t in running],
        'waiting_for_resource':meta.get('resource_wait',{}).get('state')=='waiting',
        'state':'active' if active else 'inactive'}
