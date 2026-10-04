-- Connect to the explicitly owned MySQL instance before running this file.
USE s6102_rel;
SELECT DATABASE() AS selected_database;

-- mysql_version
SELECT VERSION() AS version;

-- managers_ddl
SHOW CREATE TABLE property_managers;

-- rentals_ddl
SHOW CREATE TABLE rentals;

-- managers
SELECT id,name,company,email,created_at,updated_at FROM property_managers ORDER BY id LIMIT 3;

-- rentals
SELECT id,listing_title,listing_code,available_units,manager_id,created_at,updated_at FROM rentals ORDER BY id LIMIT 3;

-- counts
SELECT (SELECT COUNT(*) FROM property_managers) AS managers,(SELECT COUNT(*) FROM rentals) AS rentals;

-- migrations
SELECT version,name,checksum,applied_at FROM schema_migrations ORDER BY version;
