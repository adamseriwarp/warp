import pandas as pd
import mysql.connector
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for PDF generation
import datetime
from matplotlib.backends.backend_pdf import PdfPages
import warnings
warnings.filterwarnings('ignore')
import resend
import os

# ============================================================================
# DYNAMIC COLUMN WIDTH CALCULATION
# ============================================================================

def compute_col_widths(df, min_w=0.06, max_w=0.30):
    """
    Automatically compute optimal column widths based on actual text length.

    Args:
        df: DataFrame with the data to display
        min_w: Minimum width for any column (default 6%)
        max_w: Maximum width for any column (default 30%)

    Returns:
        List of column widths that sum to 1.0
    """
    max_lens = []
    for col in df.columns:
        # Get max character count in column (including header)
        lens = df[col].astype(str).map(len)
        max_lens.append(max(lens.max(), len(str(col))))

    # Calculate proportional widths
    total = sum(max_lens)
    widths = [l/total for l in max_lens]

    # Apply min/max constraints
    widths = [min(max(w, min_w), max_w) for w in widths]

    # Renormalize to sum to 1.0
    s = sum(widths)
    return [w/s for w in widths]

# ============================================================================
# CONFIGURATION
# ============================================================================
# Get configuration from environment variables (for GitHub Actions) or use defaults
TARGET_CARRIER_INPUT = os.environ.get('CARRIER_NAME', 'ILLYRIAN TRANSPORT LLC')
# Store the original input for display purposes
TARGET_CARRIER_DISPLAY = TARGET_CARRIER_INPUT
OUTPUT_PDF = f'carrier_report_{TARGET_CARRIER_INPUT.replace(" ", "_").replace("&", "and")}.pdf'

# Email Configuration
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', 're_HZz4UQ8x_5tkWo5pAFCboeMC1EAM7PG1H')
EMAIL_FROM = 'onboarding@resend.dev'  # For testing - use your verified domain in production
EMAIL_TO = os.environ.get('EMAIL_RECIPIENT', 'lior@wearewarp.com')
EMAIL_SUBJECT = f'Carrier Performance Report - {TARGET_CARRIER_DISPLAY}'
SEND_EMAIL = bool(EMAIL_TO and EMAIL_TO.strip())  # Only send if email is provided

# ============================================================================
# STEP 1: QUERY DATA FROM DATABASE
# ============================================================================
print("=" * 80)
print("CARRIER PERFORMANCE REPORT GENERATOR")
print("=" * 80)

# Database connection - use environment variables if available (for GitHub Actions)
conn = mysql.connector.connect(
    host=os.environ.get('DB_HOST', 'datahub-mysql.wearewarp.link'),
    user=os.environ.get('DB_USER', 'datahub-read'),
    password=os.environ.get('DB_PASSWORD', 'warpdbhub2'),
    database=os.environ.get('DB_NAME', 'datahub')
)

# First check the format of pickWindowFrom
print("\n🔍 Checking pickWindowFrom format...")
sample = pd.read_sql("SELECT pickWindowFrom FROM otp_reports LIMIT 10", conn)
print(f"Sample pickWindowFrom values: {sample['pickWindowFrom'].tolist()}")

# Query data from Jan 1, 2025 onwards using pickWindowFrom field
print("\n📥 Querying otp_reports from Jan 1, 2025 onwards...")
print("   (Using 'pickWindowFrom' field - stored as string in MM/DD/YYYY HH:MM:SS format)")

df = pd.read_sql("""
    SELECT
        *
    FROM otp_reports
    WHERE STR_TO_DATE(pickWindowFrom, '%m/%d/%Y %H:%i:%s') >= '2025-01-01'
    ORDER BY id DESC
""", conn)

conn.close()

# Show results
print(f"\n✅ Loaded {len(df):,} rows")
print(f"📊 Total columns: {len(df.columns)}")

# ============================================================================
# STEP 2: DATA PREPARATION
# ============================================================================
print("\n" + "=" * 80)
print("DATA PREPARATION")
print("=" * 80)

# Convert date fields to proper datetime
df['pickWindowFrom_dt'] = pd.to_datetime(df['pickWindowFrom'], errors='coerce')
df['dropWindowFrom_dt'] = pd.to_datetime(df['dropWindowFrom'], errors='coerce')
df['createdAt_dt'] = pd.to_datetime(df['createdAt'], errors='coerce')
df['updatedAt_dt'] = pd.to_datetime(df['updatedAt'], errors='coerce')

# Convert time fields for OTP/OTD calculation
df['pickTimeArrived_dt'] = pd.to_datetime(df['pickTimeArrived'], errors='coerce')
df['pickWindowTo_dt'] = pd.to_datetime(df['pickWindowTo'], errors='coerce')
df['dropTimeArrived_dt'] = pd.to_datetime(df['dropTimeArrived'], errors='coerce')
df['dropWindowTo_dt'] = pd.to_datetime(df['dropWindowTo'], errors='coerce')

print(f"\n📅 Date range (by pickWindowFrom):")
print(f"   Earliest: {df['pickWindowFrom_dt'].min()}")
print(f"   Latest: {df['pickWindowFrom_dt'].max()}")
print(f"   Valid dates: {df['pickWindowFrom_dt'].notna().sum():,} / {len(df):,}")

# ============================================================================
# STEP 3: CALCULATE OTP AND OTD
# ============================================================================
print("\n" + "=" * 80)
print("CALCULATING OTP AND OTD")
print("=" * 80)

# Calculate OTP (On Time Pickup)
def calculate_otp(row):
    if pd.isna(row['pickTimeArrived_dt']) or pd.isna(row['pickWindowTo_dt']):
        return None
    return 'On Time' if row['pickTimeArrived_dt'] < row['pickWindowTo_dt'] else 'Late'

# Calculate OTD (On Time Delivery)
def calculate_otd(row):
    if pd.isna(row['dropTimeArrived_dt']) or pd.isna(row['dropWindowTo_dt']):
        return None
    return 'On Time' if row['dropTimeArrived_dt'] < row['dropWindowTo_dt'] else 'Late'

df['OTP'] = df.apply(calculate_otp, axis=1)
df['OTD'] = df.apply(calculate_otd, axis=1)

print(f"\n✅ OTP calculated: {df['OTP'].notna().sum():,} / {len(df):,}")
print(f"✅ OTD calculated: {df['OTD'].notna().sum():,} / {len(df):,}")

# ============================================================================
# DEDUPLICATION LOGIC
# ============================================================================
print("\n" + "=" * 80)
print("DEDUPLICATION")
print("=" * 80)

print(f"\n📊 Records before deduplication: {len(df):,}")

