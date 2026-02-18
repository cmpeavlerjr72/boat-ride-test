-- Replace generic preset boats with real-world brand/model boats
-- Run AFTER 09_add_make_model.sql
--
-- Specs sourced from manufacturer websites and BoatTEST.
-- Scoring thresholds (max_safe_wind_kt, max_safe_wave_ft, comfort_bias) are
-- tuned per hull design, displacement, and intended use-case.

-- Remove old generic presets
DELETE FROM boat_profiles WHERE is_preset = true;

-- Insert real-world boat models
INSERT INTO boat_profiles
    (user_id, is_preset, make, model, name, boat_type,
     length_ft, beam_ft, draft_ft,
     max_safe_wind_kt, max_safe_wave_ft, comfort_bias)
VALUES
    -- ── Center Consoles ──────────────────────────────────────────────
    (NULL, true, 'Boston Whaler', '230 Outrage',
     'Boston Whaler 230 Outrage', 'center_console',
     23.0, 8.5, 1.5,
     28, 4.5, 0.1),

    (NULL, true, 'Contender', '25T',
     'Contender 25T', 'center_console',
     25.25, 8.5, 1.5,
     32, 5.5, 0.2),

    (NULL, true, 'Robalo', 'R242',
     'Robalo R242', 'center_console',
     24.5, 8.75, 1.7,
     28, 4.5, 0.0),

    -- ── Bay Boats ────────────────────────────────────────────────────
    (NULL, true, 'Pathfinder', '2500 HPS',
     'Pathfinder 2500 HPS', 'bay_boat',
     24.75, 8.5, 1.1,
     25, 3.5, 0.0),

    (NULL, true, 'Sportsman', 'Masters 227',
     'Sportsman Masters 227', 'bay_boat',
     22.4, 8.3, 1.2,
     22, 3.0, -0.1),

    (NULL, true, 'NauticStar', '2200XS Offshore',
     'NauticStar 2200XS Offshore', 'bay_boat',
     22.25, 8.5, 1.25,
     25, 3.5, 0.0),

    -- ── Pontoons ─────────────────────────────────────────────────────
    (NULL, true, 'Bennington', '22 SSX',
     'Bennington 22 SSX', 'pontoon',
     23.75, 8.5, 1.5,
     18, 2.0, -0.2),

    (NULL, true, 'Sun Tracker', 'Party Barge 22 DLX',
     'Sun Tracker Party Barge 22 DLX', 'pontoon',
     24.2, 8.5, 1.7,
     15, 1.5, -0.3),

    -- ── Wake Boats ───────────────────────────────────────────────────
    (NULL, true, 'MasterCraft', 'X24',
     'MasterCraft X24', 'wake_boat',
     24.2, 8.5, 2.5,
     18, 2.5, -0.2),

    (NULL, true, 'Malibu', 'Wakesetter 23 LSV',
     'Malibu Wakesetter 23 LSV', 'wake_boat',
     23.0, 8.5, 2.25,
     18, 2.5, -0.2),

    -- ── Cabin Cruisers ───────────────────────────────────────────────
    (NULL, true, 'Sea Ray', '290 Sundancer',
     'Sea Ray 290 Sundancer', 'cabin_cruiser',
     28.7, 9.0, 3.5,
     30, 5.0, 0.2),

    (NULL, true, 'Grady-White', 'Freedom 285',
     'Grady-White Freedom 285', 'cabin_cruiser',
     28.0, 9.5, 1.8,
     32, 5.5, 0.2),

    -- ── Skiff ────────────────────────────────────────────────────────
    (NULL, true, 'Hewes', 'Redfisher 18',
     'Hewes Redfisher 18', 'skiff',
     18.8, 7.9, 0.8,
     18, 2.0, -0.3),

    -- ── Sailboat ─────────────────────────────────────────────────────
    (NULL, true, 'Catalina', '315',
     'Catalina 315', 'sailboat',
     31.0, 11.6, 6.25,
     35, 7.0, 0.3),

    -- ── Kayak ────────────────────────────────────────────────────────
    (NULL, true, 'Hobie', 'Mirage Pro Angler 14',
     'Hobie Mirage Pro Angler 14', 'kayak',
     13.7, 3.2, 0.8,
     12, 1.5, -0.5)

ON CONFLICT DO NOTHING;
