"""Trust only the exact app-owned child hook; do not install a global hook."""
import copy,json,re,sys,tomllib
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.agents import Codex,resolve_runtimes,stop_process
from backend.resource_runtime import HookRuntime

def register():
    runtime=HookRuntime(SimpleNamespace(bridge={'url':'http://127.0.0.1:8766','token':'registration-only-no-tools'}))
    client=Codex(resolve_runtimes(ROOT)['codex'],ROOT)
    process=None
    try:
        process,events,errors=client.launch(True,runtime)
        client.exchange(process,events,'initialize',{'clientInfo':{'name':'codeduo_hook_registration','version':'0.1.1'}},1)
        process.stdin.write('{"method":"initialized","params":{}}\n');process.stdin.flush()
        response,_=client.exchange(process,events,'hooks/list',{},2)
        command=runtime.codex_settings['hooks']['PreToolUse'][0]['hooks'][0]['command']
        matches=[h for entry in response.get('data',[]) for h in entry.get('hooks',[]) if h.get('command')==command]
        if len(matches)!=1:raise RuntimeError('Cannot uniquely identify the app-owned hook')
        hook=matches[0];key=hook['key'];digest=hook['currentHash']
        if "'" in key or not re.fullmatch(r'sha256:[a-f0-9]{64}',digest):raise RuntimeError('Unexpected native hook identity')
        config=Path.home()/'.codex/config.toml'
        original=config.read_text(encoding='utf-8') if config.exists() else ''
        before=tomllib.loads(original);expected=copy.deepcopy(before)
        state=expected.setdefault('hooks',{}).setdefault('state',{}).setdefault(key,{})
        if set(state)-{'enabled','trusted_hash'}:raise RuntimeError('Unrecognized fields in app-owned hook trust entry')
        state.update(enabled=True,trusted_hash=digest)
        header="[hooks.state.'"+key+"']"
        block=header+'\nenabled = true\ntrusted_hash = '+json.dumps(digest)+'\n'
        if header in original:
            updated=re.sub(re.escape(header)+r'\s*\n.*?(?=^\[|\Z)',lambda _:block+'\n',original,flags=re.M|re.S)
        else:updated=original.rstrip()+'\n\n# Web collaboration: exact app-owned child hook trust only.\n'+block
        if tomllib.loads(updated)!=expected:raise RuntimeError('Refusing a config change beyond the app-owned hook trust entry')
        if updated!=original:
            temporary=config.with_name('config.toml.collab-hook.tmp');temporary.write_text(updated,encoding='utf-8');temporary.replace(config)
        return {'registered':True,'key':key,'hash':digest,'global_hook_installed':False,'tools_executed':False}
    finally:
        if process:stop_process(process)
        runtime.close()

if __name__=='__main__':print(json.dumps(register(),ensure_ascii=False))
