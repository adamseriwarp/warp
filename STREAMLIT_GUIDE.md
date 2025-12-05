# Carrier Performance Report - Streamlit App Guide

## 📁 Files Created

### 1. `app.py` - Main Streamlit Application
- **Purpose**: User interface for the report generator
- **Features**:
  - Carrier selection dropdown (auto-populated from database)
  - Week selection (multi-select)
  - Generate report button
  - Progress indicators
  - Metrics preview
  - PDF download button

### 2. `report_generator.py` - Backend Logic
- **Purpose**: All data processing and PDF generation functions
- **Functions**:
  - `load_and_process_data()` - Loads data from database, calculates OTP/OTD, deduplicates
  - `calculate_performance_metrics()` - Calculates shipments, routes, OTP%, OTD%, Tracking%
  - `analyze_delay_codes()` - Analyzes pickup and delivery delay codes
  - `generate_pdf_report()` - Generates complete PDF with all pages

## 🚀 How to Run

### Start the App
```bash
streamlit run app.py
```

The app will open at: `http://localhost:8501`

### Stop the App
Press `Ctrl+C` in the terminal

## 📊 PDF Report Pages

The generated PDF includes:

1. **Title Page** - Carrier name, weeks, generation date
2. **Performance Metrics** - Table with Shipments, Routes, OTP%, OTD%, Tracking% (with targets)
3. **Delivery Delay Codes** - Table + Pie chart of delivery delays
4. **Pickup Delay Codes** - Table + Pie chart of pickup delays
5. **Pickup Delay Details** - Paginated detailed table (12 rows per page)
6. **Delivery Delay Details** - Paginated detailed table (12 rows per page)

## 🎨 Features

### Caching
- Carrier list is cached for 1 hour (`@st.cache_data(ttl=3600)`)
- Data processing is cached for 30 minutes (`@st.cache_data(ttl=1800)`)
- Database connection is cached (`@st.cache_resource`)

### Dynamic Sizing
- All tables automatically adjust height based on number of rows
- No more oversized tables with few rows!

### Professional Theme
- White background
- Blue headers (#1976D2)
- Light gray alternating rows (#F5F5F5)
- Dark text for readability (#212121)

## 🔧 Customization

### Change Database Connection
Edit `report_generator.py`, function `get_db_connection()`:
```python
def get_db_connection():
    return mysql.connector.connect(
        host='your-host',
        user='your-user',
        password='your-password',
        database='your-database'
    )
```

### Change Default Weeks
Edit `app.py`, line with `default=`:
```python
selected_weeks = st.sidebar.multiselect(
    "Select Weeks to Analyze",
    available_weeks,
    default=[current_week - 1, current_week]  # Change this
)
```

### Change Rows Per Page (Detail Tables)
Edit `report_generator.py`, search for `rows_per_page = 12` and change the number.

## 🌐 Deployment Options

### Option 1: Streamlit Community Cloud (Free)
1. Push code to GitHub
2. Go to https://share.streamlit.io
3. Connect your GitHub repo
4. Select `app.py` as the main file
5. Click "Deploy"

**Note**: You'll need to add database credentials as secrets in Streamlit Cloud settings.

### Option 2: Local Network Access
Your team can access the app on your local network at:
```
http://YOUR_IP_ADDRESS:8501
```

Find your IP with: `ipconfig` (Windows) or `ifconfig` (Mac/Linux)

### Option 3: Deploy to a Server
- Railway.app
- Render.com
- AWS EC2
- Google Cloud Run

## 📝 Usage Instructions for Your Team

1. **Open the app** in your browser
2. **Select a carrier** from the dropdown
3. **Select weeks** to analyze (can select multiple)
4. **Click "Generate Report"**
5. **Wait** for processing (progress bar shows status)
6. **Preview** metrics in the browser
7. **Download PDF** using the download button

## 🐛 Troubleshooting

### App won't start
- Make sure you're in the correct directory
- Check that all dependencies are installed: `pip install streamlit pandas mysql-connector-python matplotlib`

### Database connection error
- Check database credentials in `report_generator.py`
- Ensure database is accessible from your network

### PDF generation fails
- Check that matplotlib is installed: `pip install matplotlib`
- Ensure there's data for the selected carrier and weeks

### Carrier not in dropdown
- Check that carrier has data in the database for 2025 onwards
- Carrier names are case-sensitive in the database

## 💡 Tips

- **Refresh data**: Click "Clear cache" in the Streamlit menu (top right) to reload carrier list
- **Multiple reports**: You can generate reports for different carriers without restarting the app
- **Browser compatibility**: Works best in Chrome, Firefox, Safari, Edge
- **Mobile friendly**: The app works on tablets and phones too!

## 🔐 Security Notes

- Database credentials are currently hardcoded in `report_generator.py`
- For production, use environment variables or Streamlit secrets
- Consider adding authentication if deploying publicly

## 📞 Support

If you encounter issues:
1. Check the terminal for error messages
2. Check the Streamlit app for error details
3. Clear cache and try again
4. Restart the app

