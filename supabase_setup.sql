-- ==========================================
-- CRYPTOBOT ULTIMATE - SUPABASE SCHEMA
-- ==========================================
-- Tables pour stocker toutes les données du bot
-- Analytics avancées, ML training, monitoring
-- ==========================================

-- Enable Row Level Security
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO postgres, anon, authenticated, service_role;

-- ==========================================
-- TABLE: trades
-- Tous les trades (entry + exit)
-- ==========================================
CREATE TABLE IF NOT EXISTS trades (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol VARCHAR(20) NOT NULL,
    action VARCHAR(10) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    amount DECIMAL(20, 8),
    signal_score DECIMAL(5, 2),
    signal_type VARCHAR(50),
    indicators JSONB,
    pnl_percent DECIMAL(10, 4),
    exit_reason VARCHAR(100),
    hold_time_minutes DECIMAL(10, 2),
    status VARCHAR(20)
);

-- Indexes pour trades
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_pnl ON trades(pnl_percent DESC);

-- ==========================================
-- TABLE: signals
-- Tous les signaux détectés (tradés ou non)
-- ==========================================
CREATE TABLE IF NOT EXISTS signals (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol VARCHAR(20) NOT NULL,
    signal_type VARCHAR(50) NOT NULL,
    score DECIMAL(5, 2) NOT NULL,
    indicators JSONB NOT NULL,
    action_taken VARCHAR(50) NOT NULL
);

-- Indexes pour signals
CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_score ON signals(score DESC);
CREATE INDEX IF NOT EXISTS idx_signals_action ON signals(action_taken);

-- ==========================================
-- TABLE: metrics
-- Métriques globales du bot (snapshots réguliers)
-- ==========================================
CREATE TABLE IF NOT EXISTS metrics (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    win_rate DECIMAL(5, 2) NOT NULL,
    total_trades INT NOT NULL,
    capital DECIMAL(20, 2) NOT NULL,
    daily_pnl DECIMAL(20, 2),
    active_positions INT,
    avg_win DECIMAL(10, 4),
    avg_loss DECIMAL(10, 4)
);

-- Index pour metrics
CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp DESC);

-- ==========================================
-- TABLE: events
-- Événements système (erreurs, alertes, optimisations)
-- ==========================================
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    data JSONB
);

-- Indexes pour events
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);

-- ==========================================
-- TABLE: parameters
-- Historique des changements de paramètres
-- ==========================================
CREATE TABLE IF NOT EXISTS parameters (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    parameter_name VARCHAR(50) NOT NULL,
    old_value TEXT,
    new_value TEXT NOT NULL,
    reason TEXT,
    applied_by VARCHAR(50)
);

