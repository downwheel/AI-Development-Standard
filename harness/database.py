"""Bounded SQL Server work plans. Credentials and row values never leave the adapter.

Only generated, typed operations are executable. This is not an arbitrary-SQL
permission checker. Gate B and the approved scope are checked by the caller;
the adapter independently pins the plan, environment, target and observations.
"""
from __future__ import annotations

import copy
import datetime
import decimal
import importlib.util
import json
import re
import time
import uuid

from .common import HarnessError, encoded, fail, now, safe_relative, sha256


def _object(properties, required=None, additional=False):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": additional}


def _array(items, minimum=0, maximum=100):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


ID = {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,95}$", "minLength": 1, "maxLength": 96}
TEXT = {"type": "string", "minLength": 1, "maxLength": 5000}
NAME = {"type": "string", "minLength": 1, "maxLength": 128, "pattern": "^[A-Za-z_][A-Za-z0-9_]{0,127}$"}
HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
REF = _object({"artifact_id": ID, "revision_id": ID, "sha256": HASH})
VALUE = {"type": ["string", "integer", "boolean", "null"], "maxLength": 4000}
COLUMN = _object({"name": NAME, "type": {"type": "string", "enum": ["int", "bigint", "smallint", "tinyint", "bit", "nvarchar", "varchar", "uniqueidentifier"]},
                  "nullable": {"type": "boolean"}, "length": {"type": "integer", "minimum": 1, "maximum": 4000}}, ["name", "type", "nullable"])
OPERATION = _object({
    "kind": {"type": "string", "enum": ["create_table", "create_index", "insert", "update", "delete"]},
    "schema": NAME, "table": NAME, "name": NAME, "columns": _array(COLUMN, 1),
    "primary_key": _array(NAME, 1, 16), "index_columns": _array(NAME, 1, 16), "unique": {"type": "boolean"},
    "rows": _array(_object({}, [], True), 1, 1000), "keys": _array(_object({}, [], True), 1, 1000),
    "values": _object({}, [], True),
    "fixture": _object({"column": NAME, "value": VALUE, "owner_id": ID}),
}, ["kind", "schema", "table"])
BASELINE = _object({"expected_absent": {"type": "boolean"}, "sha256": HASH, "data_sha256": HASH}, [])
DB_OBJECT = _object({"schema": NAME, "object_type": {"type": "string", "enum": ["table", "column", "primary-key", "foreign-key", "constraint", "index", "view", "procedure", "trigger", "role", "grant"]},
                     "name": NAME, "table": NAME, "action": {"type": "string", "enum": ["create", "alter", "drop", "data-change", "observe"]},
                     "baseline": BASELINE}, ["schema", "object_type", "name", "action", "baseline"])
MIGRATION = _object({"migration_id": ID, "order": {"type": "integer", "minimum": 1, "maximum": 100},
                     "source_path": {"type": "string", "minLength": 1, "maxLength": 512},
                     "operation": OPERATION, "sql_sha256": HASH, "parameters_sha256": HASH,
                     "expected_rows": {"type": "integer", "minimum": 0, "maximum": 1000},
                     "max_rows": {"type": "integer", "minimum": 0, "maximum": 1000},
                     "case_ids": _array(ID, 1), "generator": {"type": "string", "enum": ["team-sqlserver-2.1"]}})
DB_WORK_PLAN_SCHEMA = _object({
    "db_work_id": ID, "unit_id": ID, "unit_ref": REF, "environment_ref": REF,
    "requirement_ids": _array(ID, 1), "case_ids": _array(ID, 1),
    "engine": {"type": "string", "enum": ["sqlserver"]}, "engine_version": TEXT,
    "target_ref": HASH,
    "target": _object({"target_id": HASH, "database": TEXT, "schema": NAME, "principal_digest": HASH, "permissions_sha256": HASH}),
    "baseline_observed_at": TEXT, "objects": _array(DB_OBJECT, 1, 500), "migrations": _array(MIGRATION, 1, 100),
    "limits": _object({"statement_timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
                        "transaction_timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 900},
                        "lock_timeout_ms": {"type": "integer", "minimum": 0, "maximum": 30000},
                        "max_batch_rows": {"type": "integer", "minimum": 1, "maximum": 1000},
                        "max_observed_rows": {"type": "integer", "minimum": 1, "maximum": 1000},
                        "max_catalog_objects": {"type": "integer", "minimum": 1, "maximum": 5000},
                        "max_retries": {"type": "integer", "enum": [0]}}),
    "preservation": _object({"mode": {"type": "string", "enum": ["only-declared-objects-and-keys"]}, "invariants": _array(TEXT, 1), "backup_required": {"type": "boolean"}, "backup_ref": TEXT}, ["mode", "invariants", "backup_required"]),
    "performance": _object({"required": {"type": "boolean"}, "reason": TEXT, "max_duration_ms": {"type": "integer", "minimum": 1, "maximum": 900000}}, ["required", "reason"]),
    "recovery": _object({"strategy": {"type": "string", "enum": ["transaction"]}, "restart_policy": {"type": "string", "enum": ["inspect-before-retry"]}, "nontransactional": {"type": "boolean", "enum": [False]}}),
    "verification": _object({"case_ids": _array(ID, 1), "oracle": TEXT,
                              "cleanup": _object({"mode": {"type": "string", "enum": ["none", "rollback", "delete-owned-rows"]}, "reason": TEXT})}),
})
DB_WORK_PLAN = DB_WORK_PLAN_SCHEMA


def _validate(value, schema, location="db-work-plan"):
    # Lazy import keeps this standalone schema usable from workflow.PAYLOADS.
    from .workflow import validate
    validate(value, schema, location)


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", value):
        fail("db_identifier", "SQL identifiers must use the supported unambiguous identifier subset")
    return value


def _q(value):
    return "[" + _name(value) + "]"


def _key(obj):
    if obj["object_type"] == "index":
        if "table" not in obj:
            fail("db_baseline", "An index must name its parent table")
        return obj["schema"] + "." + obj["table"] + "." + obj["name"]
    return obj["schema"] + "." + obj["name"]


def _table_key(operation):
    return operation["schema"] + "." + operation["table"]


def _values(mapping):
    if not isinstance(mapping, dict) or not mapping or len(mapping) > 100:
        fail("db_values", "A bounded, nonempty column/value map is required")
    for key, value in mapping.items():
        _name(key)
        _validate(value, VALUE, "db-value")
    return sorted(mapping)


