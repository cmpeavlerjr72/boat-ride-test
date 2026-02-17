-- RPC function: nearby_reports
-- Finds non-expired reports within a radius (nautical miles) of a point.
-- Sandbars older than 3 months are marked as stale.
CREATE OR REPLACE FUNCTION nearby_reports(
    p_lat DOUBLE PRECISION,
    p_lon DOUBLE PRECISION,
    p_radius_nm DOUBLE PRECISION DEFAULT 5.0,
    p_types TEXT[] DEFAULT ARRAY['ride_quality', 'traffic', 'sandbar']
)
RETURNS TABLE (
    id UUID,
    user_id UUID,
    report_type TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    data JSONB,
    confirmation_count INTEGER,
    is_stale BOOLEAN,
    distance_nm DOUBLE PRECISION,
    created_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        r.id,
        r.user_id,
        r.report_type,
        r.lat,
        r.lon,
        r.data,
        r.confirmation_count,
        -- Sandbars older than 3 months are "stale"
        CASE
            WHEN r.report_type = 'sandbar' AND r.created_at < now() - INTERVAL '3 months'
            THEN true
            ELSE false
        END AS is_stale,
        -- Distance in nautical miles (1 degree ≈ 60 nm at equator, approximate)
        ST_Distance(
            r.location::geography,
            ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326)::geography
        ) / 1852.0 AS distance_nm,
        r.created_at,
        r.expires_at
    FROM crowdsource_reports r
    WHERE r.expires_at > now()
      AND r.report_type = ANY(p_types)
      AND ST_DWithin(
          r.location::geography,
          ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326)::geography,
          p_radius_nm * 1852.0  -- convert nm to meters
      )
    ORDER BY distance_nm ASC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- RPC function: create_report
-- Creates a report with automatic expiration based on type.
CREATE OR REPLACE FUNCTION create_report(
    p_user_id UUID,
    p_report_type TEXT,
    p_lat DOUBLE PRECISION,
    p_lon DOUBLE PRECISION,
    p_data JSONB DEFAULT '{}'::jsonb
)
RETURNS UUID AS $$
DECLARE
    v_expires_at TIMESTAMPTZ;
    v_id UUID;
BEGIN
    -- Set TTL based on report type
    IF p_report_type = 'sandbar' THEN
        v_expires_at := now() + INTERVAL '6 months';
    ELSE
        -- ride_quality, traffic
        v_expires_at := now() + INTERVAL '4 hours';
    END IF;

    INSERT INTO crowdsource_reports (user_id, report_type, location, lat, lon, data, expires_at)
    VALUES (
        p_user_id,
        p_report_type,
        ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326),
        p_lat,
        p_lon,
        p_data,
        v_expires_at
    )
    RETURNING crowdsource_reports.id INTO v_id;

    RETURN v_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- RPC function: confirm_report
-- Adds a confirmation (one per user per report) and increments the count.
CREATE OR REPLACE FUNCTION confirm_report(
    p_report_id UUID,
    p_user_id UUID
)
RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER;
BEGIN
    -- Insert confirmation (unique constraint prevents duplicates)
    INSERT INTO report_confirmations (report_id, user_id)
    VALUES (p_report_id, p_user_id)
    ON CONFLICT (report_id, user_id) DO NOTHING;

    -- Update confirmation count
    UPDATE crowdsource_reports
    SET confirmation_count = (
        SELECT COUNT(*) FROM report_confirmations WHERE report_id = p_report_id
    )
    WHERE id = p_report_id
    RETURNING crowdsource_reports.confirmation_count INTO v_count;

    RETURN COALESCE(v_count, 0);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
