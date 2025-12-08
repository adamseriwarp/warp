"""
Report generation functions for Carrier Performance Reports
Refactored from query_otp_clean.py
"""

import pandas as pd
import mysql.connector
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import datetime
from matplotlib.backends.backend_pdf import PdfPages
import io
import streamlit as st

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
        # Handle newlines in column names by taking the longest line
        col_name_len = max(len(line) for line in str(col).split('\n'))
        lens = df[col].astype(str).map(len)
        max_lens.append(max(lens.max(), col_name_len))

    # Calculate proportional widths
    total = sum(max_lens)
    widths = [l/total for l in max_lens]

    # Apply min/max constraints
    widths = [min(max(w, min_w), max_w) for w in widths]

    # Renormalize to sum to 1.0
    s = sum(widths)
    return [w/s for w in widths]

# ============================================================================
# DATABASE CONNECTION
# ============================================================================

def get_db_connection():
    """Create database connection"""
    # Try to use Streamlit secrets first (for cloud deployment)
    # Fall back to hardcoded values for local development
    try:
        db_config = st.secrets["database"]
        return mysql.connector.connect(
            host=db_config["host"],
            user=db_config["user"],
            password=db_config["password"],
            database=db_config["database"]
        )
    except (KeyError, FileNotFoundError):
        # Fallback for local development
        return mysql.connector.connect(
            host='datahub-mysql.wearewarp.link',
            user='datahub-read',
            password='warpdbhub2',
            database='datahub'
        )

# ============================================================================
# DATA LOADING AND PROCESSING
# ============================================================================

@st.cache_data(ttl=1800)  # Cache for 30 minutes
def load_and_process_data(carrier_name, weeks):
    """
    Load data from database and process it

    Args:
        carrier_name: Name of the carrier to filter
        weeks: List of week numbers to analyze

    Returns:
        Processed DataFrame
    """
    conn = get_db_connection()

    # Build dynamic SQL query with carrier filter
    # Note: We filter by carrier in SQL, but filter by weeks in Python
    # This is because MySQL WEEK() and Python isocalendar().week use different systems

    # Use parameterized query to prevent SQL injection
    query = """
        SELECT *
        FROM otp_reports
        WHERE LOWER(carrierName) = LOWER(%(carrier_name)s)
        AND STR_TO_DATE(pickWindowFrom, '%m/%d/%Y %H:%i:%s') >= '2025-01-01'
        ORDER BY id DESC
    """

    # Execute query with parameters
    df = pd.read_sql(query, conn, params={'carrier_name': carrier_name})

    conn.close()

    # Debug: Show how many rows were loaded
    print(f"DEBUG: Loaded {len(df)} rows for carrier '{carrier_name}'")

    # Convert date fields
    df['pickWindowFrom_dt'] = pd.to_datetime(df['pickWindowFrom'], errors='coerce')
    df['dropWindowFrom_dt'] = pd.to_datetime(df['dropWindowFrom'], errors='coerce')
    df['createdAt_dt'] = pd.to_datetime(df['createdAt'], errors='coerce')
    df['updatedAt_dt'] = pd.to_datetime(df['updatedAt'], errors='coerce')
    df['pickTimeArrived_dt'] = pd.to_datetime(df['pickTimeArrived'], errors='coerce')
    df['pickWindowTo_dt'] = pd.to_datetime(df['pickWindowTo'], errors='coerce')
    df['dropTimeArrived_dt'] = pd.to_datetime(df['dropTimeArrived'], errors='coerce')
    df['dropWindowTo_dt'] = pd.to_datetime(df['dropWindowTo'], errors='coerce')

    # Calculate OTP and OTD
    df['OTP'] = df.apply(calculate_otp, axis=1)
    df['OTD'] = df.apply(calculate_otd, axis=1)

    # Add deduplication logic
    df = add_deduplication_flags(df)

    # Impute missing delay codes
    df = impute_delay_codes(df)

    # Add week number
    df['week_number'] = df['pickWindowFrom_dt'].dt.isocalendar().week

    # Debug: Show week distribution
    if len(df) > 0:
        print(f"DEBUG: Week distribution: {df['week_number'].value_counts().to_dict()}")
        print(f"DEBUG: Filtering for weeks: {weeks}")

    # Filter for selected weeks (carrier already filtered in SQL)
    df_filtered = df[df['week_number'].isin(weeks)].copy()

    # Debug: Show filtered results
    print(f"DEBUG: After week filtering: {len(df_filtered)} rows")

    # Add lowercase column for consistency
    df_filtered['carrierName_lower'] = df_filtered['carrierName'].str.lower()

    return df_filtered