def _compile(operation):
    _validate(operation, OPERATION, "db-operation")
    kind = operation["kind"]
    table = _q(operation["schema"]) + "." + _q(operation["table"])
    common = {"kind", "schema", "table"}
    allowed = {
        "create_table": common | {"columns", "primary_key"},
        "create_index": common | {"name", "index_columns", "unique"},
        "insert": common | {"rows", "fixture"},
        "update": common | {"keys", "values", "fixture"},
        "delete": common | {"keys", "fixture"},
    }[kind]
    if set(operation) - allowed:
        fail("db_operation_fields", "Fields do not match the selected typed operation")
    required = {"create_table": {"columns", "primary_key"}, "create_index": {"name", "index_columns", "unique"},
                "insert": {"rows"}, "update": {"keys", "values"}, "delete": {"keys"}}[kind]
    if not required <= set(operation):
        fail("db_operation_fields", "Typed operation is missing required fields")
    statements, parameters = [], []
    if kind == "create_table":
        columns = operation["columns"]
        names = [c["name"] for c in columns]
        if len(set(n.lower() for n in names)) != len(names):
            fail("db_duplicate", "Column names must be unique")
        pks = operation["primary_key"]
        if len(set(pks)) != len(pks) or not set(pks) <= set(names):
            fail("db_primary_key", "Primary key must reference distinct declared columns")
        parts = []
        for column in columns:
            data_type = column["type"]
            if data_type in {"nvarchar", "varchar"}:
                if "length" not in column:
                    fail("db_column_type", "Text columns need an explicit bounded length")
                data_type += "(" + str(column["length"]) + ")"
            elif "length" in column:
                fail("db_column_type", "Length is only valid for supported text columns")
            if column["name"] in pks and column["nullable"]:
                fail("db_primary_key", "Primary key columns cannot be nullable")
            parts.append(_q(column["name"]) + " " + data_type + (" NULL" if column["nullable"] else " NOT NULL"))
        parts.append("PRIMARY KEY (" + ", ".join(map(_q, pks)) + ")")
        statements.append("CREATE TABLE " + table + " (\n  " + ",\n  ".join(parts) + "\n);")
        parameters.append([])
    elif kind == "create_index":
        cols = operation["index_columns"]
        if len(set(cols)) != len(cols):
            fail("db_duplicate", "Index columns must be unique")
        statements.append("CREATE " + ("UNIQUE " if operation["unique"] else "") + "INDEX " + _q(operation["name"]) + " ON " + table + " (" + ", ".join(map(_q, cols)) + ");")
        parameters.append([])
    elif kind == "insert":
        rows = operation["rows"]
        names = _values(rows[0])
        for row in rows:
            if _values(row) != names:
                fail("db_values", "All inserted rows must provide exactly the same columns")
            statements.append("INSERT INTO " + table + " (" + ", ".join(map(_q, names)) + ") VALUES (" + ", ".join("?" for _ in names) + ");")
            parameters.append([row[n] for n in names])
    else:
        keys = operation["keys"]
        names = _values(keys[0])
        if len({encoded(k) for k in keys}) != len(keys):
            fail("db_duplicate", "Target primary keys must be unique")
        value_names = _values(operation["values"]) if kind == "update" else []
        if set(value_names) & set(names):
            fail("db_primary_key", "Updating primary key columns is not supported")
        for key in keys:
            if _values(key) != names or any(key[n] is None for n in names):
                fail("db_primary_key", "Target keys need the same non-null primary key columns")
            prefix = "UPDATE " + table + " SET " + ", ".join(_q(n) + " = ?" for n in value_names) if kind == "update" else "DELETE FROM " + table
            statements.append(prefix + " WHERE " + " AND ".join(_q(n) + " = ?" for n in names) + ";")
            parameters.append([operation["values"][n] for n in value_names] + [key[n] for n in names])
    sql = "\n".join(statements) + "\n"
    return {"sql": sql, "sql_sha256": sha256(sql.encode("utf-8")), "parameters_sha256": sha256(encoded(parameters)),
            "statements": statements, "parameters": parameters}


def compile_migration(operation):
    """Public pre-approval SQL preview: parameters stay in the pinned typed plan."""
    compiled = _compile(operation)
    return {key: compiled[key] for key in ("sql", "sql_sha256", "parameters_sha256")}


def validate_plan(plan, executable=False):
    _validate(plan, DB_WORK_PLAN_SCHEMA)
    if plan["target_ref"] != plan["target"]["target_id"]:
        fail("db_target", "Target reference and pinned observation disagree")
    if len({m["migration_id"] for m in plan["migrations"]}) != len(plan["migrations"]):
        fail("db_duplicate", "Migration IDs must be unique")
    if len({m["source_path"].lower() for m in plan["migrations"]}) != len(plan["migrations"]):
        fail("db_duplicate", "Each migration needs a distinct reviewed product SQL file")
    if [m["order"] for m in plan["migrations"]] != list(range(1, len(plan["migrations"]) + 1)):
        fail("db_migration_order", "Migration order must be consecutive and explicit")
    if len({_key(o).lower() for o in plan["objects"]}) != len(plan["objects"]):
        fail("db_duplicate", "Each database object must have one declared action")
    for obj in plan["objects"]:
        baseline = obj["baseline"]
        if (baseline.get("expected_absent") is True) == ("sha256" in baseline):
            fail("db_baseline", "Object baseline requires expected absence or an observed definition hash")
        if obj["action"] == "create" and baseline.get("expected_absent") is not True:
            fail("db_baseline", "Creation requires an explicit absence observation")
        if obj["object_type"] == "index" and "table" not in obj:
            fail("db_baseline", "Index baseline must name its parent table")
        if obj["schema"] != plan["target"]["schema"]:
            fail("db_target", "Object is outside the pinned schema")
        if executable and (obj["object_type"] not in {"table", "index"} or obj["action"] not in {"create", "data-change", "observe"}):
            fail("db_unsupported", "This adapter cannot verify the requested object/action; use an explicitly reviewed adapter extension")
    required_changes = set()
    for migration in plan["migrations"]:
        safe_relative(migration["source_path"])
        operation = migration["operation"]
        compiled = _compile(operation)
        if migration["sql_sha256"] != compiled["sql_sha256"] or migration["parameters_sha256"] != compiled["parameters_sha256"]:
            fail("db_migration_hash", "Generated SQL or parameters differ from the pinned migration")
        if not set(migration["case_ids"]) <= set(plan["case_ids"]):
            fail("db_case_coverage", "Migration references an unknown case")
        count = len(operation.get("rows", operation.get("keys", [])))
        if migration["expected_rows"] != count or count > migration["max_rows"] or count > plan["limits"]["max_batch_rows"]:
            fail("db_row_limit", "Expected, maximum and batch row bounds disagree with the typed operation")
        if operation["schema"] != plan["target"]["schema"]:
            fail("db_target", "Migration targets a different schema")
        kind = operation["kind"]
        object_key = _table_key(operation) + ("." + operation["name"] if kind == "create_index" else "")
        action = "create" if kind.startswith("create_") else "data-change"
        matching = [o for o in plan["objects"] if _key(o) == object_key]
        if not matching or matching[0]["action"] not in ({"create", "data-change"} if action == "data-change" else {"create"}):
            fail("db_scope", "Migration does not match a declared object/action")
        required_changes.add(object_key)
        if kind == "create_index" and not any(_key(o) == _table_key(operation) for o in plan["objects"]):
            fail("db_baseline", "Index creation requires an explicit parent-table observation")
    declared_changes = {_key(o) for o in plan["objects"] if o["action"] != "observe"}
    if declared_changes != required_changes:
        fail("db_scope", "Declared and executable object changes differ")
    if not set(plan["verification"]["case_ids"]) == set(plan["case_ids"]):
        fail("db_case_coverage", "Verification must cover every declared database case")
    if plan["performance"]["required"] and "max_duration_ms" not in plan["performance"]:
        fail("db_performance", "Required duration measurement needs an explicit upper bound")
    if plan["preservation"]["backup_required"] and not plan["preservation"].get("backup_ref"):
        fail("db_backup", "The required independently prepared backup has no reference")
    if plan["limits"]["statement_timeout_seconds"] > plan["limits"]["transaction_timeout_seconds"]:
        fail("db_timeout", "Statement timeout cannot exceed the whole transaction budget")
    cleanup = plan["verification"]["cleanup"]["mode"]
    if cleanup == "delete-owned-rows":
        for migration in plan["migrations"]:
            if migration["operation"]["kind"] != "insert" or "fixture" not in migration["operation"]:
                fail("db_cleanup", "Automatic cleanup only supports newly inserted, explicitly owned fixture rows")
    return plan


