-- Add make/model columns to boat_profiles for real-world boat identification
-- Also add 'wake_boat' to the boat_type CHECK constraint

ALTER TABLE boat_profiles
    ADD COLUMN IF NOT EXISTS make  TEXT,
    ADD COLUMN IF NOT EXISTS model TEXT;

-- Update the boat_type CHECK constraint to include 'wake_boat'
ALTER TABLE boat_profiles DROP CONSTRAINT IF EXISTS boat_profiles_boat_type_check;
ALTER TABLE boat_profiles ADD CONSTRAINT boat_profiles_boat_type_check
    CHECK (boat_type IN (
        'center_console', 'bay_boat', 'pontoon', 'deck_boat',
        'cabin_cruiser', 'sailboat', 'skiff', 'jet_boat',
        'kayak', 'wake_boat', 'other'
    ));
