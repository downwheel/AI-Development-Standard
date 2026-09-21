"""Reject known selected-profile credentials before persisting source or records.

This covers literal/JSON-escaped tokens, not arbitrary transformed data or DLP.
Original product files are never silently redacted because snapshots must restore
their exact bytes.
"""
from __future__ import annotations
import json
import re
from .common import fail


def guard_journal(journal,environment,additional_profile_ids=()):
    state=journal.read()
    profiles=set(additional_profile_ids)|set(state.get('environment_profile_ids',[]))
    # Only profiles already associated with this project are inspected. Do not
    # discover credentials in unrelated folders or every user's environment.
    values=[]
    for profile_id in profiles:
        values.extend(environment.known_secret_values(profile_id))
    patterns=[]
    for value in set(values):
        if not value: continue
        forms={value,json.dumps(value,ensure_ascii=False)[1:-1],json.dumps(value,ensure_ascii=True)[1:-1]}
        patterns.extend(re.compile(rb'(?<![A-Za-z0-9_])'+re.escape(form.encode('utf-8'))+rb'(?![A-Za-z0-9_])') for form in forms)
    if not patterns: return
    original=journal.put_blob
    def checked(raw):
        if any(pattern.search(raw) for pattern in patterns):
            fail('known_secret_in_record','A selected profile credential appears in source or record content. Preserve the original file, remove the credential from the proposed artifact/source, and retry; no credential was journaled.')
        return original(raw)
    journal.put_blob=checked