def render_plan(plan):
    """Deterministic review presentation; caller prose cannot omit DB limits."""
    validate_plan(plan)
    def cell(value):
        return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")
    lines = ["# DB 작업 범위와 정량 계약", "", "작업 ID: `" + plan["db_work_id"] + "` / 단위: `" + plan["unit_id"] + "`",
             "", "대상: `" + cell(plan["target"]["database"]) + "." + cell(plan["target"]["schema"]) + "` / SQL Server `" + cell(plan["engine_version"]) + "`",
             "", "대상 관찰 ID: `" + plan["target_ref"] + "`", "", "| 객체 | 종류 | 작업 | 변경 전 기준 |", "|---|---|---|---|"]
    for obj in plan["objects"]:
        baseline = "부재 확인" if obj["baseline"].get("expected_absent") else obj["baseline"]["sha256"]
        lines.append("| " + " | ".join(map(cell, (_key(obj), obj["object_type"], obj["action"], baseline))) + " |")
    lines += ["", "| Migration / 제품 파일 | 순서 | 동작 | 예상 행 / 최대 행 | 검사 | SQL SHA-256 | 매개변수 SHA-256 |", "|---|---:|---|---:|---|---|---|"]
    for migration in plan["migrations"]:
        lines.append("| " + " | ".join(map(cell, (migration["migration_id"] + " / " + migration["source_path"], migration["order"], migration["operation"]["kind"],
                       str(migration["expected_rows"]) + " / " + str(migration["max_rows"]), ", ".join(migration["case_ids"]), migration["sql_sha256"], migration["parameters_sha256"]))) + " |")
    lines += ["", "실행 한도:", ""] + ["- `" + key + "`: " + str(value) for key, value in plan["limits"].items()]
    lines += ["", "보존 조건:", ""] + ["- " + cell(item) for item in plan["preservation"]["invariants"]]
    lines += ["", "복구: transaction / 실패 후 자동 재실행 금지, 변경 전 상태를 다시 관찰", "",
              "정리: `" + plan["verification"]["cleanup"]["mode"] + "` — " + cell(plan["verification"]["cleanup"]["reason"]), "",
              "검증 근거: " + cell(plan["verification"]["oracle"]), "",
              "성능: " + ("최대 " + str(plan["performance"]["max_duration_ms"]) + " ms" if plan["performance"]["required"] else "N/A") + " — " + cell(plan["performance"]["reason"]), "",
              "이 실행기는 임의 SQL을 실행하지 않습니다. 아래 생성 SQL과 고정된 구조화 매개변수를 함께 승인하며, 제품 파일 생성 여부와 DB 반영 여부는 별도 실행 기록으로 확인합니다."]
    for migration in plan["migrations"]:
        lines += ["", "## " + migration["migration_id"], "", "```sql", compile_migration(migration["operation"])["sql"].rstrip(), "```", "",
                  "구조화 동작 및 행·key·fixture 대상:", "", "```json", json.dumps(migration["operation"], ensure_ascii=False, sort_keys=True, indent=2), "```"]
    return "\n".join(lines) + "\n"


def _canonical(value):
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time, decimal.Decimal, uuid.UUID)):
        return str(value)
    if isinstance(value, bytes):
        return {"binary_sha256": sha256(value), "bytes": len(value)}
    if value is None or type(value) in (str, int, bool):
        return value
    fail("db_data_type", "An observed value uses a type not supported by this bounded adapter")


def _connection(resolved):
    if importlib.util.find_spec("pyodbc") is None:
        fail("db_driver_missing", "Install pyodbc in the selected Python runtime and a Microsoft SQL Server ODBC driver")
    import pyodbc
    env = resolved.env
    required = ("MSSQL_SERVER", "MSSQL_DATABASE", "MSSQL_SCHEMA", "MSSQL_DRIVER", "MSSQL_AUTH")
    if any(not env.get(key) for key in required):
        fail("db_environment_incomplete", "Required SQL Server profile fields are missing")
    driver = env["MSSQL_DRIVER"]
    if driver not in pyodbc.drivers() or not re.fullmatch(r"ODBC Driver (17|18) for SQL Server", driver):
        fail("db_driver_missing", "Select an installed Microsoft ODBC Driver 17 or 18 for SQL Server")
    def escaped(value):
        if any(char in str(value) for char in ("\x00", "\r", "\n")):
            fail("db_environment_format", "Connection fields contain unsupported control characters")
        return "{" + str(value).replace("}", "}}") + "}"
    def flag(key, default):
        value = env.get(key, default).lower()
        if value not in {"true", "false", "yes", "no", "1", "0"}:
            fail("db_environment_format", "SQL Server encryption options must be booleans")
        return "yes" if value in {"true", "yes", "1"} else "no"
    parts = {"DRIVER": driver, "SERVER": env["MSSQL_SERVER"], "DATABASE": env["MSSQL_DATABASE"],
             "Encrypt": flag("MSSQL_ENCRYPT", "yes"), "TrustServerCertificate": flag("MSSQL_TRUST_SERVER_CERTIFICATE", "no")}
    auth = env["MSSQL_AUTH"].lower()
    if auth in {"integrated", "windows"}:
        parts["Trusted_Connection"] = "yes"
    elif auth in {"sql", "sql-password"}:
        if not env.get("MSSQL_USER") or not env.get("MSSQL_PASSWORD"):
            fail("db_environment_incomplete", "SQL authentication needs the selected role's user and password")
        parts.update({"UID": env["MSSQL_USER"], "PWD": env["MSSQL_PASSWORD"]})
    else:
        fail("db_auth_unsupported", "The bounded adapter supports SQL password and Windows integrated authentication")
    try:
        timeout = int(env.get("MSSQL_CONNECTION_TIMEOUT", "10"))
    except ValueError:
        fail("db_environment_format", "Connection timeout must be an integer")
    if not 1 <= timeout <= 30:
        fail("db_environment_format", "Connection timeout must be between 1 and 30 seconds")
    try:
        return pyodbc.connect(";".join(k + "=" + escaped(v) for k, v in parts.items()), timeout=timeout, autocommit=False)
    except Exception:
        fail("db_connection_failed", "SQL Server connection failed; raw driver diagnostics are withheld to avoid credential disclosure")