-- Indexes pour parameters
CREATE INDEX IF NOT EXISTS idx_parameters_timestamp ON parameters(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_parameters_name ON parameters(parameter_name);

-- ==========================================
-- INDEXES SUPPLÉMENTAIRES pour PERFORMANCE
-- ==========================================
CREATE INDEX IF NOT EXISTS idx_trades_pnl_symbol ON trades(pnl_percent, symbol) WHERE pnl_percent IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_trades_timestamp_exit ON trades(timestamp DESC) WHERE action = 'exit';
CREATE INDEX IF NOT EXISTS idx_signals_score_action ON signals(score DESC, action_taken);

-- ==========================================
-- VIEWS: Analytics prêtes à l'emploi
-- ==========================================

-- Vue: Performance par symbole
CREATE OR REPLACE VIEW v_performance_by_symbol AS
SELECT 
    symbol,
    COUNT(*) as total_trades,
    COUNT(*) FILTER (WHERE pnl_percent > 0) as wins,
    COUNT(*) FILTER (WHERE pnl_percent <= 0) as losses,
    ROUND(100.0 * COUNT(*) FILTER (WHERE pnl_percent > 0) / NULLIF(COUNT(*), 0), 2) as win_rate,
    ROUND(AVG(pnl_percent), 4) as avg_pnl,
    ROUND(SUM(pnl_percent), 4) as total_pnl,
    ROUND(AVG(CASE WHEN pnl_percent > 0 THEN pnl_percent END), 4) as avg_win,
    ROUND(AVG(CASE WHEN pnl_percent <= 0 THEN pnl_percent END), 4) as avg_loss
FROM trades
WHERE action = 'exit' AND pnl_percent IS NOT NULL
GROUP BY symbol
ORDER BY total_pnl DESC;

-- Vue: Performance par type de signal
CREATE OR REPLACE VIEW v_performance_by_signal_type AS
SELECT 
    signal_type,
    COUNT(*) as total_trades,
    COUNT(*) FILTER (WHERE pnl_percent > 0) as wins,
    ROUND(100.0 * COUNT(*) FILTER (WHERE pnl_percent > 0) / NULLIF(COUNT(*), 0), 2) as win_rate,
    ROUND(AVG(pnl_percent), 4) as avg_pnl
FROM trades
WHERE action = 'exit' AND pnl_percent IS NOT NULL
GROUP BY signal_type
ORDER BY avg_pnl DESC;

-- Vue: Performance par heure (UTC)
CREATE OR REPLACE VIEW v_performance_by_hour AS
SELECT 
    EXTRACT(HOUR FROM timestamp) as hour_utc,
    COUNT(*) as total_trades,
    COUNT(*) FILTER (WHERE pnl_percent > 0) as wins,
    ROUND(100.0 * COUNT(*) FILTER (WHERE pnl_percent > 0) / NULLIF(COUNT(*), 0), 2) as win_rate,
    ROUND(AVG(pnl_percent), 4) as avg_pnl
FROM trades
WHERE action = 'exit' AND pnl_percent IS NOT NULL
GROUP BY EXTRACT(HOUR FROM timestamp)
ORDER BY avg_pnl DESC;

-- Vue: Métriques récentes (dernières 24h)
CREATE OR REPLACE VIEW v_recent_metrics AS
SELECT *
FROM metrics
WHERE timestamp >= NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC;

-- Vue: Alertes critiques récentes
CREATE OR REPLACE VIEW v_recent_critical_events AS
SELECT *
FROM events
WHERE severity = 'critical'
    AND timestamp >= NOW() - INTERVAL '7 days'
ORDER BY timestamp DESC;

-- ==========================================
-- FUNCTIONS: Analytics avancées
-- ==========================================

-- Function: Calculer win rate sur période
CREATE OR REPLACE FUNCTION get_win_rate(days_back INT DEFAULT 7)
RETURNS DECIMAL AS $$
    SELECT ROUND(
        100.0 * COUNT(*) FILTER (WHERE pnl_percent > 0) / 
        NULLIF(COUNT(*), 0),
        2
    )
    FROM trades
    WHERE action = 'exit'
        AND pnl_percent IS NOT NULL
        AND timestamp >= NOW() - (days_back || ' days')::INTERVAL;
$$ LANGUAGE SQL;

-- Function: Calculer Sharpe ratio
CREATE OR REPLACE FUNCTION get_sharpe_ratio(days_back INT DEFAULT 30)
RETURNS DECIMAL AS $$
    WITH daily_returns AS (
        SELECT 
            DATE(timestamp) as date,
            SUM(pnl_percent) as daily_pnl
        FROM trades
        WHERE action = 'exit'
            AND pnl_percent IS NOT NULL
            AND timestamp >= NOW() - (days_back || ' days')::INTERVAL
        GROUP BY DATE(timestamp)
    )
    SELECT ROUND(
        AVG(daily_pnl) / NULLIF(STDDEV(daily_pnl), 0),
        4
    )
    FROM daily_returns;
$$ LANGUAGE SQL;

-- Function: Meilleurs symboles
CREATE OR REPLACE FUNCTION get_top_symbols(limit_count INT DEFAULT 10)
RETURNS TABLE(
    symbol VARCHAR,
    total_trades BIGINT,
    win_rate DECIMAL,
    total_pnl DECIMAL
) AS $$
    SELECT 
        t.symbol,
        COUNT(*) as total_trades,
        ROUND(100.0 * COUNT(*) FILTER (WHERE t.pnl_percent > 0) / NULLIF(COUNT(*), 0), 2) as win_rate,
        ROUND(SUM(t.pnl_percent), 4) as total_pnl
    FROM trades t
    WHERE t.action = 'exit' AND t.pnl_percent IS NOT NULL
    GROUP BY t.symbol
    HAVING COUNT(*) >= 5
    ORDER BY total_pnl DESC
    LIMIT limit_count;
$$ LANGUAGE SQL;

-- ==========================================
-- TRIGGERS: Notifications automatiques
-- ==========================================

-- Function pour trigger
CREATE OR REPLACE FUNCTION notify_large_loss()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.action = 'exit' AND NEW.pnl_percent < -10 THEN
        INSERT INTO events (event_type, severity, message, data)
        VALUES (
            'large_loss',
            'critical',
            'Large loss detected: ' || NEW.symbol || ' ' || NEW.pnl_percent || '%',
            jsonb_build_object(
                'symbol', NEW.symbol,
                'pnl', NEW.pnl_percent,
                'exit_reason', NEW.exit_reason
            )
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop trigger if exists then create
DROP TRIGGER IF EXISTS trigger_large_loss ON trades;
CREATE TRIGGER trigger_large_loss
AFTER INSERT ON trades
FOR EACH ROW
EXECUTE FUNCTION notify_large_loss();

-- ==========================================
-- RLS (Row Level Security)
-- ==========================================

ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE parameters ENABLE ROW LEVEL SECURITY;

-- Policies pour lecture
DROP POLICY IF EXISTS "Allow read access" ON trades;
DROP POLICY IF EXISTS "Allow read access" ON signals;
DROP POLICY IF EXISTS "Allow read access" ON metrics;
DROP POLICY IF EXISTS "Allow read access" ON events;
DROP POLICY IF EXISTS "Allow read access" ON parameters;

CREATE POLICY "Allow read access" ON trades FOR SELECT USING (true);
CREATE POLICY "Allow read access" ON signals FOR SELECT USING (true);
CREATE POLICY "Allow read access" ON metrics FOR SELECT USING (true);
CREATE POLICY "Allow read access" ON events FOR SELECT USING (true);
CREATE POLICY "Allow read access" ON parameters FOR SELECT USING (true);

-- Policies pour écriture
DROP POLICY IF EXISTS "Allow insert access" ON trades;
DROP POLICY IF EXISTS "Allow insert access" ON signals;
DROP POLICY IF EXISTS "Allow insert access" ON metrics;
DROP POLICY IF EXISTS "Allow insert access" ON events;
DROP POLICY IF EXISTS "Allow insert access" ON parameters;

CREATE POLICY "Allow insert access" ON trades FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow insert access" ON signals FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow insert access" ON metrics FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow insert access" ON events FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow insert access" ON parameters FOR INSERT WITH CHECK (true);

-- ==========================================
-- SUCCESS MESSAGE
-- ==========================================
-- Si vous voyez ce message, le schema a été créé avec succès!
-- Tables créées: trades, signals, metrics, events, parameters
-- Views créées: v_performance_by_symbol, v_performance_by_signal_type, etc.
-- Functions créées: get_win_rate, get_sharpe_ratio, get_top_symbols
