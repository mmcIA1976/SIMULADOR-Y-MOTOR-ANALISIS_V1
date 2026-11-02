"""Repair only backed-up lab.4 derived learning summaries, never forecasts.

Default is offline verification. --apply uses optimistic guards in one DB
transaction; an already corrected row is verified and skipped. Keep the input
backup under ignored data/backups. No market downloads or model fitting.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import predictive_rule_learning_snapshot
from analysis_engine_selection import LAB4, LAB4_MODEL_SHA
from lab4_learning import CONTRACT
from versioning import LAB4_LEARNING_EVALUATOR_VERSION


def object_value(value):
    return json.loads(value) if isinstance(value,str) else deepcopy(value or {})


def prepare(row):
    snapshot=object_value(row['snapshot_json'])
    assert snapshot['engine_version']==LAB4
    assert snapshot['model_sha256']==LAB4_MODEL_SHA
    original=object_value(row['structured_json'])
    evidence=object_value(row['evidence_json'])
    fixed=predictive_rule_learning_snapshot(snapshot,plan_result=row['plan_result'],
        operation=dict(closed_at=row['closed_at'],close_reason=row['close_reason']),
        historical_evidence=evidence)
    if row.get('existing_fixed_horizon_label') is not None:
        assert fixed['observed_outcome']==row['existing_fixed_horizon_label']
    assert fixed['trace_contract']==CONTRACT
    assert fixed['lab4_correction']['model_sha256']==LAB4_MODEL_SHA
    fields={field for inputs in fixed['lab4_correction']['inputs_by_rule'].values() for field in inputs}
    assert fields=={'ema_slope','ema_price','cvd','volume','extension','path'}
    corrected=deepcopy(original)
    corrected['analysis_context']['predictive_rules']=fixed
    corrected['learning_evaluator_version']=LAB4_LEARNING_EVALUATOR_VERSION
    corrected['version_contract']['learning_evaluator_version']=LAB4_LEARNING_EVALUATOR_VERSION
    for key in ('pre_trade_features','post_trade_outcomes','plan_result','analysis_verdict','economic_metrics'):
        assert corrected.get(key)==original.get(key),key
    return corrected


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    path=Path(args.input).resolve()
    if not path.is_relative_to(ROOT/'data/backups'):
        raise ValueError('A private backup in data/backups is required')
    raw=path.read_bytes();rows=json.loads(raw)
    assert len({row['learning_id'] for row in rows})==len(rows)
    desired=[(row,prepare(row)) for row in rows]
    summaries=[dict(operation=row['operation_id'],learning_id=row['learning_id'],
        observed_outcome=doc['analysis_context']['predictive_rules']['observed_outcome'],
        real_close_reason=row['close_reason'],
        active_rule_count=doc['analysis_context']['predictive_rules']['active_rule_count'],
        correction_inputs=6,forecast_unchanged=True) for row,doc in desired]
    changed=0;already_correct=0
    if args.apply:
        from db import connect,close_pool
        try:
            with connect() as db:
                for row,doc in desired:
                    current=db.execute('SELECT structured_json,learning_evaluator_version FROM learning_evaluations WHERE id=? FOR UPDATE',
                        (row['learning_id'],)).fetchone()
                    if current is None:
                        raise RuntimeError('missing_learning_row')
                    source=db.execute('SELECT md5(snapshot_json) AS snapshot_md5,md5(analysis_json) AS analysis_md5 FROM recommendations WHERE id=?',
                        (row['recommendation_id'],)).fetchone()
                    if source is None or any(source[key]!=row[key] for key in ('snapshot_md5','analysis_md5')):
                        raise RuntimeError('original_forecast_changed')
                    stored=object_value(current['structured_json'])
                    existing=stored.get('analysis_context',{}).get('predictive_rules',{})
                    if current['learning_evaluator_version']==LAB4_LEARNING_EVALUATOR_VERSION:
                        if (existing.get('trace_contract')!=CONTRACT
                                or existing.get('observed_outcome')!=doc['analysis_context']['predictive_rules']['observed_outcome']
                                or existing.get('lab4_correction',{}).get('model_sha256')!=LAB4_MODEL_SHA):
                            raise RuntimeError('already_versioned_row_failed_verification')
                        already_correct+=1
                        continue
                    if current['structured_json']!=row['structured_json']:
                        raise RuntimeError('concurrent_learning_change')
                    cursor=db.execute('''UPDATE learning_evaluations
                        SET structured_json=?,learning_evaluator_version=?,updated_at=CURRENT_TIMESTAMP
                        WHERE id=? AND structured_json=? AND learning_evaluator_version=?''',
                        (json.dumps(doc,ensure_ascii=False),LAB4_LEARNING_EVALUATOR_VERSION,
                         row['learning_id'],row['structured_json'],row['learning_evaluator_version']))
                    if cursor.rowcount!=1:
                        raise RuntimeError('learning_update_guard_failed')
                    changed+=1
        finally:
            close_pool()
    report=dict(checked_at=datetime.now(timezone.utc).isoformat(),applied=args.apply,
        backup_sha256=sha256(raw).hexdigest(),updated=changed,already_correct=already_correct,
        model_refitted=False,forecasts_rewritten=0,operations_changed=0,rows=summaries)
    if args.apply:
        path.with_name(path.stem+'_repair_result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
