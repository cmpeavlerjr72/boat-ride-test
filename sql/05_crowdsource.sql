-- Crowdsource reports (Waze-like)
CREATE TABLE IF NOT EXISTS crowdsource_reports (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    report_type         TEXT NOT NULL CHECK (report_type IN ('ride_quality', 'traffic', 'sandbar')),
    location            GEOMETRY(POINT, 4326) NOT NULL,
    lat                 DOUBLE PRECISION NOT NULL,
    lon                 DOUBLE PRECISION NOT NULL,
    data                JSONB DEFAULT '{}'::jsonb,
    confirmation_count  INTEGER DEFAULT 0,
    expires_at          TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- Spatial index for nearby queries
CREATE INDEX IF NOT EXISTS idx_crowdsource_reports_location
    ON crowdsource_reports USING GIST (location);

CREATE INDEX IF NOT EXISTS idx_crowdsource_reports_expires
    ON crowdsource_reports (expires_at);

CREATE INDEX IF NOT EXISTS idx_crowdsource_reports_user
    ON crowdsource_reports (user_id);

-- RLS
ALTER TABLE crowdsource_reports ENABLE ROW LEVEL SECURITY;

-- All authenticated users can read non-expired reports
CREATE POLICY "Authenticated users can view non-expired reports"
    ON crowdsource_reports FOR SELECT
    USING (auth.uid() IS NOT NULL AND expires_at > now());

CREATE POLICY "Users can insert reports"
    ON crowdsource_reports FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own reports"
    ON crowdsource_reports FOR DELETE
    USING (auth.uid() = user_id);


-- Report confirmations (one per user per report)
CREATE TABLE IF NOT EXISTS report_confirmations (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id   UUID NOT NULL REFERENCES crowdsource_reports(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE(report_id, user_id)
);

ALTER TABLE report_confirmations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can view confirmations"
    ON report_confirmations FOR SELECT
    USING (auth.uid() IS NOT NULL);

CREATE POLICY "Users can insert confirmations"
    ON report_confirmations FOR INSERT
    WITH CHECK (auth.uid() = user_id);
