"""Security/regression boundaries, with fake secrets and temporary files only."""
import base64
import io
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.resource_locks import ResourceCoordinator,ResourceSession,readonly_command,operation_resources,robot_resource
from backend.store import clean
from backend.service import Service


class ResourceBoundaries(unittest.TestCase):
    def test_preprocessor_commands_require_a_mutation_claim(self):
        for command in ('rg --pre helper pattern file.txt','rg --pre=helper pattern file.txt','rg --hostname-bin helper pattern file.txt','rg pattern <(helper)'):
            with self.subTest(command=command):
                self.assertFalse(readonly_command(command))
                self.assertTrue(operation_resources('exec_command',{'cmd':command},ROOT))

    def test_plain_search_is_still_readonly(self):
        self.assertTrue(readonly_command('rg -n pattern file.txt'))
        self.assertEqual(operation_resources('Read',{'file_path':'file.txt'},ROOT),[])

    def test_deferred_writes_cannot_bypass_readonly_phase(self):
        session=ResourceSession(ResourceCoordinator(),'test',ROOT,threading.Event(),lambda row:None,readonly=True)
        result=session.request({'action':'check','tool_name':'DeferExecuteTool','tool_input':{'tool_name':'Write','arguments':{'file_path':str(ROOT/'never-written.txt')}}})
        self.assertEqual(result['state'],'blocked')
        self.assertEqual(session.manager.leases,{})

    def test_deferred_write_claims_actual_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary).resolve()
            result=operation_resources('DeferExecuteTool',{'tool_name':'Write','arguments':{'file_path':str(folder/'file.txt')}},ROOT)
            self.assertTrue(any(str(folder).lower() in r.lower() for r in result))

    def test_deferred_questions_and_reads_still_work(self):
        for tool in ('mcp__collab_web__ask_web_user','mcp__collab_web__coordinate_resources','Read'):
            self.assertEqual(operation_resources('DeferExecuteTool',{'tool_name':tool,'parameters':{}},ROOT),[])

    def test_unknown_deferred_tool_does_not_skip_coordination(self):
        self.assertTrue(operation_resources('DeferExecuteTool',{},ROOT))

    def test_include_aliases_share_one_robot_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'hosts.conf').write_text('Host robot-a robot-b\n HostName 192.0.2.10\n')
            config=root/'config';config.write_text('Include hosts.conf\n')
            a=robot_resource('pi@robot-a',config);b=robot_resource('admin@robot-b',config)
            self.assertEqual(a,'robot:192.0.2.10');self.assertEqual(a,b)
            coordinator=ResourceCoordinator();coordinator.request('first',[a])
            self.assertEqual(coordinator.request('second',[b])['state'],'waiting')

    def test_conditional_includes_globs_and_first_value(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'parts').mkdir()
            (root/'parts/a.conf').write_text('HostName 192.0.2.10\n')
            (root/'parts/b.conf').write_text('HostName 192.0.2.20\n')
            config=root/'config';config.write_text('Host unrelated\n Include parts/*.conf\nHost robot-a !robot-b\n Include "parts/*.conf"\nHost robot-b\n HostName 192.0.2.30\n')
            self.assertEqual(robot_resource('robot-a',config),'robot:192.0.2.10')
            self.assertEqual(robot_resource('robot-b',config),'robot:192.0.2.30')

    def test_include_cycle_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            config=Path(temporary)/'config';config.write_text('Include config\n')
            with self.assertRaises(ValueError):robot_resource('robot-a',config)

    def test_quoted_values_and_equal_sign_syntax(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'host names.conf').write_text('Host robot-a\n HostName="192.0.2.10"\n')
            config=root/'config';config.write_text('Include = "host names.conf"\n')
            self.assertEqual(robot_resource('robot-a',config),'robot:192.0.2.10')

    def test_dynamic_include_cannot_silently_split_aliases(self):
        with tempfile.TemporaryDirectory() as temporary:
            config=Path(temporary)/'config';config.write_text('Include ${UNRESOLVED}/hosts\n')
            with self.assertRaises(ValueError):robot_resource('robot-a',config)

    def test_unknown_match_condition_is_not_silently_misresolved(self):
        with tempfile.TemporaryDirectory() as temporary:
            config=Path(temporary)/'config';config.write_text('Match exec "never run this"\n HostName 192.0.2.10\n')
            with self.assertRaises(ValueError):robot_resource('robot-a',config)


class SecretBoundaries(unittest.TestCase):
    def test_short_secrets_are_redacted(self):
        for text in ('password=123456','密码：123','api_key=x','access_token=abc','{"password":"7"}'):
            with self.subTest(text=text):self.assertIn('[凭据已隐藏]',clean(text))

    def test_quoted_secret_with_spaces_does_not_leave_a_tail(self):
        text='{"password":"fake secret tail","task":"keep"}'
        result=clean(text)
        self.assertNotIn('tail',result);self.assertIn('"task":"keep"',result)
        import json
        self.assertEqual(json.loads(result)['password'],'[凭据已隐藏]')

    def test_redaction_is_idempotent(self):
        for text in ('password=123456','{"password":"fake secret"}'):
            self.assertEqual(clean(clean(text)),clean(text))

    def test_ordinary_prose_and_code_are_preserved(self):
        for text in ('检查密码长度，不输出密码。','password_length=6','line=7; mode=read_only'):
            self.assertEqual(clean(text),text)


class UploadBoundaries(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        self.service=object.__new__(Service);self.service.data=self.root
    def tearDown(self):self.temporary.cleanup()
    def upload(self,name,content):return self.service.upload({'name':name,'data':base64.b64encode(content).decode()})
    def assert_no_uploads(self):
        uploads=self.root/'uploads'
        self.assertFalse(uploads.exists() and list(uploads.iterdir()))
    def test_invalid_image_does_not_leave_files(self):
        with self.assertRaises(ValueError):self.upload('broken.png',b'not an image')
        self.assert_no_uploads()
    def test_unsupported_document_does_not_leave_files(self):
        with self.assertRaises(ValueError):self.upload('opaque.bin',bytes(range(256)))
        self.assert_no_uploads()
    def test_extraction_failure_cleans_metadata_and_blob(self):
        with patch.object(self.service,'uploaded_reference',side_effect=OSError('fixture extraction failure')):
            with self.assertRaises(OSError):self.upload('note.txt',b'fixture')
        self.assert_no_uploads()
    def test_valid_text_is_retained_and_can_be_read(self):
        reference=self.upload('note.txt',b'PUBLIC_FIXTURE')
        self.assertTrue(reference['attachable']);self.assertEqual(reference['content'],'PUBLIC_FIXTURE')
        self.assertTrue(self.service.upload_path(reference['upload_id']).is_file())
    def test_valid_image_is_retained(self):
        from PIL import Image
        buffer=io.BytesIO();Image.new('RGB',(3,3),'white').save(buffer,format='PNG')
        reference=self.upload('valid.png',buffer.getvalue())
        self.assertEqual(reference['kind'],'image');self.assertTrue(reference['attachable'])

if __name__=='__main__':unittest.main()
