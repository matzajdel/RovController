#!/bin/bash
# Test script for Robot Visualization endpoints

BASE_URL="http://localhost:2137"

echo "🤖 Testing Robot Visualization API Endpoints"
echo "=============================================="

# Test 1: Health check
echo -e "\n1️⃣ Testing health endpoint..."
curl -s "${BASE_URL}/health" | python3 -m json.tool

# Test 2: Get URDF
echo -e "\n2️⃣ Testing URDF endpoint..."
curl -s "${BASE_URL}/robot/urdf" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f'URDF source: {data[\"source\"]}'); print(f'URDF length: {len(data[\"urdf\"])} chars')"

# Test 3: Get robot status
echo -e "\n3️⃣ Testing robot status..."
curl -s "${BASE_URL}/robot/status" | python3 -m json.tool

# Test 4: Get presets
echo -e "\n4️⃣ Testing presets..."
curl -s "${BASE_URL}/robot/presets" | python3 -c "import sys, json; data=json.load(sys.stdin); print('Available presets:', list(data['presets'].keys()))"

# Test 5: Execute home preset
echo -e "\n5️⃣ Testing home preset execution..."
curl -s -X POST "${BASE_URL}/robot/preset/home" | python3 -m json.tool

# Test 6: Set joint positions
echo -e "\n6️⃣ Testing set joints endpoint..."
curl -s -X POST "${BASE_URL}/robot/set_joints" \
  -H "Content-Type: application/json" \
  -d '{
    "joint_names": ["joint_base", "joint_shoulder"],
    "positions": [0.5, -0.3],
    "duration": 2.0
  }' | python3 -m json.tool

# Test 7: IK solve
echo -e "\n7️⃣ Testing IK solver..."
curl -s -X POST "${BASE_URL}/robot/ik_solve" \
  -H "Content-Type: application/json" \
  -d '{
    "target_position": [0.3, 0.2, 0.5],
    "chain_name": "manipulator"
  }' | python3 -m json.tool

echo -e "\n✅ All tests completed!"
echo -e "\n📝 Next steps:"
echo "   1. Open frontend: http://localhost:5173/manipulator"
echo "   2. Check WebSocket connection in browser console"
echo "   3. Try moving joint sliders"
echo "   4. Test preset buttons"
