"""One bounded numerical evaluation per closed observation episode/version."""
from __future__ import annotations

from observation_numeric_evolution import (
    VERSION, MAX_CHECKPOINTS, build_evolution, canonical, digest, pack, unpack,
    compare_episodes,
)

MAX_SOURCE_BYTES = 8_000_000

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS public.operation_observation_numeric_evaluations (
    id BIGSERIAL PRIMARY KEY,
    operation_id BIGINT NOT NULL REFERENCES public.operations(id) ON DELETE RESTRICT,
    evaluator_version TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('long','short')),
    time_horizon TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ NOT NULL,
    checkpoint_count INTEGER NOT NULL CHECK (checkpoint_count >= 0),
    status TEXT NOT NULL CHECK (status IN ('complete','blocked')),
    input_sha256 TEXT NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    payload_json TEXT NOT NULL,
    payload_bytes INTEGER NOT NULL CHECK (
        payload_bytes > 0 AND payload_bytes <= 65536
        AND payload_bytes = octet_length(convert_to(payload_json,'UTF8'))
    ),
    production_effect TEXT NOT NULL DEFAULT 'none' CHECK (production_effect = 'none'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(operation_id,evaluator_version)
);
CREATE INDEX IF NOT EXISTS idx_observation_numeric_comparable
    ON public.operation_observation_numeric_evaluations
    (symbol,side,time_horizon,evaluator_version,closed_at DESC);
