"""Synthetic adapter tests. No SQL Server instance or user database is contacted."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from harness.common import HarnessError, encoded, sha256
from harness.database import (DB_WORK_PLAN_SCHEMA, SqlServerSession, _rows_hash, check_plan_current,
                              compile_migration, execute_plan, inspect_database, probe_environment, render_plan, validate_plan)


REF = {"artifact_id": "fixture", "revision_id": "revision", "sha256": "a" * 64}


def table_definition(name="Notes"):
    return {"schema": "dbo", "name": name, "object_type": "table", "columns": [
        {"name": "Id", "type": "int", "nullable": False, "length": 4},
        {"name": "Body", "type": "nvarchar", "nullable": False, "length": 200},
        {"name": "Owner", "type": "nvarchar", "nullable": False, "length": 100}],
        "primary_key": ["Id"], "unsafe": []}


class SyntheticDatabase:
    def __init__(self, catalog=None, data=None):
        self.catalog = catalog if catalog is not None else {"dbo.Notes": table_definition()}
        self.data = data if data is not None else {"dbo.Notes": [{"Id": 1, "Body": "Original", "Owner": "existing"}]}
        self.target = {"target_id": "b" * 64, "database": "SYNTHETIC", "schema": "dbo", "principal_digest": "c" * 64,
                       "permissions_sha256": "d" * 64, "permissions_digest": "d" * 64, "engine": "sqlserver", "engine_version": "16.0.fixture",
                       "can_view_definition": True, "permissions": ["SELECT", "INSERT", "UPDATE", "DELETE", "ALTER"]}
        self.calls = []
        self.connections = 0
        self.on_apply = None
        self.on_connect = None
        self.commit_error = False
        self.lock_error = False
        self.close_error = False

    def connect(self, resolved):
        self.connections += 1
        self.calls.append(("connect", self.connections))
        if self.on_connect:
            self.on_connect(self, self.connections)
        return SyntheticSession(self)


class SyntheticSession:
    def __init__(self, database):
        self.database = database
        self.local_catalog = copy.deepcopy(database.catalog)
        self.local_data = copy.deepcopy(database.data)

    def target(self, schema):
        return copy.deepcopy(self.database.target)

    def begin(self, resource, limits):
        self.database.calls.append(("begin", resource))
        if self.database.lock_error:
            raise HarnessError("db_lock_failed", "Synthetic lock refusal")
        return 2

    def catalog(self, maximum):
        return copy.deepcopy(self.local_catalog)

    def rows(self, table, maximum):
        if table["unsafe"]:
            raise HarnessError("db_unsupported", "Synthetic trigger")
        rows = copy.deepcopy(self.local_data.get(table["schema"] + "." + table["name"], []))
        if len(rows) > maximum:
            raise HarnessError("db_observation_limit", "Synthetic row limit")
        return rows

    def apply(self, operation):
        self.database.calls.append(("apply", operation["kind"]))
        key = operation["schema"] + "." + operation["table"]
        kind = operation["kind"]
        count = 0
        if kind == "create_table":
            lengths = {"int": 4, "bigint": 8, "smallint": 2, "tinyint": 1, "bit": 1, "uniqueidentifier": 16}
            self.local_catalog[key] = {"schema": operation["schema"], "name": operation["table"], "object_type": "table", "columns": [
                {"name": c["name"], "type": c["type"], "nullable": c["nullable"], "length": c.get("length", lengths.get(c["type"])) * (2 if c["type"] == "nvarchar" else 1)} for c in operation["columns"]],
                "primary_key": operation["primary_key"], "unsafe": []}
            self.local_data[key] = []
        elif kind == "create_index":
            self.local_catalog[key + "." + operation["name"]] = {"schema": operation["schema"], "name": operation["name"], "table": operation["table"],
                "object_type": "index", "columns": [{"name": c, "included": False, "descending": False} for c in operation["index_columns"]],
                "unique": operation["unique"], "filtered": False, "type": "NONCLUSTERED"}
        elif kind == "insert":
            self.local_data[key].extend(copy.deepcopy(operation["rows"]))
            count = len(operation["rows"])
        else:
            for predicate in operation["keys"]:
                matches = [row for row in self.local_data[key] if all(row.get(k) == value for k, value in predicate.items())]
                count += len(matches)
                for row in matches:
                    if kind == "delete":
                        self.local_data[key].remove(row)
                    else:
                        row.update(operation["values"])
        if self.database.on_apply:
            override = self.database.on_apply(self, operation)
            if override is not None:
                count = override
        return count

    def commit(self):
        self.database.calls.append(("commit",))
        self.database.catalog = copy.deepcopy(self.local_catalog)
        self.database.data = copy.deepcopy(self.local_data)
        if self.database.commit_error:
            raise RuntimeError("SYNTHETIC driver contains Password=NEVER-REPORT")

    def rollback(self):
        self.database.calls.append(("rollback",))

    def close(self):
        self.database.calls.append(("close",))
        if self.database.close_error:
            raise RuntimeError("SYNTHETIC driver contains Password=NEVER-REPORT")


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.db = SyntheticDatabase()
        self.resolved = SimpleNamespace(env={"MSSQL_SCHEMA": "dbo"}, binding={"profile_id": "fixture", "revision": "env1", "target_revision": "target1", "role": "migration", "role_kind": "migration"}, secret_values=("NEVER-REPORT",))

    def operation(self, kind="insert"):
        common = {"kind": kind, "schema": "dbo", "table": "Notes"}
        if kind == "insert":
            return {**common, "rows": [{"Id": 2, "Body": "Synthetic memo", "Owner": "fixture-run"}],
                    "fixture": {"column": "Owner", "value": "fixture-run", "owner_id": "fixture-run"}}
        if kind == "update":
            return {**common, "keys": [{"Id": 1}], "values": {"Body": "Changed"}}
        if kind == "delete":
            return {**common, "keys": [{"Id": 1}]}
        if kind == "create_table":
            return {**common, "table": "NewNotes", "columns": [{"name": "Id", "type": "int", "nullable": False},
                    {"name": "Body", "type": "nvarchar", "nullable": False, "length": 100}], "primary_key": ["Id"]}
        return {**common, "name": "IX_Notes_Body", "index_columns": ["Body"], "unique": False}

    def plan(self, operation=None, cleanup="none"):
        operation = operation or self.operation()
        key = operation["schema"] + "." + operation["table"]
        is_ddl = operation["kind"].startswith("create_")
        if operation["kind"] == "create_table":
            objects = [{"schema": "dbo", "object_type": "table", "name": operation["table"], "action": "create", "baseline": {"expected_absent": True}}]
        elif operation["kind"] == "create_index":
            objects = [{"schema": "dbo", "object_type": "index", "table": operation["table"], "name": operation["name"], "action": "create", "baseline": {"expected_absent": True}},
                       {"schema": "dbo", "object_type": "table", "name": operation["table"], "action": "observe", "baseline": {"sha256": sha256(encoded(self.db.catalog[key])), "data_sha256": _rows_hash(self.db.data[key])}}]
        else:
            objects = [{"schema": "dbo", "object_type": "table", "name": operation["table"], "action": "data-change", "baseline": {"sha256": sha256(encoded(self.db.catalog[key])), "data_sha256": _rows_hash(self.db.data[key])}}]
        preview = compile_migration(operation)
        rows = 0 if is_ddl else len(operation.get("rows", operation.get("keys")))
        return {"db_work_id": "db-work", "unit_id": "unit", "unit_ref": REF, "environment_ref": REF, "requirement_ids": ["req"], "case_ids": ["case-db"],
                "engine": "sqlserver", "engine_version": self.db.target["engine_version"], "target_ref": self.db.target["target_id"],
                "target": {key: self.db.target[key] for key in ("target_id", "database", "schema", "principal_digest", "permissions_sha256")},
                "baseline_observed_at": "2026-09-21T00:00:00+00:00", "objects": objects,
                "migrations": [{"migration_id": "migration-1", "order": 1, "source_path": "db/migrations/001.sql", "operation": operation, "sql_sha256": preview["sql_sha256"], "parameters_sha256": preview["parameters_sha256"],
                                "expected_rows": rows, "max_rows": rows, "case_ids": ["case-db"], "generator": "team-sqlserver-2.1"}],
                "limits": {"statement_timeout_seconds": 5, "transaction_timeout_seconds": 30, "lock_timeout_ms": 1000, "max_batch_rows": 10, "max_observed_rows": 100, "max_catalog_objects": 100, "max_retries": 0},
                "preservation": {"mode": "only-declared-objects-and-keys", "invariants": ["Keep every existing row unchanged except declared exact keys."], "backup_required": False},
                "performance": {"required": False, "reason": "Small synthetic CRUD has no product latency requirement."},
                "recovery": {"strategy": "transaction", "restart_policy": "inspect-before-retry", "nontransactional": False},
                "verification": {"case_ids": ["case-db"], "oracle": "Expected key/value content, preserved baseline rows and independent persisted observation.", "cleanup": {"mode": cleanup, "reason": "Synthetic explicit cleanup policy."}}}

    def execute(self, plan):
        return execute_plan(plan, self.resolved, approval_binding={"review_id": "synthetic-review-not-human", "plan_sha256": sha256(encoded(plan)),
                    "environment_revision": self.resolved.binding["revision"], "target_revision": self.resolved.binding["target_revision"]}, connection_factory=self.db.connect)

    def assertError(self, code, callback):
        with self.assertRaises(HarnessError) as caught:
            callback()
        self.assertEqual(code, caught.exception.code)

    def test_schema_and_preview_do_not_execute(self):
        plan = self.plan()
        validate_plan(plan, executable=True)
        self.assertTrue(DB_WORK_PLAN_SCHEMA["required"])
        preview = compile_migration(plan["migrations"][0]["operation"])
        self.assertIn("VALUES (?, ?, ?)", preview["sql"])
        self.assertNotIn("Synthetic memo", preview["sql"])
        self.assertNotIn("parameters", preview)
        self.assertEqual([], self.db.calls)

    def test_arbitrary_sql_or_identifier_injection_rejected(self):
        op = self.operation()
        op["sql"] = "DROP TABLE anything"
        self.assertError("invalid_input", lambda: compile_migration(op))
        op = self.operation()
        op["table"] = "Notes]; DROP TABLE anything;--"
        self.assertError("invalid_input", lambda: compile_migration(op))

    def test_pinned_sql_and_parameters_are_enforced(self):
        plan = self.plan()
        plan["migrations"][0]["operation"]["rows"][0]["Body"] = "Changed since review"
        self.assertError("db_migration_hash", lambda: self.execute(plan))
        self.assertEqual([], self.db.calls)

    def test_approval_and_environment_binding_required(self):
        plan = self.plan()
        self.assertError("db_approval_binding", lambda: execute_plan(plan, self.resolved, approval_binding={}, connection_factory=self.db.connect))
        self.assertError("db_environment_drift", lambda: execute_plan(plan, self.resolved, approval_binding={"review_id": "fixture", "plan_sha256": sha256(encoded(plan)), "environment_revision": "wrong", "target_revision": "target1"}, connection_factory=self.db.connect))

    def test_application_role_cannot_write(self):
        self.resolved.binding["role_kind"] = "application"
        self.assertError("db_role", lambda: self.execute(self.plan()))
        self.assertEqual([], self.db.calls)

    def test_insert_persisted_values_and_preserved_rows(self):
        plan = self.plan()
        receipt = self.execute(plan)
        self.assertEqual("passed", receipt["status"], receipt)
        self.assertTrue(receipt["committed"])
        self.assertEqual("passed", receipt["independent_observation"])
        self.assertEqual(2, self.db.connections)
        self.assertEqual("Original", self.db.data["dbo.Notes"][0]["Body"])
        self.assertEqual("Synthetic memo", self.db.data["dbo.Notes"][1]["Body"])
        self.assertNotIn("Synthetic memo", json.dumps(receipt))
        self.assertEqual(1, receipt["migrations"][0]["actual_rows"])
        self.assertTrue(check_plan_current(plan, self.resolved, receipt, self.db.connect)["current"])
        self.db.data["dbo.Notes"][1]["Body"] = "External writer"
        self.assertEqual(["db_persisted_content_changed"], check_plan_current(plan, self.resolved, receipt, self.db.connect)["blockers"])

    def test_update_and_delete_exact_primary_keys(self):
        for kind in ("update", "delete"):
            with self.subTest(kind=kind):
                self.db = SyntheticDatabase()
                receipt = self.execute(self.plan(self.operation(kind)))
                self.assertEqual("passed", receipt["status"], receipt)
                self.assertEqual(1, receipt["migrations"][0]["actual_rows"])
        self.assertEqual([], self.db.data["dbo.Notes"])

    def test_create_table_and_index_definitions(self):
        for kind in ("create_table", "create_index"):
            with self.subTest(kind=kind):
                self.db = SyntheticDatabase()
                receipt = self.execute(self.plan(self.operation(kind)))
                self.assertEqual("passed", receipt["status"], receipt)
                self.assertEqual("create", receipt["objects"]["actual"][0]["action"])
                self.assertEqual(0, receipt["migrations"][0]["actual_rows"])

    def test_target_permissions_drift_prevents_mutation(self):
        plan = self.plan()
        self.db.target["principal_digest"] = "e" * 64
        receipt = self.execute(plan)
        self.assertEqual("db_target_drift", receipt["error"]["code"])
        self.assertFalse(any(call[0] == "apply" for call in self.db.calls))

    def test_row_baseline_drift_prevents_mutation(self):
        plan = self.plan()
        self.db.data["dbo.Notes"][0]["Body"] = "User change"
        receipt = self.execute(plan)
        self.assertEqual("db_baseline_drift", receipt["error"]["code"])
        self.assertEqual("succeeded", receipt["rollback"])
        self.assertFalse(any(call[0] == "apply" for call in self.db.calls))

    def test_row_limit_violation_rolls_back_before_commit(self):
        self.db.on_apply = lambda session, operation: 2
        receipt = self.execute(self.plan())
        self.assertEqual("db_row_limit", receipt["error"]["code"])
        self.assertFalse(receipt["committed"])
        self.assertEqual("succeeded", receipt["rollback"])
        self.assertEqual(1, len(self.db.data["dbo.Notes"]))
        self.assertFalse(any(call[0] == "commit" for call in self.db.calls))

    def test_changed_unapproved_existing_row_rolls_back(self):
        def corrupt(session, operation):
            session.local_data["dbo.Notes"][0]["Body"] = "Unexpected indirect mutation"
        self.db.on_apply = corrupt
        receipt = self.execute(self.plan())
        self.assertEqual("db_content_mismatch", receipt["error"]["code"])
        self.assertEqual("Original", self.db.data["dbo.Notes"][0]["Body"])

    def test_unapproved_catalog_change_rolls_back(self):
        def corrupt(session, operation):
            session.local_catalog["dbo.Unplanned"] = table_definition("Unplanned")
        self.db.on_apply = corrupt
        receipt = self.execute(self.plan())
        self.assertEqual("db_object_diff", receipt["error"]["code"])
        self.assertNotIn("dbo.Unplanned", self.db.catalog)

    def test_wrong_created_definition_rolls_back(self):
        def corrupt(session, operation):
            session.local_catalog["dbo.NewNotes"]["columns"][1]["length"] = 50
        self.db.on_apply = corrupt
        receipt = self.execute(self.plan(self.operation("create_table")))
        self.assertEqual("db_definition_mismatch", receipt["error"]["code"])
        self.assertNotIn("dbo.NewNotes", self.db.catalog)

    def test_postcommit_failure_honestly_records_committed(self):
        def corrupt(database, connection_number):
            if connection_number == 2:
                database.data["dbo.Notes"][1]["Body"] = "Concurrent external change"
        self.db.on_connect = corrupt
        receipt = self.execute(self.plan())
        self.assertEqual("db_postcommit_mismatch", receipt["error"]["code"])
        self.assertTrue(receipt["committed"])
        self.assertEqual("committed", receipt["commit_outcome"])
        self.assertEqual("not-needed", receipt["rollback"])

    def test_commit_acknowledgement_failure_is_unknown_not_no_change(self):
        self.db.commit_error = True
        receipt = self.execute(self.plan())
        self.assertEqual("unknown", receipt["commit_outcome"])
        self.assertEqual("attempted-after-unknown-commit", receipt["rollback"])
        self.assertNotIn("NEVER-REPORT", json.dumps(receipt))
        self.assertEqual(2, len(self.db.data["dbo.Notes"]))

    def test_planned_rollback_observed_on_new_connection(self):
        receipt = self.execute(self.plan(cleanup="rollback"))
        self.assertEqual("passed", receipt["status"], receipt)
        self.assertFalse(receipt["committed"])
        self.assertEqual("succeeded-as-planned", receipt["rollback"])
        self.assertEqual("rolled-back", receipt["migrations"][0]["status"])
        self.assertEqual(1, len(self.db.data["dbo.Notes"]))
        self.assertEqual(2, self.db.connections)

    def test_owned_fixture_cleanup_preserves_preexisting_rows(self):
        receipt = self.execute(self.plan(cleanup="delete-owned-rows"))
        self.assertEqual("passed", receipt["status"], receipt)
        self.assertTrue(receipt["committed"])
        self.assertEqual("succeeded", receipt["cleanup"]["status"])
        self.assertEqual(1, receipt["cleanup"]["actual_rows"])
        self.assertEqual(1, len(self.db.data["dbo.Notes"]))
        self.assertEqual("existing", self.db.data["dbo.Notes"][0]["Owner"])
        self.assertEqual(4, self.db.connections)

    def test_fixture_owner_mismatch_prevents_write(self):
        operation = self.operation()
        operation["fixture"]["value"] = "wrong-owner"
        receipt = self.execute(self.plan(operation))
        self.assertEqual("db_fixture_owner", receipt["error"]["code"])
        self.assertFalse(any(call[0] == "apply" for call in self.db.calls))

    def test_nonkey_predicate_prevents_write(self):
        operation = self.operation("delete")
        operation["keys"] = [{"Body": "Original"}]
        receipt = self.execute(self.plan(operation))
        self.assertEqual("db_primary_key", receipt["error"]["code"])

    def test_retry_and_scope_limits_cannot_be_widened(self):
        plan = self.plan()
        plan["limits"]["max_retries"] = 1
        self.assertError("invalid_input", lambda: validate_plan(plan))
        plan = self.plan()
        plan["migrations"][0]["max_rows"] = 0
        self.assertError("db_row_limit", lambda: validate_plan(plan))
        plan = self.plan()
        plan["objects"][0]["name"] = "Other"
        self.assertError("db_scope", lambda: validate_plan(plan))

    def test_supported_subset_rejects_special_table(self):
        self.db.catalog["dbo.Notes"]["unsafe"] = ["trigger"]
        receipt = self.execute(self.plan())
        self.assertEqual("blocked", receipt["status"])
        self.assertEqual("db_unsupported", receipt["error"]["code"])

    def test_inspection_returns_hashes_counts_and_definitions_without_rows(self):
        result = inspect_database(self.resolved, [{"schema": "dbo", "table": "Notes"}, {"schema": "dbo", "table": "Missing"}], connection_factory=self.db.connect)
        self.assertEqual("passed", result["status"])
        self.assertEqual(1, result["objects"][0]["row_count"])
        self.assertTrue(result["objects"][1]["baseline"]["expected_absent"])
        self.assertNotIn("Original", json.dumps(result))
        self.assertFalse(any(call[0] in ("begin", "apply", "commit") for call in self.db.calls))

    def test_probe_driver_error_never_echoes_password(self):
        def broken(resolved):
            raise RuntimeError("Password=NEVER-REPORT")
        result = probe_environment(self.resolved, broken)
        self.assertEqual("blocked", result["status"])
        self.assertNotIn("NEVER-REPORT", json.dumps(result))

    def test_lock_failure_rolls_back_and_never_retries(self):
        self.db.lock_error = True
        receipt = self.execute(self.plan())
        self.assertEqual("db_lock_failed", receipt["error"]["code"])
        self.assertEqual("succeeded", receipt["rollback"])
        self.assertEqual(0, receipt["retries"])
        self.assertEqual(1, self.db.connections)

    def test_budget_failure_is_recorded(self):
        with patch("harness.database.time.monotonic", side_effect=[0, 31, 32]):
            receipt = self.execute(self.plan())
        self.assertEqual("db_timeout", receipt["error"]["code"])
        self.assertEqual([], self.db.calls)

    def test_review_report_includes_exact_limits_and_values(self):
        report = render_plan(self.plan())
        self.assertIn("max_observed_rows", report)
        self.assertIn("db/migrations/001.sql", report)
        self.assertIn("Synthetic memo", report)
        self.assertIn("migration-1", report)
        self.assertIn("INSERT INTO", report)

    def test_missing_driver_returns_actionable_blocker_without_installation(self):
        with patch("harness.database.importlib.util.find_spec", return_value=None):
            receipt = execute_plan(self.plan(), self.resolved, approval_binding={"review_id": "synthetic", "plan_sha256": sha256(encoded(self.plan())), "environment_revision": "env1", "target_revision": "target1"})
        self.assertEqual("blocked", receipt["status"])
        self.assertEqual("db_driver_missing", receipt["error"]["code"])

    def test_source_path_escape_and_unregistered_operation_fields_rejected(self):
        plan = self.plan()
        plan["migrations"][0]["source_path"] = "../outside.sql"
        self.assertError("invalid_path", lambda: validate_plan(plan))
        operation = self.operation("delete")
        operation["columns"] = [{"name": "Id", "type": "int", "nullable": False}]
        self.assertError("db_operation_fields", lambda: compile_migration(operation))

    def test_strict_value_types_prevent_driver_coercion(self):
        for value in (True, "2", 2147483648):
            with self.subTest(value=value):
                operation = self.operation()
                operation["rows"][0]["Id"] = value
                receipt = self.execute(self.plan(operation))
                self.assertEqual("db_values", receipt["error"]["code"])
                self.assertFalse(receipt["committed"])

    def test_cursor_is_created_after_bounded_timeout_is_set(self):
        class Cursor:
            description = None
            rowcount = 1
            def execute(self, sql, parameters):
                calls.append(("execute", sql, parameters))
            def close(self):
                calls.append(("cursor-close",))
        class Connection:
            timeout = 0
            def cursor(self):
                calls.append(("cursor-created", self.timeout))
                return Cursor()
            def close(self):
                calls.append(("connection-close",))
        calls = []
        session = SqlServerSession(Connection())
        session.statement_timeout = 5
        session.deadline = 4
        with patch("harness.database.time.monotonic", return_value=2):
            session.query("SELECT ?;", ("value",))
        self.assertEqual(("cursor-created", 2), calls[0])
        with patch("harness.database.time.monotonic", return_value=3):
            session.query("SELECT ?;", ("next",))
        self.assertEqual(("cursor-created", 1), calls[3])
        session.close()

    def test_driver_connection_fields_cannot_inject_odbc_options(self):
        from harness.database import _connection
        fake_driver = SimpleNamespace(drivers=lambda: ["ODBC Driver 18 for SQL Server"], connect=lambda connection_string, **kwargs: (connection_string, kwargs))
        self.resolved.env.update({"MSSQL_SERVER": "fixture;Encrypt=no", "MSSQL_DATABASE": "fake-db", "MSSQL_DRIVER": "ODBC Driver 18 for SQL Server",
                                 "MSSQL_AUTH": "sql", "MSSQL_USER": "fake-role", "MSSQL_PASSWORD": "}fake;Encrypt=no", "MSSQL_ENCRYPT": "true", "MSSQL_TRUST_SERVER_CERTIFICATE": "false"})
        with patch("harness.database.importlib.util.find_spec", return_value=True), patch.dict("sys.modules", {"pyodbc": fake_driver}):
            connection_string, options = _connection(self.resolved)
        self.assertIn("SERVER={fixture;Encrypt=no}", connection_string)
        self.assertIn("PWD={}}fake;Encrypt=no}", connection_string)
        self.assertIn("Encrypt={yes}", connection_string)
        self.assertIn("TrustServerCertificate={no}", connection_string)
        self.assertFalse(options["autocommit"])


if __name__ == "__main__":
    unittest.main()
