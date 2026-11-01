"""Bounded offline release preflight; does not deploy, query DBs or trade."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from analysis_engine_selection import ENGINE_VERSION, LAB4, V11
from lab4_runtime import load_model, MODEL_SHA, PACKAGE
from versioning import APP_VERSION, DATA_CONTRACT_VERSION


def verify():
    model = load_model()
    archive_path = ROOT/'outputs/engine_replacement_20261031/v011_before_integration_9dea33b4d401ee08.zip'
    with zipfile.ZipFile(archive_path) as archive:
        hashes = json.loads(archive.read('manifest.json'))
        for name, expected in hashes.items():
            if sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError('v011_archive_integrity_failed:' + name)
        preserved = ['empirical_temporal_engine.py','sequential_production_analysis.py',
                     'predictive_rule_library.py','auditorias_motor/motor_v0_11_empirical_analog.json.gz']
        for name in preserved:
            live = (ROOT/name).read_bytes()
            saved = archive.read('simulator/'+name)
            if name.endswith('.py'):
                live = live.replace(b'\r\n',b'\n')
                saved = saved.replace(b'\r\n',b'\n')
            if live != saved:
                raise ValueError('v011_frozen_baseline_changed:' + name)
    lab = ROOT.parent/'trading_lab'
    if lab.exists():
        for name, expected in model['code_sha256'].items():
            if sha256((lab/'lab'/name).read_bytes()).hexdigest() != expected:
                raise ValueError('frozen_lab4_source_changed:' + name)
    glue = ['served_analysis.py','lab4_runtime.py','sequential_production_runtime.py','analysis_engine_selection.py','versioning.py','app.js',
            'app.py','autonomous_contest.py','autonomous_scan_audit.py','limit_production_analysis.py',
            'limit_lifecycle_runtime.py','operation_observation_learning.py']
    return dict(checked_at=datetime.now(timezone.utc).isoformat(),
        status='prepared_locally_not_activated', active_engine=ENGINE_VERSION,
        app_version=APP_VERSION, data_contract_version=DATA_CONTRACT_VERSION,
        target_engine=LAB4, model_sha256=MODEL_SHA,
        base_artifact_sha256=model['artifact_sha256'], archive_files_verified=len(hashes),
        frozen_v011_files_unchanged=preserved, source_lab_fingerprint_verified=lab.exists(),
        frozen_inference_package_verified=True, remote_queries=0,database_writes=0,
        integration_code_sha256={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in glue},
        historical_records_rewritten=0, deployment_performed=False,
        rollback_selection='ANALYSIS_ENGINE_RELEASE=v0.11',
        database_backup_status='not_performed_by_this_local_preflight')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output')
    args=parser.parse_args()
    doc=verify()
    if args.output:
        path=(ROOT/args.output).resolve()
        if not path.is_relative_to(ROOT/'outputs'):
            raise ValueError('release_preflight_output_must_be_in_outputs')
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(doc,ensure_ascii=False))
