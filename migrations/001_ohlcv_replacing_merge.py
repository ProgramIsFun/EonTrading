"""Convert ohlcv from MergeTree to ReplacingMergeTree."""


def migrate(client):
    create_stmt = client.query("SHOW CREATE TABLE eontrading.ohlcv").result_rows[0][0]
    if "ReplacingMergeTree" in create_stmt:
        print("  Already ReplacingMergeTree, skipping.")
        return

    count_before = client.query("SELECT count() FROM ohlcv").result_rows[0][0]

    client.command("""
    CREATE TABLE ohlcv_new (
        symbol String, exchange String,
        interval Enum8('1s'=1,'1m'=2,'5m'=3,'15m'=4,'1h'=5,'1d'=6,'1w'=7),
        timestamp DateTime64(3, 'UTC'),
        open Float64, high Float64, low Float64, close Float64, volume Float64
    ) ENGINE = ReplacingMergeTree()
    PARTITION BY toYear(timestamp)
    ORDER BY (symbol, interval, timestamp)
    """)

    client.command("INSERT INTO ohlcv_new SELECT * FROM ohlcv")
    count_after = client.query("SELECT count() FROM ohlcv_new").result_rows[0][0]

    if count_after == count_before:
        client.command("RENAME TABLE ohlcv TO ohlcv_old, ohlcv_new TO ohlcv")
        client.command("DROP TABLE ohlcv_old")
        print(f"  Migrated {count_before:,} rows.")
    else:
        client.command("DROP TABLE ohlcv_new")
        raise RuntimeError(f"Row count mismatch: {count_before} vs {count_after}")
