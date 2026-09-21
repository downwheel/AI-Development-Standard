"""Installer effects are exercised only inside a synthetic user profile."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import install
from harness.common import HarnessError

class InstallationTests(unittest.TestCase):
    def fixture(self,base):
        shared=base/'shared'; profile=base/'profile'; private=base/'private'
        names=['development-workflow','dev-discover','dev-requirements','dev-system-design','dev-unit-design','dev-test-design','dev-implement','dev-verify','dev-review','dev-artifacts','dev-restore']
        for name in names:
            path=shared/'skills'/name/'SKILL.md'; path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('---\nname: '+name+'\ndescription: Fixture only\n---\nFixture source\n',encoding='utf-8')
        (shared/'team_harness.py').write_text('print("fixture")',encoding='utf-8')
        config=profile/'.codex/config.toml'; config.parent.mkdir(parents=True)
        original=b'theme = "fixture-theme"\n\n[mcp_servers.unrelated]\ncommand = "keep-me"\n\n[mcp_servers.development_workflow]\ncommand = "legacy.py"\nenabled = true\n'
        config.write_bytes(original)
        agents=profile/'.codex/AGENTS.md'
        routing=b'PERSONAL PREFIX\n\n'+install.OLD_START+b'\nold managed content\n'+install.OLD_END+b'\nPERSONAL SUFFIX\n'
        agents.write_bytes(routing)
        (profile/'.claude.json').write_text(json.dumps({'custom':'preserve','mcpServers':{'unrelated':{'type':'stdio','command':'keep'}}}),encoding='utf-8')
        return shared,profile,private,original,routing

    def test_install_preserves_unmanaged_settings_and_rollback(self):
        with tempfile.TemporaryDirectory() as folder:
            shared,profile,private,original,routing=self.fixture(Path(folder))
            with patch.object(install,'SOURCE',shared):
                plan=install.build_plan(profile,private,__import__('sys').executable)
                self.assertFalse(private.exists())
                result=install.install(profile,private,__import__('sys').executable)
                self.assertEqual(11,result['skill_count_per_host'])
                current=(profile/'.codex/config.toml').read_bytes()
                self.assertIn(b'[mcp_servers.unrelated]\ncommand = "keep-me"',current)
                self.assertIn(b'enabled = false',current)
                self.assertIn(b'[mcp_servers.team_harness]',current)
                agents=(profile/'.codex/AGENTS.md').read_bytes()
                self.assertTrue(agents.startswith(b'PERSONAL PREFIX\n\n'))
                self.assertTrue(agents.endswith(b'\nPERSONAL SUFFIX\n'))
                claude=json.loads((profile/'.claude.json').read_text(encoding='utf-8'))
                self.assertEqual('preserve',claude['custom'])
                self.assertEqual('keep',claude['mcpServers']['unrelated']['command'])
                self.assertFalse((shared/'.git').exists())
                self.assertFalse((profile/'.git').exists())
                preview=install.rollback(result['receipt'],False,profile,private)
                self.assertFalse(preview['conflicts'])
                install.rollback(result['receipt'],True,profile,private)
                self.assertEqual(original,(profile/'.codex/config.toml').read_bytes())
                self.assertEqual(routing,(profile/'.codex/AGENTS.md').read_bytes())
                self.assertTrue((private/'releases'/result['release_id']).exists())

    def test_post_install_user_change_prevents_rollback_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            shared,profile,private,_,_=self.fixture(Path(folder))
            with patch.object(install,'SOURCE',shared):
                result=install.install(profile,private,__import__('sys').executable)
                config=profile/'.codex/config.toml'; config.write_bytes(config.read_bytes()+b'\n# user changed this later\n')
                with self.assertRaises(HarnessError) as error: install.rollback(result['receipt'],True,profile,private)
                self.assertEqual('rollback_conflict',error.exception.code)
                self.assertIn(b'user changed this later',config.read_bytes())

    def test_unmanaged_skill_collision_stops_before_install(self):
        with tempfile.TemporaryDirectory() as folder:
            shared,profile,private,_,_=self.fixture(Path(folder))
            path=profile/'.codex/skills/dev-discover/SKILL.md'; path.parent.mkdir(parents=True); path.write_text('unrelated user Skill')
            with patch.object(install,'SOURCE',shared):
                with self.assertRaises(HarnessError) as error: install.build_plan(profile,private,__import__('sys').executable)
                self.assertEqual('skill_conflict',error.exception.code)
                self.assertFalse(private.exists())

    def test_multiline_toml_value_replacement_preserves_next_table(self):
        original=b'[mcp_servers.team_harness]\nargs = [\n  "old",\n  "literal ] # not a comment", # comment\n]\ncommand = "python"\n\n[mcp_servers.other]\nargs = ["preserve"]\n'
        updated=install.update_toml_table(original,'team_harness',{'args':['new'],'command':'new-python'})
        self.assertNotIn(b'old',updated)
        self.assertNotIn(b'literal',updated)
        self.assertIn(b'args = ["new"]',updated)
        self.assertTrue(updated.endswith(b'[mcp_servers.other]\nargs = ["preserve"]\n'))

    def test_packaging_rejects_private_env(self):
        with tempfile.TemporaryDirectory() as folder:
            shared,profile,private,_,_=self.fixture(Path(folder))
            (shared/'.env').write_text('SECRET=synthetic')
            with patch.object(install,'SOURCE',shared):
                with self.assertRaises(HarnessError) as error: install.build_plan(profile,private,__import__('sys').executable)
                self.assertEqual('secret_path',error.exception.code)

    def test_quoted_toml_header_is_updated_without_duplicate_table(self):
        for header in ['[mcp_servers."team_harness"]', "[ 'mcp_servers' . 'team_harness' ]"]:
            raw=(header+'\ncommand = "old"\n').encode('utf-8')
            updated=install.update_toml_table(raw,'team_harness',{'command':'new'})
            self.assertEqual(1,updated.count(b'team_harness'))
            self.assertIn(b'command = "new"',updated)

    def test_install_preserves_personal_policy_and_claude_extension(self):
        with tempfile.TemporaryDirectory() as folder:
            shared,profile,private,_,_=self.fixture(Path(folder))
            private.mkdir(); (private/'settings.json').write_text(json.dumps({'custom_policy':'keep'}))
            (profile/'.claude.json').write_text(json.dumps({'mcpServers':{'team_harness':{'env':{'MY_OPTION':'synthetic'}}}}))
            with patch.object(install,'SOURCE',shared): install.install(profile,private,__import__('sys').executable)
            self.assertEqual('keep',json.loads((private/'settings.json').read_text())['custom_policy'])
            self.assertEqual({'MY_OPTION':'synthetic'},json.loads((profile/'.claude.json').read_text())['mcpServers']['team_harness']['env'])

if __name__=='__main__': unittest.main()
