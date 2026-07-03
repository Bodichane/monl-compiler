-- Base de données générée automatiquement pour TechBlog

CREATE TABLE user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(255),
    email VARCHAR(255),
    role VARCHAR(255)
);

CREATE TABLE post (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(255),
    slug VARCHAR(255),
    content TEXT,
    publishedAt TIMESTAMP
);

CREATE TABLE comment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT,
    createdAt TIMESTAMP
);

-- Relation: User hasMany Post
ALTER TABLE post ADD COLUMN user_id INTEGER;
<!-- FOREIGN KEY (user_id) REFERENCES user(id) -->;

-- Relation: Post hasMany Comment
ALTER TABLE comment ADD COLUMN post_id INTEGER;
<!-- FOREIGN KEY (post_id) REFERENCES post(id) -->;

-- Relation: User hasMany Comment
ALTER TABLE comment ADD COLUMN user_id INTEGER;
<!-- FOREIGN KEY (user_id) REFERENCES user(id) -->;
