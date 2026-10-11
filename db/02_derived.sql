-- Derived analytics layer. Run after raw data is loaded (see backend/seed/generate.py).
-- Dollar-prefixed placeholders (HV_REVENUE etc.) are substituted from app/segment_rules.py so the
-- segmentation thresholds documented in the UI are the exact ones executed here.

-- ---------------------------------------------------------------- indexes
CREATE INDEX IF NOT EXISTS ix_sessions_player  ON sessions  (player_id, session_start);
CREATE INDEX IF NOT EXISTS ix_matches_player   ON matches   (player_id, match_date);
CREATE INDEX IF NOT EXISTS ix_purchases_player ON purchases (player_id, purchase_date);
CREATE INDEX IF NOT EXISTS ix_events_player    ON events    (player_id, event_date);
CREATE INDEX IF NOT EXISTS ix_events_name      ON events    (event_name);
CREATE INDEX IF NOT EXISTS ix_players_install  ON players   (install_date);

DROP TABLE IF EXISTS player_base;
DROP TABLE IF EXISTS player_daily_mode;
DROP TABLE IF EXISTS player_daily_activity;

-- ---------------------------------------------------------------- one row per player per active day
CREATE TABLE player_daily_activity AS
WITH s AS (
    SELECT player_id, session_start::date AS activity_date,
           COUNT(*) AS sessions, SUM(session_duration_minutes) AS minutes
    FROM sessions GROUP BY 1, 2
), m AS (
    SELECT player_id, match_date::date AS activity_date, COUNT(*) AS matches
    FROM matches GROUP BY 1, 2
), r AS (
    SELECT player_id, purchase_date::date AS activity_date,
           SUM(amount) AS revenue, COUNT(*) AS purchases
    FROM purchases GROUP BY 1, 2
)
SELECT player_id, activity_date,
       COALESCE(s.sessions, 0)::int   AS sessions,
       COALESCE(s.minutes, 0)::float8 AS minutes,
       COALESCE(m.matches, 0)::int    AS matches,
       COALESCE(r.revenue, 0)::float8 AS revenue,
       COALESCE(r.purchases, 0)::int  AS purchases
FROM s
FULL JOIN m USING (player_id, activity_date)
FULL JOIN r USING (player_id, activity_date);

ALTER TABLE player_daily_activity ADD PRIMARY KEY (player_id, activity_date);
CREATE INDEX ix_pda_date ON player_daily_activity (activity_date);

-- ---------------------------------------------------------------- one row per player/day/mode
CREATE TABLE player_daily_mode AS
SELECT player_id, match_date::date AS activity_date, game_mode,
       COUNT(*)::int AS matches,
       SUM((result = 'win')::int)::int AS wins,
       SUM(kills)::int AS kills,
       SUM(match_duration_minutes)::float8 AS minutes
FROM matches GROUP BY 1, 2, 3;
CREATE INDEX ix_pdm_player ON player_daily_mode (player_id, game_mode);
CREATE INDEX ix_pdm_mode_date ON player_daily_mode (game_mode, activity_date);

