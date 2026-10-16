"""Housekeeping against synthetic, disposable state only."""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.service import Service
from backend.store import uid,now

class Storage(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.service=Service(ROOT,self.root/'data',self.root/'archive',connect=False)
        self.service.store.set_setting('daily_autosave',False)
        self.s=self.service.storage;self.db=self.service.store
        self.id=self.db.conversations()[0]['id']
    def tearDown(self):
        self.service.close();self.db.db.close();self.temp.cleanup()
    def call(self,action,**data):return self.s.execute({'action':action,**data})
    def upload(self,old=True):
        ref=self.service.upload({'name':'fixture.txt','data':base64.b64encode(b'fixture').decode()})
        folder=self.service.data/'uploads'/ref['upload_id']
        if old:
            for p in (*folder.iterdir(),folder):os.utime(p,(1,1))
        return ref,folder
    def clean(self,view,ids=None,**extra):return self.call('cleanup',plan_token=view['plan_token'],ids=ids or [i['id'] for i in view['garbage']],confirmation='清理选中垃圾',**extra)
    def archive(self):self.db.update_conversation(self.id,{'archived':True})
    def export(self):
        path=self.service.archive/'2026-10-15'/'Codex'/('网页对话_'+uid()+'.md')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic history',encoding='utf-8');return path
    def test_old_orphan_can_be_cleaned_but_recent_upload_cannot(self):
        _,old=self.upload();_,recent=self.upload(False)
        view=self.call('inspect');self.assertEqual(len(view['garbage']),1)
        result=self.clean(view);self.assertTrue(result['ok']);self.assertFalse(old.exists());self.assertTrue(recent.exists())
    def test_message_compressed_original_and_browser_draft_protect_uploads(self):
        refs=[self.upload()[0] for _ in range(3)]
        self.db.message(self.id,'user','user','x',meta={'references':[refs[0]]})
        self.db.execute('INSERT INTO compactions VALUES(?,?,?,?,?,?,?)',(uid(),self.id,now(),'summary','missing',json.dumps({'messages':[{'meta':{'references':[refs[1]]}}]}),'{}'))
        view=self.call('inspect',protected_upload_ids=[refs[2]['upload_id']]);self.assertEqual(view['garbage'],[])
    def test_reference_added_after_preview_prevents_cleaning(self):
        ref,folder=self.upload();view=self.call('inspect')
        self.db.message(self.id,'user','user','x',meta={'references':[ref]})
        with self.assertRaises(ValueError):self.clean(view)
        self.assertTrue(folder.exists())
    def test_new_browser_draft_after_preview_is_protected(self):
        ref,folder=self.upload();view=self.call('inspect')
        with self.assertRaises(ValueError):self.clean(view,protected_upload_ids=[ref['upload_id']])
        self.assertTrue(folder.exists())
    def test_changed_file_requires_new_preview_and_confirmation(self):
        _,folder=self.upload();view=self.call('inspect')
        with self.assertRaises(ValueError):self.call('cleanup',plan_token=view['plan_token'],ids=[view['garbage'][0]['id']])
        (folder/'file.txt').write_text('changed')
        with self.assertRaises(ValueError):self.clean(view)
        self.assertTrue(folder.exists())
    def test_active_waiting_and_queued_jobs_block_mutation(self):
        _,folder=self.upload()
        for status in ('queued','running','waiting_input'):
            job=uid();self.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)',(job,self.id,status,'codex',1,now(),now(),job,''))
            view=self.call('inspect');self.assertTrue(view['busy'])
            with self.assertRaises(ValueError):self.clean(view)
            self.db.execute('DELETE FROM jobs WHERE id=?',(job,))
        self.assertTrue(folder.exists())
    def test_only_archived_conversations_can_enter_trash_and_restore(self):
        with self.assertRaises(ValueError):self.call('trash_conversations',ids=[self.id])
        self.archive();self.call('trash_conversations',ids=[self.id])
        self.assertEqual(self.db.conversations(True),[])
        with self.assertRaises(ValueError):self.db.conversation(self.id)
        self.call('restore_conversations',ids=[self.id])
        self.assertEqual(self.db.conversation(self.id)['archived'],1)
    def test_permanent_delete_needs_confirmation_and_removes_event_content(self):
        self.db.message(self.id,'user','user','DELETE_FIXTURE');self.archive()
        self.call('trash_conversations',ids=[self.id])
        with self.assertRaises(ValueError):self.call('purge_conversations',ids=[self.id])
        self.call('purge_conversations',ids=[self.id],confirmation='永久删除')
        self.assertIsNone(self.db.one('SELECT id FROM conversations WHERE id=?',(self.id,)))
        self.assertEqual(self.db.rows('SELECT * FROM messages'),[])
        self.assertFalse(any('DELETE_FIXTURE' in row['payload'] for row in self.db.rows('SELECT payload FROM events')))
    def test_trash_keeps_attachment_references_until_permanent_delete(self):
        ref,_=self.upload();self.db.message(self.id,'user','user','x',meta={'references':[ref]});self.archive()
        self.call('trash_conversations',ids=[self.id]);self.assertEqual(self.call('inspect')['garbage'],[])
        self.call('purge_conversations',ids=[self.id],confirmation='永久删除')
        self.assertEqual(len(self.call('inspect')['garbage']),1)
    def test_file_trash_restore_and_permanent_delete(self):
        path=self.export();files=self.call('inspect')['archive_files'];self.assertEqual(len(files),1)
        self.call('trash_files',ids=[files[0]['id']]);self.assertFalse(path.exists())
        row=self.call('inspect')['trash_files'][0]
        self.call('restore_files',ids=[row['id']]);self.assertEqual(path.read_text(),'synthetic history')
        self.call('trash_files',ids=[files[0]['id']]);row=self.call('inspect')['trash_files'][0]
        with self.assertRaises(ValueError):self.call('purge_files',ids=[row['id']])
        self.call('purge_files',ids=[row['id']],confirmation='永久删除')
        self.assertEqual(self.call('inspect')['trash_files'],[])
    def test_restore_never_overwrites_a_new_export(self):
        path=self.export();file=self.call('inspect')['archive_files'][0];self.call('trash_files',ids=[file['id']])
        row=self.call('inspect')['trash_files'][0];path.write_text('newer')
        with self.assertRaises(ValueError):self.call('restore_files',ids=[row['id']])
        self.assertEqual(path.read_text(),'newer')
    def test_source_config_and_unrelated_daily_files_are_not_candidates(self):
        day=self.service.archive/'2026-10-15'/'Codex';day.mkdir(parents=True)
        (day/'重要说明.md').write_text('keep');(self.service.data/'config.local.json').write_text('{}')
        self.assertEqual(self.call('inspect')['archive_files'],[])
        self.assertEqual(self.call('inspect')['garbage'],[])
    def test_outside_symlink_is_never_deleted(self):
        outside=self.root/'outside.txt';outside.write_text('keep')
        _,folder=self.upload();(folder/'file.txt').unlink()
        try:(folder/'file.txt').symlink_to(outside)
        except OSError:self.skipTest('Symlink creation is unavailable')
        self.assertEqual(self.call('inspect')['garbage'],[]);self.assertEqual(outside.read_text(),'keep')
    def test_failed_file_move_retains_original_and_has_no_trash_record(self):
        path=self.export();file=self.call('inspect')['archive_files'][0]
        with patch('pathlib.Path.replace',side_effect=PermissionError('fixture')):
            result=self.call('trash_files',ids=[file['id']]);self.assertFalse(result['ok'])
        self.assertTrue(path.exists());self.assertEqual(self.call('inspect')['trash_files'],[])
        self.assertEqual(list((self.service.data/'storage-trash').iterdir()),[])
    def test_reparse_attribute_blocks_cleanup_without_symlink_privileges(self):
        _,folder=self.upload();original=Path.lstat
        def lstat(path,*args,**kwargs):
            info=original(path,*args,**kwargs)
            if path==folder:
                from types import SimpleNamespace
                return SimpleNamespace(st_mode=info.st_mode,st_file_attributes=0x400)
            return info
        with patch('pathlib.Path.lstat',lstat):self.assertEqual(self.call('inspect')['garbage'],[])
        self.assertTrue(folder.exists())
    def test_partial_file_move_reports_completed_items_and_can_resume(self):
        first=self.export();second=self.export();items=self.call('inspect')['archive_files'];original=Path.replace;count=0
        def replace(path,target):
            nonlocal count
            count+=1
            if count==2:raise PermissionError('fixture')
            return original(path,target)
        with patch('pathlib.Path.replace',replace):result=self.call('trash_files',ids=[i['id'] for i in items])
        self.assertFalse(result['ok']);self.assertEqual(len(result['completed_ids']),1)
        view=self.call('inspect');self.assertEqual(len(view['trash_files']),1);self.assertEqual(len(view['archive_files']),1)
        self.call('trash_files',ids=[view['archive_files'][0]['id']]);self.assertFalse(first.exists());self.assertFalse(second.exists())
    def test_compaction_archive_outside_owned_root_is_not_purged(self):
        outside=self.root/'outside.json';outside.write_text('{}')
        self.db.execute('INSERT INTO compactions VALUES(?,?,?,?,?,?,?)',(uid(),self.id,now(),'summary',str(outside),'{}','{}'))
        self.archive();self.call('trash_conversations',ids=[self.id])
        with self.assertRaises(ValueError):self.call('purge_conversations',ids=[self.id],confirmation='永久删除')
        self.assertTrue(outside.exists());self.assertIsNotNone(self.db.one('SELECT id FROM conversations WHERE id=?',(self.id,)))
    def test_database_compaction_retains_messages(self):
        self.db.message(self.id,'user','user','keep')
        with self.assertRaises(ValueError):self.call('compact_database')
        self.call('compact_database',confirmation='整理数据库')
        self.assertEqual(self.db.conversation(self.id)['messages'][0]['content'],'keep')
    def test_shared_compaction_path_is_retained_for_other_conversation(self):
        path=self.service.data/'context-archives'/uid()/(uid()+'.json');path.parent.mkdir(parents=True);path.write_text('{}')
        other=self.db.create_conversation('keep shared archive')['id'];archive_id=uid()
        self.db.execute('INSERT INTO compactions VALUES(?,?,?,?,?,?,?)',(archive_id,self.id,now(),'summary',str(path),'{}','{}'))
        alternate=path.parent/'..'/path.parent.name/path.name
        self.db.execute('INSERT INTO compactions VALUES(?,?,?,?,?,?,?)',(uid(),other,now(),'summary',str(alternate),'{}','{}'))
        self.archive();self.call('trash_conversations',ids=[self.id])
        with self.assertRaises(ValueError):self.service.compaction_archive(archive_id)
        self.call('purge_conversations',ids=[self.id],confirmation='永久删除')
        self.assertTrue(path.exists());self.assertEqual(self.call('inspect')['garbage'],[])

if __name__=='__main__':unittest.main()
