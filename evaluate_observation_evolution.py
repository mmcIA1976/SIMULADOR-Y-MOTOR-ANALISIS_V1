"""Explicit bounded audit; stdout only, read-only unless --apply is supplied."""
from __future__ import annotations

import argparse
import json

from db import connect, close_pool
from observation_numeric_evolution import build_evolution, pack
from observation_evolution_store import (
    load_episode, persist_evolution, stored_report, historical_comparison, report_view,
)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation",type=int,required=True)
    parser.add_argument("--apply",action="store_true",help="Store one immutable compact evaluation; never change an operation")
    parser.add_argument("--rule")
    parser.add_argument("--stage")
    parser.add_argument("--metric")
    parser.add_argument("--compare",action="store_true",help="Read at most 10 prior stored episodes")
    args=parser.parse_args()
    with connect() as db:
        if not args.apply:
            db.execute("SET TRANSACTION READ ONLY")
        # Reuse a completed calculation; never rescan its source snapshots.
        report=stored_report(db,args.operation)
        persistence=None
        if report is None:
            operation,session,rows=load_episode(db,args.operation)
            report=build_evolution(operation,rows,interval_minutes=session["planned_interval_minutes"] or 20)
            if args.apply:
                persistence=persist_evolution(db,operation,rows,interval_minutes=session["planned_interval_minutes"] or 20)
        result=report_view(report,rule_id=args.rule,stage=args.stage,metric=args.metric)
        result["storage"]={"packed_bytes":len(pack(report).encode()),"persistence":persistence}
        if args.compare and report.get("status")!="blocked":
            result["historical_comparison"]=historical_comparison(db,report)
    print(json.dumps(result,ensure_ascii=False,default=str,allow_nan=False))


if __name__=="__main__":
    try:
        main()
    finally:
        close_pool()
