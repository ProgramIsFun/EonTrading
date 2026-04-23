"""Migration runner — tracks which migrations have been applied in ClickHouse."""
import os, sys, importlib.util
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.storage import ClickHouseStorage

MIGRATIONS_DIR = os.path.dirname(os.path.abspath(__file__))

storage = ClickHouseStorage()
client = storage.client

# Create tracking table if needed
client.command("""
CREATE TABLE IF NOT EXISTS eontrading.migrations (
    name String,
    applied_at DateTime DEFAULT now()
) ENGINE = MergeTree() ORDER BY name
""")

# Get already applied
applied = {r[0] for r in client.query("SELECT name FROM eontrading.migrations").result_rows}

# Find migration files (001_*.py, 002_*.py, etc.)
files = sorted(f for f in os.listdir(MIGRATIONS_DIR) if f[0].isdigit() and f.endswith(".py"))

pending = [f for f in files if f not in applied]
if not pending:
    print(f"All {len(applied)} migrations already applied.")
    sys.exit(0)

print(f"Applied: {len(applied)}, Pending: {len(pending)}\n")

for f in pending:
    print(f"Running {f}...")
    spec = importlib.util.spec_from_file_location(f[:-3], os.path.join(MIGRATIONS_DIR, f))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.migrate(client)
    client.command(f"INSERT INTO eontrading.migrations (name) VALUES ('{f}')")
    print(f"  ✅ {f} applied\n")

print("All migrations complete.")
