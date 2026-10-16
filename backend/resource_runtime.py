"""Child-local hook config. Does not edit account/project hook settings."""
import json
import os
from pathlib import Path
import sys
import tempfile

COORDINATE_TOOL={'type':'function','name':'coordinate_resources','deferLoading':False,
    'description':'修改前一次声明全部代码项目路径及机器人SSH主机/IP；只在资源冲突时等待。修改、验证和交接阶段完成后可release，不能在命令仍运行时释放。聊天和只读取证无需声明。',
    'inputSchema':{'type':'object','properties':{'action':{'type':'string','enum':['declare','release']},'code_paths':{'type':'array','items':{'type':'string'}},'robots':{'type':'array','items':{'type':'string'}}},'required':['action','code_paths','robots'],'additionalProperties':False}}

RESOURCE_INSTRUCTIONS='''\n不同对话独立执行。聊天、读取、分析无需等待；实施前用coordinate_resources（CodeBuddy为mcp__collab_web__coordinate_resources）一次声明全部会修改的代码项目根目录和会操作的机器人SSH主机/IP，尤其脚本间接访问远端或MCP操作必须声明真实目标。工具执行前还有自动协调钩子。遇到等待不能绕过，不能通过其他工具抢写；可完成独立阅读。完成修改和验证且无后台命令运行后可release；默认任务结束自动释放。共享资源协调不取代当前用户授权和车辆部署条件。'''


class HookRuntime:
    def __init__(self,session):
        self.temp=tempfile.TemporaryDirectory(prefix='collab-resource-hooks-')
        self.folder=Path(self.temp.name)
        self.script=Path(__file__).with_name('resource_hook.py').resolve()
        command='"'+sys.executable+'" "'+str(self.script)+'"'
        self.settings={'hooks':{'PreToolUse':[{'hooks':[{'type':'command','command':command,'timeout':3600,'statusMessage':'协调同一项目或机器人的操作'}]}]}}
        (self.folder/'hooks.json').write_text(json.dumps(self.settings,ensure_ascii=False),encoding='utf-8')
        self.codex_settings=json.loads(json.dumps(self.settings))
        if os.name=='nt':
            expression="& '"+sys.executable.replace("'","''")+"' '"+str(self.script).replace("'","''")+"'"
            self.codex_settings['hooks']['PreToolUse'][0]['hooks'][0]['command']='powershell.exe -NoLogo -NoProfile -NonInteractive -Command '+json.dumps(expression,ensure_ascii=False)
        self.env={**os.environ,'COLLAB_RESOURCE_URL':session.bridge['url'],'COLLAB_RESOURCE_TOKEN':session.bridge['token']}

    def codex_args(self):
        hook=self.codex_settings['hooks']['PreToolUse'][0]['hooks'][0]
        inline='[{hooks=[{type="command",command='+json.dumps(hook['command'])+',timeout=3600,statusMessage='+json.dumps(hook['statusMessage'])+'}]}]'
        return ['-c','features.hooks=true','-c','hooks.PreToolUse='+inline]

    def verify_codex(self,response):
        def walk(value):
            if isinstance(value,dict):
                if value.get('command')==self.codex_settings['hooks']['PreToolUse'][0]['hooks'][0]['command'] and (value.get('type')=='command' or value.get('handlerType')=='command'):return True
                return any(walk(v) for v in value.values())
            if isinstance(value,list):return any(walk(v) for v in value)
            return False
        commands=[]
        def collect(value):
            if isinstance(value,dict):
                if (value.get('type')=='command' or value.get('handlerType')=='command') and value.get('command'):commands.append(value['command'])
                for v in value.values():collect(v)
            elif isinstance(value,list):
                for v in value:collect(v)
        collect(response)
        # Verify only our child-local hook. Never approve or alter unrelated hooks.
        if not walk(response):raise RuntimeError('本轮资源协调钩子未加载，未开始执行工具')
        for entry in response.get('data',[]):
            for hook in entry.get('hooks',[]):
                if hook.get('command')==self.codex_settings['hooks']['PreToolUse'][0]['hooks'][0]['command'] and (not hook.get('enabled') or hook.get('trustStatus') not in ('trusted','managed')):
                    raise RuntimeError('网页资源钩子尚未登记当前哈希，未开始执行工具；运行网页提供的登记脚本后重试')

    def trust_config(self,response):
        result={'features.hooks':True,'hooks.PreToolUse':self.codex_settings['hooks']['PreToolUse']}
        for entry in response.get('data',[]):
            for hook in entry.get('hooks',[]):
                if hook.get('command')==self.codex_settings['hooks']['PreToolUse'][0]['hooks'][0]['command']:
                    prefix='hooks.state.'+json.dumps(hook['key'])
                    result[prefix+'.enabled']=True
                    result[prefix+'.trusted_hash']=hook['currentHash']
        if not result:raise RuntimeError('缺少当前任务资源钩子的精确哈希')
        return result

    def close(self):self.temp.cleanup()