# Add date columns for deduplication
df['pickDate'] = df['pickTimeArrived_dt'].dt.date
df['dropDate'] = df['dropTimeArrived_dt'].dt.date

# For each group that will be deduplicated, keep the row with the earliest time
# This ensures we keep the earliest pickTimeArrived/dropTimeArrived and its corresponding delay code

# Sort by pickTimeArrived_dt and dropTimeArrived_dt to ensure earliest times come first
df = df.sort_values(['pickTimeArrived_dt', 'dropTimeArrived_dt'], na_position='last')

# Create a deduplicated dataframe
# We'll keep track of which records to keep based on deduplication keys

# For pickup deduplication: loadId + carrierName + pickLocationName + pickDate
# For delivery deduplication: loadId + carrierName + dropLocationName + dropDate
# We need to deduplicate separately and then combine

# First, let's create deduplication keys
df['pickup_dedup_key'] = (
    df['loadId'].astype(str) + '|' +
    df['carrierName'].astype(str) + '|' +
    df['pickLocationName'].astype(str) + '|' +
    df['pickDate'].astype(str)
)

df['delivery_dedup_key'] = (
    df['loadId'].astype(str) + '|' +
    df['carrierName'].astype(str) + '|' +
    df['dropLocationName'].astype(str) + '|' +
    df['dropDate'].astype(str)
)

# Mark which records to keep for pickup deduplication
# Keep first occurrence (earliest time) for each pickup_dedup_key
df['keep_for_pickup'] = ~df.duplicated(subset=['pickup_dedup_key'], keep='first')

# Mark which records to keep for delivery deduplication
# Keep first occurrence (earliest time) for each delivery_dedup_key
df['keep_for_delivery'] = ~df.duplicated(subset=['delivery_dedup_key'], keep='first')

# Count deduplication impact
pickup_duplicates = (~df['keep_for_pickup']).sum()
delivery_duplicates = (~df['keep_for_delivery']).sum()

print(f"\n📦 PICKUP DEDUPLICATION:")
print(f"   Duplicate records found: {pickup_duplicates:,}")
print(f"   Unique pickup events: {df['keep_for_pickup'].sum():,}")

print(f"\n🚚 DELIVERY DEDUPLICATION:")
print(f"   Duplicate records found: {delivery_duplicates:,}")
print(f"   Unique delivery events: {df['keep_for_delivery'].sum():,}")

# Note: We keep the deduplication flags in the dataframe
# We'll use them later when calculating OTP/OTD percentages and delay code analysis
# We do NOT remove rows from the dataframe - we just mark which ones to use for calculations

print(f"\n✅ Deduplication flags added to dataframe")
print(f"   Use 'keep_for_pickup' flag for pickup-related calculations")
print(f"   Use 'keep_for_delivery' flag for delivery-related calculations")

# ============================================================================
# IMPUTE MISSING DELAY CODES
# ============================================================================
print("\n📝 Imputing missing delay codes...")

# Count before imputation
pickup_missing_before = df[(df['OTP'] == 'Late') &
                           ((df['pickupDelayCode'].isna()) | (df['pickupDelayCode'] == ''))].shape[0]
delivery_missing_before = df[(df['OTD'] == 'Late') &
                             ((df['deliveryDelayCode'].isna()) | (df['deliveryDelayCode'] == ''))].shape[0]

# Impute "Carrier Failure" for late pickups without delay code
df.loc[(df['OTP'] == 'Late') &
       ((df['pickupDelayCode'].isna()) | (df['pickupDelayCode'] == '')),
       'pickupDelayCode'] = 'Carrier Failure'

# Impute "Carrier Failure" for late deliveries without delay code
df.loc[(df['OTD'] == 'Late') &
       ((df['deliveryDelayCode'].isna()) | (df['deliveryDelayCode'] == '')),
       'deliveryDelayCode'] = 'Carrier Failure'

print(f"   ✅ Imputed {pickup_missing_before:,} pickup delay codes as 'Carrier Failure'")
print(f"   ✅ Imputed {delivery_missing_before:,} delivery delay codes as 'Carrier Failure'")

# Add week number column
df['week_number'] = df['pickWindowFrom_dt'].dt.isocalendar().week

# Get current week and last 2 weeks
current_week = datetime.datetime.now().isocalendar()[1]
weeks = [current_week - 1, current_week]

print(f"\n📊 Analyzing weeks: {weeks} (Current week: {current_week})")

# Filter for last 2 weeks
df_2weeks = df[df['week_number'].isin(weeks)].copy()
print(f"✅ Filtered to {len(df_2weeks):,} rows for weeks {weeks}")

# ============================================================================
# STEP 4: SAVE DATA FOR JUPYTER NOTEBOOK (OPTIONAL)
# ============================================================================
print("\n💾 Saving dataframe to files...")
df.to_pickle('otp_data.pkl')
print("   ✅ Saved to 'otp_data.pkl' (for Jupyter notebook)")

df.to_csv('otp_data.csv', index=False)
print("   ✅ Saved to 'otp_data.csv' (for inspection)")

# ============================================================================
# STEP 5: GENERATE CARRIER-SPECIFIC REPORT
# ============================================================================
print("\n" + "=" * 80)
print(f"GENERATING REPORT FOR: {TARGET_CARRIER_DISPLAY}")
print("=" * 80)

# Case-insensitive carrier name matching
print(f"\n🔍 Searching for carrier (case-insensitive): '{TARGET_CARRIER_INPUT}'")

# Create a lowercase version of carrierName for matching
df_2weeks['carrierName_lower'] = df_2weeks['carrierName'].str.lower()
target_carrier_lower = TARGET_CARRIER_INPUT.lower()

# Filter for target carrier (case-insensitive)
carrier_data = df_2weeks[df_2weeks['carrierName_lower'] == target_carrier_lower]

if len(carrier_data) == 0:
    print(f"\n❌ ERROR: No data found for carrier '{TARGET_CARRIER_INPUT}'")
    print(f"   Available carriers in weeks {weeks}:")
    available_carriers = df_2weeks['carrierName'].dropna().unique()[:20]
    for i, carrier in enumerate(available_carriers, 1):
        print(f"   {i}. {carrier}")
    print(f"\n💡 TIP: Carrier name must match exactly (case-insensitive)")
    exit(1)

# Get the actual carrier name from the data (with correct capitalization)
TARGET_CARRIER = carrier_data['carrierName'].iloc[0]

print(f"✅ Found {len(carrier_data):,} records for {TARGET_CARRIER}")

# ============================================================================
# SECTION 1: PERFORMANCE METRICS TABLE
# ============================================================================
print("\n📊 Calculating performance metrics...")

