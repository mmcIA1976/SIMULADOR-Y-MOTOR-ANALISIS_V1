"""One application analysis using the selected engine; no parallel comparator."""
from datetime import datetime, timezone

import market_data
from analysis_engine_selection import ENGINE_VERSION, LAB4, SCORING_BY_ENGINE
import sequential_production_analysis as original
from sequential_production_analysis import NewEngineAnalysisError
from sequential_production_runtime import build_production_probability_run

if ENGINE_VERSION == LAB4:
    from lab4_runtime import load_model
    load_model()


def compact_inference(value):
    """Contexts already live beside this receipt; preserve the same operands."""
    from engine_lab4.observational_context import digest
    compact = {k:v for k,v in value.items() if k not in ('prediction_input','receipt_sha256')}
    compact['source_receipt_sha256'] = value['receipt_sha256']
    compact['prediction_input'] = {k:v for k,v in value['prediction_input'].items() if k != 'stage_contexts'}
    compact['context_location'] = 'snapshot.stage_contexts'
    compact['receipt_sha256'] = digest(compact)
    return compact


def render_lab4(proposal, run, snapshot, *, include_internal_runtime=False,
                context_loader=None, context_market_price=None,
                order_book_observation_loader=None, positioning_observation_loader=None):
    from engine_lab4.observational_context import digest
    from lab4_runtime import predict_from_run, MODEL_SHA, FIELDS
    liquidation_context, liquidation = original.attach_liquidation_observation(run,proposal,
        context_loader=context_loader,context_market_price=context_market_price,analysis_at=snapshot['analysis_at'])
    book_context, book = original.attach_order_book_observation(run,proposal,
        observation_loader=order_book_observation_loader,analysis_at=snapshot['analysis_at'])
    positioning = original.attach_positioning_observation(run,proposal,
        observation_loader=positioning_observation_loader,analysis_at=snapshot['analysis_at'])
    prediction, request, provenance = predict_from_run(run)
    support = prediction.pop('support_stages')
    p = prediction['probabilities']; stages = list(request['stage_contexts'])
    names = ('tp_first_within_horizon','sl_first_within_horizon','neither_barrier_before_expiry')
    def mapped(values):
        return dict(zip(names,(values['tp'],values['sl'],values['unresolved'])))
    artifact = original.load_production_artifact()
    trace = dict(engine_version=LAB4,scoring_version=SCORING_BY_ENGINE[LAB4],
        runtime_version='preserved-lab4-runtime-v1',model_sha256=MODEL_SHA,
        artifact_id=artifact['artifact_id'],artifact_sha256=artifact['artifact_sha256'],
        selected_horizon=request['horizon'],executed_stage_count=len(stages),executed_stages=stages,
        probabilities=mapped(p),decision_probabilities=prediction['decision_probabilities'],
        probability_curve={h:mapped(v) for h,v in prediction['probability_curve'].items()},
        probability_ranges_95pct=None,uncertainty_policy='lab4_intervals_not_calibrated',
        observational_contribution_trace=prediction['observational_contribution_trace'],
        inherited_lab2=prediction['inherited_lab2'],reachability=prediction['reachability'],
        single_engine=True,parallel_probability_engines_executed=0,stage_traces=[],production_effect='served')
    survival = 1.
    for source,stage,correction in zip(support,prediction['corrected_stages'],prediction['stage_traces']):
        row = dict(source,conditional_probabilities=dict(zip(('tp_first_in_stage','sl_first_in_stage','survive_stage'),stage['conditional'])),
            cumulative_probabilities=trace['probability_curve'][stage['stage']],
            survival_entering_stage=survival,lab4_correction=correction)
        trace['stage_traces'].append(row); survival *= stage['conditional'][2]
    trace['result_sha256'] = digest(trace)
    inference = dict(contract_version='engine-inference-v1',model_sha256=MODEL_SHA,
        prediction=prediction,prediction_input=request,prediction_input_sha256=digest(request),
        feature_provenance=provenance,selected_engine=LAB4,fallback_used=False)
    inference['receipt_sha256'] = digest(inference)
    profile = {**original._temporal_profile(request['horizon'],artifact,stages),
        'version':LAB4,'model_sha256':MODEL_SHA,'method':'frozen_lab2_direction_joint_resolution',
        'confidence':'estimación experimental; intervalo pendiente de calibración',
        'validation_note':'Conserva la dirección lab.2; contraste prospectivo pendiente.',
        'observational_input_fields':list(request['features']),
        'frozen_correction_stages':[r['stage'] for r in prediction['observational_contribution_trace']]}
    for rule_trace in run['stage_rule_traces'][request['horizon']]:
        fields = [output for rule,output in FIELDS.values() if rule == rule_trace.get('rule_id')]
        if fields:
            rule_trace.update(lab4_correction_input_outputs=fields,lab4_model_sha256=MODEL_SHA)
    snapshot.update(original._geometry(proposal),engine_version=LAB4,model_sha256=MODEL_SHA,
        data_cutoff_at=run['data_cutoff_at'],
        availability=original._analysis_availability(run,proposal,stages,
            liquidation_available=liquidation['available'],order_book_available=book['available']),
        source={'entry_price':'validated trade-plan entry price','probability_market_data':'Binance USD-M closed multiscale klines',
                'probability_model':LAB4},new_engine_only=True,legacy_engine_executed=False,
        executed_analysis_engines=[LAB4],analysis_engine_execution_count=1,
        stage_contexts=run['stage_contexts'],stage_rule_traces=run['stage_rule_traces'],
        liquidation_observation=liquidation,order_book_observation=book,positioning_observation=positioning,
        probability_trace=trace,temporal_profile=profile,decision_probabilities=prediction['decision_probabilities'],
        reachability=prediction['reachability'],engine_inference=compact_inference(inference))
    result = dict(analysis_type='pre_trade',engine_version=LAB4,scoring_version=SCORING_BY_ENGINE[LAB4],
        model_sha256=MODEL_SHA,engine_family='preserved_lab2_joint_resolution',
        owner_activation='explicit_ANALYSIS_ENGINE_RELEASE',production_effect='served',
        legacy_engine_executed=False,execution_contract='one_selected_engine_one_forecast',
        executed_analysis_engines=[LAB4],analysis_engine_execution_count=1,
        tp_probability=p['tp'],sl_probability=p['sl'],range_probability=p['unresolved'],
        tp_before_sl_within_horizon_probability=p['tp'],
        probability_ranges={k:dict(low=None,high=None,label='Sin intervalo calibrado',meaning='Estimación puntual del modelo lab.4')
                            for k in ('tp','sl','range')},
        risk_level=f"{100*p['sl']:.1f}% SL",setup_grade='no aplicable',confidence=profile['confidence'],
        horizon_calibration=profile,training_decision='decisión del usuario',time_horizon=request['horizon'],parameter_advice={},
        decision_probabilities=prediction['decision_probabilities'],reachability=prediction['reachability'],
        engine_inference=inference,
        plain_summary=f"Motor v0.12-lab.4: TP antes de SL {100*p['tp']:.1f}%; SL {100*p['sl']:.1f}%; ninguno en el plazo {100*p['unresolved']:.1f}%.",
        reasons=[f"TP antes de SL: {100*p['tp']:.1f}%.",f"SL antes de TP: {100*p['sl']:.1f}%.",
                 f"Ninguno dentro del horizonte: {100*p['unresolved']:.1f}%.",'Pesos observacionales y resolución temporal congelados.'],
        alerts=['El modelo expresa probabilidades, no certeza.','La versión y sus pesos quedan identificados en cada análisis.',
                'Los alcances individuales describen continuación hipotética después del primer toque.'],
        explained_metrics=original._explained_metrics(trace),snapshot=snapshot,
        model_trace=dict(engine_version=LAB4,model_sha256=MODEL_SHA,single_engine=True,parallel_probability_engines_executed=0,
            artifact_id=artifact['artifact_id'],artifact_sha256=artifact['artifact_sha256'],temporal_profile=profile,
            stage_traces=trace['stage_traces'],probability_curve=trace['probability_curve'],selected_probabilities=trace['probabilities'],
            decision_probabilities=trace['decision_probabilities'],probability_result_sha256=trace['result_sha256'],
            source_data_sha256=run['source_data_sha256'],source_data_sha256_by_stage=run['source_data_sha256_by_stage'],
            data_cutoff_at=run['data_cutoff_at'],observational_contribution_trace=prediction['observational_contribution_trace'],production_effect='served'))
    run.update(probability_result=trace,analysis_engine_execution_count=1,executed_analysis_engines=[LAB4])
    if include_internal_runtime:
        result['_internal_runtime'] = dict(run=run,live_context={**liquidation_context,**book_context})
    return result