def calculate_otp(row):
    """Calculate On Time Pickup"""
    if pd.isna(row['pickTimeArrived_dt']) or pd.isna(row['pickWindowTo_dt']):
        return None
    return 'On Time' if row['pickTimeArrived_dt'] < row['pickWindowTo_dt'] else 'Late'

def calculate_otd(row):
    """Calculate On Time Delivery"""
    if pd.isna(row['dropTimeArrived_dt']) or pd.isna(row['dropWindowTo_dt']):
        return None
    return 'On Time' if row['dropTimeArrived_dt'] < row['dropWindowTo_dt'] else 'Late'

def add_deduplication_flags(df):
    """Add deduplication flags to dataframe"""
    df['pickDate'] = df['pickTimeArrived_dt'].dt.date
    df['dropDate'] = df['dropTimeArrived_dt'].dt.date
    
    df = df.sort_values(['pickTimeArrived_dt', 'dropTimeArrived_dt'], na_position='last')
    
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
    
    df['keep_for_pickup'] = ~df.duplicated(subset=['pickup_dedup_key'], keep='first')
    df['keep_for_delivery'] = ~df.duplicated(subset=['delivery_dedup_key'], keep='first')
    
    return df

def impute_delay_codes(df):
    """Impute missing delay codes with 'Carrier Failure'"""
    df.loc[(df['OTP'] == 'Late') &
           ((df['pickupDelayCode'].isna()) | (df['pickupDelayCode'] == '')),
           'pickupDelayCode'] = 'Carrier Failure'
    
    df.loc[(df['OTD'] == 'Late') &
           ((df['deliveryDelayCode'].isna()) | (df['deliveryDelayCode'] == '')),
           'deliveryDelayCode'] = 'Carrier Failure'
    
    return df

# ============================================================================
# METRICS CALCULATION
# ============================================================================

def calculate_performance_metrics(df, carrier_name, weeks):
    """
    Calculate performance metrics for the carrier

    Returns:
        DataFrame with performance metrics
    """
    row_data = {'Carrier': carrier_name}

    for week in weeks:
        week_data = df[df['week_number'] == week]

        # Shipment count
        completed_shipments = week_data[(week_data['dropStatus'] == 'Succeeded') &
                                         (week_data['keep_for_delivery'] == True)]
        shipments = len(completed_shipments)

        # Routes count
        routes = week_data[week_data['loadStatus'] == 'Completed']['loadId'].nunique()

        # OTP %
        otp_data = week_data[(week_data['OTP'].notna()) &
                              (week_data['keep_for_pickup'] == True) &
                              (week_data['pickStatus'] == 'Succeeded')]
        if len(otp_data) > 0:
            otp_pct = (otp_data['OTP'] == 'On Time').sum() / len(otp_data) * 100
        else:
            otp_pct = None

        # OTD %
        otd_data = week_data[(week_data['OTD'].notna()) &
                              (week_data['keep_for_delivery'] == True) &
                              (week_data['dropStatus'] == 'Succeeded')]
        if len(otd_data) > 0:
            otd_pct = (otd_data['OTD'] == 'On Time').sum() / len(otd_data) * 100
        else:
            otd_pct = None

        # Tracking %
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

    # Reorder columns
    ordered_cols = []
    for metric in ['Shipments', 'Routes', 'OTP', 'OTD', 'Tracking']:
        for week in weeks:
            ordered_cols.append(f'{metric}_W{week}')

    carrier_result_df = carrier_result_df[ordered_cols]

    # Create multi-level columns
    new_cols = []
    for metric in ['Shipments', 'Routes', 'OTP %', 'OTD %', 'Tracking %']:
        for week in weeks:
            new_cols.append((metric, f'W{week}'))

    carrier_result_df.columns = pd.MultiIndex.from_tuples(new_cols)

    return carrier_result_df