row_data = {'Carrier': TARGET_CARRIER}

for week in weeks:
    week_data = carrier_data[carrier_data['week_number'] == week]

    # Shipment count: Count ALL shipments where dropStatus = 'Succeeded' (fully delivered)
    # Apply deduplication for delivery (no mainShipment filter)
    completed_shipments = week_data[(week_data['dropStatus'] == 'Succeeded') &
                                     (week_data['keep_for_delivery'] == True)]
    shipments = len(completed_shipments)

    # Count routes: Only count routes where loadStatus = 'Completed' (unique loadId)
    routes = week_data[week_data['loadStatus'] == 'Completed']['loadId'].nunique()

    # Calculate OTP % (ALL records, deduplicated for pickup, pickStatus = 'Succeeded')
    otp_data = week_data[(week_data['OTP'].notna()) &
                          (week_data['keep_for_pickup'] == True) &
                          (week_data['pickStatus'] == 'Succeeded')]
    if len(otp_data) > 0:
        otp_pct = (otp_data['OTP'] == 'On Time').sum() / len(otp_data) * 100
    else:
        otp_pct = None

    # Calculate OTD % (ALL records, deduplicated for delivery, dropStatus = 'Succeeded')
    otd_data = week_data[(week_data['OTD'].notna()) &
                          (week_data['keep_for_delivery'] == True) &
                          (week_data['dropStatus'] == 'Succeeded')]
    if len(otd_data) > 0:
        otd_pct = (otd_data['OTD'] == 'On Time').sum() / len(otd_data) * 100
    else:
        otd_pct = None

    # Calculate Tracking % (ALL records, deduplicated for pickup, pickStatus = 'Succeeded')
    tracking_data = week_data[(week_data['isTracking'].notna()) &
                               (week_data['keep_for_pickup'] == True) &
                               (week_data['pickStatus'] == 'Succeeded')]
    if len(tracking_data) > 0:
        tracking_pct = (tracking_data['isTracking'] == 'YES').sum() / len(tracking_data) * 100
    else:
        tracking_pct = None

    # Add to row
    row_data[f'Shipments_W{week}'] = shipments
    row_data[f'Routes_W{week}'] = routes
    row_data[f'OTP_W{week}'] = otp_pct
    row_data[f'OTD_W{week}'] = otd_pct
    row_data[f'Tracking_W{week}'] = tracking_pct

# Create dataframe
carrier_result_df = pd.DataFrame([row_data])
carrier_result_df = carrier_result_df.set_index('Carrier')

# Reorder columns to group by metric
ordered_cols = []
for metric in ['Shipments', 'Routes', 'OTP', 'OTD', 'Tracking']:
    for week in weeks:
        ordered_cols.append(f'{metric}_W{week}')

carrier_result_df = carrier_result_df[ordered_cols]

# Create multi-level columns
new_cols = pd.MultiIndex.from_tuples([
    ('Shipments', f'W{weeks[0]}'),
    ('Shipments', f'W{weeks[1]}'),
    ('Routes', f'W{weeks[0]}'),
    ('Routes', f'W{weeks[1]}'),
    ('OTP %', f'W{weeks[0]}'),
    ('OTP %', f'W{weeks[1]}'),
    ('OTD %', f'W{weeks[0]}'),
    ('OTD %', f'W{weeks[1]}'),
    ('Tracking %', f'W{weeks[0]}'),
    ('Tracking %', f'W{weeks[1]}')
])

carrier_result_df.columns = new_cols

print("✅ Performance metrics calculated")
print(carrier_result_df)

# ============================================================================
# SECTION 2: DELIVERY DELAY CODES
# ============================================================================
print("\n📊 Analyzing delivery delay codes...")

# Filter for deliveryDelayCode is not empty AND deduplicated for delivery AND dropStatus = 'Succeeded'
carrier_delay_data = carrier_data[(carrier_data['deliveryDelayCode'].notna()) &
                                   (carrier_data['deliveryDelayCode'] != '') &
                                   (carrier_data['keep_for_delivery'] == True) &
                                   (carrier_data['dropStatus'] == 'Succeeded')].copy()

# Count occurrences of each delay code
carrier_delay_counts = carrier_delay_data['deliveryDelayCode'].value_counts().reset_index()
carrier_delay_counts.columns = ['Delivery Delay Code', 'Count']

# Calculate total delivery shipments and total routes for percentage calculations
total_delivery_shipments = len(carrier_data[(carrier_data['dropStatus'] == 'Succeeded') &
                                             (carrier_data['keep_for_delivery'] == True)])
total_routes = carrier_data[carrier_data['loadStatus'] == 'Completed']['loadId'].nunique()

# Add percentage columns
carrier_delay_counts['% of Total Shipments'] = (carrier_delay_counts['Count'] / total_delivery_shipments * 100).round(1)
carrier_delay_counts['% of Total Routes'] = (carrier_delay_counts['Count'] / total_routes * 100).round(1)

# Add "On-Time" row for pie chart
on_time_delivery_count = total_delivery_shipments - carrier_delay_counts['Count'].sum()
on_time_delivery_pct = (on_time_delivery_count / total_delivery_shipments * 100).round(1)
on_time_row = pd.DataFrame({
    'Delivery Delay Code': ['On-Time'],
    'Count': [on_time_delivery_count],
    '% of Total Shipments': [on_time_delivery_pct],
    '% of Total Routes': [(on_time_delivery_count / total_routes * 100).round(1)]
})
carrier_delay_counts_with_ontime = pd.concat([on_time_row, carrier_delay_counts], ignore_index=True)

print(f"✅ Found {len(carrier_delay_data):,} shipments with delivery delay codes")
print(f"   Unique delay codes: {len(carrier_delay_counts)}")
print(f"   Total delivery shipments: {total_delivery_shipments:,}")
print(f"   On-time deliveries: {on_time_delivery_count:,} ({on_time_delivery_pct:.1f}%)")
print(f"   Total routes: {total_routes:,}")

# ============================================================================
# SECTION 3: PICKUP DELAY CODES
# ============================================================================
print("\n📊 Analyzing pickup delay codes...")

# Filter for pickupDelayCode is not empty AND deduplicated for pickup AND pickStatus = 'Succeeded'
carrier_pickup_delay_data = carrier_data[(carrier_data['pickupDelayCode'].notna()) &
                                          (carrier_data['pickupDelayCode'] != '') &
                                          (carrier_data['keep_for_pickup'] == True) &
                                          (carrier_data['pickStatus'] == 'Succeeded')].copy()

