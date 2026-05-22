# Gold Layer — Aggregated Analytics Tables
# Source : catalog_claude.silver.bookings_obt
# Target : catalog_claude.gold.*
#
# 8 aggregated Delta tables covering revenue, passengers,
# airport performance, booking trends, and demographics.

import logging
from pyspark.sql import SparkSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CATALOG       = "catalog_claude"
SILVER_SCHEMA = "silver"
SILVER_TABLE  = "bookings_obt"
GOLD_SCHEMA   = "gold"
SOURCE        = f"{CATALOG}.{SILVER_SCHEMA}.{SILVER_TABLE}"

spark = SparkSession.builder.getOrCreate()
log.info(f"Session ready | source: {SOURCE} | target: {CATALOG}.{GOLD_SCHEMA}")

# ── Ensure gold schema exists ─────────────────────────────────────────────────
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{GOLD_SCHEMA}")
log.info(f"Schema ready: {CATALOG}.{GOLD_SCHEMA}")


def save_gold_table(df, table_name: str, comment: str) -> int:
    """Write a DataFrame as a managed Delta table in the gold schema."""
    full_name = f"{CATALOG}.{GOLD_SCHEMA}.{table_name}"
    try:
        (
            df.write
            .format("delta")
            .mode("overwrite")
            .option("overwriteSchema", "true")
            .saveAsTable(full_name)
        )
        spark.sql(f"COMMENT ON TABLE {full_name} IS '{comment}'")
        count = spark.sql(f"SELECT COUNT(*) AS c FROM {full_name}").collect()[0]["c"]
        log.info(f"  [OK] {full_name} — {count} rows")
        return count
    except Exception as exc:
        log.error(f"  [FAIL] {full_name}: {exc}")
        raise


summary: dict[str, int] = {}

# ── 1. gold_airport_revenue_summary ──────────────────────────────────────────
log.info("Building gold_airport_revenue_summary …")
df = spark.sql(f"""
    SELECT
        airport_id,
        airport_name,
        city,
        country,
        COUNT(booking_id)               AS total_bookings,
        ROUND(SUM(amount),  2)          AS total_revenue,
        ROUND(AVG(amount),  2)          AS avg_revenue_per_booking
    FROM {SOURCE}
    GROUP BY airport_id, airport_name, city, country
    ORDER BY total_revenue DESC
""")
summary["gold_airport_revenue_summary"] = save_gold_table(
    df,
    "gold_airport_revenue_summary",
    "Total bookings and revenue by airport. Identifies highest-revenue airports for business planning.",
)

# ── 2. gold_top_airports ──────────────────────────────────────────────────────
log.info("Building gold_top_airports …")
df = spark.sql(f"""
    SELECT
        airport_id,
        airport_name,
        city,
        country,
        COUNT(booking_id)                AS total_bookings,
        COUNT(DISTINCT passenger_id)     AS unique_passengers,
        ROUND(SUM(amount), 2)            AS total_revenue
    FROM {SOURCE}
    GROUP BY airport_id, airport_name, city, country
    ORDER BY total_bookings DESC
""")
summary["gold_top_airports"] = save_gold_table(
    df,
    "gold_top_airports",
    "Airports ranked by booking frequency. Highlights most popular travel destinations.",
)

# ── 3. gold_monthly_booking_trends ────────────────────────────────────────────
log.info("Building gold_monthly_booking_trends …")
df = spark.sql(f"""
    SELECT
        DATE_FORMAT(TO_DATE(booking_date, 'yyyy-MM-dd'), 'yyyy-MM') AS year_month,
        COUNT(booking_id)                AS total_bookings,
        COUNT(DISTINCT passenger_id)     AS unique_passengers,
        ROUND(SUM(amount), 2)            AS total_revenue,
        ROUND(AVG(amount), 2)            AS avg_revenue_per_booking
    FROM {SOURCE}
    GROUP BY year_month
    ORDER BY year_month
""")
summary["gold_monthly_booking_trends"] = save_gold_table(
    df,
    "gold_monthly_booking_trends",
    "Month-over-month booking volume and revenue. Used for growth tracking and seasonality analysis.",
)

# ── 4. gold_airport_performance ───────────────────────────────────────────────
log.info("Building gold_airport_performance …")
df = spark.sql(f"""
    SELECT
        airport_id,
        airport_name,
        city,
        country,
        COUNT(DISTINCT flight_id)        AS total_flights,
        COUNT(DISTINCT passenger_id)     AS unique_passengers,
        COUNT(booking_id)                AS total_bookings,
        ROUND(SUM(amount), 2)            AS total_revenue,
        ROUND(AVG(amount), 2)            AS avg_booking_value,
        ROUND(MAX(amount), 2)            AS max_booking_value,
        ROUND(MIN(amount), 2)            AS min_booking_value
    FROM {SOURCE}
    GROUP BY airport_id, airport_name, city, country
""")
summary["gold_airport_performance"] = save_gold_table(
    df,
    "gold_airport_performance",
    "Comprehensive airport metrics: flights, passengers, bookings, and revenue range. Supports operational planning.",
)

