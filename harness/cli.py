from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
from .common import HarnessError

def main(argv=None):
    parser=argparse.ArgumentParser(description='Team Harness: local staged development records')
    parser.add_argument('--state-root',default=os.environ.get('TEAM_HARNESS_HOME',str(Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'TeamDevelopment')))
    parser.add_argument('--standard-root',default=str(Path(__file__).resolve().parents[1]))
    sub=parser.add_subparsers(dest='mode',required=True)
    sub.add_parser('serve')
    describe=sub.add_parser('describe'); describe.add_argument('operation',nargs='?')
    call=sub.add_parser('call'); call.add_argument('operation'); call.add_argument('--input-file'); call.add_argument('--json',dest='json_value')
    args=parser.parse_args(argv)
    try:
        from .release import verify_release
        verify_release()
        from .api import API
        api=API(args.state_root,args.standard_root)
        if args.mode=='serve':
            from .server import serve
            serve(api); return 0
        if args.mode=='describe':
            schemas=api.operations()
            if args.operation and args.operation not in schemas:
                raise HarnessError('unknown_operation','Unknown operation.')
            result=schemas[args.operation] if args.operation else schemas
        else:
            if args.input_file and args.json_value:
                raise HarnessError('invalid_input','Choose --input-file or --json, not both.')
            if args.input_file:
                path=Path(args.input_file)
                if path.stat().st_size>2*1024*1024:
                    raise HarnessError('request_too_large','Input file exceeds 2 MiB.')
                params=json.loads(path.read_text(encoding='utf-8-sig'))
            else:
                params=json.loads(args.json_value or '{}')
            result=api.call(args.operation,params)
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
        return 0
    except HarnessError as exc:
        print(json.dumps({'error':exc.code,'message':str(exc)},ensure_ascii=False))
        return 2
    except (OSError,ValueError,KeyError) as exc:
        print(json.dumps({'error':'invalid_or_unavailable_input','message':type(exc).__name__},ensure_ascii=False))
        return 2