class SqlServerSession:
    """Small DB-API boundary, injectable in tests without any live server."""
    def __init__(self, connection):
        self.connection = connection
        self.cursor = None
        self.deadline = None
        self.statement_timeout = 10

    def query(self, sql, parameters=(), maximum=5000):
        if self.deadline is not None:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                fail("db_timeout", "Whole DB work budget was exhausted")
            self.connection.timeout = max(1, min(self.statement_timeout, int(remaining)))
        else:
            self.connection.timeout = self.statement_timeout
        if self.cursor is not None:
            self.cursor.close()
        # pyodbc applies SQL_ATTR_QUERY_TIMEOUT when constructing a cursor.
        # Recreate after setting the remaining budget; an old cursor can retain
        # its former timeout even when Connection.timeout has changed.
        self.cursor = self.connection.cursor()
        self.cursor.execute(sql, parameters)
        if not self.cursor.description:
            return []
        columns = [column[0] for column in self.cursor.description]
        rows = self.cursor.fetchmany(maximum + 1)
        if len(rows) > maximum:
            fail("db_observation_limit", "Database observation exceeds the approved bound")
        return [{name: _canonical(value) for name, value in zip(columns, row)} for row in rows]

    def target(self, schema):
        row = self.query("SELECT CAST(SERVERPROPERTY('ServerName') AS nvarchar(256)) AS server_name, DB_NAME() AS database_name, CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128)) AS engine_version, USER_NAME() AS principal, SCHEMA_ID(?) AS schema_id, HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'VIEW DEFINITION') AS can_view_definition;", (schema,), maximum=1)[0]
        if row["schema_id"] is None:
            fail("db_schema_missing", "The selected SQL Server schema does not exist")
        permissions = self.query("SELECT permission_name FROM fn_my_permissions(?, 'SCHEMA') ORDER BY permission_name;", (schema,), maximum=100)
        target_id = sha256(encoded({"server": row["server_name"], "database": row["database_name"], "schema": schema}))
        permissions_hash = sha256(encoded(permissions))
        return {"target_id": target_id, "database": row["database_name"], "schema": schema, "principal_digest": sha256(encoded(row["principal"])),
                "engine": "sqlserver", "engine_version": row["engine_version"], "can_view_definition": bool(row["can_view_definition"]),
                "permissions": [r["permission_name"] for r in permissions], "permissions_sha256": permissions_hash, "permissions_digest": permissions_hash}

    def begin(self, resource, limits):
        self.statement_timeout = limits["statement_timeout_seconds"]
        self.deadline = time.monotonic() + limits["transaction_timeout_seconds"]
        self.query("SET XACT_ABORT ON; SET LOCK_TIMEOUT " + str(limits["lock_timeout_ms"]) + "; SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;")
        # pyodbc autocommit=False starts the transaction. Explicit BEGIN is only
        # needed when no preceding statement has opened it.
        self.query("IF @@TRANCOUNT = 0 BEGIN TRANSACTION;")
        started = time.monotonic()
        row = self.query("DECLARE @result int; EXEC @result = sys.sp_getapplock @Resource=?, @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=?; SELECT @result AS lock_result;", (resource, limits["lock_timeout_ms"]), maximum=1)[0]
        if row["lock_result"] < 0:
            fail("db_lock_failed", "Could not acquire the bounded transaction application lock")
        return round((time.monotonic() - started) * 1000)

    def catalog(self, maximum):
        rows = self.query("SELECT s.name AS schema_name, t.name AS table_name, c.name AS column_name, ty.name AS data_type, c.max_length, c.is_nullable, c.is_identity, c.is_computed, c.default_object_id, c.generated_always_type, t.temporal_type, t.is_memory_optimized, t.is_filetable, t.is_replicated, t.is_merge_published, t.is_tracked_by_cdc, c.is_filestream, c.encryption_type, COALESCE(mc.is_masked,0) AS is_masked FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id JOIN sys.types ty ON ty.user_type_id=c.user_type_id LEFT JOIN sys.masked_columns mc ON mc.object_id=c.object_id AND mc.column_id=c.column_id WHERE t.is_ms_shipped=0 ORDER BY s.name,t.name,c.column_id;", maximum=maximum * 100)
        result = {}
        for row in rows:
            key = row["schema_name"] + "." + row["table_name"]
            table = result.setdefault(key, {"schema": row["schema_name"], "name": row["table_name"], "object_type": "table", "columns": [], "primary_key": [], "unsafe": []})
            table["columns"].append({"name": row["column_name"], "type": row["data_type"], "nullable": bool(row["is_nullable"]), "length": row["max_length"]})
            if any(row[field] for field in ("is_identity", "is_computed", "default_object_id", "generated_always_type", "temporal_type", "is_memory_optimized", "is_filetable", "is_replicated", "is_merge_published", "is_tracked_by_cdc", "is_filestream", "encryption_type", "is_masked")):
                table["unsafe"].append("generated-or-special-table-column")
        indexes = self.query("SELECT s.name AS schema_name,t.name AS table_name,i.name AS index_name,i.is_primary_key,i.is_unique,i.has_filter,i.type_desc,c.name AS column_name,ic.key_ordinal,ic.is_included_column,ic.is_descending_key FROM sys.indexes i JOIN sys.tables t ON t.object_id=i.object_id JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id WHERE t.is_ms_shipped=0 AND i.name IS NOT NULL ORDER BY s.name,t.name,i.name,ic.key_ordinal,ic.index_column_id;", maximum=maximum * 100)
        for row in indexes:
            parent = row["schema_name"] + "." + row["table_name"]
            if row["is_primary_key"]:
                if row["key_ordinal"] > 0:
                    result[parent]["primary_key"].append(row["column_name"])
            else:
                key = parent + "." + row["index_name"]
                index = result.setdefault(key, {"schema": row["schema_name"], "table": row["table_name"], "name": row["index_name"], "object_type": "index", "unique": bool(row["is_unique"]), "filtered": bool(row["has_filter"]), "type": row["type_desc"], "columns": []})
                index["columns"].append({"name": row["column_name"], "included": bool(row["is_included_column"]), "descending": bool(row["is_descending_key"])})
        hazards = self.query("SELECT s.name AS schema_name,t.name AS table_name,'trigger' AS hazard FROM sys.triggers tr JOIN sys.tables t ON t.object_id=tr.parent_id JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE tr.is_disabled=0 UNION ALL SELECT s.name,t.name,'cascading-foreign-key' FROM sys.foreign_keys fk JOIN sys.tables t ON t.object_id=fk.referenced_object_id JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE fk.is_disabled=0 AND (fk.delete_referential_action<>0 OR fk.update_referential_action<>0) UNION ALL SELECT s.name,t.name,'row-level-security' FROM sys.security_predicates p JOIN sys.security_policies policy ON policy.object_id=p.object_id JOIN sys.tables t ON t.object_id=p.target_object_id JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE policy.is_enabled=1;", maximum=maximum)
        for row in hazards:
            key = row["schema_name"] + "." + row["table_name"]
            if key in result:
                result[key]["unsafe"].append(row["hazard"])
        if self.query("SELECT name FROM sys.triggers WHERE parent_class=0 AND is_disabled=0;", maximum=100):
            fail("db_unsupported", "Enabled database DDL triggers prevent reliable bounded-effect verification")
        if len(result) > maximum:
            fail("db_observation_limit", "Catalog exceeds the approved object bound")
        return result

    def rows(self, table, maximum):
        if not table["primary_key"]:
            fail("db_primary_key", "Data verification requires a declared primary key")
        if table["unsafe"]:
            fail("db_unsupported", "Triggers, cascading relations or generated/special columns need a separately reviewed adapter")
        if any(c["type"] not in COLUMN["properties"]["type"]["enum"] for c in table["columns"]):
            fail("db_data_type", "Table uses a type outside the bounded DML adapter")
        rows = self.query("SELECT TOP (" + str(maximum + 1) + ") " + ", ".join(_q(c["name"]) for c in table["columns"]) + " FROM " + _q(table["schema"]) + "." + _q(table["name"]) + " WITH (HOLDLOCK) ORDER BY " + ", ".join(map(_q, table["primary_key"])) + ";", maximum=maximum)
        for column in table["columns"]:
            if column["type"] == "uniqueidentifier":
                for row in rows:
                    if row[column["name"]] is not None:
                        row[column["name"]] = str(uuid.UUID(row[column["name"]]))
        return rows

    def apply(self, operation):
        compiled = _compile(operation)
        affected = 0
        for sql, parameters in zip(compiled["statements"], compiled["parameters"]):
            self.query(sql, parameters)
            if not operation["kind"].startswith("create_"):
                count = self.cursor.rowcount
                if count < 0:
                    fail("db_rowcount_unknown", "Driver did not report a verifiable affected row count")
                affected += count
        return affected

    def commit(self):
        if self.deadline is not None and time.monotonic() >= self.deadline:
            fail("db_timeout", "Whole DB work budget was exhausted before commit")
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        try:
            if self.cursor is not None:
                self.cursor.close()
        finally:
            self.connection.close()


