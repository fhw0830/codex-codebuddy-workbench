#!/usr/bin/env python3
"""Local HTTP/SSE application, Python 3.11+, no third-party backend packages."""
import argparse
import json
import mimetypes
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from backend.service import Service
from backend.store import clean, now, uid
from backend import local_files

ROOT = Path(__file__).resolve().parent
class WebServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self, format, *args):
        # Never write prompts, credentials or arbitrary request headers to stdout.
        pass

    @property
    def service(self):
        return self.server.service

    def valid_host(self):
        return self.headers.get('Host','').split(':')[0] in ('127.0.0.1','localhost')

    def valid_origin(self):
        origin=self.headers.get('Origin')
        if origin and origin not in (self.server.url, self.server.url.replace('127.0.0.1','localhost')):
            return False
        return self.headers.get('Sec-Fetch-Site') not in ('cross-site',)

    def send(self,data,status=200,kind='application/json; charset=utf-8',download=None):
        blob = json.dumps(data,ensure_ascii=False).encode('utf-8') if kind.startswith('application/json') else data.encode('utf-8') if isinstance(data,str) else data
        self.send_response(status)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(blob)))
        if self.close_connection:self.send_header('Connection','close')
        self.send_header('Cache-Control','no-store' if self.path.startswith('/api/') else 'no-cache')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if download:
            self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+urllib.parse.quote(download))
        self.end_headers()
        try:
            self.wfile.write(blob)
        except (BrokenPipeError,ConnectionResetError):
            pass

    def do_GET(self):
        if not self.valid_host() or not self.valid_origin():
            return self.send({'error':'访问来源不被允许'},403)
        parsed=urllib.parse.urlsplit(self.path)
        path=urllib.parse.unquote(parsed.path)
        query=urllib.parse.parse_qs(parsed.query)
        arg=lambda key,default='':query.get(key,[default])[0]
        try:
            if path=='/api/bootstrap':
                return self.send({'app':'codeduo-workbench','version':'0.1.0','csrf':self.server.csrf,
                    'capabilities':{'streaming_codebuddy':True,'queue':True,'steer':True,'task_plan':True,'directed_handoff':True,'user_questions':True,'phased_execution':True,'independent_conversations':True,'resource_coordination':True,'queue_actions':True,'auto_compaction':True,'resource_release_safe':True,'workbench_inspection':True},
                    'conversations':self.service.store.conversations(),'settings':self.service.store.settings(),
                    'health':self.service.health,'last_event':self.service.store.one('SELECT COALESCE(MAX(seq),0) AS seq FROM events')['seq']})
            if path=='/api/health':
                return self.send({'app':'codeduo-workbench','version':'0.1.0','health':self.service.health})
            if path=='/api/runtime':
                return self.send(self.service.runtime(arg('conversation_id')))
            if path=='/api/conversations':
                return self.send(self.service.store.conversations(arg('archived')=='1',arg('q')))
            if path=='/api/submission':
                conversation_id=arg('conversation_id');self.service.store.conversation(conversation_id)
                row=self.service.store.one('SELECT * FROM jobs WHERE conversation_id=? AND client_key=?',(conversation_id,arg('client_key')))
                return self.send({'found':bool(row),'job':row})
            if path.startswith('/api/conversations/'):
                return self.send(self.service.conversation(path.rsplit('/',1)[1]))
            if path=='/api/documents':
                return self.send(self.service.documents(arg('q')))
            if path=='/api/compaction/archive':
                return self.send(self.service.compaction_archive(arg('id')),download='旧对话原文_'+arg('id')[:12]+'.json')
            if path=='/api/local/files':
                return self.send(local_files.listing(arg('path'),arg('q'),arg('recursive')=='1'))
            if path=='/api/local/document':
                return self.send(local_files.document(arg('path'),arg('start','0')))
            if path=='/api/uploads/image':
                reference=self.service.uploaded_reference(arg('id'))
                if reference['kind']!='image':raise ValueError('附件不是图片')
                file=self.service.upload_path(arg('id'))
                return self.send(file.read_bytes(),kind=mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
            if path=='/api/document':
                return self.send(self.service.document(arg('id')))
            if path=='/api/export':
                id=arg('id')
                if arg('format')=='json':
                    return self.send(self.service.conversation(id),download='协作对话_'+id[:12]+'.json')
                return self.send(self.service.markdown(id),kind='text/markdown; charset=utf-8',download='协作对话_'+id[:12]+'.md')
            if path=='/api/events':
                return self.events(max(int(arg('after','0')),int(self.headers.get('Last-Event-ID','0'))))
            static=(ROOT/'web'/path.lstrip('/')).resolve() if path!='/' else ROOT/'web/index.html'
            if not static.is_relative_to(ROOT/'web') or not static.is_file():
                return self.send({'error':'页面不存在'},404)
            return self.send(static.read_bytes(),kind=mimetypes.guess_type(static.name)[0] or 'application/octet-stream')
        except (ValueError,KeyError) as exc:
            return self.send({'error':clean(str(exc))},400)
        except Exception:
            return self.send({'error':'读取失败，请刷新重试'},500)

    def events(self,seq):
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream; charset=utf-8')
        self.send_header('Cache-Control','no-cache')
        self.send_header('Connection','keep-alive')
        self.end_headers()
        heartbeat=time.monotonic()
        try:
            while not self.server.stopping.is_set():
                rows=self.service.store.rows('SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT 250',(seq,))
                for row in rows:
                    event={'kind':row['kind'],'payload':json.loads(row['payload'])}
                    self.wfile.write(f"id: {row['seq']}\ndata: {json.dumps(event,ensure_ascii=False)}\n\n".encode('utf-8'))
                    seq=row['seq']
                if time.monotonic()-heartbeat>10:
                    self.wfile.write(b': keep-alive\n\n'); heartbeat=time.monotonic()
                self.wfile.flush()
                self.server.stopping.wait(.05)
        except (BrokenPipeError,ConnectionResetError,OSError):
            pass
        self.close_connection=True

    def do_POST(self):
        if not self.valid_host() or not self.valid_origin() or not secrets.compare_digest(self.headers.get('X-Collab-Token',''),self.server.csrf):
            # The request body has not been consumed. Reusing this connection
            # would parse that JSON as the next HTTP request and emit HTML 400.
            self.close_connection=True
            return self.send({'error':'请求校验失败，请刷新网页'},403)
        try:length=int(self.headers.get('Content-Length','0'))
        except ValueError:
            self.close_connection=True
            return self.send({'error':'请求长度无效'},400)
        if self.headers.get('Transfer-Encoding'):
            self.close_connection=True
            return self.send({'error':'暂不支持分块请求体'},400)
        request_path=urllib.parse.urlsplit(self.path).path
        maximum=28000000 if request_path=='/api/uploads' else 600000
        if length<0 or length>maximum:
            self.close_connection=True
            return self.send({'error':'请求内容过大'},413)
        try:
            body=json.loads(self.rfile.read(length) or '{}')
            if not isinstance(body,dict):
                raise ValueError('请求必须是对象')
            path=urllib.parse.urlsplit(self.path).path
            if path=='/api/uploads':
                return self.send(self.service.upload(body),201)
            if path=='/api/storage':
                return self.send(self.service.storage.execute(body))
            if path=='/api/conversations':
                return self.send(self.service.store.create_conversation(body.get('title','新的协作对话'),body.get('brief','')),201)
            if path.startswith('/api/conversations/'):
                parts=path.split('/')
                id=parts[3]
                if len(parts)>4 and parts[4]=='fork':
                    return self.send(self.service.fork(id),201)
                if 'preferences' in body:
                    self.service.set_preferences(id,body['preferences'])
                return self.send(self.service.store.update_conversation(id,body))
            if path=='/api/messages':
                return self.send(self.service.enqueue(body),202)
            if path=='/api/resume':
                return self.send(self.service.resume(body),202)
            if path=='/api/steer':
                return self.send(self.service.steer(body),202)
            if path=='/api/queued-message':
                return self.send(self.service.queued_action(body))
            if path=='/api/answers':
                return self.send(self.service.answer_question(body),202)
            if path=='/api/resource-bridge':return self.send(self.service.resource_bridge(body))
            if path=='/api/question-bridge':
                return self.send(self.service.question_bridge(body))
            if path.startswith('/api/jobs/') and path.endswith('/stop'):
                return self.send(self.service.stop(path.split('/')[3]))
            if path=='/api/tasks':
                conversation=body.get('conversation_id','')
                self.service.store.conversation(conversation)
                title=clean(body.get('title','')).strip()[:300]
                owner=body.get('owner','user')
                if not title or owner not in ('user','codex','codebuddy'):
                    raise ValueError('请填写任务及有效负责人')
                id=uid()
                self.service.store.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?)',(id,conversation,title,owner,'todo',now(),now()))
                self.service.store.event('task',{'conversation_id':conversation})
                return self.send({'id':id},201)
            if path.startswith('/api/tasks/'):
                id=path.rsplit('/',1)[1]
                task=self.service.store.one('SELECT * FROM tasks WHERE id=?',(id,))
                if not task:
                    raise ValueError('任务不存在')
                if body.get('delete'):
                    self.service.store.execute('DELETE FROM tasks WHERE id=?',(id,))
                else:
                    status=body.get('status',task['status'])
                    owner=body.get('owner',task['owner'])
                    title=clean(body.get('title',task['title'])).strip()[:300]
                    if status not in ('todo','active','blocked','done') or owner not in ('user','codex','codebuddy') or not title:
                        raise ValueError('任务状态或负责人无效')
                    self.service.store.execute('UPDATE tasks SET title=?,owner=?,status=?,updated=? WHERE id=?',(title,owner,status,now(),id))
                self.service.store.event('task',{'conversation_id':task['conversation_id']})
                return self.send({'ok':True})
            if path=='/api/settings':
                if 'default_access_mode' in body:
                    if body['default_access_mode'] not in ('discussion','full'):raise ValueError('默认权限无效')
                    self.service.store.set_setting('default_access_mode',body['default_access_mode'])
                if 'workdir' in body:
                    folder=local_files.absolute_path(body['workdir'])
                    if not folder.is_dir():raise ValueError('工作目录不存在')
                    self.service.store.set_setting('workdir',str(folder))
                if 'daily_autosave' in body:
                    self.service.store.set_setting('daily_autosave',bool(body['daily_autosave']))
                return self.send(self.service.store.settings())
            if path=='/api/health/refresh':
                self.service.pool.submit(self.service.refresh_health)
                return self.send({'refreshing':True},202)
            if path=='/api/handoff':
                return self.send(self.service.handoff(body['conversation_id']))
            if path=='/api/shutdown':
                with self.service.dispatch_lock:
                    if self.service.store.rows("SELECT id FROM jobs WHERE status IN ('queued','running')"):
                        return self.send({'error':'仍有任务执行或排队，网页服务未停止'},409)
                    self.service.closing=True
                self.send({'stopping':True})
                self.server.stopping.set()
                threading.Thread(target=self.server.shutdown,daemon=True).start()
                return
            return self.send({'error':'接口不存在'},404)
        except (ValueError,KeyError,TypeError) as exc:
            return self.send({'error':clean(str(exc))},400)
        except Exception:
            return self.send({'error':'操作失败；记录已保留，请刷新重试'},500)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--open',action='store_true')
    parser.add_argument('--offline',action='store_true',help='Preview the UI without starting either agent CLI')
    parser.add_argument('--data',type=Path)
    parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    service=Service(ROOT,args.data,args.archive,connect=not args.offline)
    server=None
    try:
        for port in range(args.port,args.port+10):
            try:
                server=WebServer(('127.0.0.1',port),Handler)
                break
            except OSError:
                continue
        if server is None:
            raise RuntimeError('8766附近端口不可用')
        server.service=service
        server.csrf=secrets.token_urlsafe(32)
        server.stopping=threading.Event()
        server.url=f'http://127.0.0.1:{server.server_address[1]}'
        service.question_bridge_url=server.url
        (service.data/'server.json').write_text(json.dumps({'url':server.url,'started':now()},ensure_ascii=False),encoding='utf-8')
        print(server.url,flush=True)
        if args.open:
            webbrowser.open(server.url)
        server.serve_forever(poll_interval=.3)
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.stopping.set()
            server.server_close()
        service.close()

if __name__=='__main__':
    main()
