import requests, time, sys

payload = {
    "steps": [
        {
            "type": "publish",
            "topic": "/cmd_vel",
            "operation": "+=",
            "value": {"linear": {"x": 1.0, "y": 0.0, "z": 0.0}, "angular": {"x": 1.0, "y": 0.0, "z": 0.0}},
            "run_in_background": True,
            "interval_s": 1.0
        },
        {
            "type": "wait",
            "topic": "/cmd_vel",
            "condition": "eq",
            "value": {"linear": {"x": 3.0, "y": 0.0, "z": 0.0}, "angular": {"x": 3.0, "y": 0.0, "z": 0.0}},
            "timeout_s": 10.0
        }
    ]
}

print("Posting sequence...", flush=True)
try:
    res = requests.post("http://localhost:2137/science/sequence/run", json=payload)
    res.raise_for_status()
    run_id = res.json()["run_id"]
    print(f"Run ID: {run_id}", flush=True)

    for _ in range(15):
        st = requests.get(f"http://localhost:2137/science/sequence/status/{run_id}").json()
        print(f"Status: {st.get('status')} Message: {st.get('message')}", flush=True)
        if st.get("status") in ("completed", "error"):
            break
        time.sleep(1)
except Exception as e:
    print(e)
