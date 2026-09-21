"""Regenerate public schemas; new package files require explicit relative paths."""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.api import API
from harness.common import safe_relative
from harness.workflow import PAYLOADS
from harness import tool_policy


def tool_contract():
    return {'tool_policy_version': tool_policy.POLICY_VERSION,
            'plan': tool_policy.TOOL_PLAN_SCHEMA, 'observations': tool_policy.TOOL_OBSERVATIONS_SCHEMA,
            'check_bindings': tool_policy.TOOL_CHECKS_SCHEMA, 'completion_evidence': tool_policy.COMPLETION_EVIDENCE_SCHEMA,
            'results': {name: getattr(tool_policy, attribute) for name, attribute in (
                ('library_docs', 'DOC_RESULT'), ('figma', 'FIGMA_RESULT'), ('local_design', 'LOCAL_DESIGN_RESULT'),
                ('database', 'DB_RESULT'), ('browser', 'BROWSER_RESULT'))}}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--write',action='store_true',help='Write generated public schemas in this source checkout.')
    parser.add_argument('--add-package-path',action='append',default=[],help='Explicit source-relative path to add to the release allowlist.')
    args=parser.parse_args()
    data={'contracts/workflow-operations.json':API(ROOT.parent/'schema-inspection-only',ROOT).operations(),
          'contracts/artifact-payloads.json':PAYLOADS,
          'contracts/tool-policy.json':tool_contract()}
    mismatches=[]
    for name,value in data.items():
        path=ROOT/name
        text=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
        if not path.exists() or path.read_text(encoding='utf-8')!=text:
            mismatches.append(name)
            if args.write: path.write_text(text,encoding='utf-8',newline='\n')
    if args.add_package_path:
        if not args.write: parser.error('--add-package-path requires --write')
        path=ROOT/'contracts/package-files.json'; manifest=json.loads(path.read_text(encoding='utf-8'))
        for name in args.add_package_path:
            normalized=safe_relative(name).as_posix()
            if not (ROOT/normalized).is_file(): parser.error('Package path must be an existing source file: '+normalized)
            manifest['files'].append(normalized)
        manifest['files']=sorted(set(manifest['files']))
        path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'changed_schemas':mismatches,'written':args.write,'package_paths_added':args.add_package_path},ensure_ascii=False))
    return 0 if args.write or not mismatches else 1


if __name__=='__main__': raise SystemExit(main())
