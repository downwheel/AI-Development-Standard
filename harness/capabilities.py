"""Capabilities describe enforced contracts, separately from account readiness."""
from __future__ import annotations
import importlib.util


def capabilities():
    return {
        'contract_version': '2.1',
        'tool_policy_version': '1',
        'external_tool_plan_required': True,
        'external_tool_gate_evidence': True,
        'external_tool_runner_evidence': True,
        'external_tool_provenance': 'Caller-supplied design observations; runner-collected completion evidence. Not provider-authenticated call receipts.',
        'personal_environment_profiles': True,
        'role_scoped_environment': True,
        'exact_file_scope': True,
        'scope_actions_and_baselines': True,
        'unit_dependency_graph': True,
        'computed_next_actions': True,
        'computed_completion': True,
        'approved_project_runner': True,
        'bounded_evidence_attachments': True,
        'database': {
            'engine': 'sqlserver',
            'adapter': 'typed-transactional-operations',
            'driver_module_available': importlib.util.find_spec('pyodbc') is not None,
            'connection_verified': False,
            'connection_status': 'Use environment_probe for the selected personal profile and role.',
            'arbitrary_sql': False,
            'uncertain_outcome_recovery': 'Read-only observation, explicit user decision, and a new contract review; no automatic SQL retry.',
            'source_restore_is_database_restore': False,
        },
        'enforcement': 'Cooperative preflight and post-observation; native editors and external DB clients are not an OS sandbox.',
        'legacy_runs': 'Resume with their recorded immutable release; no automatic conversion.',
    }