def analyze_trade(proposal, *, loader=market_data.get_klines,context_loader=None,context_market_price=None,
                  order_book_observation_loader=None,positioning_observation_loader=None,
                  include_internal_runtime=False,effective_analysis_at=None):
    options = dict(loader=loader,context_loader=context_loader,context_market_price=context_market_price,
        order_book_observation_loader=order_book_observation_loader,positioning_observation_loader=positioning_observation_loader,
        include_internal_runtime=include_internal_runtime,effective_analysis_at=effective_analysis_at)
    if ENGINE_VERSION != LAB4:
        return original.analyze_trade(proposal,**options)
    if str(getattr(proposal,'entry_type','market')).lower() != 'market':
        raise NewEngineAnalysisError('market_entry_required')
    if proposal.time_horizon not in original.STAGE_PROFILES:
        raise NewEngineAnalysisError('unsupported_time_horizon')
    received = datetime.now(timezone.utc)
    snapshot = dict(symbol=str(proposal.symbol).upper(),side=str(proposal.side).lower(),time_horizon=proposal.time_horizon,
        entry=float(proposal.entry),take_profit=float(proposal.take_profit),stop_loss=float(proposal.stop_loss),
        **original._analysis_stamp(proposal.time_horizon,request_received_at=received,effective_analysis_at=effective_analysis_at or received))
    try:
        run = build_production_probability_run(proposal,snapshot,loader=loader,analysis_id='live-'+snapshot['symbol']+'-'+snapshot['analysis_at'],inputs_only=True)
        if run.get('status') != 'evaluated':
            raise ValueError(run.get('block_code') or 'lab4_data_blocked')
        return render_lab4(proposal,run,snapshot,include_internal_runtime=include_internal_runtime,
            context_loader=context_loader,context_market_price=context_market_price,
            order_book_observation_loader=order_book_observation_loader,positioning_observation_loader=positioning_observation_loader)
    except Exception as exc:
        details = dict(reason=str(exc)[:200],selected_engine=LAB4,fallback_used=False)
        if isinstance(exc,market_data.BinanceDeferred):
            details.update(provider_deferred=True,retry_after_seconds=exc.retry_after_seconds)
        raise NewEngineAnalysisError('lab4_analysis_blocked',details) from exc
