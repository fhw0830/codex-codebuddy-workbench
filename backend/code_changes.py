"""Display only changes supplied by a tool; never read or guess file contents."""
import difflib
import re
from .store import clean

LIMIT=60000

def changes(item,detail,name):
    result=[]
    for change in (item.get('changes') or [])[:20]:
        if not isinstance(change,dict):continue
        kind=change.get('kind','update')
        if isinstance(kind,dict):kind=kind.get('type','update')
        diff=clean(str(change.get('diff') or ''))
        result.append({'path':clean(str(change.get('path',''))),'kind':kind,'diff':diff[:LIMIT],
                       'scope':'tool','truncated':len(diff)>LIMIT})
    if result:return result
    short=name.rsplit('__',1)[-1].rsplit('.',1)[-1].lower()
    path=detail.get('file_path') or detail.get('path') or ''
    edits=detail.get('edits') if short=='multiedit' else [detail]
    if short in ('edit','multiedit') and path:
        for edit in (edits or [])[:20]:
            if not isinstance(edit,dict) or 'old_string' not in edit or 'new_string' not in edit:continue
            before=clean(str(edit['old_string']));after=clean(str(edit['new_string']))
            diff='\n'.join(difflib.unified_diff(before.splitlines(),after.splitlines(),fromfile=str(path),tofile=str(path),lineterm=''))
            result.append({'path':clean(str(path)),'kind':'update','diff':diff[:LIMIT],
                           'scope':'snippet','truncated':len(diff)>LIMIT})
    elif short in ('write','writefile','createfile') and path and 'content' in detail:
        content=clean(str(detail['content']))
        result.append({'path':clean(str(path)),'kind':'write','preview':content[:LIMIT],
                       'scope':'submitted','truncated':len(content)>LIMIT})
    # Shell tools can explicitly report a git diff, including remote SSH output.
    output=item.get('aggregatedOutput',item.get('output'))
    if not result and isinstance(output,str) and re.search(r'^diff --git ',output,re.M):
        for block in re.split(r'(?=^diff --git )',output,flags=re.M)[1:21]:
            match=re.search(r'^\+\+\+ (?:b/)?(.+)$',block,re.M) or re.search(r'^--- (?:a/)?(.+)$',block,re.M)
            result.append({'path':clean(match[1] if match else 'git diff'),'kind':'update',
                           'diff':clean(block)[:LIMIT],'scope':'tool','truncated':len(block)>LIMIT})
    return result