def _session(resolved, factory=None):
    if factory:
        return factory(resolved)
    return SqlServerSession(_connection(resolved))


def _close_safely(session):
    try:
        session.close()
    except Exception:
        fail("db_connection_close_failed", "Database connection cleanup failed; raw driver diagnostics are withheld")


def probe_environment(resolved, connection_factory=None):
    session = None
    try:
        session = _session(resolved, connection_factory)
        target = session.target(resolved.env.get("MSSQL_SCHEMA", "dbo"))
        return {"status": "passed", "observed_at": now(), **target}
    except HarnessError as exc:
        return {"status": "blocked", "code": exc.code, "message": str(exc)}
    except Exception:
        return {"status": "blocked", "code": "db_probe_failed", "message": "DB observation failed; raw driver diagnostics are withheld"}
    finally:
        if session:
            try:
                _close_safely(session)
            except HarnessError:
                return {"status": "blocked", "code": "db_connection_close_failed", "message": "Database connection cleanup failed"}


def inspect_database(resolved, tables, max_rows=1000, max_catalog_objects=5000, connection_factory=None):
    """Read-only bounded design observations, without data values or secrets."""
    if not isinstance(tables, list) or not 1 <= len(tables) <= 100:
        fail("db_observation_limit", "Select 1-100 exact table names for observation")
    normalized_tables = []
    for table in tables:
        if isinstance(table, dict):
            if set(table) != {"schema", "table"} or table["schema"] != resolved.env["MSSQL_SCHEMA"]:
                fail("db_target", "Observation table must match the selected environment schema")
            table = table["table"]
        normalized_tables.append(_name(table))
    if len(set(normalized_tables)) != len(normalized_tables):
        fail("db_duplicate", "Observation tables must be distinct")
    if not 1 <= max_rows <= 1000 or not 1 <= max_catalog_objects <= 5000:
        fail("db_observation_limit", "Observation limits are outside supported bounds")
    session = None
    try:
        session = _session(resolved, connection_factory)
        target = session.target(resolved.env["MSSQL_SCHEMA"])
        if not target["can_view_definition"]:
            fail("db_permissions", "VIEW DEFINITION is required for complete catalog observations")
        catalog = session.catalog(max_catalog_objects)
        objects = []
        for name in normalized_tables:
            key = target["schema"] + "." + name
            obj = catalog.get(key)
            if obj is None:
                objects.append({"schema": target["schema"], "name": name, "object_type": "table", "baseline": {"expected_absent": True}})
            else:
                rows = session.rows(obj, max_rows)
                objects.append({"schema": target["schema"], "name": name, "object_type": "table", "definition": obj,
                                "baseline": {"sha256": sha256(encoded(obj)), "data_sha256": _rows_hash(rows)}, "row_count": len(rows)})
        return {"status": "passed", "observed_at": now(), "target": target, "objects": objects,
                "catalog": [{"object_key": key, "object_type": obj["object_type"], "sha256": sha256(encoded(obj))} for key, obj in sorted(catalog.items())],
                "limits": {"max_rows": max_rows, "max_catalog_objects": max_catalog_objects}}
    except HarnessError:
        raise
    except Exception:
        fail("db_observation_failed", "Database observation failed; raw driver diagnostics are withheld")
    finally:
        if session:
            _close_safely(session)


def _rows_hash(rows):
    return sha256(encoded(sorted(rows, key=lambda row: encoded(row))))


def _verify_target(actual, plan):
    expected = plan["target"]
    if any(actual.get(field) != expected[field] for field in expected) or actual.get("engine_version") != plan["engine_version"]:
        fail("db_target_drift", "Actual database, schema, principal, permissions or engine version differs from the approved observation")
    if not actual.get("can_view_definition"):
        fail("db_permissions", "Complete catalog metadata requires database VIEW DEFINITION")


