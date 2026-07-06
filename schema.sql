-- Socle DB Déterministe généré automatiquement pour TodoApp

CREATE TABLE user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255),
    email VARCHAR(255)
);

CREATE TABLE todo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(255),
    completed BOOLEAN
);

-- Relation: User hasMany Todo
ALTER TABLE todo ADD COLUMN user_id INTEGER;
ALTER TABLE todo ADD CONSTRAINT fk_todo_user FOREIGN KEY (user_id) REFERENCES user(id);
