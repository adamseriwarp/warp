import pandas as pd
import mysql.connector

# Database connection
conn = mysql.connector.connect(
    host="datahub-mysql.wearewarp.link",
    user="datahub-read",
    password="warpdbhub2",
    database="datahub"
)

# Query data
df = pd.read_sql("""
    SELECT
        *
    FROM otp_reports
    WHERE STR_TO_DATE(pickWindowFrom, '%m/%d/%Y %H:%i:%s') >= '2025-01-01'
    ORDER BY id DESC
""", conn)

conn.close()

print("=" * 80)
print("DEDUPLICATION EDGE CASE ANALYSIS")
print("=" * 80)

# First, let's see what columns we have
print("\nAvailable columns:")
print(df.columns.tolist())

# Filter for mainShipment = YES
main_shipments = df[df['mainShipment'] == 'YES'].copy()
print(f"\nTotal mainShipment = YES records: {len(main_shipments):,}")

# ============================================================================
# EDGE CASE 1: Same loadId + carrierName + pickLocationName but different pickTimeArrived
# (within 10 minutes on the same date)
# ============================================================================
print("\n" + "=" * 80)
print("EDGE CASE 1: Same loadId + carrierName + pickLocationName")
print("            but pickTimeArrived differs by <= 10 minutes on same date")
print("=" * 80)

# Group by loadId + carrierName + pickLocationName
grouped = main_shipments.groupby(['loadId', 'carrierName', 'pickLocationName'])

similar_time_cases = []
for (loadId, carrierName, location), group in grouped:
    if len(group) < 2:
        continue

    # Convert pickTimeArrived to datetime
    group['pickTimeArrived_dt'] = pd.to_datetime(group['pickTimeArrived'], errors='coerce')
    group = group.dropna(subset=['pickTimeArrived_dt'])

    if len(group) < 2:
        continue

    # Check if they have different pickTimeArrived values
    unique_times = group['pickTimeArrived'].unique()
    if len(unique_times) > 1:
        # Sort by time
        group = group.sort_values('pickTimeArrived_dt')

        # Calculate time differences
        min_time = group['pickTimeArrived_dt'].min()
        max_time = group['pickTimeArrived_dt'].max()
        time_diff = (max_time - min_time).total_seconds()

        # Only include if:
        # 1. Time difference is <= 10 minutes (600 seconds)
        # 2. All times are on the same date
        if time_diff <= 600 and time_diff > 0:
            # Check if all on same date
            dates = group['pickTimeArrived_dt'].dt.date.unique()
            if len(dates) == 1:
                similar_time_cases.append({
                    'loadId': loadId,
                    'carrierName': carrierName,
                    'location': location,
                    'num_orders': len(group),
                    'warpIds': group['warpId'].tolist(),
                    'times': group['pickTimeArrived'].tolist(),
                    'time_diff_seconds': time_diff,
                    'time_diff_minutes': time_diff / 60
                })

print(f"\nFound {len(similar_time_cases)} loadIds where orders have:")
print(f"  - Same loadId + carrier + location")
print(f"  - Different pickTimeArrived (within 10 minutes on same date)")
total_warpids = sum([c['num_orders'] for c in similar_time_cases])
print(f"Total warpIDs affected: {total_warpids}")

if len(similar_time_cases) > 0:
    print("\nAll cases (sorted by time difference):")
    similar_time_cases_sorted = sorted(similar_time_cases, key=lambda x: x['time_diff_seconds'], reverse=True)
    for case in similar_time_cases_sorted[:20]:
        print(f"\n  LoadID: {case['loadId']}")
        print(f"  Carrier: {case['carrierName']}")
        print(f"  Location: {case['location']}")
        print(f"  Number of orders: {case['num_orders']}")
        print(f"  WarpIDs: {case['warpIds']}")
        print(f"  Times: {case['times']}")
        print(f"  Time difference: {case['time_diff_minutes']:.2f} minutes ({case['time_diff_seconds']:.0f} seconds)")
else:
    print("\n✅ No cases found! All orders on same loadId + carrier + location have identical pickTimeArrived")

# ============================================================================
# EDGE CASE 2: Different delay codes with NEW deduplication logic
# (loadId + carrierName + pickLocationName + pickDate)
# ============================================================================
print("\n" + "=" * 80)
print("EDGE CASE 2: Different delay codes with NEW deduplication logic")
print("            (loadId + carrierName + pickLocationName + pickDate)")
print("=" * 80)

# Add date columns
main_shipments['pickDate'] = pd.to_datetime(main_shipments['pickTimeArrived'], errors='coerce').dt.date
main_shipments['dropDate'] = pd.to_datetime(main_shipments['dropTimeArrived'], errors='coerce').dt.date

# Group by NEW deduplication logic for PICKUPS
grouped_pickup = main_shipments.groupby(['loadId', 'carrierName', 'pickLocationName', 'pickDate'])

conflicting_pickup_delay_codes = []
for (loadId, carrierName, location, pick_date), group in grouped_pickup:
    if len(group) < 2:
        continue

    # Check if they have different pickup delay codes
    delay_codes = group['pickupDelayCode'].dropna().unique()
    if len(delay_codes) > 1:
        conflicting_pickup_delay_codes.append({
            'loadId': loadId,
            'carrierName': carrierName,
            'location': location,
            'pick_date': pick_date,
            'num_orders': len(group),
            'warpIds': group['warpId'].tolist(),
            'delay_codes': delay_codes.tolist(),
            'pick_times': group['pickTimeArrived'].tolist()
        })

