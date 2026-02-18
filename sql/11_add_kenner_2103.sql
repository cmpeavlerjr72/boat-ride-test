-- Add Kenner 2103 and Sea Pro 248 Bay presets
-- Run standalone — safe to run even if 10_seed already ran

INSERT INTO boat_profiles
    (user_id, is_preset, make, model, name, boat_type,
     length_ft, beam_ft, draft_ft,
     max_safe_wind_kt, max_safe_wave_ft, comfort_bias)
VALUES
    -- Kenner 2103: Louisiana modified-V bay boat, 1,890 lbs dry, ~14-16° deadrise
    (NULL, true, 'Kenner', '2103',
     'Kenner 2103', 'bay_boat',
     21.5, 7.9, 0.9,
     22, 2.5, -0.1),

    -- Sea Pro 248 Bay: modified-V bay/CC, 3,000 lbs dry, 15° deadrise
    (NULL, true, 'Sea Pro', '248 Bay',
     'Sea Pro 248 Bay', 'bay_boat',
     24.67, 8.75, 1.25,
     25, 3.5, 0.0)

ON CONFLICT DO NOTHING;
