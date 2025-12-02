import pandas as pd
import mysql.connector

# Database connection
conn = mysql.connector.connect(
    host="datahub-mysql.wearewarp.link",
    user="datahub-read",
    password="warpdbhub2",
    database="datahub"
)

# First, let's check what dates are actually in the table
print("� Checking date range in otp_reports table...")
date_check = pd.read_sql("""
    SELECT
        MIN(pickWindowFrom) as earliest_date,
        MAX(pickWindowFrom) as latest_date,
        COUNT(*) as total_rows
    FROM otp_reports
    WHERE pickWindowFrom IS NOT NULL
""", conn)

print(f"\n📅 Date range in table:")
print(f"   Earliest: {date_check['earliest_date'].values[0]}")
print(f"   Latest: {date_check['latest_date'].values[0]}")
print(f"   Total rows with dates: {date_check['total_rows'].values[0]:,}")

# Now query without date filter to see all data
print("\n📥 Querying ALL data from otp_reports table (no date filter)...")
df = pd.read_sql("""
    SELECT
        *
    FROM otp_reports
    WHERE pickWindowFrom IS NOT NULL
    ORDER BY pickWindowFrom DESC
    LIMIT 1000
""", conn)

conn.close()

# Show dataframe info
print(f"\n✅ Loaded {len(df):,} rows")
print(f"📊 Total columns: {len(df.columns)}")

print(f"\n� First 5 rows:")
pd.set_option('display.max_columns', 10)  # Show only 10 columns for readability
print(df.head())

print(f"\n� Date range in loaded data:")
print(f"   Earliest: {df['pickWindowFrom'].min()}")
print(f"   Latest: {df['pickWindowFrom'].max()}")



print("\n" + "="*60)
print("DETAILED DATE ANALYSIS")
print("="*60)

print(f"\nSample pickWindowFrom values:")
print(df[['warpId', 'pickWindowFrom', 'dropWindowFrom']].head(10))

print(f"\nData type of pickWindowFrom: {df['pickWindowFrom'].dtype}")

# Try to convert to datetime
print("\nConverting pickWindowFrom to datetime...")
df['pickWindowFrom_dt'] = pd.to_datetime(df['pickWindowFrom'], errors='coerce')

print(f"\nDate range after conversion:")
print(f"   Earliest: {df['pickWindowFrom_dt'].min()}")
print(f"   Latest: {df['pickWindowFrom_dt'].max()}")
print(f"   Rows with valid dates: {df['pickWindowFrom_dt'].notna().sum():,}")

# Filter for 2025 data
df_2025 = df[df['pickWindowFrom_dt'] >= '2025-01-01']
print(f"\nRows from Jan 1, 2025 onwards: {len(df_2025):,}")

print("\n" + "="*60)
print("CHECKING OTHER DATE FIELDS")
print("="*60)

# Check if there are other date fields that might have more recent data
date_fields = ['createdAt', 'updatedAt', 'revenueDate', 'createWhen', 'pickWindowFrom', 'dropWindowFrom']
available_date_fields = [f for f in date_fields if f in df.columns]

print(f"\nAvailable date fields: {available_date_fields}")

for field in available_date_fields:
    print(f"\n{field}:")
    print(f"  Sample values: {df[field].head(3).tolist()}")
    # Try to convert to datetime
    temp_dt = pd.to_datetime(df[field], errors='coerce')
    if temp_dt.notna().sum() > 0:
        print(f"  Min: {temp_dt.min()}")
        print(f"  Max: {temp_dt.max()}")
        print(f"  Valid dates: {temp_dt.notna().sum():,}")
    else:
        print(f"  No valid dates found")

print("\n" + "="*60)
print("CHECKING MOST RECENT RECORDS BY ID")
print("="*60)

# Query the absolute latest records by ID (assuming higher ID = more recent)
print("\nQuerying most recent records by ID...")
conn2 = mysql.connector.connect(
    host="datahub-mysql.wearewarp.link",
    user="datahub-read",
    password="warpdbhub2",
    database="datahub"
)

latest_df = pd.read_sql("""
    SELECT
        id, warpId, pickWindowFrom, dropWindowFrom, createdAt, updatedAt, revenueDate
    FROM otp_reports
    ORDER BY id DESC
    LIMIT 10
""", conn2)

conn2.close()

print("\nMost recent 10 records (by ID):")
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)
print(latest_df)
