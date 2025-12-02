# Pickup Delay Code Analysis
# Show all shipments with pickup delay codes

import pandas as pd

# Load the data
df = pd.read_pickle('otp_data.pkl')

# Filter for shipments with pickup delay codes (not null and not empty)
pickup_delays = df[(df['pickupDelayCode'].notna()) & 
                   (df['pickupDelayCode'] != '') &
                   (df['mainShipment'] == 'YES')].copy()

# Create the pickup window column (date once, then time range)
def format_pickup_window(row):
    from_str = str(row['pickWindowFrom'])
    to_str = str(row['pickWindowTo'])

    # Split into date and time parts
    if ' ' in from_str and ' ' in to_str:
        from_date, from_time = from_str.split(' ', 1)
        to_date, to_time = to_str.split(' ', 1)

        # If same date, show date once
        if from_date == to_date:
            return f"{from_date} {from_time} - {to_time}"
        else:
            return f"{from_str} - {to_str}"
    else:
        return f"{from_str} - {to_str}"

pickup_delays['Pickup Window'] = pickup_delays.apply(format_pickup_window, axis=1)

# Select the columns we want (orderCode first, Pick Time Departed before Arrived)
result = pickup_delays[[
    'orderCode',
    'pickupDelayCode',
    'pickLocationName',
    'dropLocationName',
    'pickTimeDeparted',
    'pickTimeArrived',
    'Pickup Window'
]].copy()

# Rename columns for better readability
result.columns = [
    'Order Code',
    'Pickup Delay Code',
    'Pick Location',
    'Drop Location',
    'Pick Time Departed',
    'Pick Time Arrived',
    'Pickup Window'
]

print(f"Total shipments with pickup delay codes: {len(result)}")
print("\n" + "="*100)
print(result.to_string(index=False))

