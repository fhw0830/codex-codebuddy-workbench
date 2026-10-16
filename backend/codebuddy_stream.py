"""Normalize native CLI events without retaining hidden reasoning content."""
from datetime import datetime
from pathlib import Path
import re

from .store import clean
import json
from .token_usage import Usage


def plan_steps(values):
    if not isinstance(values, list):
        return []
    states = {'pending': 'pending', 'in_progress': 'in_progress', 'completed': 'completed'}
    return [{'step': clean(item.get('step') or item.get('content') or item.get('subject') or '')[:400],
             'status': states.get(item.get('status'), 'pending')}
            for item in values[:40] if isinstance(item, dict) and (item.get('step') or item.get('content') or item.get('subject'))]


def reported_credits(pid, cwd, request_ids):
    """Read only billing receipts attributable to this child PID and request."""
    folder = Path.home()/'.codebuddy/logs'/datetime.now().strftime('%Y-%m-%d')
    receipts = []
    seen = set()
    # Native logs aggregate multiple sessions; never attribute another PID's usage.
    for file in folder.glob('*.log'):
        if not file.name.startswith(Path(cwd).name + '__'):
            continue
        with file.open('rb') as stream:
            stream.seek(max(0, file.stat().st_size - 8*1024*1024))
            data = stream.read().decode('utf-8', errors='replace')
        for line in data.splitlines():
            if f'[pid={pid}]' not in line or '[SessionManager][credit] Credit received:' not in line:
                continue
            match = re.search(r'rootRequestId=([^,\s]+), source=raw_model_stream_event, credit=([0-9]+(?:\.[0-9]+)?)', line)
            if match and match[1] in request_ids and line not in seen:
                seen.add(line)
                receipts.append(float(match[2]))
    return receipts


