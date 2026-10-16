"""Persistent HTTP rejection must not poison the next request with unread JSON."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.service import Service
from server import WebServer,Handler

class RejectedBody(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.service=Service(ROOT,root/'data',root/'archive',connect=False)
        self.server=WebServer(('127.0.0.1',0),Handler);self.server.service=self.service;self.server.csrf='fixture-token';self.server.stopping=threading.Event()
        self.server.url='http://127.0.0.1:'+str(self.server.server_address[1]);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.client=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=3)
    def tearDown(self):
        self.client.close();self.server.shutdown();self.server.server_close();self.service.close();self.service.store.db.close();self.temp.cleanup()
    def verify_next_get(self,response,status):
        self.assertEqual(response.status,status);self.assertTrue(response.will_close);json.loads(response.read())
        self.client.request('GET','/api/health');next=self.client.getresponse()
        self.assertEqual(next.status,200);self.assertEqual(json.loads(next.read())['app'],'codeduo-workbench')
    def test_expired_token_then_bootstrap_does_not_receive_html(self):
        self.client.request('POST','/api/settings',body=json.dumps({'synthetic':True}),headers={'X-Collab-Token':'expired','Content-Type':'application/json'})
        self.verify_next_get(self.client.getresponse(),403)
        self.client.request('POST','/api/settings',body=json.dumps({'daily_autosave':False}),headers={'X-Collab-Token':'fixture-token','Content-Type':'application/json'})
        r=self.client.getresponse();self.assertEqual(r.status,200);json.loads(r.read())
    def test_oversized_body_rejection_closes_unread_connection(self):
        self.client.request('POST','/api/settings',body=b'',headers={'X-Collab-Token':'fixture-token','Content-Length':'999999999'})
        self.verify_next_get(self.client.getresponse(),413)
    def test_invalid_length_is_json_and_connection_is_closed(self):
        self.client.request('POST','/api/settings',body=b'',headers={'X-Collab-Token':'fixture-token','Content-Length':'bad'})
        self.verify_next_get(self.client.getresponse(),400)

if __name__=='__main__':unittest.main()
