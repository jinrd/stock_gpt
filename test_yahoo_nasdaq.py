import requests

url = "https://query2.finance.yahoo.com/v1/finance/search?q=나스닥"
headers = {"User-Agent": "Mozilla/5.0"}
res = requests.get(url, headers=headers)
quotes = res.json().get('quotes', [])
print("Quotes length:", len(quotes))
if quotes:
    for q in quotes[:3]:
        print(q.get('symbol'), q.get('shortname'))
