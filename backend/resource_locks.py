"""Coordinate shared mutations, not whole conversations or read-only work."""
import fnmatch
import glob
import json
import os
from pathlib import Path
import re
import shlex
import threading
from .store import uid


def canonical_path(value, cwd):
    path=Path(str(value).strip('"\''))
    if not path.is_absolute():path=Path(cwd)/path
    return os.path.normcase(str(path.resolve()))


def code_resource(value,cwd):
    path=Path(canonical_path(value,cwd))
    if path.is_file() or (not path.exists() and path.suffix):path=path.parent
    parents=(path,*path.parents)
    for parent in parents:
        git=parent/'.git'
        if git.exists():
            if git.is_file():
                text=git.read_text(encoding='utf-8',errors='replace').strip()
                git=(parent/text.split(':',1)[1].strip()).resolve() if text.startswith('gitdir:') else git
                common=git/'commondir'
                if common.is_file():git=(git/common.read_text().strip()).resolve()
            return 'code:'+canonical_path(git,cwd)
    for parent in parents:
        if any((parent/m).is_file() for m in ('pyproject.toml','package.json','setup.py','CMakeLists.txt')):
            return 'code:'+canonical_path(parent,cwd)
    return 'code:'+canonical_path(path,cwd)


def robot_resource(value,config=None):
    host=str(value).strip().lower().split('@')[-1]
    if not host or not re.fullmatch(r'[a-z0-9_.:\[\]-]+',host):raise ValueError('机器人资源必须使用SSH主机别名、主机名或IP')
    config=Path(config or Path.home()/'.ssh/config').expanduser().resolve()
    base=config.parent
    active=True;hostname=None;visited=0
    def read(file,stack=()):
        nonlocal active,hostname,visited
        file=Path(file).resolve();visited+=1
        if file in stack or len(stack)>=16 or visited>128:
            raise ValueError('SSH Include循环或层级过深；请使用机器人实际IP协调')
        try:lines=file.read_text(encoding='utf-8-sig',errors='replace').splitlines()
        except OSError as exc:raise ValueError('SSH配置无法读取；请使用机器人实际IP协调') from exc
        for line in lines:
            if hostname is not None:return
            directive=re.match(r'^\s*([a-zA-Z][a-zA-Z0-9]*)\s*(?:=\s*|\s+)(.*?)\s*$',line)
            if not directive:continue
            key=directive[1].lower()
            lexer=shlex.shlex(directive[2],posix=False);lexer.whitespace_split=True;lexer.commenters='#'
            try:words=[word.strip('"\'') for word in lexer]
            except ValueError as exc:raise ValueError('SSH配置格式无法解析；请使用机器人实际IP协调') from exc
            if not words:continue
            args=words
            if key=='host':
                patterns=[p.lower() for p in args]
                active=any(fnmatch.fnmatchcase(host,p) for p in patterns if not p.startswith('!')) and not any(fnmatch.fnmatchcase(host,p[1:]) for p in patterns if p.startswith('!'))
            elif key=='match':
                # Never execute Match exec or guess condition/final-pass semantics.
                raise ValueError('SSH Match条件暂不能安全解析；请先简化相关SSH配置再试')
            elif key=='include' and active:
                for pattern in args:
                    if '%' in pattern or '$' in pattern:
                        raise ValueError('SSH Include动态路径暂不能安全解析；请使用明确配置路径')
                    path=Path(pattern).expanduser()
                    if not path.is_absolute():path=base/path
                    for included in sorted(glob.glob(str(path))):read(included,(*stack,file))
            elif key=='hostname' and active and args:
                hostname=args[0].lower().replace('%h',host).replace('%n',host)
                if not re.fullmatch(r'[a-z0-9_.:\[\]-]+',hostname):
                    raise ValueError('SSH HostName无法安全解析；请使用机器人实际IP协调')
    if config.is_file():read(config)
    return 'robot:'+(hostname or host)


READ_TOOLS={'read','grep','glob','toolsearch','todowrite','taskcreate','taskupdate','taskget','tasklist','report_task_plan','ask_web_user','coordinate_resources','view_image','websearch','webfetch','request_user_input','mcp__collab_web__ask_web_user','mcp__collab_web__coordinate_resources'}
READ_COMMANDS={'pwd','ls','cat','head','tail','rg','grep','findstr','type','dir','get-location','get-content','get-childitem','test-path','resolve-path','select-string','select-object','where-object','convertfrom-json','format-list','format-table','out-string','get-date','get-process','get-nettcpconnection','journalctl','dmesg','uptime','df','free','ps','stat','wc','uname','echo','write-output'}


