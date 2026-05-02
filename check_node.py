import requests
import json

try:
    r = requests.get("http://localhost:8005/peers", timeout=5)
    print("Node 8005 Peers:")
    print(json.dumps(r.json(), indent=2))
except Exception as e:
    print(f"Error checking 8005: {e}")

try:
    r = requests.get("http://localhost:8005/health", timeout=5)
    print("\nNode 8005 Health:")
    print(json.dumps(r.json(), indent=2))
except Exception as e:
    print(f"Error checking 8005 health: {e}")
