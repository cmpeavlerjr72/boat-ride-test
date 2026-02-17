-- Boat profiles: user-owned boats + system presets
CREATE TABLE IF NOT EXISTS boat_profiles (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    is_preset       BOOLEAN DEFAULT false,
    name            TEXT NOT NULL,
    boat_type       TEXT CHECK (boat_type IN (
        'center_console', 'bay_boat', 'pontoon', 'deck_boat',
        'cabin_cruiser', 'sailboat', 'skiff', 'jet_boat', 'kayak', 'other'
    )) DEFAULT 'other',
    length_ft       DOUBLE PRECISION,
    beam_ft         DOUBLE PRECISION,
    draft_ft        DOUBLE PRECISION,
    max_safe_wind_kt DOUBLE PRECISION DEFAULT 25,
    max_safe_wave_ft DOUBLE PRECISION DEFAULT 4.0,
    comfort_bias    DOUBLE PRECISION DEFAULT 0.0,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- RLS: users see own boats + all presets; can only modify their own non-preset boats
ALTER TABLE boat_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own boats and presets"
    ON boat_profiles FOR SELECT
    USING (is_preset = true OR auth.uid() = user_id);

CREATE POLICY "Users can insert own boats"
    ON boat_profiles FOR INSERT
    WITH CHECK (auth.uid() = user_id AND is_preset = false);

CREATE POLICY "Users can update own non-preset boats"
    ON boat_profiles FOR UPDATE
    USING (auth.uid() = user_id AND is_preset = false);

CREATE POLICY "Users can delete own non-preset boats"
    ON boat_profiles FOR DELETE
    USING (auth.uid() = user_id AND is_preset = false);
