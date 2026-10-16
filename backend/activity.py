"""Ordered public text, tool calls and human questions; no private reasoning."""
import copy
import threading
from .store import clean,now

class Activity:
    def __init__(self):
        self.items=[];self.index={};self.lock=threading.RLock()
    def _set(self,key,fields):
        with self.lock:
            if key not in self.index:
                self.index[key]=len(self.items);self.items.append({'id':key,'at':now()})
            self.items[self.index[key]].update(fields)
    def text(self,item):
        text=clean(item.get('text',''))
        if text:self._set('text:'+str(item['id']),{'type':'text','text':text,'phase':item.get('phase')})
    def tool(self,record):
        self._set('tool:'+record['id'],{'type':'tool','tool':copy.deepcopy(record)})
    def question(self,id):self._set('question:'+id,{'type':'question','question_id':id})
    def snapshot(self):
        with self.lock:return copy.deepcopy(self.items)