def analyze_delay_codes(df, carrier_name, weeks):
    """
    Analyze delay codes for pickup and delivery

    Returns:
        Dictionary with delay code analysis
    """
    # Delivery delay codes
    carrier_delay_data = df[(df['deliveryDelayCode'].notna()) &
                             (df['deliveryDelayCode'] != '') &
                             (df['keep_for_delivery'] == True) &
                             (df['dropStatus'] == 'Succeeded')].copy()

    carrier_delay_counts = carrier_delay_data['deliveryDelayCode'].value_counts().reset_index()
    carrier_delay_counts.columns = ['Delivery Delay Code', 'Count']

    total_delivery_shipments = len(df[(df['dropStatus'] == 'Succeeded') &
                                       (df['keep_for_delivery'] == True)])
    total_routes = df[df['loadStatus'] == 'Completed']['loadId'].nunique()

    carrier_delay_counts['% of Total Shipments'] = (carrier_delay_counts['Count'] / total_delivery_shipments * 100).round(1)

    # Add "On-Time" row for delivery pie chart
    on_time_delivery_count = total_delivery_shipments - carrier_delay_counts['Count'].sum()
    on_time_delivery_pct = (on_time_delivery_count / total_delivery_shipments * 100).round(1)
    on_time_delivery_row = pd.DataFrame({
        'Delivery Delay Code': ['On-Time'],
        'Count': [on_time_delivery_count],
        '% of Total Shipments': [on_time_delivery_pct]
    })
    carrier_delay_counts_with_ontime = pd.concat([on_time_delivery_row, carrier_delay_counts], ignore_index=True)

    # Pickup delay codes
    carrier_pickup_delay_data = df[(df['pickupDelayCode'].notna()) &
                                    (df['pickupDelayCode'] != '') &
                                    (df['keep_for_pickup'] == True) &
                                    (df['pickStatus'] == 'Succeeded')].copy()

    carrier_pickup_delay_counts = carrier_pickup_delay_data['pickupDelayCode'].value_counts().reset_index()
    carrier_pickup_delay_counts.columns = ['Pickup Delay Code', 'Count']

    total_pickup_shipments = len(df[(df['pickStatus'] == 'Succeeded') &
                                     (df['keep_for_pickup'] == True)])

    carrier_pickup_delay_counts['% of Total Shipments'] = (carrier_pickup_delay_counts['Count'] / total_pickup_shipments * 100).round(1)

    # Add "On-Time" row for pickup pie chart
    on_time_pickup_count = total_pickup_shipments - carrier_pickup_delay_counts['Count'].sum()
    on_time_pickup_pct = (on_time_pickup_count / total_pickup_shipments * 100).round(1)
    on_time_pickup_row = pd.DataFrame({
        'Pickup Delay Code': ['On-Time'],
        'Count': [on_time_pickup_count],
        '% of Total Shipments': [on_time_pickup_pct]
    })
    carrier_pickup_delay_counts_with_ontime = pd.concat([on_time_pickup_row, carrier_pickup_delay_counts], ignore_index=True)

    return {
        'delivery_delay_counts': carrier_delay_counts,
        'delivery_delay_counts_with_ontime': carrier_delay_counts_with_ontime,
        'pickup_delay_counts': carrier_pickup_delay_counts,
        'pickup_delay_counts_with_ontime': carrier_pickup_delay_counts_with_ontime,
        'delivery_delay_data': carrier_delay_data,
        'pickup_delay_data': carrier_pickup_delay_data,
        'total_delivery_shipments': total_delivery_shipments,
        'total_pickup_shipments': total_pickup_shipments,
        'total_routes': total_routes
    }

