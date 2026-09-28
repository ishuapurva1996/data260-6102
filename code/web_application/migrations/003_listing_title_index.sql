-- Run only after the Part 3 HTTP benchmark and preserved EXPLAIN before evidence.
-- MySQL DDL commits implicitly. If CREATE INDEX succeeded but journal insertion
-- failed, the exact expected existing index is a no-op on the next migrate run.
-- A conflicting index definition retains its data and fails on duplicate name.
SET @hw04_part3_index_ddl = (
    SELECT IF(
        COUNT(*) = 1 AND MAX(COLUMN_NAME = 'listing_title' AND SEQ_IN_INDEX = 1 AND SUB_PART IS NULL AND NON_UNIQUE = 1 AND INDEX_TYPE = 'BTREE') = 1,
        'SELECT 1',
        'CREATE INDEX ix_rentals_listing_title ON rentals (listing_title)'
    )
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'rentals' AND INDEX_NAME = 'ix_rentals_listing_title'
);
PREPARE hw04_part3_index_statement FROM @hw04_part3_index_ddl;
EXECUTE hw04_part3_index_statement;
DEALLOCATE PREPARE hw04_part3_index_statement;