def _check_baselines(plan, catalog, data):
    for obj in plan["objects"]:
        key, baseline = _key(obj), obj["baseline"]
        current = catalog.get(key)
        if baseline.get("expected_absent") is True:
            if current is not None:
                fail("db_baseline_drift", "An object expected to be absent already exists")
        elif current is None or sha256(encoded(current)) != baseline["sha256"]:
            fail("db_baseline_drift", "Database definition differs from its approved baseline")
        if "data_sha256" in baseline and _rows_hash(data.get(key, [])) != baseline["data_sha256"]:
            fail("db_baseline_drift", "Database rows differ from the observed baseline")
        if obj["action"] == "data-change" and "data_sha256" not in baseline:
            fail("db_baseline", "Data writes require a bounded row-content baseline")


def _expected_data(operation, table, rows):
    expected = copy.deepcopy(rows)
    pk = table["primary_key"]
    if not pk:
        fail("db_primary_key", "DML requires exact primary key verification")
    names = {column["name"] for column in table["columns"]}
    kind = operation["kind"]
    by_name = {column["name"]: column for column in table["columns"]}
    def checked(mapping):
        for name, value in mapping.items():
            column = by_name.get(name)
            if not column:
                fail("db_values", "A value targets a column absent from the observed table")
            data_type = column["type"]
            if value is None:
                if not column["nullable"]:
                    fail("db_values", "A non-nullable column has a null value")
                continue
            if data_type in {"int", "bigint", "smallint", "tinyint"}:
                ranges = {"int": (-2147483648, 2147483647), "bigint": (-9223372036854775808, 9223372036854775807), "smallint": (-32768, 32767), "tinyint": (0, 255)}
                if type(value) is not int or not ranges[data_type][0] <= value <= ranges[data_type][1]:
                    fail("db_values", "Integer value is outside its observed SQL type")
            elif data_type == "bit":
                if type(value) is not bool:
                    fail("db_values", "Bit values must be explicit JSON booleans")
            elif data_type in {"nvarchar", "varchar"}:
                if not isinstance(value, str) or len(value.encode("utf-16-le")) > column["length"] * (2 if data_type == "varchar" else 1):
                    fail("db_values", "Text value is outside its observed SQL length")
                if data_type == "varchar" and not value.isascii():
                    fail("db_values", "Non-ASCII varchar conversion needs an explicitly reviewed collation-aware adapter")
            elif data_type == "uniqueidentifier":
                if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value):
                    fail("db_values", "UUID values must use normalized lowercase SQL uniqueidentifier text")
            else:
                fail("db_data_type", "DML value type is outside the supported adapter")
    for mapping in operation.get("rows", operation.get("keys", [])):
        checked(mapping)
    if "values" in operation:
        checked(operation["values"])
    def key_of(row):
        return tuple(row[name] for name in pk)
    if kind == "insert":
        seen = {key_of(row) for row in expected}
        for row in operation["rows"]:
            if set(row) != names:
                fail("db_values", "Insert must provide every table column; implicit defaults are unsupported")
            if key_of(row) in seen:
                fail("db_primary_key", "A planned inserted key already exists")
            seen.add(key_of(row))
            expected.append(copy.deepcopy(row))
    else:
        wanted = operation["keys"]
        if any(set(key) != set(pk) for key in wanted):
            fail("db_primary_key", "Data predicates must specify exactly the observed primary key")
        for key in wanted:
            matches = [r for r in expected if key_of(r) == key_of(key)]
            if len(matches) != 1:
                fail("db_row_limit", "Each planned key must match exactly one observed row")
            if kind == "delete":
                expected.remove(matches[0])
            else:
                if not set(operation["values"]) <= names:
                    fail("db_values", "Updated column is not present in the observed table")
                matches[0].update(operation["values"])
    fixture = operation.get("fixture")
    if fixture:
        touched = operation["rows"] if kind == "insert" else [r for r in rows if any(all(r[k] == v for k, v in key.items()) for key in operation["keys"])]
        if any(row.get(fixture["column"]) != fixture["value"] for row in touched):
            fail("db_fixture_owner", "Fixture operation includes rows outside its declared owner namespace")
        if kind == "update" and fixture["column"] in operation["values"] and operation["values"][fixture["column"]] != fixture["value"]:
            fail("db_fixture_owner", "Fixture ownership cannot be changed by the operation")
    return expected


def _catalog_diff(before, after):
    return [{"object_key": key, "action": "create" if key not in before else "drop" if key not in after else "alter",
             "object_type": (after.get(key) or before[key])["object_type"]}
            for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key)]


def _verify_declared_definitions(plan, catalog):
    for migration in plan["migrations"]:
        operation = migration["operation"]
        kind = operation["kind"]
        key = _table_key(operation)
        if kind == "create_table":
            table = catalog.get(key)
            expected_columns = [{"name": c["name"], "type": c["type"], "nullable": c["nullable"],
                                 "length": c.get("length", {"int": 4, "bigint": 8, "smallint": 2, "tinyint": 1, "bit": 1, "uniqueidentifier": 16}.get(c["type"])) * (2 if c["type"] == "nvarchar" else 1)} for c in operation["columns"]]
            if not table or table["columns"] != expected_columns or table["primary_key"] != operation["primary_key"] or table["unsafe"]:
                fail("db_definition_mismatch", "Created table definition differs from the reviewed typed migration")
        elif kind == "create_index":
            index = catalog.get(key + "." + operation["name"])
            columns = [{"name": name, "included": False, "descending": False} for name in operation["index_columns"]]
            if not index or index["columns"] != columns or index["unique"] != operation["unique"] or index["filtered"] or index["type"] != "NONCLUSTERED":
                fail("db_definition_mismatch", "Created index definition differs from the reviewed typed migration")


def _bounded_session(resolved, factory, deadline, statement_timeout):
    if time.monotonic() >= deadline:
        fail("db_timeout", "Whole DB work budget was exhausted")
    connection = _session(resolved, factory)
    connection.deadline = deadline
    connection.statement_timeout = statement_timeout
    return connection


def _observation(catalog, rows):
    return {"catalog_sha256": sha256(encoded(catalog)), "tables": [{"object_key": key, "sha256": _rows_hash(value), "row_count": len(value)} for key, value in sorted(rows.items())]}


