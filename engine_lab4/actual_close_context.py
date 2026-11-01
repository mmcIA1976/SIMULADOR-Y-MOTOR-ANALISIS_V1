# Generated from frozen lab functions by tools/package_lab4.py.
import math
import json
from hashlib import sha256
from datetime import datetime, timezone
from .storage import canonical
from . import observational_context as c


PRIMARY='close-context'


DEFINITION=dict(target='actual_operation_close_reason_TP_vs_SL_without_forecast_time_limit',
    horizon_role='pre-analysis_feature_context_only_never_censors_exit_label',
    population='all_available_actual_TP_SL_exits_train_context; paired_saved_v011_plans_evaluate',
    reference='TP/(TP+SL) of saved same-plan forecast, a score for actual exit, not its original horizon-specific P(TP)',
    primary=PRIMARY,previous_candidate='reuse archived predictions without refitting',
    bins=dict(volume='>=1',extension='>=1ATR',cvd='>0',strong_flow='abs(cvd)>=0.02'),
    gate='EMA slope>0, four finite pre-analysis comparable archived measurements',
    prior_strength=20,warmup=80,batch=25,min_context_train=20,min_each_class=5,
    prediction='q_new=(TP_previous_same_horizon_context+20*q_base)/(n_previous_same_horizon_context+20)',
    chronology='only analyses earlier than test block AND actual closed_at strictly before block; all available older local cases allowed',
    calibration='same bounded one-parameter formula, refitted only to earlier actual TP/SL exits with a v011 reference',
    economic_inputs=False,selection='no post-result tuning or automatic promotion',
    status='historical_exploration_previously_inspected_data_not_prospective_validation')
