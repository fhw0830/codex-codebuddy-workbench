"""Real scheduling with synthetic agents and disposable files; no robot actions."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.resource_locks import ResourceCoordinator,ResourceSession,code_resource,robot_resource,operation_resources,readonly_command
from backend.service import Service
from backend.agents import Cancelled


class Resources(unittest.TestCase):
    def test_nested_package_marker_does_not_split_one_git_repository(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'.git').mkdir();child=root/'packages/A';child.mkdir(parents=True);(child/'package.json').write_text('{}')
            self.assertEqual(code_resource(root,root),code_resource(child/'file.py',root))

    def test_remote_only_write_targets_only_the_actual_robot(self):
        resources=operation_resources('exec_command',{'cmd':'ssh pi@192.0.2.11 "sudo systemctl restart fixture"','workdir':str(ROOT)},ROOT)
        self.assertEqual(resources,['robot:192.0.2.11'])
        self.assertEqual(operation_resources('functions.exec_command',{'cmd':'git status --short'},ROOT),[])
    def test_same_project_blocks_other_project_and_readonly_continue(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);a=root/'A';b=root/'B'
            for p in (a,b):p.mkdir();(p/'package.json').write_text('{}')
            manager=ResourceCoordinator();first=manager.request('first',[code_resource(a,root)])
            self.assertEqual(first['state'],'acquired')
            second=manager.request('second',[code_resource(a/'file.py',root)])
            self.assertEqual(second['state'],'waiting')
            self.assertEqual(manager.request('third',[code_resource(b/'file.py',root)])['state'],'acquired')
            self.assertEqual(operation_resources('Read',{'file_path':str(a/'file.py')},root),[])
            self.assertTrue(readonly_command('ssh pi@robot-a "journalctl -u fms -n 50"'))
            manager.release('first');self.assertEqual(manager.poll(second['id'],'second')['state'],'acquired')

    def test_fifo_parent_paths_and_atomic_multi_resource_claim(self):
        m=ResourceCoordinator();root='code:'+str(Path.cwd())
        m.request('a',[root]);b=m.request('b',[root+ '/child','robot:one']);c=m.request('c',['robot:one'])
        self.assertEqual(c['state'],'waiting');self.assertNotIn('robot:one',m.leases)
        m.release('a');self.assertEqual(m.poll(b['id'],'b')['state'],'acquired');m.release('b')
        self.assertEqual(m.poll(c['id'],'c')['state'],'acquired')

    def test_robot_aliases_different_users_and_robots(self):
        with tempfile.TemporaryDirectory() as folder:
            config=Path(folder)/'config';config.write_text('Host robot-a robot-alias\n HostName 192.0.2.11\nHost robot-b\n HostName 192.0.2.12\n')
            a=robot_resource('pi@robot-a',config);alias=robot_resource('admin@robot-alias',config)
            self.assertEqual(a,alias);m=ResourceCoordinator();m.request('a',[a])
            self.assertEqual(m.request('b',[alias])['state'],'waiting')
            self.assertEqual(m.request('c',[robot_resource('robot-b',config)])['state'],'acquired')

    def test_worktrees_share_git_resource_and_subdirectories_resolve_to_repo(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);main=root/'main';main.mkdir();(main/'.git/worktrees/other').mkdir(parents=True)
            other=root/'other';other.mkdir();(other/'.git').write_text('gitdir: '+str(main/'.git/worktrees/other'))
            (main/'.git/worktrees/other/commondir').write_text('../..')
            self.assertEqual(code_resource(main/'src/a.py',root),code_resource(other/'src/b.py',root))

    def test_ambiguous_shell_and_git_mutations_do_not_bypass_claim(self):
        for command in ('python -c "print(1)"','git checkout main','git branch new','git diff --output=out.txt','Get-Content a > b','ssh robot-a "sudo reboot"'):
            self.assertFalse(readonly_command(command),command)
            self.assertTrue(operation_resources('Bash',{'command':command},Path.cwd()),command)
        for command in ('rg -n example file.py','git status --short','git diff','git -C "C:/project" log -1'):
            self.assertTrue(readonly_command(command),command)

    def test_cancel_closed_tokens_and_cross_owner_requests(self):
        m=ResourceCoordinator();cancel=threading.Event();session=ResourceSession(m,'a',Path.cwd(),cancel,lambda row:None)
        m.request('holder',['robot:one']);row=session.request({'action':'declare','code_paths':[],'robots':['one']})
        self.assertTrue(session.is_waiting)
        with self.assertRaises(ValueError):m.poll(row['id'],'intruder')
        cancel.set();self.assertEqual(session.request({'action':'poll','id':row['id']})['state'],'cancelled')
        # Cancellation must not release another task or release running writes early.
        self.assertEqual(m.leases['robot:one'],'holder');m.release('a');self.assertEqual(m.leases['robot:one'],'holder')

    def test_readonly_phase_rejects_mutation_without_claiming_resource(self):
        s=ResourceSession(ResourceCoordinator(),'a',Path.cwd(),threading.Event(),lambda row:None,readonly=True)
        self.assertEqual(s.request({'action':'check','tool_name':'Read'})['state'],'acquired')
        self.assertEqual(s.request({'action':'check','tool_name':'Write'})['state'],'blocked')
        self.assertEqual(s.manager.leases,{})

    def test_crossed_incremental_claims_are_blocked_instead_of_deadlocking(self):
        m=ResourceCoordinator();m.request('a',['robot:a']);m.request('b',['robot:b']);m.request('a',['robot:b'])
        row=m.request('b',['robot:a']);self.assertEqual(row['state'],'blocked');m.release('b')
        self.assertEqual(m.leases['robot:b'],'a')

    def test_current_writer_can_continue_while_another_writer_waits(self):
        m=ResourceCoordinator();m.request('first',['robot:a'])
        second=m.request('second',['robot:a'])
        self.assertEqual(m.request('first',['robot:a'])['state'],'acquired')
        self.assertEqual(m.poll(second['id'],'second')['state'],'waiting')
        m.release('first');self.assertEqual(m.poll(second['id'],'second')['state'],'acquired')

    def test_running_operation_cannot_release_its_project_early(self):
        s=ResourceSession(ResourceCoordinator(),'a',Path.cwd(),threading.Event(),lambda row:None)
        s.request({'action':'declare','code_paths':[str(Path.cwd())]})
        s.active_operations.add('still-running-shell')
        blocked=s.request({'action':'release'})
        self.assertEqual(blocked['state'],'blocked');self.assertTrue(blocked['resources_retained'])
        self.assertEqual(blocked['active_operation_ids'],['still-running-shell'])
        self.assertTrue(s.manager.leases)
        s.active_operations.clear();s.request({'action':'release'});self.assertEqual(s.manager.leases,{})


class Scheduler(unittest.TestCase):
    def test_waiting_writer_does_not_block_analysis_or_unrelated_writer_or_health(self):
        started={};release=threading.Event();written=[]
        class Agent:
            def __init__(self,*args):pass
            def models(self):return []
            def quota(self):return {}
            def run(self,prompt,model,emit,cancel,controls=None,**options):
                case=prompt.split('[当前用户请求：必须优先遵守]')[-1].strip().splitlines()[0]
                started[case].set();emit('已独立开始分析 '+case)
                if case=='reader':
                    result=controls.resources.request({'action':'check','tool_name':'Read','tool_input':{'file_path':str(a/'file.txt')}})
                    assert result['state']=='acquired';return '读取回答完成',{}
                target=b if case=='independent' else a
                row=controls.resources.request({'action':'check','tool_name':'Write','tool_input':{'file_path':str(target/'file.txt')}})
                until=time.monotonic()+4
                while row['state']=='waiting' and time.monotonic()<until:
                    if cancel.is_set():raise Cancelled('fixture stopped')
                    time.sleep(.01);row=controls.resources.request({'action':'poll','id':row['id']})
                assert row['state']=='acquired',row
                (target/'file.txt').write_text(case);written.append(case)
                if case=='first':
                    while not release.wait(.01):
                        if cancel.is_set():raise Cancelled('fixture stopped')
                return '完成 '+case,{}
        with tempfile.TemporaryDirectory() as folder,patch('backend.service.Codex',Agent),patch('backend.service.CodeBuddy',Agent):
            root=Path(folder);a=root/'A';b=root/'B'
            for p in (a,b):p.mkdir();(p/'package.json').write_text('{}')
            s=Service(ROOT,root/'data',root/'archive',connect=False);s.store.set_setting('daily_autosave',False)
            try:
                jobs={}
                for case in ('first','second','reader','independent'):
                    started[case]=threading.Event();c=s.store.create_conversation(case)['id'];s.set_preferences(c,{'access_mode':'full','workdir':str(root)})
                    jobs[case]=s.enqueue({'conversation_id':c,'content':case,'route':'codex','client_key':case})
                    self.assertTrue(started[case].wait(2),case)
                    if case=='first':
                        until=time.monotonic()+2
                        while 'first' not in written and time.monotonic()<until:time.sleep(.01)
                until=time.monotonic()+2
                while s.conversation(jobs['reader']['conversation_id'])['job']['status']=='running' and time.monotonic()<until:time.sleep(.01)
                self.assertEqual(s.conversation(jobs['reader']['conversation_id'])['job']['status'],'completed')
                until=time.monotonic()+2
                while 'independent' not in written and time.monotonic()<until:time.sleep(.01)
                self.assertIn('independent',written);self.assertNotIn('second',written)
                second=s.conversation(jobs['second']['conversation_id']);self.assertEqual(second['messages'][-1]['meta']['resource_wait']['state'],'waiting')
                self.assertTrue(s.pool.submit(lambda:True).result(timeout=1))
                release.set()
                until=time.monotonic()+3
                while 'second' not in written and time.monotonic()<until:time.sleep(.01)
                self.assertIn('second',written)
            finally:release.set();s.close();s.store.db.close()

if __name__=='__main__':unittest.main()
