"""
Test automatyczny: Satel AFSK encode/decode roundtrip
======================================================
Uruchom BEZ potrzeby podłączania sprzętu RS-232:

    cd /home/kuba/Documents/-OPS-ContolWebApp/backend
    python test_satel.py
"""

import sys
import os

# Możemy importować serwis bezpośrednio bez ROS/FastAPI
sys.path.insert(0, os.path.dirname(__file__))

from services.satel_service import encode_afsk, decode_afsk, SatelService


def test_roundtrip(message: str, label: str = "") -> bool:
    """Encode then decode, verify match."""
    raw = message.encode("utf-8")
    signal = encode_afsk(raw)
    recovered = decode_afsk(signal)

    try:
        recovered_text = recovered.decode("utf-8")
    except UnicodeDecodeError:
        recovered_text = recovered.hex()

    ok = recovered_text == message
    status = "✅ PASS" if ok else "❌ FAIL"
    tag = f"[{label}] " if label else ""
    print(f"  {status}  {tag}input={message!r}  decoded={recovered_text!r}  "
          f"signal={len(signal)} B")
    return ok


def test_loopback_service():
    """Test SatelService.loopback()"""
    svc = SatelService()
    result = svc.loopback("Satel test loopback 🔁")
    ok = result.get("match", False)
    print(f"  {'✅ PASS' if ok else '❌ FAIL'}  SatelService.loopback()  match={ok}  "
          f"decoded={result.get('decoded')!r}")
    return ok


def test_mock_send_receive():
    """Mock send (generates signal), then mock receive with empty bytes (no signal)."""
    svc = SatelService()
    snd = svc.send("test mock send", mock=True)
    ok = snd.get("status") == "ok" and snd.get("mock") is True
    print(f"  {'✅ PASS' if ok else '❌ FAIL'}  SatelService.send(mock=True)  status={snd.get('status')}")
    return ok


def test_list_ports():
    """list_ports() should return a list (may be empty in CI)."""
    svc = SatelService()
    ports = svc.list_ports()
    ok = isinstance(ports, list)
    print(f"  {'✅ PASS' if ok else '❌ FAIL'}  SatelService.list_ports()  ports={ports}")
    return ok


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n═══════════════════════════════════════════════")
    print("  Satel AFSK Roundtrip Test Suite")
    print("═══════════════════════════════════════════════\n")

    results = []

    print("▶ Roundtrip tests:")
    results.append(test_roundtrip("Hello Satel!", "short"))
    results.append(test_roundtrip("Hello Satel 123", "with digits"))
    results.append(test_roundtrip("A" * 20, "repeated chars"))

    print("\n▶ SatelService tests:")
    results.append(test_loopback_service())
    results.append(test_mock_send_receive())
    results.append(test_list_ports())

    passed = sum(results)
    total  = len(results)
    print(f"\n{'═' * 47}")
    print(f"  Wynik: {passed}/{total} testów zaliczonych")
    print(f"{'═' * 47}\n")

    sys.exit(0 if passed == total else 1)
