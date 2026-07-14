import pandas as pd

df = pd.read_excel('한국투자증권API.xlsx', sheet_name=None)
for sheet_name, sheet_data in df.items():
    for index, row in sheet_data.iterrows():
        row_str = ' '.join([str(val) for val in row.values])
        if '미체결' in row_str or '정정취소가능주문' in row_str or 'VTTC8036R' in row_str:
            print(f"Sheet: {sheet_name}, Row: {index}, Data: {row_str}")
