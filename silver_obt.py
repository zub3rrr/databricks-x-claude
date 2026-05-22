# Silver Layer — One Big Table (OBT)
# Join catalog_claude.bronze.bookings + passengers + airports into a single denormalised table

from pyspark.sql import SparkSession

CATALOG       = "catalog_claude"
BRONZE_SCHEMA = "bronze"
SILVER_SCHEMA = "silver"
TARGET_TABLE  = "bookings_obt"

spark = SparkSession.builder.getOrCreate()
print(f"Session ready | source: {CATALOG}.{BRONZE_SCHEMA} | target: {CATALOG}.{SILVER_SCHEMA}")

bookings   = spark.table(f"{CATALOG}.{BRONZE_SCHEMA}.bookings")
passengers = spark.table(f"{CATALOG}.{BRONZE_SCHEMA}.passengers")
airports   = spark.table(f"{CATALOG}.{BRONZE_SCHEMA}.airports")

# bookings ← passengers on passenger_id, then ← airports on airport_id
obt = (
    bookings
    .join(passengers, on="passenger_id", how="left")
    .join(airports,   on="airport_id",   how="left")
)

full_name = f"{CATALOG}.{SILVER_SCHEMA}.{TARGET_TABLE}"
(
    obt.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(full_name)
)

count = spark.sql(f"SELECT COUNT(*) AS c FROM {full_name}").collect()[0]["c"]
print(f"OBT written: {full_name} | {count} rows | columns: {obt.columns}")
print("Done.")
