-- HW4 shared schema. Requires MySQL 8.0.16+ for enforced CHECK constraints.
-- Tables are additive; this migration never deletes or replaces stored rows.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER NOT NULL AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(320) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_users_email UNIQUE (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    user_id INTEGER NOT NULL,
    created_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    last_activity_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    INDEX ix_sessions_user_id (user_id),
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS property_managers (
    id INTEGER NOT NULL AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS rentals (
    id INTEGER NOT NULL AUTO_INCREMENT,
    listing_title VARCHAR(255) NOT NULL,
    property_address VARCHAR(255) NOT NULL,
    submitter_email VARCHAR(320) NOT NULL,
    description TEXT NOT NULL,
    property_type VARCHAR(20) NOT NULL,
    terms_accepted BOOLEAN NOT NULL,
    manager_id INTEGER NULL,
    PRIMARY KEY (id),
    INDEX ix_rentals_manager_id (manager_id),
    CONSTRAINT fk_rentals_manager FOREIGN KEY (manager_id) REFERENCES property_managers (id) ON DELETE SET NULL,
    CONSTRAINT ck_rentals_title CHECK (CHAR_LENGTH(TRIM(listing_title)) > 0),
    CONSTRAINT ck_rentals_address CHECK (CHAR_LENGTH(TRIM(property_address)) > 0),
    CONSTRAINT ck_rentals_description CHECK (CHAR_LENGTH(description) >= 26),
    CONSTRAINT ck_rentals_property_type CHECK (property_type IN ('apartment', 'house', 'condo', 'townhouse')),
    CONSTRAINT ck_rentals_terms CHECK (terms_accepted = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
