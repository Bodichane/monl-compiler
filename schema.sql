-- Socle DB Déterministe généré automatiquement pour ContactManager

CREATE TABLE IF NOT EXISTS contact (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(255),
    address TEXT
);
