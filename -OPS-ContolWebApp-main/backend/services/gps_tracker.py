"""
GPS Service — standalone ROS 2 + Flask microservice for rover positioning.

Subscribes to /gps/fix (NavSatFix) and /heading (Float32) topics and
exposes the current rover position over a lightweight Flask HTTP API
on port 5001.

Features:
  • Live position tracking from ROS 2 GPS topics
  • Manual position override (when manual_mode is enabled)
  • Position history logging to CSV
  • Last-known position persistence across restarts

Configuration is stored in ``gps_config.json`` alongside this file.
"""
import rclpy
from rclpy.node import Node
 
from sensor_msgs.msg import NavSatFix
from std_msgs.msg import Float32
from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
import json
import os
import csv
from datetime import datetime
import time

# --- ŚCIEŻKI ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')
CONFIG_FILE = os.path.join(DATA_DIR, 'gps_config.json')
LOG_FILE = os.path.join(BASE_DIR, '..', 'logs', 'gps_history.csv')
LAST_POS_FILE = os.path.join(DATA_DIR, 'last_position.json')

# --- DOMYŚLNA KONFIGURACJA ---
default_config = {
    "log_data": False,
    "log_interval": 1.0,
    "manual_mode": False
}

# --- STAN ŁAZIKA (Domyślnie zera, ale zaraz załadujemy z pliku) ---
rover_state = {
    'lat': 50.041187,  # Domyślnie np. Rzeszów, jeśli plik nie istnieje
    'lng': 21.999121,
    'alt': 0.0,
    'heading': 0.0
}
current_config = default_config.copy()
last_log_time = datetime.now()

# --- FUNKCJE PLIKOWE ---
def load_config():
    global current_config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                current_config = json.load(f)
        except:
            pass
    else:
        save_config()

def save_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump(current_config, f, indent=4)

# --- NOWOŚĆ: Zapis/Odczyt ostatniej pozycji ---
def load_last_position():
    global rover_state
    if os.path.exists(LAST_POS_FILE):
        try:
            with open(LAST_POS_FILE, 'r') as f:
                data = json.load(f)
                rover_state['lat'] = data.get('lat', rover_state['lat'])
                rover_state['lng'] = data.get('lng', rover_state['lng'])
                print(f"Załadowano ostatnią pozycję: {rover_state['lat']}, {rover_state['lng']}")
        except Exception as e:
            print(f"Błąd odczytu ostatniej pozycji: {e}")

def save_last_position():
    try:
        with open(LAST_POS_FILE, 'w') as f:
            json.dump({
                'lat': rover_state['lat'],
                'lng': rover_state['lng']
            }, f)
    except Exception as e:
        print(f"Błąd zapisu pozycji: {e}")

def append_to_log(lat, lng, alt):
    file_exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['Timestamp', 'Latitude', 'Longitude', 'Altitude'])
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), lat, lng, alt])

# --- FLASK ---
app = Flask(__name__)
CORS(app)

@app.route('/api/gps', methods=['GET'])
def get_gps_data():
    return jsonify(rover_state)

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(current_config)

@app.route('/api/config', methods=['POST'])
def update_config():
    global current_config
    new_data = request.json
    current_config.update(new_data)
    save_config()
    return jsonify({"status": "ok", "config": current_config})

@app.route('/api/set_position', methods=['POST'])
def set_manual_position():
    data = request.json
    if current_config.get('manual_mode'):
        rover_state['lat'] = float(data.get('lat', rover_state['lat']))
        rover_state['lng'] = float(data.get('lng', rover_state['lng']))
        save_last_position() # Zapisz przy ręcznej zmianie
        return jsonify({"status": "ok"})
    else:
        return jsonify({"status": "error"}), 400

def run_flask():
    app.run(host='0.0.0.0', port=5001, debug=False)

# --- ROS NODE ---
class GpsService(Node):
    def __init__(self):
        super().__init__('gps_service_node')
        self.create_subscription(NavSatFix, '/gps/fix', self.gps_callback, 10)
        self.create_subscription(Float32, '/heading', self.heading_callback, 10)
        
        load_config()
        load_last_position() # <-- Ładujemy pozycję przy starcie
        self.get_logger().info("GPS Service Ready. Port 5001.")

    def gps_callback(self, msg):
        if current_config.get('manual_mode'):
            return

        global last_log_time
        # Aktualizacja stanu
        rover_state['lat'] = msg.latitude
        rover_state['lng'] = msg.longitude
        rover_state['alt'] = msg.altitude
        
        # Zapisz "ostatnią pozycję" (dla restartu systemu)
        # Robimy to w pamięci operacyjnej OS, zapis fizyczny zależy od bufora,
        # ale dla bezpieczeństwa można to robić rzadziej. Tu robimy przy każdym callbacku
        # bo to prosty plik tekstowy.
        save_last_position()

        # Logika historii (CSV)
        if current_config.get('log_data'):
            now = datetime.now()
            if (now - last_log_time).total_seconds() >= current_config.get('log_interval', 1.0):
                append_to_log(msg.latitude, msg.longitude, msg.altitude)
                last_log_time = now

    def heading_callback(self, msg):
        rover_state['heading'] = msg.data

def main(args=None):
    rclpy.init(args=args)
    gps_service = GpsService()
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    try:
        rclpy.spin(gps_service)
    except KeyboardInterrupt:
        pass
    finally:
        gps_service.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()