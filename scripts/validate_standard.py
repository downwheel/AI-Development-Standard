"""Run the portable standard's actual tests and optionally save a local receipt."""
import argparse
import json
from pathlib import Path
import sys
import time
import unittest
sys.dont_write_bytecode=True
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',help='Optional absolute JSON report path outside the common source')
    args=parser.parse_args()
    destination=Path(args.output).absolute() if args.output else None
    if destination:
        from harness.history import _no_links
        _no_links(destination); destination=destination.resolve()
    if destination and (destination==SOURCE or SOURCE in destination.parents):
        parser.error('Keep generated verification evidence outside the shared source.')
    start=time.monotonic()
    from install import source_manifest
    before_manifest=source_manifest()
    suite=unittest.defaultTestLoader.discover(str(SOURCE/'tests'),top_level_dir=str(SOURCE))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    after_manifest=source_manifest()
    unchanged=before_manifest['content_sha256']==after_manifest['content_sha256']
    receipt={'schema_version':1,'scope':'isolated synthetic fixtures; no product or external account operations',
             'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
             'skipped':[{'test':str(test),'reason':reason} for test,reason in result.skipped],
             'successful':result.wasSuccessful() and unchanged,'duration_seconds':round(time.monotonic()-start,3),
             'tested_release_id':before_manifest['release_id'],'source_unchanged_during_validation':unchanged,
             'source_content_sha256':before_manifest['content_sha256'],
             'python':sys.version,'platform':sys.platform,
             'failed_tests':[str(test) for test,_ in result.failures+result.errors]}
    if destination:
        from harness.history import _no_links
        from harness.registry import atomic_json
        _no_links(destination); atomic_json(destination,receipt)
    print(json.dumps(receipt,ensure_ascii=False,indent=2))
    return 0 if result.wasSuccessful() and unchanged else 1


if __name__=='__main__': raise SystemExit(main())