# Count occurrences of each delay code
carrier_pickup_delay_counts = carrier_pickup_delay_data['pickupDelayCode'].value_counts().reset_index()
carrier_pickup_delay_counts.columns = ['Pickup Delay Code', 'Count']

# Calculate total pickup shipments (use same total_routes from delivery section)
total_pickup_shipments = len(carrier_data[(carrier_data['pickStatus'] == 'Succeeded') &
                                          (carrier_data['keep_for_pickup'] == True)])

# Add percentage columns
carrier_pickup_delay_counts['% of Total Shipments'] = (carrier_pickup_delay_counts['Count'] / total_pickup_shipments * 100).round(1)
carrier_pickup_delay_counts['% of Total Routes'] = (carrier_pickup_delay_counts['Count'] / total_routes * 100).round(1)

# Add "On-Time" row for pie chart
on_time_pickup_count = total_pickup_shipments - carrier_pickup_delay_counts['Count'].sum()
on_time_pickup_pct = (on_time_pickup_count / total_pickup_shipments * 100).round(1)
on_time_pickup_row = pd.DataFrame({
    'Pickup Delay Code': ['On-Time'],
    'Count': [on_time_pickup_count],
    '% of Total Shipments': [on_time_pickup_pct],
    '% of Total Routes': [(on_time_pickup_count / total_routes * 100).round(1)]
})
carrier_pickup_delay_counts_with_ontime = pd.concat([on_time_pickup_row, carrier_pickup_delay_counts], ignore_index=True)

print(f"✅ Found {len(carrier_pickup_delay_data):,} shipments with pickup delay codes")
print(f"   Unique delay codes: {len(carrier_pickup_delay_counts)}")
print(f"   Total pickup shipments: {total_pickup_shipments:,}")
print(f"   On-time pickups: {on_time_pickup_count:,} ({on_time_pickup_pct:.1f}%)")
print(f"   Total routes: {total_routes:,}")

# ============================================================================
# SECTION 4: PREPARE DETAILED DELAY TABLES
# ============================================================================
print("\n📊 Preparing detailed delay tables...")

# Pickup delay details table
def format_pickup_window(row):
    from_str = str(row['pickWindowFrom'])
    to_str = str(row['pickWindowTo'])

    if ' ' in from_str and ' ' in to_str:
        from_date, from_time = from_str.split(' ', 1)
        to_date, to_time = to_str.split(' ', 1)

        if from_date == to_date:
            return f"{from_date} {from_time} - {to_time}"
        else:
            return f"{from_str} - {to_str}"
    else:
        return f"{from_str} - {to_str}"

if len(carrier_pickup_delay_data) > 0:
    carrier_pickup_delay_data['Pickup Window'] = carrier_pickup_delay_data.apply(format_pickup_window, axis=1)

    # Create Lane column: "City, State > City, State"
    carrier_pickup_delay_data['Lane'] = (
        carrier_pickup_delay_data['pickCity'].fillna('') + ', ' +
        carrier_pickup_delay_data['pickState'].fillna('') + ' > ' +
        carrier_pickup_delay_data['dropCity'].fillna('') + ', ' +
        carrier_pickup_delay_data['dropState'].fillna('')
    )

    pickup_delay_details = carrier_pickup_delay_data[[
        'orderCode',
        'pickupDelayCode',
        'Lane',
        'Pickup Window',
        'pickTimeDeparted',
        'pickTimeArrived',
        'isTracking'
    ]].copy()

    pickup_delay_details.columns = [
        'Order Code',
        'Pickup Delay Code',
        'Lane',
        'Pickup Window',
        'Pick Departed',
        'Pick Arrived',
        'Tracking'
    ]
else:
    pickup_delay_details = None

# Delivery delay details table
def format_drop_window(row):
    from_str = str(row['dropWindowFrom'])
    to_str = str(row['dropWindowTo'])

    if ' ' in from_str and ' ' in to_str:
        from_date, from_time = from_str.split(' ', 1)
        to_date, to_time = to_str.split(' ', 1)

        if from_date == to_date:
            return f"{from_date} {from_time} - {to_time}"
        else:
            return f"{from_str} - {to_str}"
    else:
        return f"{from_str} - {to_str}"

if len(carrier_delay_data) > 0:
    carrier_delay_data['Drop Window'] = carrier_delay_data.apply(format_drop_window, axis=1)

    # Create Lane column: "City, State > City, State"
    carrier_delay_data['Lane'] = (
        carrier_delay_data['pickCity'].fillna('') + ', ' +
        carrier_delay_data['pickState'].fillna('') + ' > ' +
        carrier_delay_data['dropCity'].fillna('') + ', ' +
        carrier_delay_data['dropState'].fillna('')
    )

    delivery_delay_details = carrier_delay_data[[
        'orderCode',
        'deliveryDelayCode',
        'Lane',
        'Drop Window',
        'dropTimeDeparted',
        'dropTimeArrived',
        'isTracking'
    ]].copy()

    delivery_delay_details.columns = [
        'Order Code',
        'Delivery Delay Code',
        'Lane',
        'Drop Window',
        'Drop Departed',
        'Drop Arrived',
        'Tracking'
    ]
else:
    delivery_delay_details = None

print(f"✅ Detailed delay tables prepared")

# ============================================================================
# STEP 6: GENERATE PDF REPORT
# ============================================================================
print("\n" + "=" * 80)
print("GENERATING PDF REPORT")
print("=" * 80)

# Define professional color scheme (White background theme)
WARP_GREEN = '#2E7D32'  # Professional dark green accent
WARP_DARK = '#1976D2'   # Professional blue for headers
WARP_GRAY = '#F5F5F5'   # Light gray for alternating rows
WARP_WHITE = '#FFFFFF'  # White background
WARP_BORDER = '#BDBDBD' # Light gray border
WARP_TEXT = '#212121'   # Dark text for readability

# Define professional pie chart color palette - Tableau Classic (Industry Standard)
# Reordered: Coral Red first, Steel Blue 7th
PIE_COLORS = ['#E15759', '#F28E2B', '#76B7B2', '#59A14F', '#EDC948', '#B07AA1',
              '#4E79A7', '#FF9DA7', '#9C755F', '#BAB0AC', '#A0CBE8', '#FFBE7D']

# Create PDF
pdf_pages = PdfPages(OUTPUT_PDF)

