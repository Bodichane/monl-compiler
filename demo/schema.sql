-- Socle DB Déterministe généré automatiquement pour AtelierVelo

CREATE TABLE IF NOT EXISTS _monl_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    salt VARCHAR(255) NOT NULL,
    actor VARCHAR(255) NOT NULL,
    anon_handle VARCHAR(255) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS _monl_revoked_tokens (
    jti VARCHAR(64) PRIMARY KEY,
    revoked_at TIMESTAMP NOT NULL,
    expires_at REAL
);

CREATE TABLE IF NOT EXISTS _monl_rate_limit (
    bucket VARCHAR(32) NOT NULL,
    client_ip VARCHAR(64) NOT NULL,
    attempted_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate_limit_lookup ON _monl_rate_limit (bucket, client_ip, attempted_at);

CREATE TABLE IF NOT EXISTS "product" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    "name" VARCHAR(255),
    "price" NUMERIC(10, 2),
    "description" TEXT,
    "imageUrl" VARCHAR(255),
    "category" VARCHAR(255),
    "stock" INTEGER
);

CREATE TABLE IF NOT EXISTS "order" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    "total" NUMERIC(10, 2),
    "status" VARCHAR(255),
    "note" TEXT,
    "customer_id" INTEGER,
    FOREIGN KEY ("customer_id") REFERENCES _monl_users(id)
);

CREATE TABLE IF NOT EXISTS "customer" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    "displayName" VARCHAR(255)
);
