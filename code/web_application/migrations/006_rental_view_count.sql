-- MySQL commits DDL independently of the migration journal. Resume if the
-- column was added but the journal entry was not written.
SET @s6102_view_count_ddl = IF(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'rentals' AND column_name = 'view_count'
    ),
    'SELECT 1',
    'ALTER TABLE rentals ADD COLUMN view_count BIGINT NOT NULL DEFAULT 0'
);
PREPARE s6102_view_count_migration FROM @s6102_view_count_ddl;
EXECUTE s6102_view_count_migration;
DEALLOCATE PREPARE s6102_view_count_migration;
