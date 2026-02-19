CREATE TABLE IF NOT EXISTS repositories (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    owner         TEXT NOT NULL,
    name          TEXT NOT NULL,
    url           TEXT NOT NULL UNIQUE,
    description   TEXT,
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK(status IN ('pending','active','archived','deleted','error')),
    is_private    BOOLEAN NOT NULL DEFAULT 0,
    local_path    TEXT,
    last_cloned   TEXT,
    last_updated  TEXT,
    last_checked  TEXT,
    error_message TEXT,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(owner, name)
);

CREATE TABLE IF NOT EXISTS archives (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id        INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    filename       TEXT NOT NULL,
    file_path      TEXT NOT NULL,
    size_bytes     INTEGER NOT NULL,
    file_count     INTEGER NOT NULL,
    is_incremental BOOLEAN NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS file_hashes (
    repo_id    INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    file_path  TEXT NOT NULL,
    md5_hash   TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    PRIMARY KEY (repo_id, file_path)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
