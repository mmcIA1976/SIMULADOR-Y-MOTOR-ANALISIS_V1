"""One explicit release selection shared by users, LIMIT, workers and bots.

The 1-Nov approved global release selects lab.4 for web and worker by default.
Set ANALYSIS_ENGINE_RELEASE=v0.11 explicitly for a coordinated rollback.
An invalid selection aborts startup; there is no probability-engine fallback.
"""
import os

V11 = 'TP-SL-EMPIRICAL-ANALOG-v0.11'
LAB4 = 'TP-SL-EXPERIMENTAL-v0.12-lab.4'
LAB4_MODEL_SHA = '1061816d0899ab541e61bf6e3b789dcb08d7328091f1a4ce2285bf1e59576a32'
RELEASES = {'v0.11': V11, V11: V11, 'v0.12-lab.4': LAB4, LAB4: LAB4}
SETTING = os.environ.get('ANALYSIS_ENGINE_RELEASE', 'v0.12-lab.4')
if SETTING not in RELEASES:
    raise ValueError('unsupported_ANALYSIS_ENGINE_RELEASE')
ENGINE_VERSION = RELEASES[SETTING]
SCORING_BY_ENGINE = {V11: 'historical-analog-first-touch-v0.11',
                     LAB4: 'frozen-lab2-direction-joint-resolution-v0.12-lab.4'}
SCORING_VERSION = SCORING_BY_ENGINE[ENGINE_VERSION]
RUNTIME_VERSION = ('empirical-analog-runtime-v0.11' if ENGINE_VERSION == V11
                   else 'preserved-lab4-runtime-v1')


def result_version_contract(result, contract):
    """Use the recorded engine, never today's selection, for saved results."""
    version = result.get('engine_version', contract['engine_version'])
    from versioning import scoring_version_for_legacy_engine
    saved = {**contract, 'engine_version': version,
             'scoring_version': result.get('scoring_version') or scoring_version_for_legacy_engine(version)}
    saved.pop('model_sha256',None)
    if result.get('model_sha256'):
        saved['model_sha256'] = result['model_sha256']
    elif version == LAB4:
        saved['model_sha256'] = LAB4_MODEL_SHA
    if version in (V11,LAB4):
        saved['prospective_runtime_version'] = ('empirical-analog-runtime-v0.11' if version==V11 else 'preserved-lab4-runtime-v1')
    return saved
