import streamlit as st
import pandas as pd
import mysql.connector
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import datetime
from matplotlib.backends.backend_pdf import PdfPages
import warnings
warnings.filterwarnings('ignore')
import io

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================
st.set_page_config(
    page_title="Carrier Performance Reports",
    page_icon="🚚",
    layout="wide"
)

# ============================================================================
# PASSWORD PROTECTION
# ============================================================================

def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        # Get password from secrets, fallback to default for local development
        try:
            correct_password = st.secrets.get("password", "W@rp123!")
        except:
            correct_password = "W@rp123!"

        if st.session_state["password"] == correct_password:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
        else:
            st.session_state["password_correct"] = False

    # First run, show input for password
    if "password_correct" not in st.session_state:
        st.title("🚚 Carrier Performance Reports")
        st.markdown("### 🔒 Authentication Required")
        st.text_input(
            "Please enter the password to access the app:",
            type="password",
            on_change=password_entered,
            key="password"
        )
        st.info("💡 Contact your administrator if you don't have the password.")
        return False

    # Password not correct, show input + error
    elif not st.session_state["password_correct"]:
        st.title("🚚 Carrier Performance Reports")
        st.markdown("### 🔒 Authentication Required")
        st.text_input(
            "Please enter the password to access the app:",
            type="password",
            on_change=password_entered,
            key="password"
        )
        st.error("❌ Incorrect password. Please try again.")
        return False

    # Password correct
    else:
        return True

# Check password before showing the app
if not check_password():
    st.stop()

# ============================================================================
# TITLE AND DESCRIPTION
# ============================================================================
st.title("🚚 Carrier Performance Report Generator")
st.markdown("Generate detailed performance reports for carriers including OTP, OTD, and delay analysis.")

# ============================================================================
# SIDEBAR - USER INPUTS
# ============================================================================
st.sidebar.header("⚙️ Report Settings")

# Database connection function
@st.cache_resource
def get_db_connection():
    """Create database connection (cached)"""
    return mysql.connector.connect(
        host='datahub-mysql.wearewarp.link',
        user='datahub-read',
        password='warpdbhub2',
        database='datahub'
    )

# Load available carriers
@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_available_carriers():
    """Get list of unique carriers from database"""
    conn = get_db_connection()
    query = """
        SELECT DISTINCT carrierName 
        FROM otp_reports 
        WHERE carrierName IS NOT NULL 
        AND carrierName != ''
        AND STR_TO_DATE(pickWindowFrom, '%m/%d/%Y %H:%i:%s') >= '2025-01-01'
        ORDER BY carrierName
    """
    df = pd.read_sql(query, conn)
    return df['carrierName'].tolist()

# Get carriers
with st.spinner("Loading carriers..."):
    carriers = get_available_carriers()

# Carrier selection
selected_carrier = st.sidebar.selectbox(
    "Select Carrier",
    carriers,
    index=carriers.index('ILLYRIAN TRANSPORT LLC') if 'ILLYRIAN TRANSPORT LLC' in carriers else 0
)

# Week selection
current_week = datetime.datetime.now().isocalendar()[1]
available_weeks = list(range(current_week - 10, current_week + 1))

selected_weeks = st.sidebar.multiselect(
    "Select Weeks to Analyze",
    available_weeks,
    default=[current_week - 1, current_week]
)

# Generate button
generate_button = st.sidebar.button("📊 Generate Report", type="primary", use_container_width=True)

# ============================================================================
# HELPER TEXT
# ============================================================================
if not generate_button:
    st.info("👈 Select a carrier and weeks from the sidebar, then click 'Generate Report'")
    
    # Show some stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Available Carriers", len(carriers))
    with col2:
        st.metric("Current Week", current_week)
    with col3:
        st.metric("Weeks Selected", len(selected_weeks))

# ============================================================================
# MAIN LOGIC - RUNS WHEN BUTTON IS CLICKED
# ============================================================================
if generate_button:
    if len(selected_weeks) == 0:
        st.error("⚠️ Please select at least one week to analyze")
        st.stop()
    
    # Show progress
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Import the report generation functions
    # We'll create these next
    from report_generator import (
        load_and_process_data,
        calculate_performance_metrics,
        analyze_delay_codes,
        generate_pdf_report
    )
    
    try:
        # Step 1: Load data
        status_text.text("📥 Loading data from database...")
        progress_bar.progress(20)
        df = load_and_process_data(selected_carrier, selected_weeks)
        
        # Step 2: Calculate metrics
        status_text.text("📊 Calculating performance metrics...")
        progress_bar.progress(40)
        metrics_df = calculate_performance_metrics(df, selected_carrier, selected_weeks)
        
        # Step 3: Analyze delays
        status_text.text("🔍 Analyzing delay codes...")
        progress_bar.progress(60)
        delay_data = analyze_delay_codes(df, selected_carrier, selected_weeks)
        
        # Step 4: Generate PDF
        status_text.text("📄 Generating PDF report...")
        progress_bar.progress(80)
        pdf_bytes = generate_pdf_report(df, selected_carrier, selected_weeks, metrics_df, delay_data)
        
        # Complete
        progress_bar.progress(100)
        status_text.text("✅ Report generated successfully!")
        
        # Display results
        st.success(f"✅ Report generated for **{selected_carrier}** - Weeks {selected_weeks}")
        
        # Show metrics preview
        st.subheader("📊 Performance Metrics Preview")
        st.dataframe(metrics_df, use_container_width=True)
        
        # Download button
        st.download_button(
            label="📥 Download PDF Report",
            data=pdf_bytes,
            file_name=f"carrier_report_{selected_carrier.replace(' ', '_')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
        
    except Exception as e:
        st.error(f"❌ Error generating report: {str(e)}")
        st.exception(e)