def readonly_command(command):
    # Deliberately narrow: never guess that arbitrary Python/PowerShell is read-only.
    if re.search(r'[<>`${}]|(?<!&)&(?!&)|\$\(|\b(?:tee|out-file|set-content|add-content)\b',command,re.I):return False
    if re.match(r'^\s*ssh(?:\.exe)?\s',command,re.I):
        try:words=shlex.split(command,posix=False)[1:]
        except ValueError:return False
        i=0
        while i<len(words):
            if words[i] in ('-p','-i','-F','-l'):i+=2;continue
            if words[i]=='-o':
                if i+1>=len(words) or not re.match(r'^(BatchMode|ConnectTimeout|StrictHostKeyChecking|ServerAliveInterval)=',words[i+1],re.I):return False
                i+=2;continue
            if words[i].startswith('-'):return False
            return readonly_command(' '.join(words[i+1:]).strip('"\''))
        return False
    parts=re.split(r'\s*(?:&&|\|\||[;|\n])\s*',command.strip())
    for part in parts:
        if not part:continue
        try:words=shlex.split(part,posix=False)
        except ValueError:return False
        if not words:return False
        name=Path(words[0].strip('"\'')).stem.lower()
        if name=='git':
            args=words[1:]
            if args[:1]==['-C']:args=args[2:]
            if not args or args[0] not in ('status','diff','log','show','rev-parse','ls-files','ls-remote','branch'):return False
            if args[0]=='branch' and any(a not in ('-a','--all','-r','--remotes','--show-current','--list','-v','-vv') for a in args[1:]):return False
            if any(a in ('--output','--ext-diff','--textconv') or a.startswith('--output=') for a in args):return False
        elif name=='rg':
            if any(re.match(r'^--(?:pre|hostname-bin)(?:=|$)',word.strip('"\''),re.I) for word in words[1:]):return False
        elif name=='systemctl':
            if len(words)<2 or words[1] not in ('status','show','is-active','is-enabled','list-units'):return False
        elif name not in READ_COMMANDS:return False
    return bool(parts and command.strip())


def ssh_targets(command):
    targets=[]
    try:words=shlex.split(command,posix=False)
    except ValueError:return targets
    for i,word in enumerate(words):
        if Path(word.strip('"\'')).stem.lower() not in ('ssh','scp','sftp'):continue
        args=iter(words[i+1:])
        for arg in args:
            arg=arg.strip('"\'')
            if arg in ('-p','-P','-i','-F','-o','-J','-l'):next(args,None);continue
            if arg.startswith('-'):continue
            match=re.match(r'(?:[^@\s]+@)?([a-zA-Z0-9_.-]+)(?::/.*)?$',arg)
            if match and (Path(word.strip('"\'')).stem.lower()!='scp' or ':' in arg or '@' in arg):targets.append(match[1])
            if Path(word.strip('"\'')).stem.lower()=='ssh':break
    return targets


def operation_resources(name,arguments,cwd,declared=(),_depth=0):
    name=name.rsplit('.',1)[-1]
    arguments=arguments if isinstance(arguments,dict) else {'command':str(arguments)}
    if name.lower()=='deferexecutetool':
        target=arguments.get('tool_name') or arguments.get('toolName') or arguments.get('tool') or arguments.get('name')
        payload=next((arguments[key] for key in ('arguments','parameters','tool_input','input') if key in arguments),{})
        if isinstance(payload,str):
            try:payload=json.loads(payload)
            except (ValueError,TypeError):payload=None
        if isinstance(target,str) and target and isinstance(payload,dict) and _depth<8:
            return operation_resources(target,payload,cwd,declared,_depth+1)
        return sorted(set(declared)|{code_resource(cwd,cwd)})
    if name.lower() in READ_TOOLS or re.search(r'__(?:read_file|read_multiple_files|list_directory|get_file_info|search_files|read_page|read_thread|list_threads)$',name.lower()):return []
    command=arguments.get('command') or arguments.get('cmd') or ''
    if isinstance(command,list):command=' '.join(str(part) for part in command)
    command=str(command)
    if name.lower() in ('bash','powershell','exec_command','shell','shellexec') and readonly_command(command):return []
    if re.match(r'^\s*ssh(?:\.exe)?\s',command,re.I):
        try:words=shlex.split(command,posix=False)
        except ValueError:words=[]
        # A single quoted remote command does not mutate the local working directory.
        if words and words[-1].startswith(('"',"'")) and words[-1][-1:]==words[-1][:1] and not any(re.search(r'[;&|>]',w) for w in words[:-1]):
            targets=ssh_targets(command)
            if targets:return sorted(set(declared)|{robot_resource(t) for t in targets})
    paths=[arguments[key] for key in ('file_path','path','cwd','workdir') if arguments.get(key)]
    paths+=re.findall(r'^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$',command,re.M)
    paths+=re.findall(r'["\']([A-Za-z]:[\\/][^"\']+)["\']',command)
    # git -C changes where a push/build/edit takes place.
    match=re.search(r'\bgit\s+-C\s+("[^"]+"|\S+)',command)
    if match:paths.append(match[1])
    resources={code_resource(path,cwd) for path in paths or [cwd]}
    for target in ssh_targets(command):resources.add(robot_resource(target))
    resources.update(declared)
    return sorted(resources)


