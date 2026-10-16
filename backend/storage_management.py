"""Explicit, scoped housekeeping. Preview first; never follow links or purge in use."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time
from .store import now,uid

BUSY="('queued','running','waiting_input')"
UID=re.compile(r'^[a-f0-9]{32}$')
DATE=re.compile(r'^\d{4}-\d{2}-\d{2}$')
EXPORT=re.compile(r'^(?:网页对话_[a-f0-9]{32}|网页交接_\d{6}_[a-f0-9]{12})\.md$')
GRACE=7*86400

class StorageManagement:
    def __init__(self,service):
        self.service=service;self.store=service.store;self.plans={}
        self.store.execute('CREATE TABLE IF NOT EXISTS storage_trash_files (id TEXT PRIMARY KEY,relative_path TEXT NOT NULL,bytes INTEGER NOT NULL,created TEXT NOT NULL)')

    def idle(self):
        if self.service.closing:raise ValueError('网页正在更新，请稍后操作')
        if self.store.one(f'SELECT id FROM jobs WHERE status IN {BUSY} LIMIT 1'):
            raise ValueError('仍有执行、排队或等待回答的任务；仅可查看，结束任务后再清理')

    def safe(self,path,root,missing=False):
        root=Path(root).absolute();path=Path(path).absolute()
        try:relative=path.relative_to(root)
        except ValueError:raise ValueError('文件超出协作台管理范围')
        for part in (root,*[root.joinpath(*relative.parts[:n]) for n in range(1,len(relative.parts)+1)]):
            try:info=part.lstat()
            except FileNotFoundError:
                if missing:continue
                raise ValueError('文件已不存在，请重新预览')
            if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                raise ValueError('链接或重解析目录不参与清理')
        if not path.resolve().is_relative_to(root.resolve()):raise ValueError('文件超出协作台管理范围')
        return path

    def ids(self,values):
        if not isinstance(values,list) or not values or len(values)>200:raise ValueError('请选择1至200项')
        if any(not isinstance(v,str) for v in values):raise ValueError('选择项无效')
        return list(dict.fromkeys(values))

    def references(self):
        uploads=set();archives=set()
        def walk(value):
            if isinstance(value,dict):
                if isinstance(value.get('upload_id'),str):uploads.add(value['upload_id'])
                for child in value.values():walk(child)
            elif isinstance(value,list):
                for child in value:walk(child)
        # Include queued snapshots, trash conversations, and compressed originals.
        for row in self.store.rows('SELECT meta FROM messages'):
            try:walk(json.loads(row['meta']))
            except (ValueError,TypeError):raise ValueError('消息引用记录无法核对，暂不清理附件')
        for row in self.store.rows('SELECT archive_path,archive_json FROM compactions'):
            archives.add(str(Path(row['archive_path']).resolve()))
            try:walk(json.loads(row['archive_json']))
            except (ValueError,TypeError):raise ValueError('压缩原文引用无法核对，暂不清理附件')
        return uploads,archives

    def garbage(self,protected=()):
        uploads,archives=self.references();uploads.update(protected)
        items=[];cutoff=time.time()-GRACE;data=self.service.data
        root=data/'uploads'
        if root.exists():
            self.safe(root,data)
            for folder in list(root.iterdir())[:10000]:
                try:
                    if not UID.fullmatch(folder.name) or folder.name in uploads:continue
                    self.safe(folder,root)
                    if not folder.is_dir():continue
                    files=list(folder.iterdir())
                    if any(not p.is_file() or p.name!='metadata.json' and not re.fullmatch(r'file(?:\.[a-z0-9]+)?',p.name) for p in files):continue
                    for p in files:self.safe(p,root)
                    if max([folder.stat().st_mtime]+[p.stat().st_mtime for p in files])>cutoff:continue
                    title='未完成的上传'
                    metadata=folder/'metadata.json'
                    if metadata.exists():
                        title=json.loads(metadata.read_text(encoding='utf-8')).get('name','未引用附件')
                    items.append(self.item('upload',folder,files,str(title),data))
                except (OSError,ValueError,TypeError):continue
        root=data/'context-archives'
        if root.exists():
            self.safe(root,data)
            for folder in list(root.iterdir())[:10000]:
                try:
                    self.safe(folder,root)
                    if not UID.fullmatch(folder.name) or not folder.is_dir():continue
                    for path in list(folder.iterdir())[:10000]:
                        self.safe(path,root)
                        if path.is_file() and re.fullmatch(r'[a-f0-9]{32}\.json',path.name) and str(path.resolve()) not in archives and path.stat().st_mtime<=cutoff:
                            items.append(self.item('orphan_archive',path,[path],'未登记的压缩原文',data))
                except (OSError,ValueError):continue
        return items

    def item(self,kind,path,files,title,root):
        signatures=[(str(p.relative_to(root)),p.stat().st_size,p.stat().st_mtime_ns) for p in sorted(files)]
        key=hashlib.sha256((kind+str(path.relative_to(root))).encode()).hexdigest()
        return {'id':key,'kind':kind,'name':title,'relative_path':path.relative_to(root).as_posix(),
            'bytes':sum(row[1] for row in signatures),'signature':signatures,'files':files,'path':path}

    def archive_files(self):
        root=self.service.archive;result=[]
        if not root.is_dir():return result
        for day in sorted(root.iterdir(),reverse=True):
            if not DATE.fullmatch(day.name):continue
            for owner in ('Codex','CodeBuddy'):
                folder=day/owner
                try:
                    self.safe(folder,root)
                    if not folder.is_dir():continue
                    for file in folder.iterdir():
                        if not EXPORT.fullmatch(file.name):continue
                        self.safe(file,root)
                        if not file.is_file():continue
                        relative=file.relative_to(root).as_posix()
                        result.append({'id':hashlib.sha256(relative.encode()).hexdigest(),'name':relative,'bytes':file.stat().st_size,'path':file})
                        if len(result)>=2000:return result
                except (OSError,ValueError):continue
        return result

    def overview(self,protected=()):
        candidates=self.garbage(protected)
        public=lambda item:{key:item[key] for key in ('id','name','bytes','relative_path')}
        self.plans={key:value for key,value in self.plans.items() if value['expires']>time.monotonic()}
        if len(self.plans)>=20:self.plans.pop(next(iter(self.plans)))
        token=secrets.token_urlsafe(24)
        self.plans[token]={'expires':time.monotonic()+600,'protected':set(protected),'items':{item['id']:item for item in candidates}}
        query='SELECT c.id,c.title,c.updated,(SELECT count(*) FROM messages m WHERE m.conversation_id=c.id) AS messages FROM conversations c WHERE c.archived=? ORDER BY c.updated DESC'
        return {'plan_token':token,'grace_days':7,'estimated_bytes':sum(i['bytes'] for i in candidates),
            'garbage':[public(i) for i in candidates[:2000]],
            'archived':self.store.rows(query,(1,)),'trash':self.store.rows(query,(2,)),
            'archive_files':[{k:i[k] for k in ('id','name','bytes')} for i in self.archive_files()],
            'trash_files':self.store.rows('SELECT * FROM storage_trash_files ORDER BY created DESC'),
            'busy':bool(self.store.one(f'SELECT id FROM jobs WHERE status IN {BUSY} LIMIT 1')),
            'database_bytes':sum(p.stat().st_size for p in (self.service.data/'collaboration.sqlite3',self.service.data/'collaboration.sqlite3-wal') if p.exists()),
            'notes':['清理只涉及协作台自有文件；当前日志、配置和源码不在清理范围。','附件需超过7天、未被任何消息或压缩原文引用，且不在本浏览器草稿中。其他浏览器草稿请先发送或导出。','每日导出文件单独管理；删除对话不会自动删除这些导出文件。']}

    def execute(self,body):
        action=body.get('action')
        with self.service.dispatch_lock,self.store.lock:
            if action=='inspect':
                protected=body.get('protected_upload_ids',[])
                if not isinstance(protected,list) or len(protected)>10000:raise ValueError('草稿附件保护列表无效')
                return self.overview([v for v in protected if isinstance(v,str) and UID.fullmatch(v)])
            self.idle()
            if action=='cleanup':return self.cleanup(body)
            if action in ('trash_conversations','restore_conversations','purge_conversations'):return self.conversations(action,body)
            if action in ('trash_files','restore_files','purge_files'):return self.files(action,body)
            if action=='compact_database':
                if body.get('confirmation')!='整理数据库':raise ValueError('请确认整理数据库')
                self.store.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                self.store.db.execute('VACUUM')
                self.store.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                return {'ok':True,'message':'数据库已整理；不会删除对话记录'}
            raise ValueError('存储管理操作无效')

    def cleanup(self,body):
        if body.get('confirmation')!='清理选中垃圾':raise ValueError('请确认具体清理范围')
        plan=self.plans.pop(body.get('plan_token',''),None)
        if not plan or plan['expires']<=time.monotonic():raise ValueError('预览已失效，请重新扫描')
        ids=self.ids(body.get('ids'))
        protected=body.get('protected_upload_ids',[])
        if not isinstance(protected,list) or len(protected)>10000:raise ValueError('草稿附件保护列表无效')
        protected=plan['protected']|{v for v in protected if isinstance(v,str) and UID.fullmatch(v)}
        fresh={i['id']:i for i in self.garbage(protected)}
        for id in ids:
            if id not in plan['items'] or id not in fresh or fresh[id]['signature']!=plan['items'][id]['signature']:
                raise ValueError('文件或引用已变化，未开始清理，请重新扫描')
        removed=[];freed=0
        for id in ids:
            item=fresh[id]
            try:
                for file in item['files']:
                    self.safe(file,self.service.data);file.unlink()
                if item['kind']=='upload':item['path'].rmdir()
                removed.append(id);freed+=item['bytes']
            except OSError:
                return {'ok':False,'removed':removed,'removed_bytes':freed,'message':'部分文件被占用或无权限，已完成部分不会重放，请重新扫描'}
        self.store.event('storage',{'action':'cleanup','count':len(removed)})
        return {'ok':True,'removed':removed,'removed_bytes':freed,'message':f'已清理{len(removed)}项'}

    def conversations(self,action,body):
        ids=self.ids(body.get('ids'));rows=[]
        for id in ids:
            row=self.store.one('SELECT * FROM conversations WHERE id=?',(id,))
            if not row or row['archived']!=(1 if action=='trash_conversations' else 2):raise ValueError('只可处理当前归档或回收区中的对话，请刷新列表')
            rows.append(row)
        if action=='purge_conversations' and body.get('confirmation')!='永久删除':raise ValueError('请确认永久删除选中的对话')
        if action!='purge_conversations':
            target=2 if action=='trash_conversations' else 1
            try:
                self.store.db.executemany('UPDATE conversations SET archived=?,updated=? WHERE id=?',[(target,now(),r['id']) for r in rows])
                self.store.db.commit()
            except Exception:self.store.db.rollback();raise
        else:
            paths=[]
            all_archives=self.store.rows('SELECT conversation_id,archive_path FROM compactions')
            for id in ids:
                for row in self.store.rows('SELECT archive_path FROM compactions WHERE conversation_id=?',(id,)):
                    path=Path(row['archive_path'])
                    root=self.service.data/'context-archives'
                    self.safe(path,root,missing=True)
                    relative=path.absolute().relative_to(root.absolute())
                    if len(relative.parts)!=2 or not UID.fullmatch(relative.parts[0]) or not re.fullmatch(r'[a-f0-9]{32}\.json',relative.parts[1]):
                        raise ValueError('压缩原文路径不是协作台生成的文件，未删除对话')
                    if path.exists():
                        other=[r for r in all_archives if Path(r['archive_path']).resolve()==path.resolve()]
                        if all(r['conversation_id'] in ids for r in other):paths.append(path)
            try:
                for table in ('messages','tasks','jobs','input_requests','compactions'):
                    self.store.db.executemany('DELETE FROM '+table+' WHERE conversation_id=?',[(id,) for id in ids])
                for id in ids:
                    self.store.db.execute('DELETE FROM settings WHERE key IN (?,?)',('models:'+id,'compression:'+id))
                    self.store.db.execute("DELETE FROM events WHERE json_valid(payload) AND (json_extract(payload,'$.conversation_id')=? OR (kind='conversation' AND json_extract(payload,'$.id')=?))",(id,id))
                self.store.db.executemany('DELETE FROM conversations WHERE id=?',[(id,) for id in ids])
                self.store.db.commit()
            except Exception:self.store.db.rollback();raise
            # Unlinked archives become previewable garbage if a file removal fails.
            remaining=0
            for path in set(paths):
                try:self.safe(path,self.service.data/'context-archives');path.unlink(missing_ok=True)
                except (OSError,ValueError):remaining+=1
        self.store.event('storage',{'action':action,'conversation_ids':ids})
        return {'ok':True,'conversation_ids':ids,'message':'已移入回收区，可恢复' if action=='trash_conversations' else '已恢复到归档列表' if action=='restore_conversations' else '已永久删除选中对话；附件和每日导出单独管理','pending_archive_files':remaining if action=='purge_conversations' else 0}

    def files(self,action,body):
        ids=self.ids(body.get('ids'));root=self.service.data/'storage-trash'
        completed=[]
        if action=='trash_files':
            available={i['id']:i for i in self.archive_files()}
            if any(id not in available for id in ids):raise ValueError('文件列表已变化，请重新扫描')
            for id in ids:
                item=available[id];source=self.safe(item['path'],self.service.archive)
                trash_id=uid();folder=root/trash_id;self.safe(folder,self.service.data,missing=True);folder.mkdir(parents=True)
                target=folder/'file'
                try:source.replace(target)
                except OSError:
                    folder.rmdir()
                    return self.file_failure(action,completed)
                try:self.store.execute('INSERT INTO storage_trash_files VALUES(?,?,?,?)',(trash_id,item['name'],item['bytes'],now()))
                except Exception:target.replace(source);folder.rmdir();raise
                completed.append(id)
        else:
            if action=='purge_files' and body.get('confirmation')!='永久删除':raise ValueError('请确认永久删除选中的文件')
            rows=[]
            for id in ids:
                if not UID.fullmatch(id):raise ValueError('文件标识无效')
                row=self.store.one('SELECT * FROM storage_trash_files WHERE id=?',(id,))
                if not row:raise ValueError('回收文件已变化，请刷新')
                source=self.safe(root/id/'file',root,missing=action=='purge_files')
                target=self.safe(self.service.archive/row['relative_path'],self.service.archive,missing=True)
                if action=='restore_files' and target.exists():raise ValueError('原位置已有同名文件，未覆盖，请先处理冲突')
                rows.append((row,source,target))
            for row,source,target in rows:
                try:
                    if action=='restore_files':
                        target.parent.mkdir(parents=True,exist_ok=True);source.replace(target)
                        try:self.store.execute('DELETE FROM storage_trash_files WHERE id=?',(row['id'],))
                        except Exception:target.replace(source);raise
                    else:
                        source.unlink(missing_ok=True);self.store.execute('DELETE FROM storage_trash_files WHERE id=?',(row['id'],))
                    completed.append(row['id'])
                    try:source.parent.rmdir()
                    except OSError:pass
                except OSError:return self.file_failure(action,completed)
        self.store.event('storage',{'action':action,'count':len(ids)})
        return {'ok':True,'message':'已移入文件回收区，可恢复' if action=='trash_files' else '文件已恢复' if action=='restore_files' else '选中文件已永久删除'}

    def file_failure(self,action,completed):
        self.store.event('storage',{'action':action,'count':len(completed),'partial':True})
        return {'ok':False,'completed_ids':completed,'message':f'已完成{len(completed)}项；其余文件被占用或无权限，已刷新列表，请重新选择'}
