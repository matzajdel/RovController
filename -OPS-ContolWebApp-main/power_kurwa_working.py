import rclpy
from rclpy.node import Node
from std_msgs.msg import String

class PowerKurwaTrzymaj(Node):
    def __init__(self):
        super().__init__('PowerRangers')
        
        # Zbiór (set) do przechowywania unikalnych, aktualnie włączonych elementów (np. 'C2', 'C5')
        self.active_items = set()

        # 1. Subskrybent nasłuchujący na topicu /string_topic
        self.subscription = self.create_subscription(
            String,
            '/string_topic',
            self.listener_callback,
            10
        )

        # 2. Publisher publikujący na tym samym topicu
        self.publisher_ = self.create_publisher(String, '/string_topic', 10)

        # 3. Timer do cyklicznego wysyłania zapisanego stanu (np. co 3 sekundy)
        # Możesz dostosować ten czas lub całkowicie go usunąć, jeśli wolisz wysyłać tylko przy zmianie.
        self.timer = self.create_timer(0.1, self.publish_saved_states)
        
        self.get_logger().info('Węzeł uruchomiony. Nasłuchuję i publikuję na /string_topic...')

    def listener_callback(self, msg):
        # Pobieramy tekst i usuwamy ewentualne białe znaki
        text = msg.data.strip()

        # Przetwarzanie wiadomości włączającej (ON)
        if text.endswith('-ON'):
            item = text.split('-ON')[0]
            # Sprawdzamy, czy element jest nowy, aby zapobiec pętli z własnych wiadomości
            if item not in self.active_items:
                self.active_items.add(item)
                self.get_logger().info(f'Nowy element ON zapamiętany: {item}')
                self.publish_saved_states() # Opublikuj natychmiast po zmianie

        # Przetwarzanie wiadomości wyłączającej (OFF)
        elif text.endswith('-OFF'):
            item = text.split('-OFF')[0]
            if item in self.active_items:
                self.active_items.remove(item)
                self.get_logger().info(f'Element OFF usunięty: {item}')
                self.publish_saved_states() # Opublikuj natychmiast po zmianie

    def publish_saved_states(self):
        """Wysyła zapisane wiadomości na ten sam topic."""
        # Jeśli nic nie jest włączone, możemy opcjonalnie nic nie wysyłać
        if not self.active_items:
            return 

        # Wyślij każdy aktywny element jako osobną wiadomość CX-ON
        for item in self.active_items:
            msg = String()
            msg.data = f'{item}-ON'
            self.publisher_.publish(msg)
            
        # UWAGA: Ponieważ wysyłamy format 'CX-ON', nasz własny subskrybent to odbierze, 
        # ale warunek 'if item not in self.active_items' zignoruje tę wiadomość, blokując pętlę.

def main(args=None):
    rclpy.init(args=args)
    node = PowerKurwaTrzymaj()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