def execute_plan(plan, resolved, *, approval_binding, connection_factory=None):
    """Execute one previously authorized plan, returning evidence for every result.

    The caller must verify an actual current Gate B decision, matching scope and
    plan ref before invocation. This function never accepts AI approval prose.
    A failed commit acknowledgement is explicitly an unknown commit outcome.
    """
    validate_plan(plan, executable=True)
    plan_hash = sha256(encoded(plan))
    if not isinstance(approval_binding, dict) or not approval_binding.get("review_id") or approval_binding.get("plan_sha256") != plan_hash:
        fail("db_approval_binding", "Execution requires a current Gate B binding to this exact DB plan")
    for key in ("revision", "target_revision"):
        if approval_binding.get("environment_" + key if key == "revision" else key) != resolved.binding.get(key):
            fail("db_environment_drift", "Resolved environment does not match the approved binding")
    if resolved.binding.get("role_kind", resolved.binding.get("role")) not in {"migration", "fixture"}:
        fail("db_role", "Database changes require an explicit migration or fixture role")
    started = time.monotonic()
    deadline = started + plan["limits"]["transaction_timeout_seconds"]
    receipt = {"db_work_id": plan["db_work_id"], "plan_sha256": plan_hash, "review_id": approval_binding["review_id"],
               "environment_binding": copy.deepcopy(resolved.binding), "target_ref": plan["target_ref"], "started_at": now(),
               "status": "running", "committed": False, "commit_outcome": "not-attempted", "rollback": "not-needed", "cleanup": {"status": "not-needed"},
               "migrations": [{"migration_id": m["migration_id"], "status": "not-run", "sql_sha256": m["sql_sha256"], "parameters_sha256": m["parameters_sha256"],
                               "expected_rows": m["expected_rows"], "max_rows": m["max_rows"]} for m in plan["migrations"]],
               "objects": {"planned": [{"object_key": _key(o), "object_type": o["object_type"], "action": o["action"]} for o in plan["objects"] if o["action"] != "observe"], "actual": []},
               "limits": copy.deepcopy(plan["limits"]), "retries": 0, "independent_observation": "not-run", "differences": [], "case_results": []}
    session = observer = None
    before = expected_rows = None
    transaction_started = False
    try:
        session = _bounded_session(resolved, connection_factory, deadline, plan["limits"]["statement_timeout_seconds"])
        target = session.target(plan["target"]["schema"])
        _verify_target(target, plan)
        receipt["permissions_sha256"] = target["permissions_sha256"]
        transaction_started = True
        receipt["lock_wait_ms"] = session.begin("team-harness:" + plan["target_ref"], plan["limits"])
        session.deadline = deadline
        before = session.catalog(plan["limits"]["max_catalog_objects"])
        touched_tables = {_table_key(m["operation"]) for m in plan["migrations"]}
        data_before = {key: session.rows(before[key], plan["limits"]["max_observed_rows"]) for key in touched_tables if key in before}
        _check_baselines(plan, before, data_before)
        expected_rows = copy.deepcopy(data_before)
        for index, migration in enumerate(plan["migrations"]):
            if time.monotonic() >= deadline:
                fail("db_timeout", "Whole DB work budget was exhausted")
            operation = migration["operation"]
            entry = receipt["migrations"][index]
            entry["status"] = "running"
            migration_started = time.monotonic()
            table_key = _table_key(operation)
            current_catalog = session.catalog(plan["limits"]["max_catalog_objects"])
            if operation["kind"] in {"insert", "update", "delete"}:
                if table_key not in current_catalog:
                    fail("db_baseline", "DML table is missing")
                expected_rows[table_key] = _expected_data(operation, current_catalog[table_key], expected_rows.get(table_key, []))
                if len(expected_rows[table_key]) > plan["limits"]["max_observed_rows"]:
                    fail("db_observation_limit", "Planned result exceeds the bounded content observation")
            elif operation["kind"] == "create_table":
                expected_rows[table_key] = []
            actual_count = session.apply(operation)
            entry.update({"actual_rows": actual_count, "duration_ms": round((time.monotonic() - migration_started) * 1000), "status": "executed"})
            if actual_count != migration["expected_rows"] or actual_count > migration["max_rows"]:
                fail("db_row_limit", "Actual affected rows violate the pinned expectation or maximum")
        after = session.catalog(plan["limits"]["max_catalog_objects"])
        _verify_declared_definitions(plan, after)
        changes = _catalog_diff(before, after)
        receipt["objects"]["actual"] = changes
        expected_changes = sorted(((_key(o), o["action"], o["object_type"]) for o in plan["objects"] if o["action"] == "create"))
        if sorted((o["object_key"], o["action"], o["object_type"]) for o in changes) != expected_changes:
            fail("db_object_diff", "Actual catalog changes differ from the approved object actions")
        for key, expected in expected_rows.items():
            actual = session.rows(after[key], plan["limits"]["max_observed_rows"])
            if _rows_hash(actual) != _rows_hash(expected):
                fail("db_content_mismatch", "Observed primary keys, values or preserved rows differ from the expected content")
        duration = round((time.monotonic() - started) * 1000)
        if plan["performance"]["required"] and duration > plan["performance"]["max_duration_ms"]:
            fail("db_performance", "Measured work duration exceeds its approved maximum")
        cleanup_mode = plan["verification"]["cleanup"]["mode"]
        if cleanup_mode == "rollback":
            session.rollback()
            receipt["rollback"] = "succeeded-as-planned"
            receipt["cleanup"] = {"status": "succeeded", "mode": "rollback"}
            for entry in receipt["migrations"]:
                entry["status"] = "rolled-back"
            expected_catalog, expected_observation = before, data_before
        else:
            receipt["commit_outcome"] = "unknown"
            session.commit()
            receipt["committed"] = True
            receipt["commit_outcome"] = "committed"
            expected_catalog, expected_observation = after, expected_rows
        transaction_started = False
        session.close()
        session = None
        observer = _bounded_session(resolved, connection_factory, deadline, plan["limits"]["statement_timeout_seconds"])
        _verify_target(observer.target(plan["target"]["schema"]), plan)
        observed_catalog = observer.catalog(plan["limits"]["max_catalog_objects"])
        if observed_catalog != expected_catalog:
            fail("db_postcommit_mismatch", "Independent connection observed a different catalog")
        for key, expected in expected_observation.items():
            if _rows_hash(observer.rows(observed_catalog[key], plan["limits"]["max_observed_rows"])) != _rows_hash(expected):
                fail("db_postcommit_mismatch", "Independent connection observed different persisted or preserved data")
        receipt["independent_observation"] = "passed"
        observer.close()
        observer = None
        if cleanup_mode == "delete-owned-rows":
            _cleanup_owned(plan, resolved, after, expected_rows, data_before, receipt, connection_factory, deadline)
            expected_observation = data_before
        receipt["final_observation"] = _observation(expected_catalog, expected_observation)
        if time.monotonic() >= deadline:
            fail("db_timeout", "Whole DB work budget was exhausted during independent verification")
        if plan["performance"]["required"] and round((time.monotonic() - started) * 1000) > plan["performance"]["max_duration_ms"]:
            fail("db_performance", "Measured end-to-end database work exceeds its approved duration bound")
        receipt["status"] = "passed"
        receipt["case_results"] = [{"case_id": case_id, "status": "passed", "oracle": "typed-operation-content-and-independent-observation"} for case_id in plan["verification"]["case_ids"]]
    except Exception as exc:
        code = exc.code if isinstance(exc, HarnessError) else "db_execution_failed"
        receipt["status"] = "blocked" if code in {"db_driver_missing", "db_environment_incomplete", "db_connection_failed", "db_unsupported", "db_permissions"} else "failed"
        receipt["error"] = {"code": code, "message": str(exc) if isinstance(exc, HarnessError) else "DB execution failed; raw diagnostics are withheld"}
        receipt["differences"].append(code)
        if session and transaction_started:
            try:
                session.rollback()
                receipt["rollback"] = "succeeded" if receipt["commit_outcome"] != "unknown" else "attempted-after-unknown-commit"
            except Exception:
                receipt["rollback"] = "failed-or-unknown"
        for entry in receipt["migrations"]:
            if entry["status"] == "running":
                entry["status"] = "failed"
            elif entry["status"] == "executed" and receipt["rollback"] in {"succeeded", "succeeded-as-planned"}:
                entry["status"] = "rolled-back"
        receipt["case_results"] = [{"case_id": case_id, "status": "blocked" if receipt["status"] == "blocked" else "failed"} for case_id in plan["verification"]["case_ids"]]
    finally:
        for connection in (observer, session):
            if connection:
                try:
                    connection.close()
                except Exception:
                    receipt["differences"].append("connection-close-failed")
                    receipt["status"] = "failed"
        receipt["duration_ms"] = round((time.monotonic() - started) * 1000)
        receipt["performance"] = {"required": plan["performance"]["required"], "reason": plan["performance"]["reason"], "measured_duration_ms": receipt["duration_ms"]}
        if plan["performance"]["required"]:
            receipt["performance"]["max_duration_ms"] = plan["performance"]["max_duration_ms"]
        receipt["finished_at"] = now()
    return receipt