ALTER TABLE public.operation_observation_numeric_evaluations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.operation_observation_numeric_evaluations FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT ON public.operation_observation_numeric_evaluations TO service_role;
REVOKE ALL ON SEQUENCE public.operation_observation_numeric_evaluations_id_seq FROM PUBLIC,anon,authenticated;
GRANT USAGE,SELECT ON SEQUENCE public.operation_observation_numeric_evaluations_id_seq TO service_role;
"""


def ensure_numeric_evolution_table(db):
    db.executescript(SCHEMA_SQL)


def load_episode(db, operation_id):
    operation = db.execute("""
        SELECT id,symbol,side,time_horizon,status,entry,stop_loss,take_profit,
               started_at,closed_at,close_reason,close_price,final_pnl
        FROM operations WHERE id = ?
    """, (int(operation_id),)).fetchone()
    if operation is None:
        raise ValueError("numeric_evolution_operation_not_found")
    session = db.execute("""
        SELECT id,planned_interval_minutes FROM operation_observation_sessions
        WHERE operation_id = ?
    """, (int(operation_id),)).fetchone()
    if session is None:
        raise ValueError("numeric_evolution_session_not_found")
    budget = db.execute("""
        SELECT COUNT(*) AS n,
               COALESCE(SUM(octet_length(COALESCE((r.snapshot_json::jsonb->'stage_rule_traces')::text,''))
                 + octet_length(COALESCE((r.snapshot_json::jsonb->'stage_contexts')::text,''))
                 + octet_length(COALESCE((r.snapshot_json::jsonb->'rule_catalog')::text,''))),0) AS bytes
        FROM operation_observation_checkpoints c
        LEFT JOIN recommendations r ON r.id=c.recommendation_id
        WHERE c.session_id=?
    """, (int(session["id"]),)).fetchone()
    if int(budget["n"]) > MAX_CHECKPOINTS or int(budget["bytes"]) > MAX_SOURCE_BYTES:
        raise ValueError("numeric_evolution_source_read_budget_exceeded")
    rows = db.execute("""
        SELECT c.checkpoint_code,c.checkpoint_number,c.observed_at,c.market_price,
               c.contract_quality,c.formal_learning_eligible,
               jsonb_build_object(
                   'stage_rule_traces',r.snapshot_json::jsonb->'stage_rule_traces',
                   'stage_contexts',r.snapshot_json::jsonb->'stage_contexts',
                   'rule_catalog',r.snapshot_json::jsonb->'rule_catalog'
               ) AS snapshot_json
        FROM operation_observation_checkpoints c
        LEFT JOIN recommendations r ON r.id=c.recommendation_id
        WHERE c.session_id=? ORDER BY c.checkpoint_number LIMIT ?
    """, (int(session["id"]),MAX_CHECKPOINTS+1)).fetchall()
    return dict(operation), dict(session), [dict(r) for r in rows]


def persisted_status(db, operation_id):
    row=db.execute("""
        SELECT status,checkpoint_count,payload_bytes,evaluator_version,created_at
        FROM operation_observation_numeric_evaluations
        WHERE operation_id=? AND evaluator_version=?
    """,(int(operation_id),VERSION)).fetchone()
    return dict(row) if row else {"status":"not_evaluated","evaluator_version":VERSION}


def persist_evolution(db, operation, checkpoints, *, interval_minutes=20):
    if str(operation.get("status")) != "CLOSED" or not operation.get("closed_at"):
        raise ValueError("numeric_evolution_closed_operation_required")
    identity_error = None
    try:
        identity = source_identity(operation, checkpoints, interval_minutes)
    except (ValueError, TypeError, KeyError) as exc:
        # Even unreadable evidence must yield a small explicit failure, not a
        # recurring exception in the worker's terminal-learning path.
        import hashlib
        identity_error = type(exc).__name__
        identity = digest({"operation_id":int(operation["id"]),
            "unreadable_contract_sha256":hashlib.sha256(str(checkpoints).encode()).hexdigest()})
    existing=db.execute("""
        SELECT status,checkpoint_count,payload_bytes,input_sha256
        FROM operation_observation_numeric_evaluations
        WHERE operation_id=? AND evaluator_version=?
    """,(int(operation["id"]),VERSION)).fetchone()
    # Immutable closed checkpoint facts: finalization retries perform no rewrite.
    if existing:
        if existing["input_sha256"] != identity:
            raise ValueError("numeric_evolution_source_changed_requires_review")
        return {**dict(existing),"reused":True,"version":VERSION}
    try:
        if identity_error:
            raise ValueError("numeric_evolution_unreadable_source:" + identity_error)
        if any(r.get("contract_quality") != "exact" or not r.get("formal_learning_eligible") for r in checkpoints):
            raise ValueError("numeric_evolution_inexact_source_contract")
        report=build_evolution(operation,checkpoints,interval_minutes=interval_minutes)
        payload=pack(report)
        status="complete"
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        # A missing/oversized analytical contract must not stop TP/SL vigilance.
        status="blocked"
        payload=canonical({"version":VERSION,"status":status,"reason":str(exc),"production_effect":"none"})
    size=len(payload.encode())
    db.execute("""
        INSERT INTO operation_observation_numeric_evaluations
            (operation_id,evaluator_version,symbol,side,time_horizon,started_at,closed_at,
             checkpoint_count,status,input_sha256,payload_json,payload_bytes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(operation_id,evaluator_version) DO NOTHING
    """,(int(operation["id"]),VERSION,operation["symbol"],operation["side"],operation["time_horizon"],
          operation["started_at"],operation["closed_at"],len(checkpoints),status,identity,payload,size))
    return {"status":status,"version":VERSION,"checkpoint_count":len(checkpoints),"payload_bytes":size,"reused":False}


def source_identity(operation, checkpoints, interval_minutes):
    # Hash only the consumed contract, so full and projected snapshots agree.
    from observation_numeric_evolution import snapshot_rule_traces
    facts=[]
    for row in checkpoints:
        snapshot=_snapshot(row.get("snapshot_json"))
        facts.append({"code":row["checkpoint_code"],"time":str(row["observed_at"]),
            "price":row["market_price"],"quality":row.get("contract_quality"),
            "eligible":row.get("formal_learning_eligible"),
            "traces":snapshot_rule_traces(snapshot),"contexts":snapshot.get("stage_contexts"),
            "catalog":snapshot.get("rule_catalog")})
    return digest({"operation":{k:str(operation.get(k)) for k in
        ("id","symbol","side","time_horizon","started_at","closed_at")},
        "interval_minutes":interval_minutes,"checkpoints":facts})


def _snapshot(value):
    from observation_numeric_evolution import obj
    return obj(value)


def stored_report(db, operation_id):
    row=db.execute("""SELECT status,payload_json FROM operation_observation_numeric_evaluations
        WHERE operation_id=? AND evaluator_version=?""",(int(operation_id),VERSION)).fetchone()
    if not row:
        return None
    return unpack(row["payload_json"]) if row["status"]=="complete" else _snapshot(row["payload_json"])


def historical_comparison(db, report, *, limit=10):
    # This is an explicit audit request, never part of a web polling loop.
    rows=db.execute("""
        SELECT payload_json FROM operation_observation_numeric_evaluations
        WHERE symbol=? AND side=? AND time_horizon=? AND evaluator_version=?
          AND status='complete' AND closed_at<=? AND operation_id<>?
        ORDER BY closed_at DESC LIMIT ?
    """,(report["symbol"],report["side"],report["time_horizon"],VERSION,
          report["started_at"],int(report["operation_id"]),max(1,min(20,int(limit))))).fetchall()
    return compare_episodes(report,[unpack(row["payload_json"]) for row in rows])


def report_view(report, *, rule_id=None, stage=None, metric=None):
    if report.get("status")=="blocked":
        return report
    inventory={}
    for series in report["series"]:
        key=(series["stage"],series["rule_id"])
        item=inventory.setdefault(key,{"stage":key[0],"rule_id":key[1],"variables":0})
        item["variables"]+=1
    selected=[s for s in report["series"] if rule_id and s["rule_id"]==rule_id
              and (stage is None or s["stage"]==stage) and (metric is None or s["metric"]==metric)]
    selected_keys={s["key"] for s in selected}
    result = {"version":report["version"],"operation_id":report["operation_id"],
        "checkpoint_count":report["checkpoint_count"],"variable_series":len(report["series"]),
        "rule_inventory":list(inventory.values()),"series":selected,
        "joint_patterns":[p for p in report["joint_patterns"] if p["left"] in selected_keys or p["right"] in selected_keys],
        "semantics":report["semantics"],"availability":report["availability"]}
    def public(item):
        if isinstance(item, dict):
            return {k:public(v) for k,v in item.items() if not k.startswith("_")}
        return [public(v) for v in item] if isinstance(item,list) else item
    return public(result)
