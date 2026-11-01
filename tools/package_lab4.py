"""Package frozen inference functions, without training or lab runtime imports.

Run locally before release. Never connects to a database or deploys anything.
Source functions are copied verbatim by AST boundaries and recorded by hash.
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT.parent / 'trading_lab'
MODEL_SHA = '1061816d0899ab541e61bf6e3b789dcb08d7328091f1a4ce2285bf1e59576a32'
HEADER = '''# Generated from frozen lab functions by tools/package_lab4.py.
import math
import json
from hashlib import sha256
from datetime import datetime, timezone
from .storage import canonical
'''
# Only inference is shipped. No fitting, downloads, reports or database modules.
SPECS = {
    'observational_context': (['KEYS', 'FIELDS'], ['digest', 'finite', 'epoch', 'logit', 'sigmoid'], ''),
    'actual_close_context': (['PRIMARY', 'DEFINITION'], [], 'from . import observational_context as c\n'),
    'actual_close_side_weights': (['PRIMARY', 'KEYS', 'SPECS'], ['eligible', 'key', 'predict'], 'from . import observational_context as c\n'),
    'long_rebound_review': ([], ['usable', 'predict'], 'from . import observational_context as c, actual_close_side_weights as w\n'),
    'short_flow_response': ([], ['eligible', 'target', 'response_band', 'context_key', 'predict'], 'from . import observational_context as c, actual_close_side_weights as w\n'),
    'long_extension_context': ([], ['eligible', 'value', 'context_key', 'predict'], 'from . import actual_close_side_weights as w\n'),
    'engine_proposal': (['ENGINE_VERSION', 'FIELD_RULES'], ['temperature', 'raw_prediction', 'apply_frozen'],
        'from . import observational_context as c, actual_close_context as a, actual_close_side_weights as w, long_rebound_review as r, short_flow_response as f, long_extension_context as e\n'),
    'correction_review': (['STAGES'], ['stages', 'gate_key', 'predict'], ''),
    'correction_predictor': (['VERSION', 'ENGINE_VERSION'], ['archived_row', 'apply_frozen'], 'from . import observational_context as c, engine_proposal as p, correction_review as r\n'),
    'temporal_engine': ([], ['probability_vector', 'cumulative', 'marginal_reachability'], 'from . import observational_context as c\nSTAGES = ("intraday_short", "intraday_wide", "short_swing")\n'),
    'preserved_temporal_engine': (['VERSION', 'ENGINE_VERSION', 'DEFINITION'], ['validate_q', 'hazards', 'split_mass', 'predict'], 'from . import temporal_engine as base\n'),
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def package():
    model_raw = (LAB / 'releases/v0.12-lab.4/model.json').read_bytes()
    if digest(model_raw) != MODEL_SHA:
        raise ValueError('frozen_lab4_model_changed')
    model = json.loads(model_raw)
    parent = model['binary_model']['parent_model']
    if parent['selected_variant'] != 'frozen-66':
        raise ValueError('unapproved_inference_variant')
    output = ROOT / 'engine_lab4'
    output.mkdir(exist_ok=True)
    provenance = {}
    for name, (constants, functions, imports) in SPECS.items():
        raw = (LAB / 'lab' / (name + '.py')).read_bytes()
        text = raw.decode('utf-8-sig')
        nodes = []
        found = set()
        for node in ast.parse(text).body:
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)] if isinstance(node, ast.Assign) else []
            if (isinstance(node, ast.FunctionDef) and node.name in functions) or set(targets) & set(constants):
                nodes.append(ast.get_source_segment(text, node))
                found.update(targets or [node.name])
        if found != set(constants + functions):
            raise ValueError(f'package_missing_definitions:{name}:{found}')
        compiled = HEADER + imports + '\n\n' + '\n\n\n'.join(nodes) + '\n'
        compile(compiled, name, 'exec')
        (output / (name + '.py')).write_text(compiled, encoding='utf-8', newline='\n')
        provenance[name] = {'source_sha256': digest(raw), 'constants': constants,
                            'functions': {n: digest(ast.get_source_segment(text, next(x for x in ast.parse(text).body if isinstance(x, ast.FunctionDef) and x.name == n)).encode()) for n in functions}}
    (output / '__init__.py').write_text('"""Frozen lab.4 inference only. No runtime dependency on the lab app."""\n', encoding='utf-8')
    (output / 'storage.py').write_text('import json\n\ndef canonical(value):\n    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)\n', encoding='utf-8')
    (output / 'model.json').write_bytes(model_raw)
    manifest = {'model_sha256': MODEL_SHA, 'source_frozen_at': model['frozen_at'],
                'base_artifact_sha256': model['artifact_sha256'], 'source_functions': provenance,
                'files': {p.name: digest(p.read_bytes()) for p in sorted(output.iterdir()) if p.suffix in ('.py', '.json') and p.name != 'manifest.json'}}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'model_sha256': MODEL_SHA, 'inference_files': len(manifest['files']), 'training_functions_shipped': 0}))


def archive_v11():
    files = sorted(set(ROOT.glob('*.py')) | set((ROOT / 'tests').glob('test_*.py')) |
                   {ROOT / 'requirements.txt', ROOT / 'auditorias_motor/motor_v0_11_empirical_analog.json.gz'})
    files += sorted((LAB / 'releases/v0.12-lab.4').glob('*.*'))
    values = {(('simulator/' + str(p.relative_to(ROOT)).replace('\\', '/')) if p.is_relative_to(ROOT)
               else 'lab4/' + p.name): p.read_bytes() for p in files}
    manifest = {name: digest(raw) for name, raw in values.items()}
    mid = digest(json.dumps(manifest, sort_keys=True).encode())
    folder = ROOT / 'outputs/engine_replacement_20261031'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ('v011_before_integration_' + mid[:16] + '.zip')
    if not path.exists():
        with zipfile.ZipFile(path, 'x', zipfile.ZIP_DEFLATED) as archive:
            for name, raw in values.items():
                archive.writestr(name, raw)
            archive.writestr('manifest.json', json.dumps(manifest, indent=2, sort_keys=True))
    print(json.dumps({'archive': str(path), 'files': len(values), 'manifest_sha256': mid,
                      'database_writes': 0, 'historical_records_rewritten': 0}))


def test_fixture():
    source = LAB / 'data/experiments/fixtures/preserved_engine_api_synthetic.json'
    request = json.loads(source.read_bytes())['prediction_input']
    # Existing synthetic API fixture, never scored as a real trade.
    clean = {k:request[k] for k in ('analysis_at','stage_contexts','features','operand_timestamps')}
    target = ROOT / 'tests/fixtures/lab4_synthetic_context.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(clean, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
    print(json.dumps({'synthetic_fixture':str(target), 'bytes':target.stat().st_size}))


if __name__ == '__main__':
    if '--archive-v11' in sys.argv: archive_v11()
    elif '--test-fixture' in sys.argv: test_fixture()
    else: package()
