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

print(f"✅ Found {len(carrier_delay_data):,} shipments with delivery delay codes")
print(f"   Unique delay codes: {len(carrier_delay_counts)}")

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

print(f"✅ Found {len(carrier_pickup_delay_data):,} shipments with pickup delay codes")
print(f"   Unique delay codes: {len(carrier_pickup_delay_counts)}")

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
        'pickTimeDeparted',
        'pickTimeArrived',
        'Pickup Window',
        'isTracking'
    ]].copy()

    pickup_delay_details.columns = [
        'Order Code',
        'Pickup Delay Code',
        'Lane',
        'Pick Departed',
        'Pick Arrived',
        'Pickup Window',
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
        'dropTimeDeparted',
        'dropTimeArrived',
        'Drop Window',
        'isTracking'
    ]].copy()

    delivery_delay_details.columns = [
        'Order Code',
        'Delivery Delay Code',
        'Lane',
        'Drop Departed',
        'Drop Arrived',
        'Drop Window',
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

# Define WARP color scheme
WARP_GREEN = '#00FF41'  # Neon green accent
WARP_DARK = '#1A1A1A'   # Dark background
WARP_GRAY = '#2D2D2D'   # Lighter gray for alternating rows
WARP_WHITE = '#FFFFFF'  # White text/background
WARP_BORDER = '#404040' # Border color

# Define professional pie chart color palette (Dark Professional)
PIE_COLORS = ['#4A90E2', '#7B68EE', '#50C878', '#F4A460', '#E57373', '#9575CD',
              '#64B5F6', '#BA68C8', '#81C784', '#FFB74D']

# Create PDF
pdf_pages = PdfPages(OUTPUT_PDF)

try:
    # ========================================================================
    # PAGE 1: TITLE PAGE
    # ========================================================================
    fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_DARK)

    fig.text(0.5, 0.7, f'Carrier Performance Report',
             ha='center', fontsize=24, fontweight='bold', color=WARP_GREEN)
    fig.text(0.5, 0.6, f'{TARGET_CARRIER}',
             ha='center', fontsize=20, fontweight='bold', color=WARP_WHITE)
    fig.text(0.5, 0.5, f'Weeks {weeks[0]} & {weeks[1]}',
             ha='center', fontsize=16, fontweight='bold', color=WARP_WHITE)
    fig.text(0.5, 0.4, f'Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}',
             ha='center', fontsize=12, fontweight='bold', style='italic', color=WARP_WHITE)

    plt.axis('off')
    pdf_pages.savefig(fig, facecolor=WARP_DARK)
    plt.close()

    # ========================================================================
    # PAGE 2: PERFORMANCE METRICS TABLE
    # ========================================================================
    fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_DARK)

    # Title
    fig.text(0.5, 0.92, 'Performance Metrics',
             ha='center', fontsize=18, fontweight='bold', color=WARP_GREEN)

    # Create a more structured table layout
    ax = fig.add_subplot(111)
    ax.axis('off')

    # Prepare simplified table data - transpose for better readability
    table_data = []

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
    val_w0 = carrier_result_df[('OTP %', f'W{weeks[0]}')].values[0]
    val_w1 = carrier_result_df[('OTP %', f'W{weeks[1]}')].values[0]
    table_data.append(['OTP %', f'{val_w0:.1f}%' if not pd.isna(val_w0) else '-',
                       f'{val_w1:.1f}%' if not pd.isna(val_w1) else '-'])

    # OTD %
    val_w0 = carrier_result_df[('OTD %', f'W{weeks[0]}')].values[0]
    val_w1 = carrier_result_df[('OTD %', f'W{weeks[1]}')].values[0]
    table_data.append(['OTD %', f'{val_w0:.1f}%' if not pd.isna(val_w0) else '-',
                       f'{val_w1:.1f}%' if not pd.isna(val_w1) else '-'])

    # Tracking %
    val_w0 = carrier_result_df[('Tracking %', f'W{weeks[0]}')].values[0]
    val_w1 = carrier_result_df[('Tracking %', f'W{weeks[1]}')].values[0]
    table_data.append(['Tracking %', f'{val_w0:.1f}%' if not pd.isna(val_w0) else '-',
                       f'{val_w1:.1f}%' if not pd.isna(val_w1) else '-'])

    # Create table
    table = ax.table(cellText=table_data, cellLoc='center', loc='center',
                     bbox=[0.2, 0.3, 0.6, 0.5])
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.scale(1, 3)

    # Style header row - WARP theme
    for i in range(3):
        table[(0, i)].set_facecolor(WARP_DARK)
        table[(0, i)].set_text_props(weight='bold', color=WARP_GREEN, fontsize=13)
        table[(0, i)].set_edgecolor(WARP_BORDER)
        table[(0, i)].set_linewidth(2)

    # Style metric column and add alternating row colors
    for i in range(1, len(table_data)):
        # Metric column (first column)
        table[(i, 0)].set_facecolor(WARP_DARK)
        table[(i, 0)].set_text_props(weight='bold', color=WARP_GREEN)
        table[(i, 0)].set_edgecolor(WARP_BORDER)
        table[(i, 0)].set_linewidth(1.5)

        # Data columns with alternating colors
        row_color = WARP_GRAY if i % 2 == 0 else WARP_DARK
        for j in range(1, 3):
            table[(i, j)].set_facecolor(row_color)
            table[(i, j)].set_text_props(weight='bold', color=WARP_WHITE)
            table[(i, j)].set_edgecolor(WARP_BORDER)
            table[(i, j)].set_linewidth(1)

    # Add carrier name at top
    fig.text(0.5, 0.82, TARGET_CARRIER,
             ha='center', fontsize=14, fontweight='bold', style='italic', color=WARP_WHITE)

    pdf_pages.savefig(fig, facecolor=WARP_DARK)
    plt.close()

    # ========================================================================
    # PAGE 3: DELIVERY DELAY CODES
    # ========================================================================
    fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_DARK)

    # Title
    fig.text(0.5, 0.95, 'Delivery Delay Codes',
             ha='center', fontsize=18, fontweight='bold', color=WARP_GREEN, transform=fig.transFigure)

    if len(carrier_delay_counts) > 0:
        # Create two subplots: table on left, pie chart on right
        ax1 = plt.subplot(1, 2, 1)
        ax1.axis('tight')
        ax1.axis('off')

        # Table
        table_data = [['Delivery Delay Code', 'Count']]
        for _, row in carrier_delay_counts.iterrows():
            table_data.append([row['Delivery Delay Code'], str(row['Count'])])

        table = ax1.table(cellText=table_data, cellLoc='left', loc='center',
                         bbox=[0, 0.2, 1, 0.6])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2)

        # Set column widths - wider for delay code column
        for i in range(len(table_data)):
            table[(i, 0)].set_width(0.75)  # Delay Code column - wider
            table[(i, 1)].set_width(0.25)  # Count column - narrower

        # Style header - WARP theme
        table[(0, 0)].set_facecolor(WARP_DARK)
        table[(0, 0)].set_text_props(weight='bold', color=WARP_GREEN, fontsize=11)
        table[(0, 0)].set_edgecolor(WARP_BORDER)
        table[(0, 0)].set_linewidth(2)
        table[(0, 1)].set_facecolor(WARP_DARK)
        table[(0, 1)].set_text_props(weight='bold', color=WARP_GREEN, fontsize=11)
        table[(0, 1)].set_edgecolor(WARP_BORDER)
        table[(0, 1)].set_linewidth(2)

        # Style data rows with alternating colors
        for i in range(1, len(table_data)):
            row_color = WARP_GRAY if i % 2 == 0 else WARP_DARK
            table[(i, 0)].set_facecolor(row_color)
            table[(i, 0)].set_text_props(weight='bold', color=WARP_WHITE)
            table[(i, 0)].set_edgecolor(WARP_BORDER)
            table[(i, 0)].set_linewidth(1)
            table[(i, 1)].set_facecolor(row_color)
            table[(i, 1)].set_text_props(weight='bold', color=WARP_WHITE)
            table[(i, 1)].set_edgecolor(WARP_BORDER)
            table[(i, 1)].set_linewidth(1)
            # Center-align the count column
            table[(i, 1)].set_text_props(ha='center', weight='bold', color=WARP_WHITE)

        # Pie chart
        ax2 = plt.subplot(1, 2, 2)

        def autopct_format(pct):
            return f'{pct:.1f}%' if pct >= 5 else ''

        wedges, texts, autotexts = ax2.pie(carrier_delay_counts['Count'],
                                            autopct=autopct_format,
                                            startangle=90,
                                            colors=PIE_COLORS,
                                            wedgeprops={'edgecolor': WARP_DARK, 'linewidth': 2})

        # Style percentage text
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(10)
            autotext.set_weight('bold')

        # Legend - positioned below the pie chart
        ax2.legend(wedges, carrier_delay_counts['Delivery Delay Code'],
                  title="Delay Codes",
                  loc="upper center",
                  bbox_to_anchor=(0.5, -0.05),
                  fontsize=9,
                  ncol=2,
                  facecolor=WARP_DARK,
                  edgecolor=WARP_BORDER,
                  labelcolor=WARP_WHITE)

        # Style legend title
        legend = ax2.get_legend()
        if legend:
            legend.get_title().set_color(WARP_GREEN)
            legend.get_title().set_fontsize(10)
            legend.get_title().set_weight('bold')
    else:
        fig.text(0.5, 0.5, 'No delivery delay codes found',
                 ha='center', fontsize=14, fontweight='bold', style='italic', color=WARP_WHITE)

    pdf_pages.savefig(fig, facecolor=WARP_DARK)
    plt.close()

    # ========================================================================
    # PAGE 4: PICKUP DELAY CODES
    # ========================================================================
    fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_DARK)

    # Title
    fig.text(0.5, 0.95, 'Pickup Delay Codes',
             ha='center', fontsize=18, fontweight='bold', color=WARP_GREEN, transform=fig.transFigure)

    if len(carrier_pickup_delay_counts) > 0:
        # Create two subplots: table on left, pie chart on right
        ax1 = plt.subplot(1, 2, 1)
        ax1.axis('tight')
        ax1.axis('off')

        # Table
        table_data = [['Pickup Delay Code', 'Count']]
        for _, row in carrier_pickup_delay_counts.iterrows():
            table_data.append([row['Pickup Delay Code'], str(row['Count'])])

        table = ax1.table(cellText=table_data, cellLoc='left', loc='center',
                         bbox=[0, 0.2, 1, 0.6])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2)

        # Set column widths - wider for delay code column
        for i in range(len(table_data)):
            table[(i, 0)].set_width(0.75)  # Delay Code column - wider
            table[(i, 1)].set_width(0.25)  # Count column - narrower

        # Style header - WARP theme
        table[(0, 0)].set_facecolor(WARP_DARK)
        table[(0, 0)].set_text_props(weight='bold', color=WARP_GREEN, fontsize=11)
        table[(0, 0)].set_edgecolor(WARP_BORDER)
        table[(0, 0)].set_linewidth(2)
        table[(0, 1)].set_facecolor(WARP_DARK)
        table[(0, 1)].set_text_props(weight='bold', color=WARP_GREEN, fontsize=11)
        table[(0, 1)].set_edgecolor(WARP_BORDER)
        table[(0, 1)].set_linewidth(2)

        # Style data rows with alternating colors
        for i in range(1, len(table_data)):
            row_color = WARP_GRAY if i % 2 == 0 else WARP_DARK
            table[(i, 0)].set_facecolor(row_color)
            table[(i, 0)].set_text_props(weight='bold', color=WARP_WHITE)
            table[(i, 0)].set_edgecolor(WARP_BORDER)
            table[(i, 0)].set_linewidth(1)
            table[(i, 1)].set_facecolor(row_color)
            table[(i, 1)].set_text_props(weight='bold', color=WARP_WHITE)
            table[(i, 1)].set_edgecolor(WARP_BORDER)
            table[(i, 1)].set_linewidth(1)
            # Center-align the count column
            table[(i, 1)].set_text_props(ha='center', weight='bold', color=WARP_WHITE)

        # Pie chart
        ax2 = plt.subplot(1, 2, 2)

        def autopct_format(pct):
            return f'{pct:.1f}%' if pct >= 5 else ''

        wedges, texts, autotexts = ax2.pie(carrier_pickup_delay_counts['Count'],
                                            autopct=autopct_format,
                                            startangle=90,
                                            colors=PIE_COLORS,
                                            wedgeprops={'edgecolor': WARP_DARK, 'linewidth': 2})

        # Style percentage text
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(10)
            autotext.set_weight('bold')

        # Legend - positioned below the pie chart
        ax2.legend(wedges, carrier_pickup_delay_counts['Pickup Delay Code'],
                  title="Delay Codes",
                  loc="upper center",
                  bbox_to_anchor=(0.5, -0.05),
                  fontsize=9,
                  ncol=2,
                  facecolor=WARP_DARK,
                  edgecolor=WARP_BORDER,
                  labelcolor=WARP_WHITE)

        # Style legend title
        legend = ax2.get_legend()
        if legend:
            legend.get_title().set_color(WARP_GREEN)
            legend.get_title().set_fontsize(10)
            legend.get_title().set_weight('bold')
    else:
        fig.text(0.5, 0.5, 'No pickup delay codes found',
                 ha='center', fontsize=14, fontweight='bold', style='italic', color=WARP_WHITE)

    pdf_pages.savefig(fig, facecolor=WARP_DARK)
    plt.close()

    # ========================================================================
    # PAGE 5+: PICKUP DELAY DETAILS TABLE (PAGINATED)
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

            fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_DARK)

            # Title with page number
            if total_pages > 1:
                fig.text(0.5, 0.95, f'Pickup Delay Details - Page {page_num + 1} of {total_pages}',
                         ha='center', fontsize=18, fontweight='bold', color=WARP_GREEN, transform=fig.transFigure)
            else:
                fig.text(0.5, 0.95, 'Pickup Delay Details',
                         ha='center', fontsize=18, fontweight='bold', color=WARP_GREEN, transform=fig.transFigure)

            fig.text(0.5, 0.92, f'(Showing records {start_idx + 1}-{end_idx} of {total_rows} total)',
                     ha='center', fontsize=10, fontweight='bold', style='italic', color=WARP_WHITE, transform=fig.transFigure)

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
            # Columns: Order Code, Pickup Delay Code, Lane,
            #          Pick Departed, Pick Arrived, Pickup Window, Tracking
            col_widths = [0.11, 0.14, 0.24, 0.13, 0.13, 0.18, 0.07]
            for i, width in enumerate(col_widths):
                for j in range(len(table_data)):
                    table[(j, i)].set_width(width)

            # Style header row - WARP theme
            for i in range(len(display_data.columns)):
                table[(0, i)].set_facecolor(WARP_DARK)
                table[(0, i)].set_text_props(weight='bold', color=WARP_GREEN, fontsize=7, wrap=True, ha='center', va='center')
                table[(0, i)].set_edgecolor(WARP_BORDER)
                table[(0, i)].set_linewidth(1.5)

            # Set header height to allow for wrapped text
            for i in range(len(display_data.columns)):
                table[(0, i)].set_height(0.04)

            # Style data rows with alternating colors
            for i in range(1, len(table_data)):
                row_color = WARP_GRAY if i % 2 == 0 else WARP_DARK
                for j in range(len(display_data.columns)):
                    table[(i, j)].set_facecolor(row_color)
                    table[(i, j)].set_edgecolor(WARP_BORDER)
                    table[(i, j)].set_linewidth(0.5)
                    # Enable text wrapping for all cells
                    table[(i, j)].set_text_props(wrap=True, weight='bold', color=WARP_WHITE)

            pdf_pages.savefig(fig, facecolor=WARP_DARK)
            plt.close()

    # ========================================================================
    # PAGE 6+: DELIVERY DELAY DETAILS TABLE (PAGINATED)
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

            fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_DARK)

            # Title with page number
            if total_pages > 1:
                fig.text(0.5, 0.95, f'Delivery Delay Details - Page {page_num + 1} of {total_pages}',
                         ha='center', fontsize=18, fontweight='bold', color=WARP_GREEN, transform=fig.transFigure)
            else:
                fig.text(0.5, 0.95, 'Delivery Delay Details',
                         ha='center', fontsize=18, fontweight='bold', color=WARP_GREEN, transform=fig.transFigure)

            fig.text(0.5, 0.92, f'(Showing records {start_idx + 1}-{end_idx} of {total_rows} total)',
                     ha='center', fontsize=10, fontweight='bold', style='italic', color=WARP_WHITE, transform=fig.transFigure)

            ax = fig.add_subplot(111)
            ax.axis('tight')
            ax.axis('off')

            # Prepare table data
            table_data = [display_data.columns.tolist()]
            for _, row in display_data.iterrows():
                table_data.append([str(val) if not pd.isna(val) else '' for val in row])

            # Create table
            table = ax.table(cellText=table_data, cellLoc='left', loc='center',
                            bbox=[0, 0, 1, 0.85])
            table.auto_set_font_size(False)
            table.set_fontsize(5.5)
            table.scale(1, 1.2)

            # Set custom column widths to prevent text cutoff
            # Columns: Order Code, Delivery Delay Code, Lane,
            #          Drop Departed, Drop Arrived, Drop Window, Tracking
            col_widths = [0.11, 0.14, 0.24, 0.13, 0.13, 0.18, 0.07]
            for i, width in enumerate(col_widths):
                for j in range(len(table_data)):
                    table[(j, i)].set_width(width)

            # Style header row - WARP theme
            for i in range(len(display_data.columns)):
                table[(0, i)].set_facecolor(WARP_DARK)
                table[(0, i)].set_text_props(weight='bold', color=WARP_GREEN, fontsize=7, wrap=True, ha='center', va='center')
                table[(0, i)].set_edgecolor(WARP_BORDER)
                table[(0, i)].set_linewidth(1.5)

            # Set header height to allow for wrapped text
            for i in range(len(display_data.columns)):
                table[(0, i)].set_height(0.06)

            # Style data rows with alternating colors
            for i in range(1, len(table_data)):
                row_color = WARP_GRAY if i % 2 == 0 else WARP_DARK
                for j in range(len(display_data.columns)):
                    table[(i, j)].set_facecolor(row_color)
                    table[(i, j)].set_edgecolor(WARP_BORDER)
                    table[(i, j)].set_linewidth(0.5)
                    # Enable text wrapping for all cells
                    table[(i, j)].set_text_props(wrap=True, weight='bold', color=WARP_WHITE)

            pdf_pages.savefig(fig, facecolor=WARP_DARK)
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

