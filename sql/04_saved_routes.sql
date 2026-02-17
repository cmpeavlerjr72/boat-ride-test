-- Saved routes
CREATE TABLE IF NOT EXISTS saved_routes (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT,
    route_points JSONB NOT NULL,  -- [{lat, lon, name?}, ...]
    region      TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_saved_routes_user ON saved_routes(user_id);

-- RLS: users see/modify only their own routes
ALTER TABLE saved_routes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own routes"
    ON saved_routes FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own routes"
    ON saved_routes FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own routes"
    ON saved_routes FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own routes"
    ON saved_routes FOR DELETE
    USING (auth.uid() = user_id);
