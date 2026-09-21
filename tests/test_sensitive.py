"""Selected literal credentials are rejected, not redacted into restore snapshots."""
import json
import unittest
from types import SimpleNamespace
from harness.common import HarnessError
from harness.sensitive import guard_journal


class SensitiveJournalTests(unittest.TestCase):
    def test_selected_profile_literal_and_json_escaped_values_never_reach_store(self):
        values=['synthetic-database-password','quote"slash\\password']
        seen=[]; requested=[]
        journal=SimpleNamespace(read=lambda:{'environment_profile_ids':['selected']},put_blob=lambda raw:seen.append(raw))
        environment=SimpleNamespace(known_secret_values=lambda profile:requested.append(profile) or values)
        guard_journal(journal,environment)
        for raw in [b'password = "synthetic-database-password"',json.dumps({'value':values[1]}).encode(),values[1].encode()]:
            with self.assertRaises(HarnessError) as caught: journal.put_blob(raw)
            self.assertEqual('known_secret_in_record',caught.exception.code)
        self.assertEqual([],seen); self.assertEqual(['selected'],requested)
        journal.put_blob(b'ordinary source bytes')
        self.assertEqual([b'ordinary source bytes'],seen)

    def test_short_literal_tokens_do_not_match_unrelated_words_or_hashes(self):
        seen=[]
        journal=SimpleNamespace(read=lambda:{},put_blob=lambda raw:seen.append(raw))
        environment=SimpleNamespace(known_secret_values=lambda profile:['sa','12'])
        guard_journal(journal,environment,['draft-profile'])
        journal.put_blob(b'same safe source hash abc123de')
        with self.assertRaises(HarnessError): journal.put_blob(b'user="sa"')
        self.assertEqual(1,len(seen))

    def test_unselected_profiles_are_not_discovered(self):
        seen=[]
        journal=SimpleNamespace(read=lambda:{'artifacts':{}},put_blob=lambda raw:seen.append(raw))
        environment=SimpleNamespace(known_secret_values=lambda _:self.fail('Unrelated private profile must not be read.'))
        guard_journal(journal,environment); journal.put_blob(b'ordinary')
        self.assertEqual([b'ordinary'],seen)


if __name__=='__main__': unittest.main()
