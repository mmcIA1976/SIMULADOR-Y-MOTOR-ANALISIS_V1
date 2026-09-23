-- Shared, bounded Binance REST quota and IP-wide backoff. One row only.
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';
CREATE TABLE IF NOT EXISTS public.binance_request_budget (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    minute BIGINT NOT NULL DEFAULT -1,
    weight INTEGER NOT NULL DEFAULT 0,
    requests INTEGER NOT NULL DEFAULT 0,
    observed INTEGER NOT NULL DEFAULT 0,
    blocked_until DOUBLE PRECISION NOT NULL DEFAULT 0,
    reason VARCHAR(120) NOT NULL DEFAULT ''
);
INSERT INTO public.binance_request_budget(id) VALUES (1)
ON CONFLICT (id) DO NOTHING;
ALTER TABLE public.binance_request_budget ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.binance_request_budget FROM PUBLIC, anon, authenticated;
GRANT SELECT, UPDATE ON public.binance_request_budget TO service_role;
COMMIT;
