import pandas as pd
from pathlib import Path
from datetime import datetime

# Find all CSV files in the current directory (root folder)
csv_files = list(Path('.').glob('*.csv'))


if not csv_files:
    print("No CSV files found in the root folder.")
    exit(0)

print(f"Found {len(csv_files)} CSV files:")
for f in csv_files:
    print(f" - {f}")

# Read and concatenate all CSV files
df_list = []
for file in csv_files:
    try:
        df = pd.read_csv(file)
        df_list.append(df)
    except Exception as e:
        print(f"Error reading {file}: {e}")

if not df_list:
    print("No data to merge.")
    exit(0)

merged_df = pd.concat(df_list, ignore_index=True)

# Save merged file with timestamp
out_name = f"merged_training_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
merged_df.to_csv(out_name, index=False)
print(f"Merged CSV saved as {out_name}")