-- ---------------------------------------------------------------- one row per player (denormalised)
CREATE TABLE player_base AS
WITH bounds AS (
    SELECT value::date AS max_date FROM meta_info WHERE key = 'max_date'
), act AS (
    SELECT a.player_id, a.activity_date, a.sessions, a.minutes, a.matches, a.revenue,
           (a.activity_date - p.install_date) AS day_n
    FROM player_daily_activity a JOIN players p USING (player_id)
), agg AS (
    SELECT player_id,
        SUM(sessions) AS sessions_total,
        SUM(minutes) AS minutes_total,
        SUM(matches) AS matches_total,
        SUM(revenue) AS revenue_total,
        COUNT(*) FILTER (WHERE sessions > 0) AS active_days_total,
        MAX(activity_date) FILTER (WHERE sessions > 0) AS last_session_date,
        SUM(sessions) FILTER (WHERE day_n <= 6)  AS sessions_7d,
        SUM(minutes)  FILTER (WHERE day_n <= 6)  AS minutes_7d,
        SUM(matches)  FILTER (WHERE day_n <= 6)  AS matches_7d,
        SUM(revenue)  FILTER (WHERE day_n <= 13) AS revenue_14d,
        SUM(sessions) FILTER (WHERE activity_date > (SELECT max_date FROM bounds) - 30) AS sessions_30d,
        SUM(minutes)  FILTER (WHERE activity_date > (SELECT max_date FROM bounds) - 30) AS minutes_30d,
        SUM(matches)  FILTER (WHERE activity_date > (SELECT max_date FROM bounds) - 30) AS matches_30d,
        COUNT(*) FILTER (WHERE sessions > 0 AND activity_date > (SELECT max_date FROM bounds) - 14) AS active_days_14d,
        BOOL_OR(day_n = 1 AND sessions > 0) AS ret1,
        BOOL_OR(day_n = 7 AND sessions > 0) AS ret7,
        BOOL_OR(day_n = 30 AND sessions > 0) AS ret30,
        BOOL_OR(day_n BETWEEN 8 AND 14 AND sessions > 0) AS ret_8_14
    FROM act GROUP BY player_id
), first_mode AS (
    SELECT DISTINCT ON (player_id) player_id, game_mode AS first_game_mode
    FROM matches ORDER BY player_id, match_date
), early_matches AS (
    SELECT player_id,
           AVG(placement)::float8 AS first5_avg_placement,
           AVG((result = 'win')::int)::float8 AS first5_win_rate,
           AVG(kills)::float8 AS first5_avg_kills
    FROM (SELECT player_id, placement, result, kills,
                 ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY match_date) AS rn
          FROM matches) x
    WHERE rn <= 5 GROUP BY player_id
), ev AS (
    SELECT e.player_id,
        BOOL_OR(e.event_name = 'tutorial_complete') AS tutorial_completed,
        COUNT(*) FILTER (WHERE e.event_name = 'crash'
                         AND e.event_date::date - p.install_date <= 6) AS crashes_7d,
        COUNT(*) FILTER (WHERE e.event_name = 'crash') AS crashes_total
    FROM events e JOIN players p USING (player_id)
    GROUP BY e.player_id
), joined AS (
    SELECT p.player_id, p.country, p.platform, p.device, d.device_tier, p.install_date,
           p.acquisition_source,
           (SELECT max_date FROM bounds) - p.install_date AS days_since_install,
           (SELECT max_date FROM bounds) - a.last_session_date AS days_since_last_session,
           a.sessions_total, a.minutes_total, a.matches_total, a.revenue_total, a.active_days_total,
           a.last_session_date, a.sessions_7d, a.minutes_7d, a.matches_7d, a.revenue_14d,
           a.sessions_30d, a.minutes_30d, a.matches_30d, a.active_days_14d,
           a.ret1, a.ret7, a.ret30, a.ret_8_14,
           fm.first_game_mode, em.first5_avg_placement, em.first5_win_rate, em.first5_avg_kills,
           COALESCE(ev.tutorial_completed, FALSE) AS tutorial_completed,
           COALESCE(ev.crashes_7d, 0) AS crashes_7d,
           COALESCE(ev.crashes_total, 0) AS crashes_total
    FROM players p
    JOIN devices d USING (device)
    JOIN agg a USING (player_id)
    LEFT JOIN first_mode fm USING (player_id)
    LEFT JOIN early_matches em USING (player_id)
    LEFT JOIN ev USING (player_id)
)
SELECT
    j.player_id, j.country, j.platform, j.device, j.device_tier, j.install_date, j.acquisition_source,
    j.days_since_install, j.days_since_last_session, j.last_session_date,
    j.sessions_total::int, j.minutes_total::float8, COALESCE(j.matches_total, 0)::int AS matches_total,
    COALESCE(j.revenue_total, 0)::float8 AS revenue_total, j.active_days_total::int,
    COALESCE(j.sessions_7d, 0)::int AS sessions_7d, COALESCE(j.minutes_7d, 0)::float8 AS minutes_7d,
    COALESCE(j.matches_7d, 0)::int AS matches_7d, COALESCE(j.revenue_14d, 0)::float8 AS revenue_14d,
    COALESCE(j.sessions_30d, 0)::int AS sessions_30d, COALESCE(j.minutes_30d, 0)::float8 AS minutes_30d,
    COALESCE(j.matches_30d, 0)::int AS matches_30d, j.active_days_14d::int,
    -- retention flags: NULL when the player has not yet had the chance to reach day N
    CASE WHEN j.days_since_install >= 1  THEN COALESCE(j.ret1, FALSE)::int  END AS d1,
    CASE WHEN j.days_since_install >= 7  THEN COALESCE(j.ret7, FALSE)::int  END AS d7,
    CASE WHEN j.days_since_install >= 30 THEN COALESCE(j.ret30, FALSE)::int END AS d30,
    CASE WHEN j.days_since_install >= 14 THEN (NOT COALESCE(j.ret_8_14, FALSE))::int END AS early_churn,
    j.first_game_mode, j.first5_avg_placement, j.first5_win_rate, j.first5_avg_kills,
    j.tutorial_completed::int AS tutorial_completed, j.crashes_7d::int, j.crashes_total::int,
    (j.crashes_7d > 0)::int AS crashed_7d,
    -- rule-based lifecycle segment (priority order matters)
    CASE
        WHEN j.days_since_install <= $NEW_DAYS                    THEN 'New Players'
        WHEN j.days_since_last_session >= $CHURN_DAYS             THEN 'Churned Players'
        WHEN j.days_since_last_session >= $RISK_DAYS              THEN 'At-Risk Players'
        WHEN COALESCE(j.revenue_total, 0) >= $HV_REVENUE          THEN 'High-Value Players'
        WHEN j.active_days_14d >= $ENGAGED_ACTIVE_DAYS_14D        THEN 'Engaged Players'
        ELSE 'Casual Players'
    END AS segment
FROM joined j;

ALTER TABLE player_base ADD PRIMARY KEY (player_id);
CREATE INDEX ix_pb_install ON player_base (install_date);
CREATE INDEX ix_pb_country ON player_base (country);
CREATE INDEX ix_pb_segment ON player_base (segment);
CREATE INDEX ix_pb_source  ON player_base (acquisition_source);

ANALYZE;
