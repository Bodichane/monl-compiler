-- Socle DB Déterministe généré automatiquement pour AnonForum

CREATE TABLE IF NOT EXISTS _monlang_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    salt VARCHAR(255) NOT NULL,
    actor VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS _monlang_revoked_tokens (
    jti VARCHAR(64) PRIMARY KEY,
    revoked_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS "post" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    "content" TEXT,
    "author" VARCHAR(255)
);
