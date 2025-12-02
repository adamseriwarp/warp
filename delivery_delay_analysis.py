# Delivery Delay Code Analysis
# Show all shipments with delivery delay codes

import pandas as pd

# Load the data
df = pd.read_pickle('otp_data.pkl')

# Filter for shipments with delivery delay codes (not null and not empty)
delivery_delays = df[(df['deliveryDelayCode'].notna()) & 
                     (df['deliveryDelayCode'] != '') &
                     (df['mainShipment'] == 'YES')].copy()

# Create the drop window column (date once, then time range)
def format_drop_window(row):
    from_str = str(row['dropWindowFrom'])
    to_str = str(row['dropWindowTo'])
    
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

delivery_delays['Drop Window'] = delivery_delays.apply(format_drop_window, axis=1)

# Select the columns we want (orderCode first, Drop Time Departed before Arrived)
result = delivery_delays[[
    'orderCode',
    'deliveryDelayCode',
    'pickLocationName', 
    'dropLocationName',
    'dropTimeDeparted',
    'dropTimeArrived',
    'Drop Window'
]].copy()

# Rename columns for better readability
result.columns = [
    'Order Code',
    'Delivery Delay Code',
    'Pick Location',
    'Drop Location', 
    'Drop Time Departed',
    'Drop Time Arrived',
    'Drop Window'
]

print(f"Total shipments with delivery delay codes: {len(result)}")
print("\n" + "="*100)
print(result.to_string(index=False))

