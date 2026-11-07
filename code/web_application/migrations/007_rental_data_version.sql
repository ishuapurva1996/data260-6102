-- One durable version for the rental facts exposed to the Q&A pipeline.
CREATE TABLE IF NOT EXISTS rental_data_version (
    id TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    dataset_id CHAR(32) CHARACTER SET ascii NOT NULL,
    version BIGINT UNSIGNED NOT NULL,
    CONSTRAINT ck_rental_data_version_singleton CHECK (id = 1)
) ENGINE=InnoDB;

INSERT INTO rental_data_version (id, dataset_id, version) VALUES (1, REPLACE(UUID(), '-', ''), 1)
ON DUPLICATE KEY UPDATE id = id;
