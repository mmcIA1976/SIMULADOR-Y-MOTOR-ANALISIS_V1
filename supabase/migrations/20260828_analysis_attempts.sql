CREATE TABLE IF NOT EXISTS analysis_attempts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recommendation_id BIGINT REFERENCES recommendations(id) ON DELETE SET NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('long', 'short')),
    time_horizon TEXT NOT NULL,
    entry_type TEXT NOT NULL CHECK(entry_type IN ('market', 'pending')),
    outcome TEXT NOT NULL CHECK(outcome IN ('completed', 'blocked', 'failed')),
    error_code TEXT,
    engine_version TEXT NOT NULL,
    duration_ms INTEGER NOT NULL CHECK(duration_ms >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_analysis_attempts_user_time
    ON analysis_attempts(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_analysis_attempts_outcome_time
    ON analysis_attempts(outcome, created_at);

ALTER TABLE analysis_attempts ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE analysis_attempts FROM anon, authenticated;
