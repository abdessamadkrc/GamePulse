-- GamePulse schema (SYNTHETIC portfolio data - not affiliated with Garena or Free Fire)
-- Raw operational tables. Derived analytics tables live in 02_derived.sql.

CREATE TABLE IF NOT EXISTS devices (
    device       TEXT PRIMARY KEY,
    platform     TEXT NOT NULL,
    device_tier  TEXT NOT NULL CHECK (device_tier IN ('low', 'mid', 'high'))
);

CREATE TABLE IF NOT EXISTS players (
    player_id           INTEGER PRIMARY KEY,
    country             TEXT NOT NULL,
    platform            TEXT NOT NULL,
    device              TEXT NOT NULL REFERENCES devices (device),
    install_date        DATE NOT NULL,
    acquisition_source  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id                BIGINT PRIMARY KEY,
    player_id                 INTEGER NOT NULL REFERENCES players (player_id),
    session_start             TIMESTAMP NOT NULL,
    session_duration_minutes  NUMERIC(6, 1) NOT NULL
);

CREATE TABLE IF NOT EXISTS matches (
    match_id               BIGINT PRIMARY KEY,
    player_id              INTEGER NOT NULL REFERENCES players (player_id),
    match_date             TIMESTAMP NOT NULL,
    game_mode              TEXT NOT NULL,
    kills                  SMALLINT NOT NULL,
    placement              SMALLINT NOT NULL,
    match_duration_minutes NUMERIC(5, 1) NOT NULL,
    result                 TEXT NOT NULL CHECK (result IN ('win', 'loss'))
);

CREATE TABLE IF NOT EXISTS purchases (
    purchase_id    BIGINT PRIMARY KEY,
    player_id      INTEGER NOT NULL REFERENCES players (player_id),
    purchase_date  TIMESTAMP NOT NULL,
    amount         NUMERIC(8, 2) NOT NULL,   -- synthetic USD
    item_type      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id    BIGINT PRIMARY KEY,
    player_id   INTEGER NOT NULL REFERENCES players (player_id),
    event_name  TEXT NOT NULL,
    event_date  TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS experiment_catalog (
    experiment_id  TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT NOT NULL,
    hypothesis     TEXT NOT NULL,
    primary_kpi    TEXT NOT NULL,
    control_label  TEXT NOT NULL,
    test_label     TEXT NOT NULL,
    start_date     DATE NOT NULL,
    end_date       DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id    TEXT NOT NULL REFERENCES experiment_catalog (experiment_id),
    player_id        INTEGER NOT NULL REFERENCES players (player_id),
    variant          TEXT NOT NULL CHECK (variant IN ('control', 'test')),
    assignment_date  DATE NOT NULL,
    PRIMARY KEY (experiment_id, player_id)
);

CREATE TABLE IF NOT EXISTS meta_info (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
