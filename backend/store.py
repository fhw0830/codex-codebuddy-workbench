import datetime as dt
import json
import re
import sqlite3
import threading
import uuid
from pathlib import Path

ZONE = dt.timezone(dt.timedelta(hours=8))
def now():
    return dt.datetime.now(ZONE).isoformat(timespec='seconds')
def uid():
    return uuid.uuid4().hex
def _hide_assigned_secrets(text):
    pattern = r'''(?im)(?<![\w])((?:["']?)(?:api[_-]?key|access[_-]?token|password|passwd|pwd|密码)(?:["']?)\s*[=:：]\s*)(?!["']?\[凭据已隐藏\])("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s"',;{}\]]+)'''
    def hide(match):
        value=match[2]
        quote=value[0] if value[:1] in ('"',"'") else ''
        return match[1]+quote+'[凭据已隐藏]'+quote
    return re.sub(pattern,hide,text)

def clean(text):
    text = str(text or '')
    text = re.sub(r'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----.*?-----END (?:OPENSSH |RSA |EC )?PRIVATE KEY-----', '[私钥已隐藏]', text, flags=re.S)
    text = _hide_assigned_secrets(text)
    text = re.sub(r'(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s\"\',;]+',r'\1[凭据已隐藏]',text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]{16,}\b', '[凭据已隐藏]', text)
    return text

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,title TEXT NOT NULL,brief TEXT NOT NULL DEFAULT '',
                archived INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL,updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,conversation_id TEXT REFERENCES conversations(id),role TEXT,agent TEXT,
                content TEXT NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL,meta TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,conversation_id TEXT REFERENCES conversations(id),title TEXT NOT NULL,
                owner TEXT NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,conversation_id TEXT REFERENCES conversations(id),status TEXT NOT NULL,
                route TEXT NOT NULL,rounds INTEGER NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,
                client_key TEXT UNIQUE,error TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,payload TEXT NOT NULL,created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS compactions (
                id TEXT PRIMARY KEY,conversation_id TEXT REFERENCES conversations(id),created TEXT,
                summary TEXT NOT NULL,archive_path TEXT NOT NULL,archive_json TEXT NOT NULL,meta TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS input_requests (
                id TEXT PRIMARY KEY,conversation_id TEXT REFERENCES conversations(id),job_id TEXT,message_id TEXT,
                agent TEXT,state TEXT,questions TEXT,answers TEXT NOT NULL DEFAULT '{}',transport TEXT,
                blocking INTEGER,created TEXT,updated TEXT,user_message_id TEXT);
        ''')
        # Preserve answerable questions after a web/process restart; never replay work automatically.
        self.db.execute("UPDATE jobs SET status='waiting_input',updated=? WHERE status='running' AND id IN (SELECT job_id FROM input_requests WHERE state IN ('pending','submitted','followup'))",(now(),))
        self.db.execute("UPDATE messages SET meta=json_set(meta,'$.delivery.state','waiting') WHERE role='user' AND COALESCE(json_extract(meta,'$.delivery.mode'),'send') NOT IN ('steer','answer') AND json_extract(meta,'$.job_id') IN (SELECT id FROM jobs WHERE status='waiting_input')")
        self.db.execute("UPDATE jobs SET status='interrupted',error='网页服务中断；未自动重复提交',updated=? WHERE status IN ('queued','running')", (now(),))
        self.db.execute("UPDATE messages SET status='interrupted' WHERE status='streaming'")
        self.db.execute("UPDATE input_requests SET state='followup',updated=? WHERE state IN ('pending','submitted')",(now(),))
        self.db.execute("UPDATE messages SET meta=json_set(meta,'$.delivery.state','interrupted') WHERE role='user' AND json_extract(meta,'$.delivery.state') IN ('queued','pending') AND json_extract(meta,'$.job_id') IN (SELECT id FROM jobs WHERE status='interrupted')")
        self.db.execute("UPDATE messages SET meta=json_set(meta,'$.delivery.state','interrupted','$.timing.status','interrupted','$.timing.elapsed_s',NULL) WHERE role='user' AND json_extract(meta,'$.delivery.state')='started' AND json_extract(meta,'$.job_id') IN (SELECT id FROM jobs WHERE status='interrupted')")
        self.db.commit()

    def execute(self, sql, args=()):
        with self.lock:
            cursor = self.db.execute(sql, args)
            self.db.commit()
            return cursor

    def rows(self, sql, args=()):
        with self.lock:
            return [dict(row) for row in self.db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.rows(sql, args)
        return rows[0] if rows else None

    def event(self, kind, payload):
        return self.execute('INSERT INTO events(kind,payload,created) VALUES(?,?,?)', (kind, json.dumps(payload, ensure_ascii=False), now())).lastrowid

    def conversations(self, archived=False, search=''):
        items=self._conversations(archived,search)
        for item in items:
            item['waiting_input']=bool(self.one("SELECT id FROM input_requests WHERE conversation_id=? AND state IN ('pending','followup') AND blocking=1 AND job_id IN (SELECT id FROM jobs WHERE status IN ('running','waiting_input')) LIMIT 1",(item['id'],)))
        return items

    def _conversations(self, archived=False, search=''):
        if search:
            return self.rows('''SELECT DISTINCT c.*,EXISTS(SELECT 1 FROM jobs j WHERE j.conversation_id=c.id AND j.status IN ('queued','running','waiting_input')) AS busy FROM conversations c LEFT JOIN messages m ON m.conversation_id=c.id
                WHERE c.archived=? AND (c.title LIKE ? OR m.content LIKE ?) ORDER BY c.updated DESC''', (int(archived), '%'+search+'%', '%'+search+'%'))
        return self.rows("SELECT c.*,EXISTS(SELECT 1 FROM jobs j WHERE j.conversation_id=c.id AND j.status IN ('queued','running','waiting_input')) AS busy FROM conversations c WHERE archived=? ORDER BY updated DESC", (int(archived),))

    def create_conversation(self, title='新的协作对话', brief=''):
        item = dict(id=uid(), title=clean(title)[:100] or '新的协作对话', brief=clean(brief)[:16000], archived=0, created=now(), updated=now())
        self.execute('INSERT INTO conversations VALUES(:id,:title,:brief,:archived,:created,:updated)', item)
        self.event('conversation', {'id':item['id']})
        return item

    def conversation(self, id):
        item = self.one('SELECT * FROM conversations WHERE id=?', (id,))
        if not item:
            raise ValueError('对话不存在')
        if item['archived']==2:
            raise ValueError('对话已在回收区，请从存储管理恢复')
        item['messages'] = self.rows('SELECT * FROM messages WHERE conversation_id=? ORDER BY rowid', (id,))
        for message in item['messages']:
            message['meta'] = json.loads(message['meta'])
        item['tasks'] = self.rows('SELECT * FROM tasks WHERE conversation_id=? ORDER BY created DESC', (id,))
        item['job'] = self.one("SELECT * FROM jobs WHERE conversation_id=? ORDER BY rowid DESC LIMIT 1", (id,))
        active=self.one("SELECT * FROM jobs WHERE conversation_id=? AND status IN ('queued','running','waiting_input') ORDER BY rowid LIMIT 1",(id,))
        if active:item['job']=active
        item['queue']=self.rows("SELECT * FROM jobs WHERE conversation_id=? AND status='queued' AND id!=? ORDER BY rowid",(id,(active or {}).get('id','')))
        item['compactions']=self.rows('SELECT id,created,summary,meta FROM compactions WHERE conversation_id=? ORDER BY rowid',(id,))
        for c in item['compactions']:c['meta']=json.loads(c['meta'])
        item['compression']=self.setting('compression:'+id,{})
        return item

    def update_conversation(self, id, changes):
        if self.conversation(id)['archived']==2:
            raise ValueError('对话已在回收区，请从存储管理恢复')
        for key in ('title','brief','archived'):
            if key in changes:
                value = int(bool(changes[key])) if key == 'archived' else clean(changes[key])[:100 if key == 'title' else 16000]
                self.execute(f'UPDATE conversations SET {key}=?,updated=? WHERE id=?', (value, now(), id))
        self.event('conversation', {'id':id})
        return self.conversation(id)

    def message(self, conversation_id, role, agent, content='', status='completed', meta=None):
        id = uid()
        self.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?)', (id,conversation_id,role,agent,clean(content),status,now(),json.dumps(meta or {}, ensure_ascii=False)))
        self.execute('UPDATE conversations SET updated=? WHERE id=?', (now(),conversation_id))
        self.event('message', {'conversation_id':conversation_id,'id':id})
        return id

    def update_message(self, id, content, status='streaming', meta=None):
        with self.lock:
            old=self.one('SELECT conversation_id,content,status FROM messages WHERE id=?',(id,))
            if not old:
                raise ValueError('回复不存在')
            content=clean(content)
            if meta is None:
                self.execute('UPDATE messages SET content=?,status=? WHERE id=?', (content,status,id))
            else:
                self.execute('UPDATE messages SET content=?,status=?,meta=? WHERE id=?', (content,status,json.dumps(meta,ensure_ascii=False),id))
            payload={'id':id,'conversation_id':old['conversation_id']}
            if status=='streaming' and meta is None and content.startswith(old['content']):
                payload.update({'base_length':len(old['content'].encode('utf-16-le'))//2,'delta':content[len(old['content']):]})
                if payload['delta']:
                    self.event('message_delta',payload)
            else:
                self.event('message',payload)

    def setting(self, key, default=None):
        item = self.one('SELECT value FROM settings WHERE key=?',(key,))
        return json.loads(item['value']) if item else default

    def settings(self):
        return {row['key']:json.loads(row['value']) for row in self.rows('SELECT * FROM settings')}

    def set_setting(self, key, value):
        self.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key,json.dumps(value,ensure_ascii=False)))

    def create_job(self, conversation_id, route, rounds, client_key, content, meta, allow_queue=False, message_id=None):
        # Enqueue and user message are one transaction, including idempotency.
        with self.lock:
            existing = self.one('SELECT * FROM jobs WHERE client_key=?', (client_key,))
            if existing:
                if existing['conversation_id'] != conversation_id:
                    raise ValueError('消息标识属于其他对话')
                return existing, False
            conversation = self.conversation(conversation_id)
            if conversation['archived']:
                raise ValueError('请先恢复归档对话')
            if not allow_queue and self.one("SELECT id FROM jobs WHERE conversation_id=? AND status IN ('queued','running','waiting_input')",(conversation_id,)):
                raise ValueError('这条对话仍在生成，请先等待或停止')
            if len(self.rows("SELECT id FROM jobs WHERE conversation_id=? AND status='queued'",(conversation_id,)))>=20:
                raise ValueError('待发送消息已达20条，请先等待当前任务完成')
            job = dict(id=uid(),conversation_id=conversation_id,status='queued',route=route,rounds=rounds,created=now(),updated=now(),client_key=client_key,error='')
            meta={**meta,'job_id':job['id'],'delivery':{'mode':'queue' if allow_queue else 'send','state':'queued'}}
            try:
                self.db.execute('INSERT INTO jobs VALUES(:id,:conversation_id,:status,:route,:rounds,:created,:updated,:client_key,:error)',job)
                if message_id:
                    owned=self.one("SELECT id FROM messages WHERE id=? AND conversation_id=? AND role='user'",(message_id,conversation_id))
                    if not owned:raise ValueError('补充消息不属于当前对话')
                    self.db.execute('UPDATE messages SET content=?,meta=? WHERE id=?',(clean(content),json.dumps(meta,ensure_ascii=False),message_id))
                else:
                    self.db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?)',(uid(),conversation_id,'user','user',clean(content),'completed',now(),json.dumps(meta,ensure_ascii=False)))
                title = conversation['title']
                if title == '新的协作对话':
                    title = clean(content).replace('\n',' ')[:26] or title
                self.db.execute('UPDATE conversations SET title=?,updated=? WHERE id=?',(title,now(),conversation_id))
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
        self.event('job',{'id':job['id'],'conversation_id':conversation_id})
        return job, True

    def update_job(self, id, status, error=''):
        self.execute('UPDATE jobs SET status=?,error=?,updated=? WHERE id=?', (status,clean(error),now(),id))
        item = self.one('SELECT * FROM jobs WHERE id=?',(id,))
        self.event('job',{'id':id,'conversation_id':item['conversation_id']})
