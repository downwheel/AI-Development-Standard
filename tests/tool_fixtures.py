"""Explicit N/A declarations for isolated source-only regression fixtures."""


def no_tool_plan():
    return [{"capability": name, "mode": "not_applicable", "reason": "SYNTHETIC source-only fixture; no external product behavior", "unit_ids": []}
            for name in ("ui_design", "library_docs", "browser", "database")]
