#!/bin/bash

# Zabezpieczenie: sprawdzenie uprawnień roota
if [ "$EUID" -ne 0 ]; then
  echo "Proszę uruchomić ten skrypt jako root (np. używając sudo)."
  exit 1
fi

# Konfiguracja ścieżek
INSTALL_DIR="/opt/ros2_cpu_temp"
SCRIPT_PATH="$INSTALL_DIR/cpu_temp_pub.py"
SERVICE_PATH="/etc/systemd/system/ros2_cpu_temp.service"

# Ustalenie nazwy użytkownika, który odpalił sudo, by nie uruchamiać usługi jako root
USER_NAME=${SUDO_USER:-$USER}

echo "🛠️  Tworzenie katalogu na aplikację: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

echo "🐍 Tworzenie węzła ROS 2 w Pythonie..."
cat << 'EOF' > "$SCRIPT_PATH"
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32

class CpuTempPublisher(Node):
    def __init__(self):
        super().__init__('cpu_temp_publisher')
        self.publisher_ = self.create_publisher(Float32, '/cpu_temp', 10)
        # Zegar wywołujący funkcję co 2 sekundy
        self.timer = self.create_timer(2.0, self.timer_callback)

    def timer_callback(self):
        try:
            # Standardowa ścieżka do czujnika temperatury w systemach Linux
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp_raw = f.read().strip()
            
            # Wartość jest w milistopniach, dzielimy na 1000
            temp_c = float(temp_raw) / 1000.0
            
            msg = Float32()
            msg.data = temp_c
            self.publisher_.publish(msg)
            
        except Exception as e:
            self.get_logger().error(f'Nie można odczytać temperatury: {e}')

def main(args=None):
    rclpy.init(args=args)
    node = CpuTempPublisher()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
EOF

# Nadanie uprawnień do wykonania
chmod +x "$SCRIPT_PATH"

echo "⚙️  Tworzenie usługi systemd..."
cat << EOF > "$SERVICE_PATH"
[Unit]
Description=ROS2 Humble CPU Temperature Publisher
After=network.target

[Service]
Type=simple
User=$USER_NAME
# Wczytanie środowiska ROS 2 przed uruchomieniem skryptu
ExecStart=/bin/bash -c "source /opt/ros/humble/setup.bash && /usr/bin/python3 $SCRIPT_PATH"
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

echo "🚀 Uruchamianie usługi..."
systemctl daemon-reload
systemctl enable ros2_cpu_temp.service
systemctl start ros2_cpu_temp.service

echo "✅ Gotowe! Węzeł działa w tle i publikuje dane na topic /cpu_temp."
echo "--------------------------------------------------------"
echo "🔍 Sprawdź logi usługi:"
echo "   journalctl -u ros2_cpu_temp.service -f"
echo "📡 Zobacz wysyłane dane (otwórz nowy terminal i wczytaj ROSa):"
echo "   ros2 topic echo /cpu_temp"
echo "--------------------------------------------------------"