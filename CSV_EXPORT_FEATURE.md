# CSV Export Feature

## Overview
Added CSV export functionality to the Streamlit app that allows users to download detailed pickup and delivery data including **both delayed AND on-time shipments**.

## What's New

### 1. Two New CSV Export Functions in `report_generator.py`

#### `generate_pickup_details_csv(df)`
- Exports all successful pickups (deduplicated)
- Includes columns:
  - Order Code
  - Pickup Status (delay code or "On-Time")
  - Lane (pickup city/state > drop city/state)
  - Pickup Window
  - Pick Departed
  - Pick Arrived
  - Tracking
  - OTP Result
- **Sorted**: Delayed pickups first, then on-time pickups

#### `generate_delivery_details_csv(df)`
- Exports all successful deliveries (deduplicated)
- Includes columns:
  - Order Code
  - Delivery Status (delay code or "On-Time")
  - Lane (pickup city/state > drop city/state)
  - Drop Window
  - Drop Departed
  - Drop Arrived
  - Tracking
  - OTD Result
- **Sorted**: Delayed deliveries first, then on-time deliveries

### 2. Updated Streamlit UI in `app.py`

#### Download Buttons Section
- **3 columns layout**:
  1. PDF Report download (existing)
  2. Pickup Details CSV download (NEW)
  3. Delivery Details CSV download (NEW)

#### CSV Preview Tabs
- Two tabs showing preview of CSV data:
  1. **Pickup Details tab**: Shows first 20 rows of pickup CSV
  2. **Delivery Details tab**: Shows first 20 rows of delivery CSV
- Each tab shows total count and indicates it includes both delayed and on-time shipments

## Key Differences from PDF Report

| Feature | PDF Report | CSV Export |
|---------|-----------|------------|
| **Delayed Shipments** | ✅ Included | ✅ Included |
| **On-Time Shipments** | ❌ Not shown in detail tables | ✅ **Included** |
| **Status Column** | Only shows delay codes | Shows delay code OR "On-Time" |
| **Sorting** | By delay code | Delayed first, then on-time |
| **Purpose** | Executive summary | Detailed analysis |

## Use Cases

### For Operations Teams
- Analyze patterns in on-time vs delayed shipments
- Identify which lanes have consistent on-time performance
- Compare tracking compliance across all shipments

### For Data Analysis
- Calculate delay rates by lane
- Identify time-of-day patterns
- Analyze carrier performance trends

### For Carrier Communication
- Share complete shipment history
- Highlight both successes and issues
- Provide data for performance discussions

## File Naming Convention

### Pickup CSV
```
pickup_details_{CARRIER_NAME}_weeks_{WEEK1-WEEK2}.csv
```
Example: `pickup_details_ILLYRIAN_TRANSPORT_LLC_weeks_49-50.csv`

### Delivery CSV
```
delivery_details_{CARRIER_NAME}_weeks_{WEEK1-WEEK2}.csv
```
Example: `delivery_details_ILLYRIAN_TRANSPORT_LLC_weeks_49-50.csv`

## Technical Details

### Deduplication
- Uses same deduplication logic as PDF report
- Pickup CSV: `keep_for_pickup == True`
- Delivery CSV: `keep_for_delivery == True`

### Filtering
- Pickup CSV: `pickStatus == 'Succeeded'`
- Delivery CSV: `dropStatus == 'Succeeded'`

### Status Logic
```python
# If delay code exists and is not empty -> show delay code
# Otherwise -> show "On-Time"
Status = delay_code if delay_code else "On-Time"
```

## Testing

To test locally:
1. Run `streamlit run app.py`
2. Select a carrier and weeks
3. Click "Generate Report"
4. Look for 3 download buttons
5. Click "Pickup Details CSV" or "Delivery Details CSV"
6. Check the preview tabs below

## Deployment

Changes are ready to push to GitHub. Once pushed, Streamlit Cloud will automatically redeploy with the new CSV export feature.

