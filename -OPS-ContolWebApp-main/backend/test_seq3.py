import requests, time

payload = {
    "steps": [
        {
            "type": "publish",
            "topic": "/rgb",
            "operation": "+=",
            "value": [1, 1, 1],
            "run_in_background": True,
            "interval_s": 0.2
        },
        {
            "type": "wait",
            "topic": "/rgb",
            "condition": "eq",
            "value": [4, 4, 4],
            "timeout_s": 10.0
        }
    ]
}

res = requests.post("http://localhost:2137/science/sequence/run", json=payload)
run_id = res.json()["run_id"]
print(f"Run ID: {run_id}")

for _ in range(25):
    st = requests.get(f"http://localhost:2137/science/sequence/status/{run_id}").json()
    print(st["status"], st.get("message"))
    if st["status"] in ("completed", "error"):
        break
    time.sleep(0.5)