try:
    # ========================================================================
    # PAGE 1: TITLE PAGE
    # ========================================================================
    fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_WHITE)

    # Add WARP logo at the top
    try:
        logo = plt.imread('/Users/adamseri/Desktop/Code/wearewarp/dashboard/warp_logo.png')
        # Create axes for logo positioning (centered, top of page)
        ax_logo = fig.add_axes([0.35, 0.70, 0.3, 0.2])  # [left, bottom, width, height]
        ax_logo.imshow(logo)
        ax_logo.axis('off')
    except Exception as e:
        print(f"⚠️  Warning: Could not load logo: {e}")

    fig.text(0.5, 0.6, f'Carrier Performance Report',
             ha='center', fontsize=24, fontweight='bold', color=WARP_DARK)
    fig.text(0.5, 0.5, f'{TARGET_CARRIER}',
             ha='center', fontsize=20, fontweight='bold', color=WARP_TEXT)
    fig.text(0.5, 0.4, f'Weeks {weeks[0]} & {weeks[1]}',
             ha='center', fontsize=16, fontweight='bold', color=WARP_TEXT)
    fig.text(0.5, 0.3, f'Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}',
             ha='center', fontsize=12, fontweight='bold', style='italic', color=WARP_TEXT)

    plt.axis('off')
    pdf_pages.savefig(fig, facecolor=WARP_WHITE)
    plt.close()

    # ========================================================================
    # PAGE 2: PERFORMANCE METRICS TABLE
    # ========================================================================
    fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_WHITE)

    # Title
    fig.text(0.5, 0.92, 'Performance Metrics',
             ha='center', fontsize=18, fontweight='bold', color=WARP_DARK)

    # Create a more structured table layout
    ax = fig.add_subplot(111)
    ax.axis('off')

    # Define color scheme function
    def get_performance_color(value, target):
        """
        Returns color based on performance vs target.
        Green if meets/exceeds target, gradient red->orange->yellow if below.
        """
        if pd.isna(value):
            return WARP_WHITE

        if value >= target:
            return '#90EE90'  # Light green (meets target)

        # Calculate how far below target (as percentage points)
        gap = target - value

        # Define color gradient based on gap severity
        if gap >= 10:  # 10+ percentage points below
            return '#FF4444'  # Bright red (very bad)
        elif gap >= 5:  # 5-10 percentage points below
            return '#FF6666'  # Red (bad)
        elif gap >= 2:  # 2-5 percentage points below
            return '#FF9966'  # Orange-red (concerning)
        else:  # 0-2 percentage points below
            return '#FFB366'  # Light orange (slightly below)

    # Prepare simplified table data - transpose for better readability
    table_data = []

    # Store raw values for color coding
    metrics_values = {}

    # Header
    table_data.append(['Metric', f'Week {weeks[0]}', f'Week {weeks[1]}'])

    # Shipments
    val_w0 = carrier_result_df[('Shipments', f'W{weeks[0]}')].values[0]
    val_w1 = carrier_result_df[('Shipments', f'W{weeks[1]}')].values[0]
    table_data.append(['Shipments', f'{int(val_w0)}' if not pd.isna(val_w0) else '-',
                       f'{int(val_w1)}' if not pd.isna(val_w1) else '-'])

    # Routes
    val_w0 = carrier_result_df[('Routes', f'W{weeks[0]}')].values[0]
    val_w1 = carrier_result_df[('Routes', f'W{weeks[1]}')].values[0]
    table_data.append(['Routes', f'{int(val_w0)}' if not pd.isna(val_w0) else '-',
                       f'{int(val_w1)}' if not pd.isna(val_w1) else '-'])

    # OTP %
    otp_w0 = carrier_result_df[('OTP %', f'W{weeks[0]}')].values[0]
    otp_w1 = carrier_result_df[('OTP %', f'W{weeks[1]}')].values[0]
    metrics_values['OTP'] = [(otp_w0, 98.5), (otp_w1, 98.5)]
    table_data.append(['OTP %\n(Target 98.5%)', f'{otp_w0:.1f}%' if not pd.isna(otp_w0) else '-',
                       f'{otp_w1:.1f}%' if not pd.isna(otp_w1) else '-'])

    # OTD %
    otd_w0 = carrier_result_df[('OTD %', f'W{weeks[0]}')].values[0]
    otd_w1 = carrier_result_df[('OTD %', f'W{weeks[1]}')].values[0]
    metrics_values['OTD'] = [(otd_w0, 99.9), (otd_w1, 99.9)]
    table_data.append(['OTD %\n(Target 99.9%)', f'{otd_w0:.1f}%' if not pd.isna(otd_w0) else '-',
                       f'{otd_w1:.1f}%' if not pd.isna(otd_w1) else '-'])

    # Tracking %
    track_w0 = carrier_result_df[('Tracking %', f'W{weeks[0]}')].values[0]
    track_w1 = carrier_result_df[('Tracking %', f'W{weeks[1]}')].values[0]
    metrics_values['Tracking'] = [(track_w0, 100.0), (track_w1, 100.0)]
    table_data.append(['Tracking %\n(Target 100%)', f'{track_w0:.1f}%' if not pd.isna(track_w0) else '-',
                       f'{track_w1:.1f}%' if not pd.isna(track_w1) else '-'])

    # Create table
    table = ax.table(cellText=table_data, cellLoc='center', loc='center',
                     bbox=[0.2, 0.35, 0.6, 0.45])
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.scale(1, 3)

    # Dynamic column widths based on actual content
    temp_df = pd.DataFrame(table_data[1:], columns=table_data[0])
    col_widths = compute_col_widths(temp_df, min_w=0.15, max_w=0.50)
    for i in range(len(table_data)):
        for j, width in enumerate(col_widths):
            table[(i, j)].set_width(width)

    # Style header row - professional theme
    for i in range(3):
        table[(0, i)].set_facecolor(WARP_DARK)
        table[(0, i)].set_text_props(weight='bold', color=WARP_WHITE, fontsize=13)
        table[(0, i)].set_edgecolor(WARP_BORDER)
        table[(0, i)].set_linewidth(2)

    # Style metric column and data cells with performance colors
    for i in range(1, len(table_data)):
        # Metric column (first column)
        table[(i, 0)].set_facecolor(WARP_DARK)
        # Use smaller font for rows with targets (OTP, OTD, Tracking)
        if i >= 3:  # OTP %, OTD %, Tracking % rows
            table[(i, 0)].set_text_props(weight='bold', color=WARP_WHITE, fontsize=10)
        else:  # Shipments, Routes rows
            table[(i, 0)].set_text_props(weight='bold', color=WARP_WHITE, fontsize=12)
        table[(i, 0)].set_edgecolor(WARP_BORDER)
        table[(i, 0)].set_linewidth(1.5)

        # Data columns with performance-based colors
        for j in range(1, 3):
            # Default color for non-performance metrics
            if i <= 2:  # Shipments and Routes rows
                row_color = WARP_GRAY if i % 2 == 0 else WARP_WHITE
                table[(i, j)].set_facecolor(row_color)
            else:  # OTP, OTD, Tracking rows (i = 3, 4, 5)
                # Get the metric name and values
                metric_names = ['OTP', 'OTD', 'Tracking']
                metric_idx = i - 3
                metric_name = metric_names[metric_idx]

                # Get value and target for this cell
                value, target = metrics_values[metric_name][j - 1]
                cell_color = get_performance_color(value, target)
                table[(i, j)].set_facecolor(cell_color)

            table[(i, j)].set_text_props(weight='bold', color=WARP_TEXT)
            table[(i, j)].set_edgecolor(WARP_BORDER)
            table[(i, j)].set_linewidth(1)

    # Add carrier name at top
    fig.text(0.5, 0.82, TARGET_CARRIER,
             ha='center', fontsize=14, fontweight='bold', style='italic', color=WARP_TEXT)

    pdf_pages.savefig(fig, facecolor=WARP_WHITE)
    plt.close()

    # ========================================================================
    # PAGE 3: PICKUP DELAY CODES (OTP)
    # ========================================================================
    fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_WHITE)

    # Title
    fig.text(0.5, 0.95, 'Pickup Delay Codes',
             ha='center', fontsize=18, fontweight='bold', color=WARP_DARK, transform=fig.transFigure)

    if len(carrier_pickup_delay_counts) > 0:
        # Create two subplots: table on left, pie chart on right
        ax1 = plt.subplot(1, 2, 1)
        ax1.axis('tight')
        ax1.axis('off')

        # Table with 3 columns - removed % of Total Routes
        table_data = [['Pickup\nDelay Code', 'Count', '% of Total\nShipments']]
        for _, row in carrier_pickup_delay_counts.iterrows():
            table_data.append([
                row['Pickup Delay Code'],
                str(row['Count']),
                f"{row['% of Total Shipments']:.1f}%"
            ])

        # Dynamic bbox sizing based on number of rows
        n_rows = len(table_data)  # includes header
        row_height = 0.08  # height per row
        max_height = 0.6   # maximum table height
        bbox_height = min(max_height, row_height * n_rows)
        bbox_y = 0.5 - bbox_height / 2  # center vertically

        table = ax1.table(cellText=table_data, cellLoc='left', loc='center',
                         bbox=[0, bbox_y, 1, bbox_height])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1)  # no artificial scaling

        # Dynamic column widths based on actual content
        temp_df = pd.DataFrame(table_data[1:], columns=table_data[0])
        col_widths = compute_col_widths(temp_df, min_w=0.10, max_w=0.70)
        for i in range(len(table_data)):
            for j, width in enumerate(col_widths):
                table[(i, j)].set_width(width)

        # Style header - professional theme
        for j in range(3):
            table[(0, j)].set_facecolor(WARP_DARK)
            table[(0, j)].set_text_props(weight='bold', color=WARP_WHITE, fontsize=10, wrap=True, ha='center', va='center')
            table[(0, j)].set_edgecolor(WARP_BORDER)
            table[(0, j)].set_linewidth(2)
            table[(0, j)].set_height(0.08)  # Increase header height to accommodate wrapped text

        # Style data rows with alternating colors
        for i in range(1, len(table_data)):
            row_color = WARP_GRAY if i % 2 == 0 else WARP_WHITE
            for j in range(3):
                table[(i, j)].set_facecolor(row_color)
                table[(i, j)].set_text_props(weight='bold', color=WARP_TEXT)
                table[(i, j)].set_edgecolor(WARP_BORDER)
                table[(i, j)].set_linewidth(1)
                # Center-align count and percentage columns
                if j > 0:
                    table[(i, j)].set_text_props(ha='center', weight='bold', color=WARP_TEXT)

        # Pie chart (using data with On-Time included)
        ax2 = plt.subplot(1, 2, 2)

        def autopct_format(pct):
            return f'{pct:.1f}%' if pct >= 5 else ''

        # Create color list: professional green for On-Time, then regular colors for delays
        pie_colors_with_ontime = ['#4CAF50'] + PIE_COLORS[:len(carrier_pickup_delay_counts)]

        wedges, texts, autotexts = ax2.pie(carrier_pickup_delay_counts_with_ontime['Count'],
                                            autopct=autopct_format,
                                            startangle=90,
                                            colors=pie_colors_with_ontime,
                                            wedgeprops={'edgecolor': WARP_WHITE, 'linewidth': 2})

        # Style percentage text
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(10)
            autotext.set_weight('bold')

        # Add "Total Shipments" text above legend
        ax2.text(0.5, -0.10, f'Total Shipments: {total_pickup_shipments}',
                ha='center', va='top', fontsize=11, fontweight='bold',
                color=WARP_TEXT, transform=ax2.transAxes)

        # Legend - positioned below the "Total Shipments" text
        ax2.legend(wedges, carrier_pickup_delay_counts_with_ontime['Pickup Delay Code'],
                  title="Pickup Status",
                  loc="upper center",
                  bbox_to_anchor=(0.5, -0.20),
                  fontsize=9,
                  ncol=2,
                  facecolor=WARP_WHITE,
                  edgecolor=WARP_BORDER,
                  labelcolor=WARP_TEXT)

        # Style legend title
        legend = ax2.get_legend()
        if legend:
            legend.get_title().set_color(WARP_DARK)
            legend.get_title().set_fontsize(10)
            legend.get_title().set_weight('bold')
    else:
        fig.text(0.5, 0.5, 'No pickup delay codes found',
                 ha='center', fontsize=14, fontweight='bold', style='italic', color=WARP_TEXT)

    pdf_pages.savefig(fig, facecolor=WARP_WHITE)
    plt.close()

    # ========================================================================
    # PAGE 4: PICKUP DELAY DETAILS (OTP)
    # ========================================================================
    if pickup_delay_details is not None and len(pickup_delay_details) > 0:
        # Pagination settings
        rows_per_page = 25
        total_rows = len(pickup_delay_details)
        total_pages = (total_rows + rows_per_page - 1) // rows_per_page  # Ceiling division

        for page_num in range(total_pages):
            start_idx = page_num * rows_per_page
            end_idx = min(start_idx + rows_per_page, total_rows)
            display_data = pickup_delay_details.iloc[start_idx:end_idx]

            fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_WHITE)

            # Title with page number
            if total_pages > 1:
                fig.text(0.5, 0.95, f'Pickup Delay Details - Page {page_num + 1} of {total_pages}',
                         ha='center', fontsize=18, fontweight='bold', color=WARP_DARK, transform=fig.transFigure)
            else:
                fig.text(0.5, 0.95, 'Pickup Delay Details',
                         ha='center', fontsize=18, fontweight='bold', color=WARP_DARK, transform=fig.transFigure)

            fig.text(0.5, 0.92, f'(Showing records {start_idx + 1}-{end_idx} of {total_rows} total)',
                     ha='center', fontsize=10, fontweight='bold', style='italic', color=WARP_TEXT, transform=fig.transFigure)

            ax = fig.add_subplot(111)
            ax.axis('tight')
            ax.axis('off')

            # Prepare table data
            table_data = [display_data.columns.tolist()]
            for _, row in display_data.iterrows():
                table_data.append([str(val) if not pd.isna(val) else '' for val in row])

            # Create table
            # Adjust bbox height based on number of rows to prevent oversized headers
            num_rows = len(table_data)
            bbox_height = min(0.85, 0.1 + (num_rows * 0.05))  # Dynamic height based on row count
            bbox_y = 0.85 - bbox_height  # Position from top
            table = ax.table(cellText=table_data, cellLoc='left', loc='center',
                            bbox=[0, bbox_y, 1, bbox_height])
            table.auto_set_font_size(False)
            table.set_fontsize(5.5)
            table.scale(1, 1.2)

            # Set custom column widths to prevent text cutoff
            # Dynamic column widths based on actual content
            col_widths = compute_col_widths(display_data)
            for i, width in enumerate(col_widths):
                for j in range(len(table_data)):
                    table[(j, i)].set_width(width)

            # Style header row - professional theme
            for i in range(len(display_data.columns)):
                table[(0, i)].set_facecolor(WARP_DARK)
                table[(0, i)].set_text_props(weight='bold', color=WARP_WHITE, fontsize=7, wrap=True, ha='center', va='center')
                table[(0, i)].set_edgecolor(WARP_BORDER)
                table[(0, i)].set_linewidth(1.5)

            # Set header height to allow for wrapped text
            for i in range(len(display_data.columns)):
                table[(0, i)].set_height(0.04)

            # Style data rows with alternating colors
            for i in range(1, len(table_data)):
                row_color = WARP_GRAY if i % 2 == 0 else WARP_WHITE
                for j in range(len(display_data.columns)):
                    table[(i, j)].set_facecolor(row_color)
                    table[(i, j)].set_edgecolor(WARP_BORDER)
                    table[(i, j)].set_linewidth(0.5)
                    # Enable text wrapping for all cells
                    table[(i, j)].set_text_props(wrap=True, weight='bold', color=WARP_TEXT)

            pdf_pages.savefig(fig, facecolor=WARP_WHITE)
            plt.close()

    # ========================================================================
    # PAGE 5: DELIVERY DELAY CODES (OTD)
    # ========================================================================
    fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_WHITE)

    # Title
    fig.text(0.5, 0.95, 'Delivery Delay Codes',
             ha='center', fontsize=18, fontweight='bold', color=WARP_DARK, transform=fig.transFigure)

    if len(carrier_delay_counts) > 0:
        # Create two subplots: table on left, pie chart on right
        ax1 = plt.subplot(1, 2, 1)
        ax1.axis('tight')
        ax1.axis('off')

        # Table with 3 columns - removed % of Total Routes
        table_data = [['Delivery\nDelay Code', 'Count', '% of Total\nShipments']]
        for _, row in carrier_delay_counts.iterrows():
            table_data.append([
                row['Delivery Delay Code'],
                str(row['Count']),
                f"{row['% of Total Shipments']:.1f}%"
            ])

        # Dynamic bbox sizing based on number of rows
        n_rows = len(table_data)  # includes header
        row_height = 0.08  # height per row
        max_height = 0.6   # maximum table height
        bbox_height = min(max_height, row_height * n_rows)
        bbox_y = 0.5 - bbox_height / 2  # center vertically

        table = ax1.table(cellText=table_data, cellLoc='left', loc='center',
                         bbox=[0, bbox_y, 1, bbox_height])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1)  # no artificial scaling

        # Dynamic column widths based on actual content
        temp_df = pd.DataFrame(table_data[1:], columns=table_data[0])
        col_widths = compute_col_widths(temp_df, min_w=0.10, max_w=0.70)
        for i in range(len(table_data)):
            for j, width in enumerate(col_widths):
                table[(i, j)].set_width(width)

        # Style header - professional theme
        for j in range(3):
            table[(0, j)].set_facecolor(WARP_DARK)
            table[(0, j)].set_text_props(weight='bold', color=WARP_WHITE, fontsize=10, wrap=True, ha='center', va='center')
            table[(0, j)].set_edgecolor(WARP_BORDER)
            table[(0, j)].set_linewidth(2)
            table[(0, j)].set_height(0.08)  # Increase header height to accommodate wrapped text

        # Style data rows with alternating colors
        for i in range(1, len(table_data)):
            row_color = WARP_GRAY if i % 2 == 0 else WARP_WHITE
            for j in range(3):
                table[(i, j)].set_facecolor(row_color)
                table[(i, j)].set_text_props(weight='bold', color=WARP_TEXT)
                table[(i, j)].set_edgecolor(WARP_BORDER)
                table[(i, j)].set_linewidth(1)
                # Center-align count and percentage columns
                if j > 0:
                    table[(i, j)].set_text_props(ha='center', weight='bold', color=WARP_TEXT)

        # Pie chart (using data with On-Time included)
        ax2 = plt.subplot(1, 2, 2)

        def autopct_format(pct):
            return f'{pct:.1f}%' if pct >= 5 else ''

        # Create color list: professional green for On-Time, then regular colors for delays
        pie_colors_with_ontime = ['#4CAF50'] + PIE_COLORS[:len(carrier_delay_counts)]

        wedges, texts, autotexts = ax2.pie(carrier_delay_counts_with_ontime['Count'],
                                            autopct=autopct_format,
                                            startangle=90,
                                            colors=pie_colors_with_ontime,
                                            wedgeprops={'edgecolor': WARP_WHITE, 'linewidth': 2})

        # Style percentage text
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(10)
            autotext.set_weight('bold')

        # Add "Total Shipments" text above legend
        ax2.text(0.5, -0.10, f'Total Shipments: {total_delivery_shipments}',
                ha='center', va='top', fontsize=11, fontweight='bold',
                color=WARP_TEXT, transform=ax2.transAxes)

        # Legend - positioned below the "Total Shipments" text
        ax2.legend(wedges, carrier_delay_counts_with_ontime['Delivery Delay Code'],
                  title="Delivery Status",
                  loc="upper center",
                  bbox_to_anchor=(0.5, -0.20),
                  fontsize=9,
                  ncol=2,
                  facecolor=WARP_WHITE,
                  edgecolor=WARP_BORDER,
                  labelcolor=WARP_TEXT)

        # Style legend title
        legend = ax2.get_legend()
        if legend:
            legend.get_title().set_color(WARP_DARK)
            legend.get_title().set_fontsize(10)
            legend.get_title().set_weight('bold')
    else:
        fig.text(0.5, 0.5, 'No delivery delay codes found',
                 ha='center', fontsize=14, fontweight='bold', style='italic', color=WARP_TEXT)

    pdf_pages.savefig(fig, facecolor=WARP_WHITE)
    plt.close()

    # ========================================================================
    # PAGE 6+: DELIVERY DELAY DETAILS TABLE (OTD - PAGINATED)
    # ========================================================================
    if delivery_delay_details is not None and len(delivery_delay_details) > 0:
        # Pagination settings
        rows_per_page = 25
        total_rows = len(delivery_delay_details)
        total_pages = (total_rows + rows_per_page - 1) // rows_per_page  # Ceiling division

        for page_num in range(total_pages):
            start_idx = page_num * rows_per_page
            end_idx = min(start_idx + rows_per_page, total_rows)
            display_data = delivery_delay_details.iloc[start_idx:end_idx]

            fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_WHITE)

            # Title with page number
            if total_pages > 1:
                fig.text(0.5, 0.95, f'Delivery Delay Details - Page {page_num + 1} of {total_pages}',
                         ha='center', fontsize=18, fontweight='bold', color=WARP_DARK, transform=fig.transFigure)
            else:
                fig.text(0.5, 0.95, 'Delivery Delay Details',
                         ha='center', fontsize=18, fontweight='bold', color=WARP_DARK, transform=fig.transFigure)

            fig.text(0.5, 0.92, f'(Showing records {start_idx + 1}-{end_idx} of {total_rows} total)',
                     ha='center', fontsize=10, fontweight='bold', style='italic', color=WARP_TEXT, transform=fig.transFigure)

            ax = fig.add_subplot(111)
            ax.axis('tight')
            ax.axis('off')

            # Prepare table data
            table_data = [display_data.columns.tolist()]
            for _, row in display_data.iterrows():
                table_data.append([str(val) if not pd.isna(val) else '' for val in row])

            # Create table
            # Adjust bbox height based on number of rows to prevent oversized headers
            num_rows = len(table_data)
            bbox_height = min(0.85, 0.1 + (num_rows * 0.05))  # Dynamic height based on row count
            bbox_y = 0.85 - bbox_height  # Position from top
            table = ax.table(cellText=table_data, cellLoc='left', loc='center',
                            bbox=[0, bbox_y, 1, bbox_height])
            table.auto_set_font_size(False)
            table.set_fontsize(5.5)
            table.scale(1, 1.2)

            # Set custom column widths to prevent text cutoff
            # Dynamic column widths based on actual content
            col_widths = compute_col_widths(display_data)
            for i, width in enumerate(col_widths):
                for j in range(len(table_data)):
                    table[(j, i)].set_width(width)

            # Style header row - professional theme
            for i in range(len(display_data.columns)):
                table[(0, i)].set_facecolor(WARP_DARK)
                table[(0, i)].set_text_props(weight='bold', color=WARP_WHITE, fontsize=7, wrap=True, ha='center', va='center')
                table[(0, i)].set_edgecolor(WARP_BORDER)
                table[(0, i)].set_linewidth(1.5)

            # Set header height to allow for wrapped text
            for i in range(len(display_data.columns)):
                table[(0, i)].set_height(0.04)

            # Style data rows with alternating colors
            for i in range(1, len(table_data)):
                row_color = WARP_GRAY if i % 2 == 0 else WARP_WHITE
                for j in range(len(display_data.columns)):
                    table[(i, j)].set_facecolor(row_color)
                    table[(i, j)].set_edgecolor(WARP_BORDER)
                    table[(i, j)].set_linewidth(0.5)
                    # Enable text wrapping for all cells
                    table[(i, j)].set_text_props(wrap=True, weight='bold', color=WARP_TEXT)

            pdf_pages.savefig(fig, facecolor=WARP_WHITE)
            plt.close()

    print(f"\n✅ PDF report generated successfully!")
    print(f"   📄 File: {OUTPUT_PDF}")

