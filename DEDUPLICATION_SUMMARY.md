# Deduplication Implementation Summary

## Date: 2025-12-01

## Overview
Implemented deduplication logic to prevent double-counting when multiple orders are on the same truck picking up/delivering at the same location on the same date.

---

## Deduplication Logic

### For Pickups:
**Deduplicate by:** `loadId` + `carrierName` + `pickLocationName` + `pickDate`

- Same truck (loadId)
- Same carrier
- Same pickup location
- Same pickup date (ignoring time)
- **Keep:** Earliest `pickTimeArrived` and its corresponding delay code

### For Deliveries:
**Deduplicate by:** `loadId` + `carrierName` + `dropLocationName` + `dropDate`

- Same truck (loadId)
- Same carrier
- Same delivery location
- Same delivery date (ignoring time)
- **Keep:** Earliest `dropTimeArrived` and its corresponding delay code

---

## Impact Analysis (Full Dataset)

### Overall Dataset:
- **Total records:** 353,846

### Pickup Deduplication:
- **Duplicate records found:** 160,857 (45.5%)
- **Unique pickup events:** 192,989
- **Reduction:** 45.5%

### Delivery Deduplication:
- **Duplicate records found:** 112,079 (31.7%)
- **Unique delivery events:** 241,767
- **Reduction:** 31.7%

---

## Edge Cases Analyzed

### 1. Different pickup times on same date (within 10 minutes):
- **Found:** 279 loadIds
- **Total warpIDs affected:** 794 orders
- **Example:** Same truck picking up 6 orders, some at 09:22:47, others at 09:32:11

### 2. Conflicting delay codes after deduplication:
- **Pickup delay codes:** 22 cases (93 orders affected)
- **Delivery delay codes:** 52 cases (151 orders affected)
- **Solution:** Keep delay code from order with earliest time

---

## Changes Made to `query_otp_clean.py`

### 1. Added Deduplication Section (Lines 113-185)
- Created `pickDate` and `dropDate` columns
- Sorted by `pickTimeArrived_dt` and `dropTimeArrived_dt` to ensure earliest times come first
- Created deduplication keys for pickup and delivery
- Added `keep_for_pickup` and `keep_for_delivery` flags

### 2. Updated Performance Metrics Calculation (Lines 254-297)
- **Shipments count:** Now uses deduplicated pickup events
- **OTP %:** Only counts deduplicated pickup events (`keep_for_pickup == True`)
- **OTD %:** Only counts deduplicated delivery events (`keep_for_delivery == True`)
- **Tracking %:** Uses deduplicated pickup events

### 3. Updated Delay Code Analysis (Lines 330-357)
- **Delivery delay codes:** Filtered by `keep_for_delivery == True`
- **Pickup delay codes:** Filtered by `keep_for_pickup == True`

### 4. Delay Details Tables
- Automatically use deduplicated data since they reference `carrier_delay_data` and `carrier_pickup_delay_data`

---

## Example: ILLYRIAN TRANSPORT LLC

### Before Deduplication (estimated):
- Week 48: ~24 shipments
- Week 49: ~27 shipments

### After Deduplication:
- Week 48: 14 shipments
- Week 49: 16 shipments

**Reduction:** ~40% fewer shipments counted (matching overall trend)

---

## Testing Performed

1. ✅ Created `test_deduplication.py` to analyze edge cases
2. ✅ Verified deduplication logic with multiple test runs
3. ✅ Confirmed delay codes are preserved from earliest time
4. ✅ Generated PDF report for ILLYRIAN TRANSPORT LLC
5. ✅ Verified all sections of report use deduplicated data

---

## Notes

- Deduplication flags are added to the dataframe but rows are NOT removed
- This allows flexibility for future analysis that may need non-deduplicated data
- The flags are used consistently across all calculations:
  - Performance metrics
  - Delay code analysis
  - Delay details tables
  - OTP/OTD percentages

---

## Files Modified

1. `query_otp_clean.py` - Main report generation script
2. `test_deduplication.py` - Edge case analysis script (created)

---

## Next Steps

1. ✅ Deduplication implemented and tested
2. ⏭️ Consider automating report generation with GitHub Actions
3. ⏭️ Set up email domain verification with Resend
4. ⏭️ Deploy automated weekly reports

