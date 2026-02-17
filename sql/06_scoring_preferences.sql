-- Scoring preferences: per-user sensitivity multipliers
CREATE TABLE IF NOT EXISTS scoring_preferences (
    user_id         UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    wind_multiplier   DOUBLE PRECISION DEFAULT 1.0 CHECK (wind_multiplier BETWEEN 0.2 AND 3.0),
    wave_multiplier   DOUBLE PRECISION DEFAULT 1.0 CHECK (wave_multiplier BETWEEN 0.2 AND 3.0),
    period_multiplier DOUBLE PRECISION DEFAULT 1.0 CHECK (period_multiplier BETWEEN 0.2 AND 3.0),
    chop_multiplier   DOUBLE PRECISION DEFAULT 1.0 CHECK (chop_multiplier BETWEEN 0.2 AND 3.0),
    precip_multiplier DOUBLE PRECISION DEFAULT 1.0 CHECK (precip_multiplier BETWEEN 0.2 AND 3.0),
    tide_multiplier   DOUBLE PRECISION DEFAULT 1.0 CHECK (tide_multiplier BETWEEN 0.2 AND 3.0),
    overall_offset    DOUBLE PRECISION DEFAULT 0.0 CHECK (overall_offset BETWEEN -20 AND 20),
    updated_at        TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE scoring_preferences ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own preferences"
    ON scoring_preferences FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can upsert own preferences"
    ON scoring_preferences FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own preferences"
    ON scoring_preferences FOR UPDATE
    USING (auth.uid() = user_id);


-- Scoring feedback: historical ratings for nudge algorithm
CREATE TABLE IF NOT EXISTS scoring_feedback (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    lat                 DOUBLE PRECISION NOT NULL,
    lon                 DOUBLE PRECISION NOT NULL,
    feedback_time       TIMESTAMPTZ DEFAULT now(),
    original_score      DOUBLE PRECISION NOT NULL,
    user_rating         INTEGER NOT NULL CHECK (user_rating BETWEEN 1 AND 5),
    conditions_snapshot JSONB,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scoring_feedback_user ON scoring_feedback(user_id);

ALTER TABLE scoring_feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own feedback"
    ON scoring_feedback FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own feedback"
    ON scoring_feedback FOR INSERT
    WITH CHECK (auth.uid() = user_id);