except Exception as e:
    print(f"\n❌ Error generating PDF: {e}")
    import traceback
    traceback.print_exc()
finally:
    pdf_pages.close()

# ============================================================================
# STEP 7: EMAIL REPORT
# ============================================================================
print("\n" + "=" * 80)
print("EMAIL FUNCTIONALITY")
print("=" * 80)

if SEND_EMAIL:
    try:
        # Initialize Resend
        resend.api_key = RESEND_API_KEY

        # Read the PDF file
        with open(OUTPUT_PDF, 'rb') as f:
            pdf_content = f.read()

        # Prepare email
        # Support both single email (string) and multiple emails (list)
        email_to = EMAIL_TO if isinstance(EMAIL_TO, list) else [EMAIL_TO]

        email_body = f"""
        <html>
        <body>
            <h2>Carrier Performance Report</h2>
            <p>Dear {TARGET_CARRIER},</p>

            <p>Please find attached your carrier performance report for the past 2 weeks.</p>

            <p>If you have any questions about this report, please contact us.</p>

            <p>Best regards,<br>
            Warp Team</p>
        </body>
        </html>
        """

        # Send email with attachment
        params = {
            "from": EMAIL_FROM,
            "to": email_to,
            "subject": EMAIL_SUBJECT,
            "html": email_body,
            "attachments": [
                {
                    "filename": OUTPUT_PDF,
                    "content": list(pdf_content)
                }
            ]
        }

        print(f"📧 Sending email to: {', '.join(email_to)}")
        print(f"   From: {EMAIL_FROM}")
        print(f"   Subject: {EMAIL_SUBJECT}")

        response = resend.Emails.send(params)

        print(f"✅ Email sent successfully!")
        print(f"   Email ID: {response['id']}")

    except Exception as e:
        print(f"❌ Error sending email: {e}")
        import traceback
        traceback.print_exc()
else:
    print("⏸️  Email sending is disabled (SEND_EMAIL = False)")
    print(f"   To enable, set SEND_EMAIL = True in the configuration")

print("\n" + "=" * 80)
print("REPORT GENERATION COMPLETE")
print("=" * 80)
print(f"✅ Report saved to: {OUTPUT_PDF}")
print(f"✅ Data saved to: otp_data.pkl and otp_data.csv")

