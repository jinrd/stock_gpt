import requests

try:
    res = requests.get("http://localhost:8000/api/screener?exchange=NAS")
    print("Status:", res.status_code)
    print("Data:", res.json())
except Exception as e:
    print("Error:", e)
