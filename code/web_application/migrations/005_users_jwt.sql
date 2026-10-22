-- Additive HW7 migration. The Python runner checks each DDL step before applying
-- it, because MySQL commits DDL implicitly. Existing identities/hashes survive.
ALTER TABLE users ADD COLUMN username VARCHAR(64) NULL;
ALTER TABLE users ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'reader';
UPDATE users SET username = CONCAT('legacy_', id) WHERE username IS NULL;
ALTER TABLE users MODIFY username VARCHAR(64) NOT NULL;
ALTER TABLE users ADD CONSTRAINT uq_users_username UNIQUE (username);
ALTER TABLE users ADD CONSTRAINT ck_users_role CHECK (role IN ('reader', 'writer', 'moderator'));
ALTER TABLE users ADD CONSTRAINT ck_users_username CHECK (CHAR_LENGTH(TRIM(username)) > 0);
