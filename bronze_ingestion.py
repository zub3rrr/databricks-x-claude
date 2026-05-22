# Bronze Layer Ingestion — catalog_claude.bronze
# Fetch CSVs from GitHub via Pandas, write as Delta tables via Spark

import pandas as pd
from pyspark.sql import SparkSession

CATALOG = "catalog_claude"
SCHEMA  = "bronze"

SOURCES = {
    "airports":   "https://raw.githubusercontent.com/anshlambagit/Claude_X_Dtabricks/refs/heads/main/airports.csv",
    "bookings":   "https://raw.githubusercontent.com/anshlambagit/Claude_X_Dtabricks/refs/heads/main/bookings.csv",
    "passengers": "https://raw.githubusercontent.com/anshlambagit/Claude_X_Dtabricks/refs/heads/main/passengers.csv",
}

spark = SparkSession.builder.getOrCreate()
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")
print(f"Session ready | {CATALOG}.{SCHEMA}")

for table, url in SOURCES.items():
    print(f"\n[{table}] Fetching {url}")
    pdf = pd.read_csv(url)
    pdf.columns = [c.strip().lower().replace(" ", "_") for c in pdf.columns]
    print(f"[{table}] Rows: {len(pdf)} | Cols: {list(pdf.columns)}")

    sdf = spark.createDataFrame(pdf)
    full_name = f"{CATALOG}.{SCHEMA}.{table}"
    sdf.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(full_name)
    count = spark.sql(f"SELECT COUNT(*) AS c FROM {full_name}").collect()[0]["c"]
    print(f"[{table}] Table written: {full_name} | {count} rows")

print("\n=== VERIFICATION ===")
for table in SOURCES:
    full_name = f"{CATALOG}.{SCHEMA}.{table}"
    count = spark.sql(f"SELECT COUNT(*) AS c FROM {full_name}").collect()[0]["c"]
    print(f"  {full_name}: {count} rows")

tables = spark.sql(f"SHOW TABLES IN {CATALOG}.{SCHEMA}").collect()
print(f"\nSHOW TABLES IN {CATALOG}.{SCHEMA}:")
for t in tables:
    print(f"  - {t['tableName']}")

print("\nDone.")
