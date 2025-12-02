import streamlit as st
import pandas as pd
import mysql.connector
from datetime import datetime

# Database connection
@st.cache_resource
def get_connection():
    return mysql.connector.connect(
        host="datahub-mysql.wearewarp.link",
        user="datahub-read",
        password="warpdbhub2",
        database="datahub"
    )

# Query data
@st.cache_data(ttl=43200)  # Cache for 12 hours
def load_data(query):
    conn = get_connection()
    df = pd.read_sql(query, conn)
    return df

# ============================================
# DASHBOARD HEADER
# ============================================
st.title("🚚 Warp Dashboard")
st.write(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Auto-refresh button
if st.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# ============================================
# DATE RANGE SELECTOR
# ============================================
st.subheader("📅 Select Date Range")

col1, col2 = st.columns(2)
with col1:
    days_back = st.selectbox(
        "Time Period",
        options=[7, 14, 30, 60, 90, 180, 365],
        index=2,  # Default to 30 days
        format_func=lambda x: f"Last {x} days"
    )

with col2:
    max_rows = st.selectbox(
        "Max Rows to Load",
        options=[1000, 5000, 10000, 25000, 50000],
        index=2,  # Default to 10,000
        format_func=lambda x: f"{x:,} rows"
    )

# ============================================
# LOAD DATA
# ============================================
df = load_data(f"""
    SELECT
        id,
        routeId,
        status,
        equipmentType,
        equipment,
        carrierName,
        firstPickupTimezone,
        DATE(firstPickupTimezone) as pickup_date
    FROM routes
    WHERE firstPickupTimezone >= CURDATE() - INTERVAL {days_back} DAY
        AND firstPickupTimezone IS NOT NULL
    ORDER BY firstPickupTimezone DESC
    LIMIT {max_rows}
""")

# ============================================
# DATA CHECK
# ============================================
if len(df) == 0:
    st.error(f"⚠️ No data found for the last {days_back} days. Try selecting a longer time period.")
    st.stop()

# Show actual date range of data
min_date = df['pickup_date'].min()
max_date = df['pickup_date'].max()
st.info(f"📅 Showing data from **{min_date}** to **{max_date}** ({len(df):,} routes)")

# ============================================
# KEY METRICS (Big Numbers at the Top)
# ============================================
st.header("📊 Key Metrics")

col1, col2, col3, col4 = st.columns(4)

with col1:
    total_routes = len(df)
    st.metric("Total Routes (30 days)", f"{total_routes:,}")

with col2:
    completed = len(df[df['status'] == 'completed'])
    st.metric("Completed Routes", f"{completed:,}")

with col3:
    completion_rate = (completed / total_routes * 100) if total_routes > 0 else 0
    st.metric("Completion Rate", f"{completion_rate:.1f}%")

with col4:
    unique_carriers = df['carrierName'].nunique()
    st.metric("Active Carriers", f"{unique_carriers:,}")

# ============================================
# CHARTS & VISUALIZATIONS
# ============================================

# Routes Over Time
st.header("📈 Routes Over Time")
routes_by_date = df.groupby('pickup_date').size().reset_index(name='count')
st.line_chart(routes_by_date.set_index('pickup_date')['count'])

# Two columns for side-by-side charts
col1, col2 = st.columns(2)

with col1:
    st.subheader("🚛 Routes by Equipment Type")
    equipment_counts = df['equipmentType'].value_counts()
    st.bar_chart(equipment_counts)

with col2:
    st.subheader("📊 Routes by Status")
    status_counts = df['status'].value_counts()
    st.bar_chart(status_counts)

# Top Carriers
st.header("🏆 Top 10 Carriers by Route Volume")
top_carriers = df['carrierName'].value_counts().head(10)
st.bar_chart(top_carriers)

# ============================================
# FILTERS & INTERACTIVE DATA EXPLORATION
# ============================================
st.header("🔍 Filter & Explore Data")

# Filter by equipment type
selected_equipment = st.multiselect(
    "Filter by Equipment Type",
    options=df['equipmentType'].unique().tolist(),
    default=[]
)

# Filter by status
selected_status = st.multiselect(
    "Filter by Status",
    options=df['status'].unique().tolist(),
    default=[]
)

# Apply filters
filtered_df = df.copy()
if selected_equipment:
    filtered_df = filtered_df[filtered_df['equipmentType'].isin(selected_equipment)]
if selected_status:
    filtered_df = filtered_df[filtered_df['status'].isin(selected_status)]

# Show filtered results
st.write(f"Showing {len(filtered_df):,} routes")
st.dataframe(filtered_df)

# ============================================
# RAW DATA (Expandable Section)
# ============================================
with st.expander("📋 View All Column Names"):
    st.write(f"**Total columns:** {len(df.columns)}")
    st.write(", ".join(df.columns))