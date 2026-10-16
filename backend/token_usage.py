"""Numeric usage only: per-call snapshots, never prompts or reasoning text."""
from datetime import datetime
from pathlib import Path
import json, math

FIELDS=('input','output','total','cache_read','cache_write','reasoning')

def number(value):
    if isinstance(value,bool):return None
    try:n=float(value)
    except (TypeError,ValueError):return None
    return int(n) if math.isfinite(n) and n>=0 and n.is_integer() else None

def normalize(raw):
    if not isinstance(raw,dict):return {}
    def pick(*keys):
        return next((n for k in keys if (n:=number(raw.get(k))) is not None),None)
    input=pick('prompt_tokens','input_tokens','inputTokens')
    output=pick('completion_tokens','output_tokens','outputTokens')
    cached=pick('cache_read_input_tokens','cached_tokens','cacheReadInputTokens')
    write=pick('cache_creation_input_tokens','cacheWriteInputTokens','cacheCreationInputTokens')
    detail=raw.get('prompt_tokens_details') or raw.get('input_tokens_details') or {}
    if cached is None:cached=number(detail.get('cached_tokens'))
    reasoning=pick('reasoning_tokens','think_total_tokens')
    if reasoning is None:reasoning=number((raw.get('completion_tokens_details') or raw.get('output_tokens_details') or {}).get('reasoning_tokens'))
    # CodeBuddy's CLI already includes cache buckets in input_tokens. Its native
    # modelUsage.inputTokens instead excludes them; normalize that explicit shape.
    if input is not None and 'inputTokens' in raw:
        input+=(cached or 0)+(write or 0)
    total=pick('total_tokens','totalTokens')
    if input is not None and output is not None:total=input+output
    return {k:v for k,v in dict(input=input,output=output,total=total,cache_read=cached,cache_write=write,reasoning=reasoning).items() if v is not None}

class Usage:
    def __init__(self):self.calls={};self.sources=set();self.final={};self.alias={}
    def add(self,key,raw,source='stream',alias=None):
        values=normalize(raw)
        if not values:return False
        if alias and alias!=key:
            self.alias[alias]=key
            if alias in self.calls:self.calls.setdefault(key,{}).update(self.calls.pop(alias))
        key=self.alias.get(key,key)
        if not key:return False
        existing=self.calls.setdefault(key,{})
        # A preliminary assistant placeholder may arrive after a completed delta.
        if not any(values.values()) and any(existing.values()):return False
        existing.update(values);self.sources.add(source)
        return True
    def event(self,event):
        if event.get('parent_tool_use_id'):return False
        meta=event.get('_meta') or {};provider=event.get('providerData') or {}
        stream=event.get('event') or {};message=event.get('message') or stream.get('message') or {}
        model_id=meta.get('codebuddy.ai/modelRequestId')
        key=event.get('_messageId') or meta.get('codebuddy.ai/llmMessageId') or provider.get('messageId') or message.get('id') or model_id
        changed=False
        for container in [message,stream,provider]:
            for name in ('usage','rawUsage'):
                values=normalize(container.get(name))
                if not any(values.values()):continue
                changed=self.add(key,container.get(name),'stream',model_id) or changed
        if event.get('type')=='result':
            self.final=normalize(event.get('usage'))
        elif event.get('type') in ('assistant','message'):
            changed=self.add(key,event.get('usage'),'stream',model_id) or changed
        return changed
    def receipts(self,pid,cwd,request_ids):
        if not pid:return
        folder=Path.home()/'.codebuddy/logs'/datetime.now().strftime('%Y-%m-%d')
        for file in folder.glob('*.log'):
            if not file.name.startswith(Path(cwd).name+'__'):continue
            with file.open('rb') as stream:
                stream.seek(max(0,file.stat().st_size-12*1024*1024));data=stream.read().decode('utf-8',errors='replace')
            for line in data.splitlines():
                if f'[pid={pid}]' not in line or 'qua.end:' not in line:continue
                try:raw=json.loads(line.split('qua.end:',1)[1].strip())
                except ValueError:continue
                if raw.get('conversation_request_id') not in request_ids:continue
                key=raw.get('message_id')
                # Native zero counters also mean unavailable on some providers; only retain
                # input/output/total receipts. Reasoning/cache require explicit stream usage.
                self.add(key,{k:raw[k] for k in ('prompt_tokens','completion_tokens','total_tokens') if k in raw},'cli_receipts')
    def summary(self,expected=0):
        records=list(self.calls.values())
        aggregate='input' in self.final and 'output' in self.final and (self.final.get('total',0)>0 or not any(r.get('total',0)>0 for r in records))
        if aggregate:records=[self.final]
        fields={k:sum(r[k] for r in records if k in r) for k in FIELDS if any(k in r for r in records)}
        if not fields:return None
        coverage={k:sum(k in r for r in records) for k in fields}
        for key in ('cache_read','cache_write','reasoning'):
            if key in fields and coverage[key]<len(records):fields.pop(key)
        complete=sum('input' in r and 'output' in r for r in records)
        return {**fields,'reported_requests':expected if aggregate else len(records),'complete_requests':expected if aggregate else complete,'expected_requests':expected,
                'partial':(complete<len(records) or (not aggregate and len(records)<expected)),
                'coverage':coverage,'sources':sorted(self.sources),'scope':'result' if aggregate else 'requests'}