print(f"\n📦 PICKUP DELAY CODES:")
print(f"Found {len(conflicting_pickup_delay_codes)} cases where orders have DIFFERENT pickup delay codes")
print(f"Total orders affected: {sum([c['num_orders'] for c in conflicting_pickup_delay_codes])}")

if len(conflicting_pickup_delay_codes) > 0:
    print("\nSample cases:")
    for case in conflicting_pickup_delay_codes[:10]:
        print(f"\n  LoadID: {case['loadId']}")
        print(f"  Carrier: {case['carrierName']}")
        print(f"  Location: {case['location']}")
        print(f"  Pick Date: {case['pick_date']}")
        print(f"  Number of orders: {case['num_orders']}")
        print(f"  WarpIDs: {case['warpIds']}")
        print(f"  Pick Times: {case['pick_times']}")
        print(f"  Different delay codes: {case['delay_codes']}")

# Group by NEW deduplication logic for DELIVERIES
grouped_delivery = main_shipments.groupby(['loadId', 'carrierName', 'dropLocationName', 'dropDate'])

conflicting_delivery_delay_codes = []
for (loadId, carrierName, location, drop_date), group in grouped_delivery:
    if len(group) < 2:
        continue

    # Check if they have different delivery delay codes
    delay_codes = group['deliveryDelayCode'].dropna().unique()
    if len(delay_codes) > 1:
        conflicting_delivery_delay_codes.append({
            'loadId': loadId,
            'carrierName': carrierName,
            'location': location,
            'drop_date': drop_date,
            'num_orders': len(group),
            'warpIds': group['warpId'].tolist(),
            'delay_codes': delay_codes.tolist(),
            'drop_times': group['dropTimeArrived'].tolist()
        })

print(f"\n🚚 DELIVERY DELAY CODES:")
print(f"Found {len(conflicting_delivery_delay_codes)} cases where orders have DIFFERENT delivery delay codes")
print(f"Total orders affected: {sum([c['num_orders'] for c in conflicting_delivery_delay_codes])}")

if len(conflicting_delivery_delay_codes) > 0:
    print("\nSample cases:")
    for case in conflicting_delivery_delay_codes[:10]:
        print(f"\n  LoadID: {case['loadId']}")
        print(f"  Carrier: {case['carrierName']}")
        print(f"  Location: {case['location']}")
        print(f"  Drop Date: {case['drop_date']}")
        print(f"  Number of orders: {case['num_orders']}")
        print(f"  WarpIDs: {case['warpIds']}")
        print(f"  Drop Times: {case['drop_times']}")
        print(f"  Different delay codes: {case['delay_codes']}")

# ============================================================================
# DEDUPLICATION IMPACT ANALYSIS (NEW LOGIC)
# ============================================================================
print("\n" + "=" * 80)
print("DEDUPLICATION IMPACT ANALYSIS (NEW LOGIC)")
print("=" * 80)

# Count before deduplication
total_before = len(main_shipments)

# Count after deduplication with NEW logic
# For pickups: loadId + carrierName + pickLocationName + pickDate
deduplicated_pickup = main_shipments.drop_duplicates(subset=['loadId', 'carrierName', 'pickLocationName', 'pickDate'])
total_after_pickup = len(deduplicated_pickup)

# For deliveries: loadId + carrierName + dropLocationName + dropDate
deduplicated_delivery = main_shipments.drop_duplicates(subset=['loadId', 'carrierName', 'dropLocationName', 'dropDate'])
total_after_delivery = len(deduplicated_delivery)

print(f"\nPICKUP DEDUPLICATION (loadId + carrierName + pickLocationName + pickDate):")
print(f"  Before: {total_before:,} records")
print(f"  After:  {total_after_pickup:,} records")
print(f"  Reduction: {total_before - total_after_pickup:,} records ({(total_before - total_after_pickup) / total_before * 100:.1f}%)")

print(f"\nDELIVERY DEDUPLICATION (loadId + carrierName + dropLocationName + dropDate):")
print(f"  Before: {total_before:,} records")
print(f"  After:  {total_after_delivery:,} records")
print(f"  Reduction: {total_before - total_after_delivery:,} records ({(total_before - total_after_delivery) / total_before * 100:.1f}%)")

# Show some examples of duplicates with NEW logic
print("\n" + "=" * 80)
print("SAMPLE DUPLICATE GROUPS (NEW LOGIC)")
print("(loadId + carrierName + pickLocationName + pickDate)")
print("=" * 80)

duplicate_groups = main_shipments.groupby(['loadId', 'carrierName', 'pickLocationName', 'pickDate']).filter(lambda x: len(x) > 1)
duplicate_groups_summary = duplicate_groups.groupby(['loadId', 'carrierName', 'pickLocationName', 'pickDate']).agg({
    'warpId': lambda x: list(x),
    'pickupDelayCode': lambda x: list(x),
    'pickTimeArrived': lambda x: list(x),
}).head(10)

print(f"\nShowing first 10 duplicate groups:")
for idx, row in duplicate_groups_summary.iterrows():
    loadId, carrierName, location, pick_date = idx
    print(f"\nLoadID: {loadId}")
    print(f"Carrier: {carrierName}")
    print(f"Location: {location}")
    print(f"Pick Date: {pick_date}")
    print(f"WarpIDs: {row['warpId']}")
    print(f"Pick Times: {row['pickTimeArrived']}")
    print(f"Delay Codes: {row['pickupDelayCode']}")

