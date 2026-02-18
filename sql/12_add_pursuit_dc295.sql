-- Add Pursuit DC 295 preset
-- Premium offshore dual console, 9,700 lbs w/ twins, 21° deep-V deadrise

INSERT INTO boat_profiles
    (user_id, is_preset, make, model, name, boat_type,
     length_ft, beam_ft, draft_ft,
     max_safe_wind_kt, max_safe_wave_ft, comfort_bias)
VALUES
    (NULL, true, 'Pursuit', 'DC 295',
     'Pursuit DC 295', 'cabin_cruiser',
     31.75, 9.83, 1.83,
     32, 5.5, 0.2)
ON CONFLICT DO NOTHING;
