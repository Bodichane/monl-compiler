-- Socle DB Déterministe généré automatiquement pour TodoApp

CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255),
    email VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS todo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(255),
    completed BOOLEAN,
    user_id INTEGER,
    FOREIGN KEY (user_id) REFERENCES user(id)
);
