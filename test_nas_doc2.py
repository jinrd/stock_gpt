import pandas as pd
df = pd.read_excel('한국투자증권API.xlsx', sheet_name='해외주식조건검색')
for idx, row in df.iterrows():
    if "실전 Domain" in str(row.values) or "모의 Domain" in str(row.values):
        print(row.values)