def overlap(a,b):
    if a==b:return True
    if a.startswith('code:') and b.startswith('code:'):
        x,y=a[5:].replace('\\','/').rstrip('/'),b[5:].replace('\\','/').rstrip('/')
        return x.startswith(y+'/') or y.startswith(x+'/')
    return False


def covers(a,b):
    if a==b:return True
    if a.startswith('code:') and b.startswith('code:'):
        x,y=a[5:].replace('\\','/').rstrip('/'),b[5:].replace('\\','/').rstrip('/')
        return y.startswith(x+'/')
    return False


class ResourceCoordinator:
    def __init__(self):
        self.lock=threading.RLock();self.leases={};self.requests={}

    def request(self,owner,resources):
        with self.lock:
            id=uid();self.requests[id]={'id':id,'owner':owner,'resources':sorted(set(resources)),'state':'waiting','blockers':[]}
            self._advance();return dict(self.requests[id])

    def _advance(self):
        earlier=[]
        for request in self.requests.values():
            if request['state']!='waiting':continue
            owner=request['owner'];resources=request['resources']
            needed=[r for r in resources if not any(held_by==owner and covers(held,r) for held,held_by in self.leases.items())]
            blockers={held_by for held,held_by in self.leases.items() if held_by!=owner and any(overlap(held,r) for r in resources)}
            blockers.update(q['owner'] for q in earlier if q['owner']!=owner and any(overlap(a,b) for a in q['resources'] for b in needed))
            request['blockers']=sorted(blockers)
            if not blockers:
                for resource in resources:self.leases[resource]=owner
                request['state']='acquired'
            else:earlier.append(request)
        # Prevent two incremental reservations from waiting on each other forever.
        graph={}
        for q in self.requests.values():
            if q['state']=='waiting':graph.setdefault(q['owner'],set()).update(q['blockers'])
        def reaches(start,node,seen):
            if node==start:return True
            if node in seen:return False
            return any(reaches(start,n,seen|{node}) for n in graph.get(node,()))
        for q in reversed(list(self.requests.values())):
            if q['state']=='waiting' and any(reaches(q['owner'],n,set()) for n in q['blockers']):
                q['state']='blocked';q['reason']='资源交叉等待；请一次声明全部项目和机器人，或完成并释放当前操作后重试。';break

    def poll(self,id,owner):
        with self.lock:
            row=self.requests.get(id)
            if not row or row['owner']!=owner:raise ValueError('资源请求不属于当前任务')
            self._advance();return dict(row)

    def release(self,owner):
        with self.lock:
            self.leases={key:value for key,value in self.leases.items() if value!=owner}
            self.requests={key:value for key,value in self.requests.items() if value['owner']!=owner}
            self._advance()


class ResourceSession:
    def __init__(self,manager,owner,cwd,cancel,changed,readonly=False):
        self.manager,self.owner,self.cwd,self.cancel,self.changed=manager,owner,cwd,cancel,changed
        self.readonly=readonly;self.closed=False;self.declared=set();self.waiting=set();self.last_states={};self.bridge=None;self.active_operations=set()

    @property
    def is_waiting(self):return bool(self.waiting)

    def notify(self,row):
        key=(row['state'],tuple(row.get('blockers',())))
        if self.last_states.get(row['id'])!=key:
            self.last_states[row['id']]=key
            if row['state']=='waiting':self.waiting.add(row['id'])
            else:self.waiting.discard(row['id'])
            self.changed(row)
        return row

    def request(self,body):
        if self.closed or self.cancel.is_set():return {'state':'cancelled'}
        if body.get('action')=='poll':return self.notify(self.manager.poll(body['id'],self.owner))
        if body.get('action')=='release':
            if self.waiting or self.active_operations:
                return {'state':'blocked','reason':'操作尚未结束，资源继续保留。结束操作后可重试释放；正常结束任务时网页会收尾。',
                    'resources_retained':True,'active_operation_ids':sorted(self.active_operations),
                    'waiting_request_ids':sorted(self.waiting)}
            self.manager.release(self.owner);self.declared.clear();return {'state':'released'}
        if body.get('action')=='declare':
            resources=[code_resource(p,self.cwd) for p in body.get('code_paths',[])]+[robot_resource(r) for r in body.get('robots',[])]
            if not resources:raise ValueError('需要具体项目路径或机器人SSH主机')
        elif body.get('action')=='check':
            resources=operation_resources(body.get('tool_name',''),body.get('tool_input',{}),body.get('cwd') or self.cwd,self.declared)
            if not resources:return {'state':'acquired','resources':[]}
        else:raise ValueError('资源操作无效')
        if self.readonly:return {'state':'blocked','reason':'首轮只读讨论，不执行写入或车辆操作'}
        if body.get('action')=='declare':self.declared.update(resources)
        return self.notify(self.manager.request(self.owner,resources))