def generate_pdf_report(df, carrier_name, weeks, metrics_df, delay_data):
    """
    Generate PDF report

    Returns:
        PDF as bytes
    """
    # Color scheme
    WARP_GREEN = '#2E7D32'
    WARP_DARK = '#1976D2'
    WARP_GRAY = '#F5F5F5'
    WARP_WHITE = '#FFFFFF'
    WARP_BORDER = '#BDBDBD'
    WARP_TEXT = '#212121'
    # Tableau Classic color palette - Reordered: Coral Red first, Steel Blue 7th
    PIE_COLORS = ['#E15759', '#F28E2B', '#76B7B2', '#59A14F', '#EDC948', '#B07AA1',
                  '#4E79A7', '#FF9DA7', '#9C755F', '#BAB0AC', '#A0CBE8', '#FFBE7D']

    def get_performance_color(value, target):
        """Returns color based on performance vs target."""
        if pd.isna(value):
            return WARP_WHITE
        if value >= target:
            return '#90EE90'  # Light green (meets target)
        gap = target - value
        if gap >= 10:
            return '#FF4444'  # Bright red (very bad)
        elif gap >= 5:
            return '#FF6666'  # Red (bad)
        elif gap >= 2:
            return '#FF9966'  # Orange-red (concerning)
        else:
            return '#FFB366'  # Light orange (slightly below)

    # Create PDF in memory
    buffer = io.BytesIO()
    pdf_pages = PdfPages(buffer)

    try:
        # PAGE 1: Title Page
        fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_WHITE)

        # Add WARP logo at the top
        try:
            logo = plt.imread('warp_logo.png')
            ax_logo = fig.add_axes([0.35, 0.70, 0.3, 0.2])
            ax_logo.imshow(logo)
            ax_logo.axis('off')
        except Exception as e:
            print(f"⚠️  Warning: Could not load logo: {e}")

        fig.text(0.5, 0.6, f'Carrier Performance Report',
                 ha='center', fontsize=24, fontweight='bold', color=WARP_DARK)
        fig.text(0.5, 0.5, f'{carrier_name}',
                 ha='center', fontsize=20, fontweight='bold', color=WARP_TEXT)
        fig.text(0.5, 0.4, f'Weeks {weeks[0]} & {weeks[1]}' if len(weeks) == 2 else f'Weeks {", ".join(map(str, weeks))}',
                 ha='center', fontsize=16, fontweight='bold', color=WARP_TEXT)
        fig.text(0.5, 0.3, f'Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}',
                 ha='center', fontsize=12, fontweight='bold', style='italic', color=WARP_TEXT)
        plt.axis('off')
        pdf_pages.savefig(fig, facecolor=WARP_WHITE)
        plt.close()

        # PAGE 2: Performance Metrics
        fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_WHITE)
        fig.text(0.5, 0.92, 'Performance Metrics',
                 ha='center', fontsize=18, fontweight='bold', color=WARP_DARK)

        ax = fig.add_subplot(111)
        ax.axis('off')

        # Prepare table data
        table_data = []
        table_data.append(['Metric', f'Week {weeks[0]}', f'Week {weeks[1]}'] if len(weeks) == 2 else ['Metric'] + [f'Week {w}' for w in weeks])

        # Add rows
        for metric_name, metric_key in [('Shipments', 'Shipments'), ('Routes', 'Routes'),
                                         ('OTP %\n(Target 98.5%)', 'OTP %'),
                                         ('OTD %\n(Target 99.9%)', 'OTD %'),
                                         ('Tracking %\n(Target 100%)', 'Tracking %')]:
            row = [metric_name]
            for week in weeks:
                val = metrics_df[(metric_key, f'W{week}')].values[0]
                if metric_key in ['OTP %', 'OTD %', 'Tracking %']:
                    row.append(f'{val:.1f}%' if not pd.isna(val) else '-')
                else:
                    row.append(f'{int(val)}' if not pd.isna(val) else '-')
            table_data.append(row)

        # Create table
        table = ax.table(cellText=table_data, cellLoc='center', loc='center',
                         bbox=[0.2, 0.3, 0.6, 0.5])
        table.auto_set_font_size(False)
        table.set_fontsize(12)
        table.scale(1, 3)

        # Dynamic column widths based on actual content
        temp_df = pd.DataFrame(table_data[1:], columns=table_data[0])
        col_widths = compute_col_widths(temp_df, min_w=0.15, max_w=0.50)
        for i in range(len(table_data)):
            for j, width in enumerate(col_widths):
                table[(i, j)].set_width(width)

        # Style header
        for i in range(len(table_data[0])):
            table[(0, i)].set_facecolor(WARP_DARK)
            table[(0, i)].set_text_props(weight='bold', color=WARP_WHITE, fontsize=13)
            table[(0, i)].set_edgecolor(WARP_BORDER)
            table[(0, i)].set_linewidth(2)

        # Style rows with color coding for performance metrics
        metric_targets = {'OTP %': 98.5, 'OTD %': 99.9, 'Tracking %': 100.0}
        metric_keys = ['Shipments', 'Routes', 'OTP %', 'OTD %', 'Tracking %']

        for i in range(1, len(table_data)):
            table[(i, 0)].set_facecolor(WARP_DARK)
            if i >= 3:
                table[(i, 0)].set_text_props(weight='bold', color=WARP_WHITE, fontsize=10)
            else:
                table[(i, 0)].set_text_props(weight='bold', color=WARP_WHITE, fontsize=12)
            table[(i, 0)].set_edgecolor(WARP_BORDER)
            table[(i, 0)].set_linewidth(1.5)

            metric_key = metric_keys[i - 1]
            for j in range(1, len(table_data[0])):
                week_idx = j - 1
                val = metrics_df[(metric_key, f'W{weeks[week_idx]}')].values[0]

                # Apply color coding for performance metrics
                if metric_key in metric_targets and not pd.isna(val):
                    cell_color = get_performance_color(val, metric_targets[metric_key])
                else:
                    cell_color = WARP_GRAY if i % 2 == 0 else WARP_WHITE

                table[(i, j)].set_facecolor(cell_color)
                table[(i, j)].set_text_props(weight='bold', color=WARP_TEXT)
                table[(i, j)].set_edgecolor(WARP_BORDER)
                table[(i, j)].set_linewidth(1)

        fig.text(0.5, 0.82, carrier_name,
                 ha='center', fontsize=14, fontweight='bold', style='italic', color=WARP_TEXT)

        pdf_pages.savefig(fig, facecolor=WARP_WHITE)
        plt.close()

        # PAGE 3: Pickup Delay Codes (OTP)
        carrier_pickup_delay_counts = delay_data['pickup_delay_counts']
        carrier_pickup_delay_counts_with_ontime = delay_data['pickup_delay_counts_with_ontime']
        total_pickup_shipments = delay_data['total_pickup_shipments']

        fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_WHITE)
        fig.text(0.5, 0.95, 'Pickup Delay Codes',
                 ha='center', fontsize=18, fontweight='bold', color=WARP_DARK, transform=fig.transFigure)

        if len(carrier_pickup_delay_counts) > 0:
            # Table on left
            ax1 = plt.subplot(1, 2, 1)
            ax1.axis('tight')
            ax1.axis('off')

            table_data = [['Pickup\nDelay Code', 'Count', '% of Total\nShipments']]
            for _, row in carrier_pickup_delay_counts.iterrows():
                table_data.append([
                    row['Pickup Delay Code'],
                    str(row['Count']),
                    f"{row['% of Total Shipments']:.1f}%"
                ])

            # Dynamic sizing
            n_rows = len(table_data)
            row_height = 0.08
            max_height = 0.6
            bbox_height = min(max_height, row_height * n_rows)
            bbox_y = 0.5 - bbox_height / 2

            table = ax1.table(cellText=table_data, cellLoc='left', loc='center',
                             bbox=[0, bbox_y, 1, bbox_height])
            table.auto_set_font_size(False)
            table.set_fontsize(10)
            table.scale(1, 1)

            # Dynamic column widths based on actual content
            # Create temp DataFrame for width calculation
            temp_df = pd.DataFrame(table_data[1:], columns=table_data[0])
            col_widths = compute_col_widths(temp_df, min_w=0.12, max_w=0.65)
            for i in range(len(table_data)):
                for j, width in enumerate(col_widths):
                    table[(i, j)].set_width(width)

            # Style header
            for j in range(3):
                table[(0, j)].set_facecolor(WARP_DARK)
                table[(0, j)].set_text_props(weight='bold', color=WARP_WHITE, fontsize=10, wrap=True, ha='center', va='center')
                table[(0, j)].set_edgecolor(WARP_BORDER)
                table[(0, j)].set_linewidth(2)
                table[(0, j)].set_height(0.08)

            # Style data rows
            for i in range(1, len(table_data)):
                row_color = WARP_GRAY if i % 2 == 0 else WARP_WHITE
                for j in range(3):
                    table[(i, j)].set_facecolor(row_color)
                    table[(i, j)].set_text_props(weight='bold', color=WARP_TEXT)
                    table[(i, j)].set_edgecolor(WARP_BORDER)
                    table[(i, j)].set_linewidth(1)
                    if j > 0:
                        table[(i, j)].set_text_props(ha='center', weight='bold', color=WARP_TEXT)

            # Pie chart on right
            ax2 = plt.subplot(1, 2, 2)

            def autopct_format(pct):
                return f'{pct:.1f}%' if pct >= 5 else ''

            # Use with_ontime data for pie chart
            pie_colors_with_ontime = ['#4CAF50'] + PIE_COLORS[:len(carrier_pickup_delay_counts)]

            wedges, texts, autotexts = ax2.pie(carrier_pickup_delay_counts_with_ontime['Count'],
                                                autopct=autopct_format,
                                                startangle=90,
                                                colors=pie_colors_with_ontime,
                                                wedgeprops={'edgecolor': WARP_WHITE, 'linewidth': 2})

            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontsize(10)
                autotext.set_weight('bold')

            # Add "Total Shipments" text above legend
            ax2.text(0.5, -0.10, f'Total Shipments: {total_pickup_shipments}',
                    ha='center', va='top', fontsize=11, fontweight='bold',
                    color=WARP_TEXT, transform=ax2.transAxes)

            # Legend below the text
            ax2.legend(wedges, carrier_pickup_delay_counts_with_ontime['Pickup Delay Code'],
                      title="Pickup Status",
                      loc="upper center",
                      bbox_to_anchor=(0.5, -0.20),
                      fontsize=9,
                      ncol=2,
                      facecolor=WARP_WHITE,
                      edgecolor=WARP_BORDER,
                      labelcolor=WARP_TEXT)

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

        # PAGE 4+: Pickup Delay Details (OTP - paginated)
        carrier_pickup_delay_data = delay_data['pickup_delay_data']

        if len(carrier_pickup_delay_data) > 0:
            # Format pickup window
            def format_pickup_window(row):
                from_str = str(row['pickWindowFrom'])
                to_str = str(row['pickWindowTo'])
                if ' ' in from_str and ' ' in to_str:
                    from_date, from_time = from_str.split(' ', 1)
                    to_date, to_time = to_str.split(' ', 1)
                    if from_date == to_date:
                        return f"{from_date} {from_time} - {to_time}"
                return f"{from_str} - {to_str}"

            carrier_pickup_delay_data['Pickup Window'] = carrier_pickup_delay_data.apply(format_pickup_window, axis=1)
            carrier_pickup_delay_data['Lane'] = (
                carrier_pickup_delay_data['pickCity'].fillna('') + ', ' +
                carrier_pickup_delay_data['pickState'].fillna('') + ' > ' +
                carrier_pickup_delay_data['dropCity'].fillna('') + ', ' +
                carrier_pickup_delay_data['dropState'].fillna('')
            )

            pickup_delay_details = carrier_pickup_delay_data[[
                'orderCode', 'pickupDelayCode', 'Lane', 'Pickup Window',
                'pickTimeDeparted', 'pickTimeArrived', 'isTracking'
            ]].copy()

            pickup_delay_details.columns = [
                'Order Code', 'Pickup Delay Code', 'Lane', 'Pickup Window',
                'Pick Departed', 'Pick Arrived', 'Tracking'
            ]

            # Paginate
            rows_per_page = 12
            total_rows = len(pickup_delay_details)
            total_pages = (total_rows + rows_per_page - 1) // rows_per_page

            for page_num in range(total_pages):
                start_idx = page_num * rows_per_page
                end_idx = min(start_idx + rows_per_page, total_rows)
                display_data = pickup_delay_details.iloc[start_idx:end_idx]

                fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_WHITE)

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

                table_data = [display_data.columns.tolist()]
                for _, row in display_data.iterrows():
                    table_data.append([str(val) if not pd.isna(val) else '' for val in row])

                # Dynamic sizing
                num_rows = len(table_data)
                bbox_height = min(0.85, 0.1 + (num_rows * 0.05))
                bbox_y = 0.85 - bbox_height
                table = ax.table(cellText=table_data, cellLoc='left', loc='center',
                                bbox=[0, bbox_y, 1, bbox_height])
                table.auto_set_font_size(False)
                table.set_fontsize(5.5)
                table.scale(1, 1.2)

                # Dynamic column widths based on actual content
                col_widths = compute_col_widths(display_data)
                for i, width in enumerate(col_widths):
                    for j in range(len(table_data)):
                        table[(j, i)].set_width(width)

                # Style header
                for i in range(len(display_data.columns)):
                    table[(0, i)].set_facecolor(WARP_DARK)
                    table[(0, i)].set_text_props(weight='bold', color=WARP_WHITE, fontsize=7, wrap=True, ha='center', va='center')
                    table[(0, i)].set_edgecolor(WARP_BORDER)
                    table[(0, i)].set_linewidth(1.5)
                    table[(0, i)].set_height(0.04)

                # Style data rows
                for i in range(1, len(table_data)):
                    row_color = WARP_GRAY if i % 2 == 0 else WARP_WHITE
                    for j in range(len(display_data.columns)):
                        table[(i, j)].set_facecolor(row_color)
                        table[(i, j)].set_edgecolor(WARP_BORDER)
                        table[(i, j)].set_linewidth(0.5)
                        table[(i, j)].set_text_props(wrap=True, weight='bold', color=WARP_TEXT)

                pdf_pages.savefig(fig, facecolor=WARP_WHITE)
                plt.close()

        # PAGE 5: Delivery Delay Codes (OTD)
        carrier_delay_counts = delay_data['delivery_delay_counts']
        carrier_delay_counts_with_ontime = delay_data['delivery_delay_counts_with_ontime']
        total_delivery_shipments = delay_data['total_delivery_shipments']

        fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_WHITE)
        fig.text(0.5, 0.95, 'Delivery Delay Codes',
                 ha='center', fontsize=18, fontweight='bold', color=WARP_DARK, transform=fig.transFigure)

        if len(carrier_delay_counts) > 0:
            # Table on left
            ax1 = plt.subplot(1, 2, 1)
            ax1.axis('tight')
            ax1.axis('off')

            table_data = [['Delivery\nDelay Code', 'Count', '% of Total\nShipments']]
            for _, row in carrier_delay_counts.iterrows():
                table_data.append([
                    row['Delivery Delay Code'],
                    str(row['Count']),
                    f"{row['% of Total Shipments']:.1f}%"
                ])

            # Dynamic sizing
            n_rows = len(table_data)
            row_height = 0.08
            max_height = 0.6
            bbox_height = min(max_height, row_height * n_rows)
            bbox_y = 0.5 - bbox_height / 2

            table = ax1.table(cellText=table_data, cellLoc='left', loc='center',
                             bbox=[0, bbox_y, 1, bbox_height])
            table.auto_set_font_size(False)
            table.set_fontsize(10)
            table.scale(1, 1)

            # Dynamic column widths based on actual content
            # Create temp DataFrame for width calculation
            temp_df = pd.DataFrame(table_data[1:], columns=table_data[0])
            col_widths = compute_col_widths(temp_df, min_w=0.12, max_w=0.65)
            for i in range(len(table_data)):
                for j, width in enumerate(col_widths):
                    table[(i, j)].set_width(width)

            # Style header
            for j in range(3):
                table[(0, j)].set_facecolor(WARP_DARK)
                table[(0, j)].set_text_props(weight='bold', color=WARP_WHITE, fontsize=10, wrap=True, ha='center', va='center')
                table[(0, j)].set_edgecolor(WARP_BORDER)
                table[(0, j)].set_linewidth(2)
                table[(0, j)].set_height(0.08)

            # Style data rows
            for i in range(1, len(table_data)):
                row_color = WARP_GRAY if i % 2 == 0 else WARP_WHITE
                for j in range(3):
                    table[(i, j)].set_facecolor(row_color)
                    table[(i, j)].set_text_props(weight='bold', color=WARP_TEXT)
                    table[(i, j)].set_edgecolor(WARP_BORDER)
                    table[(i, j)].set_linewidth(1)
                    if j > 0:
                        table[(i, j)].set_text_props(ha='center', weight='bold', color=WARP_TEXT)

            # Pie chart on right
            ax2 = plt.subplot(1, 2, 2)

            def autopct_format(pct):
                return f'{pct:.1f}%' if pct >= 5 else ''

            # Use with_ontime data for pie chart
            pie_colors_with_ontime = ['#4CAF50'] + PIE_COLORS[:len(carrier_delay_counts)]

            wedges, texts, autotexts = ax2.pie(carrier_delay_counts_with_ontime['Count'],
                                                autopct=autopct_format,
                                                startangle=90,
                                                colors=pie_colors_with_ontime,
                                                wedgeprops={'edgecolor': WARP_WHITE, 'linewidth': 2})

            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontsize(10)
                autotext.set_weight('bold')

            # Add "Total Shipments" text above legend
            ax2.text(0.5, -0.10, f'Total Shipments: {total_delivery_shipments}',
                    ha='center', va='top', fontsize=11, fontweight='bold',
                    color=WARP_TEXT, transform=ax2.transAxes)

            # Legend below the text
            ax2.legend(wedges, carrier_delay_counts_with_ontime['Delivery Delay Code'],
                      title="Delivery Status",
                      loc="upper center",
                      bbox_to_anchor=(0.5, -0.20),
                      fontsize=9,
                      ncol=2,
                      facecolor=WARP_WHITE,
                      edgecolor=WARP_BORDER,
                      labelcolor=WARP_TEXT)

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

        # PAGE 6+: Delivery Delay Details (OTD - paginated)
        carrier_delay_data = delay_data['delivery_delay_data']

        if len(carrier_delay_data) > 0:
            # Format drop window
            def format_drop_window(row):
                from_str = str(row['dropWindowFrom'])
                to_str = str(row['dropWindowTo'])
                if ' ' in from_str and ' ' in to_str:
                    from_date, from_time = from_str.split(' ', 1)
                    to_date, to_time = to_str.split(' ', 1)
                    if from_date == to_date:
                        return f"{from_date} {from_time} - {to_time}"
                return f"{from_str} - {to_str}"

            carrier_delay_data['Drop Window'] = carrier_delay_data.apply(format_drop_window, axis=1)
            carrier_delay_data['Lane'] = (
                carrier_delay_data['pickCity'].fillna('') + ', ' +
                carrier_delay_data['pickState'].fillna('') + ' > ' +
                carrier_delay_data['dropCity'].fillna('') + ', ' +
                carrier_delay_data['dropState'].fillna('')
            )

            delivery_delay_details = carrier_delay_data[[
                'orderCode', 'deliveryDelayCode', 'Lane', 'Drop Window',
                'dropTimeDeparted', 'dropTimeArrived', 'isTracking'
            ]].copy()

            delivery_delay_details.columns = [
                'Order Code', 'Delivery Delay Code', 'Lane', 'Drop Window',
                'Drop Departed', 'Drop Arrived', 'Tracking'
            ]

            # Paginate
            rows_per_page = 12
            total_rows = len(delivery_delay_details)
            total_pages = (total_rows + rows_per_page - 1) // rows_per_page

            for page_num in range(total_pages):
                start_idx = page_num * rows_per_page
                end_idx = min(start_idx + rows_per_page, total_rows)
                display_data = delivery_delay_details.iloc[start_idx:end_idx]

                fig = plt.figure(figsize=(11, 8.5), facecolor=WARP_WHITE)

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

                table_data = [display_data.columns.tolist()]
                for _, row in display_data.iterrows():
                    table_data.append([str(val) if not pd.isna(val) else '' for val in row])

                # Dynamic sizing
                num_rows = len(table_data)
                bbox_height = min(0.85, 0.1 + (num_rows * 0.05))
                bbox_y = 0.85 - bbox_height
                table = ax.table(cellText=table_data, cellLoc='left', loc='center',
                                bbox=[0, bbox_y, 1, bbox_height])
                table.auto_set_font_size(False)
                table.set_fontsize(5.5)
                table.scale(1, 1.2)

                # Dynamic column widths based on actual content
                col_widths = compute_col_widths(display_data)
                for i, width in enumerate(col_widths):
                    for j in range(len(table_data)):
                        table[(j, i)].set_width(width)

                # Style header
                for i in range(len(display_data.columns)):
                    table[(0, i)].set_facecolor(WARP_DARK)
                    table[(0, i)].set_text_props(weight='bold', color=WARP_WHITE, fontsize=7, wrap=True, ha='center', va='center')
                    table[(0, i)].set_edgecolor(WARP_BORDER)
                    table[(0, i)].set_linewidth(1.5)
                    table[(0, i)].set_height(0.06)

                # Style data rows
                for i in range(1, len(table_data)):
                    row_color = WARP_GRAY if i % 2 == 0 else WARP_WHITE
                    for j in range(len(display_data.columns)):
                        table[(i, j)].set_facecolor(row_color)
                        table[(i, j)].set_edgecolor(WARP_BORDER)
                        table[(i, j)].set_linewidth(0.5)
                        table[(i, j)].set_text_props(wrap=True, weight='bold', color=WARP_TEXT)

                pdf_pages.savefig(fig, facecolor=WARP_WHITE)
                plt.close()

    finally:
        pdf_pages.close()

    buffer.seek(0)
    return buffer.getvalue()