# ── 5. gold_passenger_booking_summary ────────────────────────────────────────
log.info("Building gold_passenger_booking_summary …")
df = spark.sql(f"""
    SELECT
        passenger_id,
        name                             AS passenger_name,
        gender,
        nationality,
        COUNT(booking_id)                AS total_bookings,
        ROUND(SUM(amount), 2)            AS total_spend,
        ROUND(AVG(amount), 2)            AS avg_spend_per_booking,
        ROUND(MAX(amount), 2)            AS max_single_booking,
        COUNT(DISTINCT airport_id)       AS airports_visited,
        COUNT(DISTINCT flight_id)        AS flights_taken
    FROM {SOURCE}
    GROUP BY passenger_id, name, gender, nationality
    ORDER BY total_spend DESC
""")
summary["gold_passenger_booking_summary"] = save_gold_table(
    df,
    "gold_passenger_booking_summary",
    "Passenger-level lifetime booking behaviour: spend, frequency, airports visited. Supports CRM and loyalty programs.",
)

# ── 6. gold_gender_booking_summary ────────────────────────────────────────────
log.info("Building gold_gender_booking_summary …")
df = spark.sql(f"""
    SELECT
        gender,
        COUNT(DISTINCT passenger_id)     AS unique_passengers,
        COUNT(booking_id)                AS total_bookings,
        ROUND(SUM(amount), 2)            AS total_revenue,
        ROUND(AVG(amount), 2)            AS avg_spend_per_booking
    FROM {SOURCE}
    GROUP BY gender
""")
summary["gold_gender_booking_summary"] = save_gold_table(
    df,
    "gold_gender_booking_summary",
    "Booking and revenue distribution by passenger gender. Supports demographic analysis and targeted marketing.",
)

# ── 7. gold_nationality_revenue ───────────────────────────────────────────────
log.info("Building gold_nationality_revenue …")
df = spark.sql(f"""
    SELECT
        nationality,
        COUNT(DISTINCT passenger_id)     AS unique_passengers,
        COUNT(booking_id)                AS total_bookings,
        ROUND(SUM(amount), 2)            AS total_revenue,
        ROUND(AVG(amount), 2)            AS avg_spend_per_passenger
    FROM {SOURCE}
    GROUP BY nationality
    ORDER BY total_revenue DESC
""")
summary["gold_nationality_revenue"] = save_gold_table(
    df,
    "gold_nationality_revenue",
    "Revenue and booking volume by passenger nationality. Identifies key traveller markets for route planning.",
)

# ── 8. gold_peak_travel_days ──────────────────────────────────────────────────
log.info("Building gold_peak_travel_days …")
df = spark.sql(f"""
    SELECT
        TO_DATE(booking_date, 'yyyy-MM-dd')                              AS travel_date,
        DAYOFWEEK(TO_DATE(booking_date, 'yyyy-MM-dd'))                   AS day_of_week_num,
        DATE_FORMAT(TO_DATE(booking_date, 'yyyy-MM-dd'), 'EEEE')         AS day_of_week_name,
        COUNT(booking_id)                                                AS total_bookings,
        COUNT(DISTINCT passenger_id)                                     AS unique_passengers,
        ROUND(SUM(amount), 2)                                            AS total_revenue
    FROM {SOURCE}
    GROUP BY travel_date, day_of_week_num, day_of_week_name
    ORDER BY total_bookings DESC
""")
summary["gold_peak_travel_days"] = save_gold_table(
    df,
    "gold_peak_travel_days",
    "Daily booking volumes and revenue to identify peak travel days. Supports capacity planning and dynamic pricing.",
)

# ── Validation summary ────────────────────────────────────────────────────────
log.info("=" * 65)
log.info("GOLD LAYER BUILD COMPLETE")
log.info("=" * 65)
for tbl, cnt in summary.items():
    log.info(f"  {CATALOG}.{GOLD_SCHEMA}.{tbl:<42} {cnt:>6} rows")
log.info("=" * 65)

log.info("Sample — gold_top_airports (top 5):")
spark.sql(f"""
    SELECT airport_name, city, country, total_bookings, total_revenue
    FROM {CATALOG}.{GOLD_SCHEMA}.gold_top_airports
    LIMIT 5
""").show(truncate=False)

log.info("Sample — gold_monthly_booking_trends:")
spark.sql(f"""
    SELECT year_month, total_bookings, total_revenue
    FROM {CATALOG}.{GOLD_SCHEMA}.gold_monthly_booking_trends
    ORDER BY year_month
    LIMIT 5
""").show(truncate=False)

log.info("Sample — gold_airport_revenue_summary (top 5):")
spark.sql(f"""
    SELECT airport_name, city, total_bookings, total_revenue
    FROM {CATALOG}.{GOLD_SCHEMA}.gold_airport_revenue_summary
    LIMIT 5
""").show(truncate=False)

log.info("Sample — gold_passenger_booking_summary (top spenders):")
spark.sql(f"""
    SELECT passenger_name, nationality, total_bookings, total_spend
    FROM {CATALOG}.{GOLD_SCHEMA}.gold_passenger_booking_summary
    LIMIT 5
""").show(truncate=False)

log.info("Done.")