def _cleanup_owned(plan, resolved, expected_catalog, expected_rows, original_rows, receipt, factory, deadline):
    session = observer = None
    receipt["cleanup"] = {"status": "running", "mode": "delete-owned-rows", "planned_rows": sum(m["expected_rows"] for m in plan["migrations"]), "actual_rows": 0}
    try:
        session = _bounded_session(resolved, factory, deadline, plan["limits"]["statement_timeout_seconds"])
        _verify_target(session.target(plan["target"]["schema"]), plan)
        session.begin("team-harness:" + plan["target_ref"], plan["limits"])
        session.deadline = deadline
        catalog = session.catalog(plan["limits"]["max_catalog_objects"])
        if catalog != expected_catalog:
            fail("db_cleanup_conflict", "Catalog changed before fixture cleanup")
        for key, expected in expected_rows.items():
            if _rows_hash(session.rows(catalog[key], plan["limits"]["max_observed_rows"])) != _rows_hash(expected):
                fail("db_cleanup_conflict", "Data changed after verification; automatic fixture cleanup is blocked")
        for migration in reversed(plan["migrations"]):
            operation = migration["operation"]
            table = catalog[_table_key(operation)]
            cleanup = {"kind": "delete", "schema": operation["schema"], "table": operation["table"],
                       "keys": [{key: row[key] for key in table["primary_key"]} for row in operation["rows"]], "fixture": operation["fixture"]}
            current = session.rows(table, plan["limits"]["max_observed_rows"])
            _expected_data(cleanup, table, current)
            count = session.apply(cleanup)
            if count != migration["expected_rows"] or count > migration["max_rows"]:
                fail("db_cleanup_limit", "Fixture cleanup affected a different number of owned rows")
            receipt["cleanup"]["actual_rows"] += count
        for key, expected in original_rows.items():
            if _rows_hash(session.rows(catalog[key], plan["limits"]["max_observed_rows"])) != _rows_hash(expected):
                fail("db_cleanup_mismatch", "Fixture cleanup did not restore the original preserved content")
        receipt["cleanup"]["commit_outcome"] = "unknown"
        session.commit()
        receipt["cleanup"]["commit_outcome"] = "committed"
        session.close()
        session = None
        observer = _bounded_session(resolved, factory, deadline, plan["limits"]["statement_timeout_seconds"])
        _verify_target(observer.target(plan["target"]["schema"]), plan)
        if observer.catalog(plan["limits"]["max_catalog_objects"]) != expected_catalog:
            fail("db_cleanup_mismatch", "Independent cleanup catalog observation failed")
        for key, expected in original_rows.items():
            if _rows_hash(observer.rows(expected_catalog[key], plan["limits"]["max_observed_rows"])) != _rows_hash(expected):
                fail("db_cleanup_mismatch", "Independent cleanup persistence observation failed")
        receipt["cleanup"]["status"] = "succeeded"
    except Exception:
        receipt["cleanup"]["status"] = "failed"
        if session:
            try:
                session.rollback()
                receipt["cleanup"]["rollback"] = "attempted"
            except Exception:
                receipt["cleanup"]["rollback"] = "failed-or-unknown"
        raise
    finally:
        for connection in (observer, session):
            if connection:
                connection.close()


def check_plan_current(plan, resolved, receipt, connection_factory=None):
    """Fresh independent post-state check; source Git never restores DB state."""
    validate_plan(plan, executable=True)
    if receipt.get("status") != "passed" or receipt.get("plan_sha256") != sha256(encoded(plan)) or not receipt.get("final_observation"):
        return {"current": False, "blockers": ["db_receipt_not_passed_or_different_plan"]}
    if receipt.get("environment_binding") != resolved.binding:
        return {"current": False, "blockers": ["db_environment_observation_changed"]}
    session = None
    try:
        deadline = time.monotonic() + min(60, plan["limits"]["transaction_timeout_seconds"])
        session = _bounded_session(resolved, connection_factory, deadline, plan["limits"]["statement_timeout_seconds"])
        _verify_target(session.target(plan["target"]["schema"]), plan)
        catalog = session.catalog(plan["limits"]["max_catalog_objects"])
        expected = receipt["final_observation"]
        if sha256(encoded(catalog)) != expected["catalog_sha256"]:
            return {"current": False, "blockers": ["db_catalog_changed"]}
        for table in expected["tables"]:
            rows = session.rows(catalog[table["object_key"]], plan["limits"]["max_observed_rows"])
            if _rows_hash(rows) != table["sha256"] or len(rows) != table["row_count"]:
                return {"current": False, "blockers": ["db_persisted_content_changed"]}
        return {"current": True, "blockers": [], "observed_at": now(), "observation": expected}
    except Exception as exc:
        return {"current": False, "blockers": [exc.code if isinstance(exc, HarnessError) else "db_currentness_observation_failed"]}
    finally:
        if session:
            try:
                session.close()
            except Exception:
                return {"current": False, "blockers": ["db_connection_close_failed"]}
