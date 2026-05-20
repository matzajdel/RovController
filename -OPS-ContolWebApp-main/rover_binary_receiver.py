#!/usr/bin/env python3
"""
Rover Binary Receiver - Odpowiednik na łazik
===========================================
Ten skrypt należy uruchomić na komputerze ŁAZIKA.
Czyta zdefiniowane ramki binarne (Satel) i publikuje
bezpośrednio do Twoich poszczególnych topiców ROS 2.
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Int8MultiArray, Int32MultiArray, Float64MultiArray, Float32MultiArray
import serial
import threading
import argparse
import time

class SerialReceiverNode(Node):
    def __init__(self, port_name: str, baud: int):
        super().__init__('serial_receiver')
        
        # Odtworzone topici wprost z 'ros2 topic list' i oryginalnego bridge'a
        self.drive_publisher = self.create_publisher(Twist, '/cmd_vel', 10)
        self.mani_publisher = self.create_publisher(Float64MultiArray, '/array_topic', 10)
        self.arrow_publisher = self.create_publisher(Int32MultiArray, '/arrow_keys', 10)
        self.rgb_publisher = self.create_publisher(Float32MultiArray, '/rgb', 10)
        self.gps_publisher = self.create_publisher(Float64MultiArray, '/gps_waypoint', 10)
        self.button_publisher = self.create_publisher(Int32MultiArray, '/ESP32_GIZ/led_state_topic', 10)
        
        self.port_name = port_name
        self.baud = baud
        self.ser = None
        
        self.get_logger().info(f"Uruchamianie nasłuchu Satel na porcie {port_name} (Baud: {baud})")
        self._connect_serial()
        
        self.running = True
        self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.read_thread.start()

    def _connect_serial(self):
        try:
            self.ser = serial.Serial(self.port_name, self.baud, timeout=1)
            self.get_logger().info("✅ Połączono z radiomodemem Satel. Nasłuchuję ramek binarnych...")
        except Exception as e:
            self.get_logger().error(f"❌ Błąd otwarcia portu szeregowego: {e}")

    def _byte_to_float(self, val: int) -> float:
        """Mapuje bajt [0, 254] z powrotem na float [-1.0, 1.0]"""
        return (val - 128.0) / 127.0

    def _byte_to_float_100(self, val: int) -> float:
        """Mapuje bajt [0, 254] z powrotem na float [-100.0, 100.0]"""
        return (val / 254.0 * 200.0) - 100.0

    def _read_loop(self):
        buffer = b''
        while self.running:
            if self.ser and self.ser.is_open:
                try:
                    data = self.ser.read(self.ser.in_waiting or 1)
                    if data:
                        buffer += data
                        buffer = self._process_buffer(buffer)
                except Exception as e:
                    self.get_logger().error(f"Błąd odczytu: {e}")
                    time.sleep(1)
            else:
                time.sleep(1)
                
    def _process_buffer(self, buffer: bytes) -> bytes:
        while True:
            start_idx = buffer.find(b'$')
            if start_idx == -1:
                return b'' # Brak znaku startu ramki, czyścimy śmieci
            
            buffer = buffer[start_idx:]
            end_idx = buffer.find(b'#')
            
            if end_idx == -1:
                if len(buffer) > 256: # Ochrona przed przepełnieniem bufora
                    return buffer[1:]
                return buffer # Czekamy na dokończenie ramki
                
            frame = buffer[:end_idx+1]
            buffer = buffer[end_idx+1:]
            self._parse_frame(frame)
            
        return buffer

    def _parse_frame(self, frame: bytes):
        """
        Słownik nagłówków (Headers) w protokole binarnym:
          DV (Drive Vector)    - Jazda 2-osiowa (linear_x, angular_z). Wsteczna kompatybilność.
          D4 (Drive 4-axis)    - Jazda 4-osiowa (linear_x, linear_y, linear_z, angular_z). Pełne wsparcie m.in. dla trybu Hill Climb.
          MN (Manipulator)     - Ramiona manipulatora (6 osi).
          GS (Gamepad/Steering)- Klawisze strzałek / d-pad (4 przyciski).
          SL (Science LED)     - Pojedyncza wartość jasności (szary kolor). Wsteczna kompatybilność.
          RG (RGB)             - Pasek LED RGB (3 oddzielne wartości: Red, Green, Blue).
          GL (General LED)     - Stan łazika: Tryb jazdy, Autonomia, Manual (przekazywane jako bitmaska).
          GP (GPS)             - Współrzędne GPS (Longitude, Latitude). Obecnie placeholder.
        """
        if len(frame) < 5: 
            return # Zbyt krótka ramka: $ + 2 znaki nagłówka + checksum + #
        
        header = frame[1:3].decode('ascii', errors='ignore')
        data = frame[3:-2]
        checksum = frame[-2]
        
        # Weryfikacja sumy kontrolnej Modulo-256
        calculated_checksum = sum(data) % 256
        if checksum != calculated_checksum:
            self.get_logger().warn(f"Błąd CRC dla {header}. Oczekiwano {checksum}, jest {calculated_checksum}")
            return
            
        try:
            if header == "DV" and len(data) == 2:
                msg = Twist()
                msg.linear.x = self._byte_to_float(data[0])
                msg.angular.z = self._byte_to_float(data[1])
                self.drive_publisher.publish(msg)
                
            elif header == "D4" and len(data) == 4:
                msg = Twist()
                msg.linear.x = self._byte_to_float(data[0])
                msg.linear.y = self._byte_to_float(data[1])
                msg.linear.z = self._byte_to_float(data[2])
                msg.angular.z = self._byte_to_float(data[3])
                self.drive_publisher.publish(msg)
                
            elif header == "MN" and len(data) == 6:
                msg = Float64MultiArray()
                msg.data = [self._byte_to_float_100(b) for b in data]
                self.mani_publisher.publish(msg)
                
            elif header == "GS" and len(data) == 4:
                msg = Int32MultiArray()
                msg.data = list(data)
                self.arrow_publisher.publish(msg)
                
            elif header == "SL" and len(data) == 1:
                msg = Float32MultiArray()
                val = float(data[0])
                msg.data = [val, val, val] # Szary kolor o podanej jasności
                self.rgb_publisher.publish(msg)
                
            elif header == "RG" and len(data) == 3:
                msg = Float32MultiArray()
                msg.data = [float(data[0]), float(data[1]), float(data[2])]
                self.rgb_publisher.publish(msg)
                
            elif header == "GL" and len(data) == 1:
                msg = Int32MultiArray()
                manual = (data[0] >> 0) & 1
                autonomy = (data[0] >> 1) & 1
                kill = (data[0] >> 2) & 1
                
                mode = 0 if kill else 1
                r = 255 if autonomy else 0
                b = 255 if manual else 0
                
                msg.data = [mode, r, 0, b]
                self.button_publisher.publish(msg)
                
            elif header == "GP" and len(data) == 8: # Opcjonalnie na przyszłość dla GPS
                pass
                
        except Exception as e:
             self.get_logger().error(f"Błąd parsowania dla nagłówka {header}: {e}")

def main(args=None):
    rclpy.init(args=args)
    parser = argparse.ArgumentParser(description="Rover Satel Binary Receiver")
    parser.add_argument("--port", type=str, default="/dev/ttyUSB0", help="Port szeregowy Satela")
    parser.add_argument("--baud", type=int, default=9600, help="Prędkość RS-232")
    parsed_args, _ = parser.parse_known_args()
    
    node = SerialReceiverNode(port_name=parsed_args.port, baud=parsed_args.baud)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.running = False
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
