"""
Helper script to get a list of all active carriers from the database.
Use this to update the carrier dropdown in the GitHub Actions workflow.
"""

import pandas as pd
import mysql.connector
import os

# Database connection
conn = mysql.connector.connect(
    host=os.environ.get('DB_HOST', 'datahub-mysql.wearewarp.link'),
    user=os.environ.get('DB_USER', 'datahub-read'),
    password=os.environ.get('DB_PASSWORD', 'warpdbhub2'),
    database=os.environ.get('DB_NAME', 'datahub')
)

print("=" * 80)
print("FETCHING ACTIVE CARRIERS")
print("=" * 80)

# Query to get all carriers from the last 4 weeks with at least 5 shipments
query = """
SELECT 
    carrierName,
    COUNT(*) as shipment_count,
    MAX(STR_TO_DATE(pickWindowFrom, '%m/%d/%Y %H:%i:%s')) as last_shipment
FROM otp_reports
WHERE STR_TO_DATE(pickWindowFrom, '%m/%d/%Y %H:%i:%s') >= DATE_SUB(NOW(), INTERVAL 4 WEEK)
    AND carrierName IS NOT NULL
    AND carrierName != ''
GROUP BY carrierName
HAVING shipment_count >= 5
ORDER BY shipment_count DESC
"""

df = pd.read_sql(query, conn)
conn.close()

print(f"\n✅ Found {len(df)} active carriers with 5+ shipments in the last 4 weeks\n")

print("=" * 80)
print("CARRIER LIST FOR GITHUB ACTIONS WORKFLOW")
print("=" * 80)
print("\nCopy this into .github/workflows/generate-carrier-report.yml")
print("under the 'options:' section:\n")

print("        options:")
for carrier in df['carrierName'].tolist():
    print(f"          - '{carrier}'")
print("          - 'ALL_CARRIERS'")

print("\n" + "=" * 80)
print("CARRIER STATISTICS")
print("=" * 80)
print(df.to_string(index=False))

print("\n" + "=" * 80)
print("DONE!")
print("=" * 80)

