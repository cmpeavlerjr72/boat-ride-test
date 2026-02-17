-- Seed ~10 preset boat profiles (no user_id, is_preset = true)
INSERT INTO boat_profiles (user_id, is_preset, name, boat_type, length_ft, beam_ft, draft_ft, max_safe_wind_kt, max_safe_wave_ft, comfort_bias)
VALUES
    (NULL, true, '17ft Skiff',          'skiff',           17, 6.5,  0.8,  20, 2.5, -0.2),
    (NULL, true, '20ft Bay Boat',       'bay_boat',        20, 8.0,  1.0,  25, 3.5,  0.0),
    (NULL, true, '22ft Center Console', 'center_console',  22, 8.5,  1.5,  25, 4.0,  0.0),
    (NULL, true, '24ft Deck Boat',      'deck_boat',       24, 8.5,  1.5,  20, 3.0, -0.1),
    (NULL, true, '24ft Pontoon',        'pontoon',         24, 8.5,  1.5,  18, 2.5, -0.3),
    (NULL, true, '26ft Center Console', 'center_console',  26, 9.0,  1.8,  30, 5.0,  0.1),
    (NULL, true, '30ft Cabin Cruiser',  'cabin_cruiser',   30, 10.5, 2.5,  30, 5.0,  0.2),
    (NULL, true, '35ft Sailboat',       'sailboat',        35, 11.0, 5.5,  35, 6.0,  0.3),
    (NULL, true, '18ft Jet Boat',       'jet_boat',        18, 7.5,  1.0,  25, 3.0,  0.0),
    (NULL, true, 'Kayak / Paddleboard', 'kayak',           12, 2.5,  0.3,  12, 1.5, -0.5)
ON CONFLICT DO NOTHING;