class StreamState:
    def __init__(self, emit, on_tool, on_progress, record_tool, full_access):
        self.emit, self.on_tool, self.on_progress = emit, on_tool, on_progress
        self.record_tool, self.full_access = record_tool, full_access
        self.messages, self.tool_names = {}, {}
        self.metadata, self.result = {}, None
        self.request_ids, self.model_requests = set(), set()
        self.credits, self.credit_ids = [], set()
        self.tool_calls, self.last_phase = 0, None
        self.session_id, self.active_request = None, None
        self.tasks, self.task_calls = {}, {}
        self.token_usage=Usage()

    def progress(self, phase, **fields):
        if self.on_progress and (phase != self.last_phase or fields):
            self.last_phase = phase
            self.on_progress({'phase': phase, **fields})

    def tool(self, item, status):
        record = self.record_tool(item, status)
        record['name']=self.tool_names.get(record['id'],record['name'])
        if not self.full_access and record['name'] not in ('mcp__collab_web__ask_web_user','ToolSearch','DeferExecuteTool'):
            raise RuntimeError('当前为仅讨论权限；工具调用已终止')
        id = record['id']
        if id not in self.tool_names:
            self.tool_calls += 1
        if record['name'] not in ('toolResult', 'tool_result'):
            self.tool_names[id] = record['name']
        record['name'] = self.tool_names.get(id, record['name'])
        if self.on_tool:
            self.on_tool(record)
        detail = item.get('input') or item.get('arguments') or {}
        if isinstance(detail, str):
            try: detail = json.loads(detail)
            except ValueError: detail = {}
        if isinstance(detail, dict):
            plan = plan_steps(detail.get('todos') or detail.get('plan'))
            if plan:
                self.progress('planning', plan=plan)
            if record['name']=='TaskCreate' and detail.get('subject'):
                self.task_calls[id]=detail['subject']
                self.tasks.setdefault(id,{'step':clean(detail['subject'])[:400],'status':'pending'})
                self.progress('planning',plan=list(self.tasks.values()))
            elif record['name']=='TaskUpdate' and detail.get('taskId'):
                task_id=str(detail['taskId'])
                task=self.tasks.get(task_id)
                if task:
                    task.update({'status':detail.get('status',task['status'])})
                    if detail.get('subject'):task['step']=clean(detail['subject'])[:400]
                    self.progress('planning',plan=plan_steps(list(self.tasks.values())))
        if id in self.task_calls and status=='completed':
            match=re.search(r'Task\s*#(\d+)',record.get('output',''))
            if match and id in self.tasks:self.tasks[match[1]]=self.tasks.pop(id)
        self.progress('tools' if status in ('running', 'preparing') else 'analysis', tool_name=record['name'])

    def update_text(self, id, text, append=False):
        self.messages[id] = self.messages.get(id, '') + text if append else text
        if self.on_progress:self.on_progress({'activity':{'type':'text','id':id,'text':self.messages[id]}})
        self.emit('\n\n'.join(value for value in self.messages.values() if value))
        self.progress('reply')

    def consume(self, event):
        kind = event.get('type')
        provider = event.get('providerData') or {}
        meta = event.get('_meta') or {}
        request = event.get('_requestId') or provider.get('conversationRequestId')
        if request and not event.get('parent_tool_use_id'):
            self.request_ids.add(request)
            self.active_request = request
        self.session_id = event.get('session_id') or self.session_id
        model_request = meta.get('codebuddy.ai/modelRequestId') or provider.get('traceId')
        if model_request:
            self.model_requests.add(model_request)
        if self.token_usage.event(event) or kind=='result':
            summary=self.token_usage.summary(len(self.model_requests))
            if summary:
                self.metadata['token_usage']=summary
                if self.on_progress:self.on_progress({'token_usage':summary})
        credit = provider.get('rawUsage', {}).get('credit', provider.get('usage', {}).get('credit'))
        credit_id = provider.get('traceId') or provider.get('messageId') or request or event.get('id')
        if isinstance(credit, (int, float)) and credit_id not in self.credit_ids:
            self.credit_ids.add(credit_id)
            self.credits.append(credit)
            if self.on_progress:self.on_progress({'credit':sum(self.credits),'credit_requests':len(self.credits),'credit_is_partial':True})
        message_id = event.get('_messageId') or meta.get('codebuddy.ai/llmMessageId') or provider.get('messageId') or event.get('uuid') or event.get('id') or ('reply-'+str(request or self.active_request) if request or self.active_request else 'reply')
        if kind == 'system':
            if event.get('subtype') == 'init':
                if event.get('model') and event['model']!='unknown':self.metadata['model'] = event['model']
                self.progress('analysis')
            elif event.get('reason') == 'reasoning_in_progress':
                self.progress('analysis')
            elif event.get('status') == 'compacting':
                self.progress('context')
        elif kind == 'stream_event' and not event.get('parent_tool_use_id'):
            stream = event.get('event') or {}
            delta = stream.get('delta') or {}
            if delta.get('type') == 'text_delta':
                self.update_text(message_id, delta.get('text', ''), append=True)
            elif delta.get('type') in ('thinking_delta', 'signature_delta'):
                self.progress('analysis')
            elif stream.get('type') == 'content_block_start':
                part = stream.get('content_block') or {}
                if part.get('type') == 'tool_use':
                    self.tool(part, 'preparing')
                elif part.get('type') == 'thinking':
                    self.progress('analysis')
        elif kind in ('assistant', 'message'):
            assistant = event.get('message', {}) if kind == 'assistant' else event
            if assistant.get('role', 'assistant') != 'assistant':
                return
            values = assistant.get('content') or []
            text = '\n'.join(part.get('text', '') for part in values if part.get('type') in ('text', 'output_text'))
            if text and not event.get('parent_tool_use_id'):
                self.update_text(message_id, text)
            self.metadata.update({k: v for k, v in provider.items() if k in ('model', 'requestModelId', 'requestModelName', 'traceId', 'conversationRequestId', 'usage', 'rawUsage', 'messageId')})
            for part in values:
                if part.get('type') in ('tool_use', 'tool_call', 'function_call'):
                    self.tool(part, 'running')
        elif kind == 'function_call':
            self.tool(event, 'running')
        elif kind == 'function_call_result':
            self.tool(event, event.get('status', 'completed'))
        elif kind == 'user':
            for part in event.get('message', {}).get('content', []) if isinstance(event.get('message', {}).get('content'), list) else []:
                if part.get('type') == 'tool_result':
                    self.tool({'id': part['tool_use_id'], 'type': 'toolResult', 'output': part.get('content', '')}, 'failed' if part.get('is_error') else 'completed')
        elif kind == 'result':
            self.result = event
            if event.get('is_error') or event.get('subtype') != 'success':
                detail=clean(event.get('result') or 'CodeBuddy生成失败')
                streamed='\n\n'.join(self.messages.values())
                if detail=='CodeBuddy生成失败' and re.search(r'500\s+internal server error',streamed,re.I):detail=streamed[-900:]
                if re.search(r'500\s+internal server error',detail,re.I):
                    detail='CodeBuddy模型请求返回500；本轮未完成，已执行工具需先核对。'+detail[-900:]
                raise RuntimeError(detail)
            final=event.get('result')
            if final and final not in self.messages.values() and final!='\n\n'.join(self.messages.values()):
                self.update_text('final-result',final)
            self.emit(event.get('result') or '\n\n'.join(self.messages.values()))
