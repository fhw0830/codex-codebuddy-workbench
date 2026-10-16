"""Per-child PreToolUse guard. No credentials or commands are logged."""
import json
import os
import sys
import time
import urllib.request

sys.stdin.reconfigure(encoding='utf-8',errors='strict')
sys.stdout.reconfigure(encoding='utf-8',errors='strict')

def main():
    try:
        event=json.load(sys.stdin)
        url=os.environ['COLLAB_RESOURCE_URL'];token=os.environ['COLLAB_RESOURCE_TOKEN']
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        boot=json.load(opener.open(url+'/api/bootstrap',timeout=5))
        def call(body):
            request=urllib.request.Request(url+'/api/resource-bridge',data=json.dumps({**body,'token':token}).encode(),headers={'Content-Type':'application/json','X-Collab-Token':boot['csrf']})
            return json.load(opener.open(request,timeout=10))
        result=call({'action':'check','tool_name':event.get('tool_name',''),'tool_input':event.get('tool_input') or {},'cwd':event.get('cwd')})
        deadline=time.monotonic()+3500
        while result['state']=='waiting' and time.monotonic()<deadline:
            time.sleep(.25);result=call({'action':'poll','id':result['id']})
        if result['state']!='acquired':raise ValueError(result.get('reason') or '共享资源等待结束，本操作尚未执行，请在原任务中重试')
        # Both engines accept a successful hook with no decision. Codex treats
        # permissionDecision=allow without updatedInput as an unsupported field.
        print('{}')
    except Exception:
        # Native hook engines can continue after generic hook errors. Explicit denial
        # must be returned on all failures, rather than an unsupported JSON field.
        print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':'操作尚未执行：资源协调未通过，请查看网页等待状态，勿绕过协调。'}}))
        return 2
    return 0

if __name__=='__main__':sys.exit(main())
