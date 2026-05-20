# rov_backend 🚀

Natywny, wysoce wydajny backend napisany w języku Dart przeznaczony dla aplikacji Flutter na system Android. Pakiet umożliwia bezpośrednie sterowanie atrapą łazika marsjańskiego za pomocą poleceń ROS2 przez WiFi (poprzez ROSBridge WebSocket na porcie `9090`), eliminując potrzebę stosowania jakichkolwiek komputerów lub stacji pośredniczących.

Backend uruchamia w tle lokalny serwer HTTP i WebSocket na porcie `2137`, działając jako przezroczysty serwer proxy/adapter. Dzięki temu oryginalny frontend React (lub nowy frontend we Flutterze) może łączyć się bezpośrednio z telefonem bez wprowadzania jakichkolwiek modyfikacji w kodzie frontendu.

---

## Spis Treści
- [Główne Funkcje](#główne-funkcje)
- [Architektura Systemu](#architektura-systemu)
- [Instalacja i Konfiguracja we Flutterze](#instalacja-i-konfiguracja-we-flutterze)
- [Integracja Lifecycle (Cykl Życia Aplikacji)](#integracja-lifecycle-cykl-życia-aplikacji)
- [Specyfikacja API (Port 2137)](#specyfikacja-api-port-2137)
  - [HTTP REST Endpoints](#http-rest-endpoints)
  - [WebSocket API (`/ws`)](#websocket-api-ws)
- [Zaawansowane Tryby Sterowania (Jazda)](#zaawansowane-tryby-sterowania-jazda)
- [Zarządzanie Bazą Danych](#zarządzanie-bazą-danych)

---

## Główne Funkcje

1. **Bezpośrednie sterowanie (Direct Phone-to-Rover):** Połączenie z protokołem ROSBridge (`ws://IP_ŁAZIKA:9090`) bez zewnętrznego komputera stacjonarnego.
2. **Lokalny serwer proxy (Port 2137):** Obsługa CORS, WebSocket (`/ws`) oraz zapytań HTTP REST dla pełnej kompatybilności z dowolnym frontendem.
3. **Lokalna Baza Danych:** Zapisywanie konfiguracji przycisków, konfiguracji paneli naukowych i makr w formacie JSON bezpośrednio w pamięci telefonu Android.
4. **Zaawansowana Logika Jazdy:** Cztery tryby jazdy (`PROSTY`, `SKRĘT`, `OBRÓT`, `FREESTYLE`) z obsługą strefy martwej (*deadzone*), limitów prędkości, wstecznego biegu i kwadratowego mapowania osi.
5. **Keepalive Watchdog (10Hz):** Ciągłe wysyłanie ramek sterujących `geometry_msgs/msg/Twist` z częstotliwością 10Hz, zapobiegające awaryjnemu zatrzymaniu łazika przez wbudowany Watchdog.
6. **Sekwencje Makr:** Obsługa asynchronicznych serii komend z zadanym opóźnieniem czasu w tle.

---

## Architektura Systemu

```
                                     +-------------------------------------------+
                                     |             Android Device                |
                                     |                                           |
+--------------------+               |  +------------------+     +------------+  |
|   React Frontend   | <---HTTP/WS------->  Local server   | <-> | Local DB   |  |
|  (Webview / Port)  |   Port 2137   |  |   (RovServer)    |     | (JSON)     |  |
+--------------------+               |  +--------+---------+     +------------+  |
                                     |           |                               |
                                     |  +--------v---------+                     |
                                     |  |  ControlService  |                     |
                                     |  |  (Steering Mode) |                     |
                                     |  +--------+---------+                     |
                                     |           |                               |
                                     |  +--------v---------+                     |
                                     |  |   RoverClient    |                     |
                                     |  +--------+---------+                     |
                                     +-----------|-------------------------------+
                                                 |
                                            WiFi | WebSocket (Port 9090)
                                                 v
                                     +---------------------------+
                                     |    Mars Rover (ROS 2)     |
                                     +---------------------------+
```

---

## Instalacja i Konfiguracja we Flutterze

### 1. Dodanie pakietu do projektu Flutter

W pliku `pubspec.yaml` Twojego głównego projektu Flutter dodaj zależność do folderu `rov_backend`:

```yaml
dependencies:
  flutter:
    sdk: flutter
  
  # Import lokalny pakietu backendu
  rov_backend:
    path: ./rov_backend
  
  # Wymagane do pobrania ścieżki dokumentów na telefonie
  path_provider: ^2.1.1
```

### 2. Inicjalizacja i Uruchomienie Backend-u

Aby uruchomić serwer backendu, należy najpierw ustalić bezpieczną ścieżkę do przechowywania plików bazy danych (za pomocą `path_provider`), a następnie wywołać metodę `.start()` na instancji `RovBackend`.

Najlepiej zrobić to w pliku `lib/main.dart` przed uruchomieniem interfejsu użytkownika aplikacji:

```dart
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:rov_backend/rov_backend.dart';

// Utworzenie globalnego koordynatora (Singleton lub obiekt globalny)
final rovBackend = RovBackend();

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // 1. Pobranie bezpiecznego katalogu na dokumenty w systemie Android
  final directory = await getApplicationDocumentsDirectory();
  final String dbStoragePath = directory.path;

  // 2. Konfiguracja adresu IP łazika (np. z ustawień aplikacji lub domyślny)
  const String roverIp = "192.168.2.100"; // Zmień na IP swojego łazika

  try {
    // 3. Uruchomienie backendu
    await rovBackend.start(
      roverIp: roverIp,
      storagePath: dbStoragePath,
      localPort: 2137, // Lokalny port serwera proxy (default: 2137)
      roverPort: 9090, // Port rosbridge na łaziku (default: 9090)
    );
    print("Backend został pomyślnie uruchomiony!");
  } catch (e) {
    print("Błąd podczas startu backendu: $e");
  }

  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Rov Controller',
      theme: ThemeData.dark(),
      home: const HomeScreen(),
    );
  }
}
```

---

## Integracja Lifecycle (Cykl Życia Aplikacji)

Aplikacje na Androidzie mogą zostać zminimalizowane, zawieszone przez system, lub całkowicie zamknięte. Aby uniknąć wycieków pamięci, zajmowania portów w tle lub niepotrzebnego zużycia baterii, **należy odpowiednio zarządzać cyklem życia backendu**.

Do tego celu zaleca się użycie widżetu typu `StatefulWidget` oraz klasy `WidgetsBindingObserver`:

```dart
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:rov_backend/rov_backend.dart';
import 'main.dart'; // import instancji rovBackend

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    // Rejestracja obserwatora cyklu życia aplikacji
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    // Usunięcie obserwatora cyklu życia
    WidgetsBinding.instance.removeObserver(this);
    // Bezpieczne zatrzymanie serwerów przy zamykaniu ekranu
    rovBackend.stop();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    
    if (state == AppLifecycleState.paused || state == AppLifecycleState.detached) {
      // Aplikacja idzie do tła lub jest zamykana - zatrzymujemy loop sterowania i klientów
      print("AppLifecycle: Aplikacja w tle - zatrzymanie backendu");
      rovBackend.stop();
    } else if (state == AppLifecycleState.resumed) {
      // Aplikacja wraca na pierwszy plan - wznawiamy połączenia i serwer
      print("AppLifecycle: Powrót aplikacji - wznawianie backendu");
      _rebuildBackend();
    }
  }

  Future<void> _rebuildBackend() async {
    if (!rovBackend.isStarted) {
      final directory = await getApplicationDocumentsDirectory();
      await rovBackend.start(
        roverIp: "192.168.2.100", 
        storagePath: directory.path,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Sterownik Łazika Marsjańskiego"),
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            ElevatedButton(
              onPressed: () async {
                // Bezpośrednie wywołanie metody z backendu w kodzie Dart!
                rovBackend.controlService.publishStop();
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text("Wysłano STOP bezpośrednio z Dart")),
                );
              },
              child: const Text("Zatrzymaj Łazik (Direct Dart)"),
            ),
          ],
        ),
      ),
    );
  }
}
```

---

## Specyfikacja API (Port 2137)

Lokalny serwer udostępnia zestaw punktów końcowych HTTP REST oraz serwer WebSocket, zapewniając 100% kompatybilności wstecznej z oryginalnym kodem frontendu React.

### HTTP REST Endpoints

| Metoda | Endpoint | Opis | Przykładowy Payload / Odpowiedź |
| :--- | :--- | :--- | :--- |
| **GET** | `/health` lub `/status` | Sprawdzenie statusu serwera i połączenia z łazikiem | `{"status":"healthy","rover_connected":true,"rover_ip":"192.168.2.100"}` |
| **GET** | `/steering/get_state` | Pobranie aktualnego stanu silników i trybu jazdy | `{"status":"success","state":{...}}` |
| **GET** | `/ros/saved_commands` | Pobranie wszystkich zapisanych niestandardowych komend | `{"commands":{"/my_topic":[...]}}` |
| **GET** | `/ros/ui_config` | Pobranie ustawień UI dla danego topicu (`?topic=name`) | Odrębny obiekt JSON konfiguracji |
| **GET** | `/ros/science_layout` | Pobranie konfiguracji kafelków panelu naukowego | `{"instance":"default", "layout": [...]}` |
| **POST** | `/joystick` | Aktualizacja współrzędnych wirtualnego joysticka | `{"x": 0.5, "y": -0.8}` |
| **POST** | `/joystick/release` | Zwolnienie nacisku joysticka (reset do 0,0 i stop) | Brak |
| **POST** | `/joystick/activate` | Aktywacja trybu joysticka | Brak |
| **POST** | `/joystick/deactivate` | Dezaktywacja joysticka (wysyła STOP) | Brak |
| **POST** | `/cmd_vel` | Wysłanie uproszczonej komendy prędkości liniowej/kątowej | `{"linear_x": 0.5, "angular_z": -0.2}` |
| **POST** | `/cmd_vel_full` | Wysłanie pełnego obiektu typu Twist | Obiekt JSON kompatybilny z `geometry_msgs/msg/Twist` |
| **POST** | `/stop` | Natychmiastowe zatrzymanie wszystkich silników łazika | Brak |
| **POST** | `/steering/set_drive_mode` | Zmiana trybu jazdy (0 = PROSTY, 1 = SKRĘT, 2 = OBRÓT, 3 = FREESTYLE) | `{"mode_id": 2}` |
| **POST** | `/steering/set_motor_mode` | Ustawienie trybu silników (0.0 = PID, 1.0 = PWM) | `{"motor_mode": 1.0}` |
| **POST** | `/steering/set_speed_limits` | Zmiana limitów prędkości maksymalnej i skrętu | `{"max_speed": 0.8, "max_turn": 0.6}` |
| **POST** | `/steering/set_target_topic` | Zmiana nazwy topicu ROS 2 dla poleceń jazdy | `{"topic": "cmd_vel_nav"}` |
| **POST** | `/array_topic/<1-6>` | Bezpośrednie wysłanie wartości na odpowiednią oś manipulatora | `{"value": 45.0}` |
| **POST** | `/ros/saved_commands` | Zapisanie nowej niestandardowej komendy do bazy | `{"topic":"/led","name":"ON","value":1,"type":"std_msgs/msg/Int32","isDefault":true}` |
| **POST** | `/ros/ui_config` | Zapisanie układu przycisków UI dla danego topicu | `{"topic": "/led", "config": {...}}` |
| **POST** | `/ros/science_layout` | Zapisanie nowego szablonu panelu naukowego | Obiekt JSON szablonu |
| **POST** | `/ros/publish` | Jednorazowe opublikowanie dowolnej komendy w systemie ROS 2 | `{"topic": "/test", "type": "std_msgs/msg/Float64", "value": 3.14}` |
| **POST** | `/ros/macro` | Uruchomienie sekwencji makr w tle z opóźnieniami czasowymi | `{"steps": [{"action":"publish", "topic":"/x", "value":1}, {"action":"wait_time", "delay":1.5}]}` |
| **DELETE** | `/ros/saved_commands` | Usunięcie wybranej komendy z lokalnej bazy danych | `{"topic": "/led", "name": "ON"}` |

### WebSocket API (`/ws`)

Najbardziej zalecaną metodą komunikacji z wirtualnym joystickiem i gamepadem w czasie rzeczywistym jest połączenie WebSocket z adresem `ws://localhost:2137/ws`.

Odbiera ono zdarzenia o następujących formatach JSON:

#### 1. Ruch Joysticka
```json
{
  "type": "joystick",
  "x": 0.452,
  "y": -0.891
}
```

#### 2. Zwolnienie Joysticka
```json
{
  "type": "joystick_release"
}
```

#### 3. Zdarzenia Gamepada (HID Event)
Kompatybilne ze standardem sterowania kontrolerami w przeglądarkach internetowych:
```json
{
  "type": "gamepad_event",
  "action": "move",
  "code": "LJoy",
  "axes": {
    "x": 0.05,
    "y": -0.85
  }
}
```

---

## Zaawansowane Tryby Sterowania (Jazda)

`ControlService` automatycznie oblicza wartości sterowania kołami w oparciu o wyselekcjonowany tryb:

1. **PROSTY (mode_id: 0):** Ruch do przodu/tyłu lub jazda bokiem (krab). Wykorzystuje przełącznik wstecznego biegu (Bumper `RB` na gamepadzie).
2. **SKRĘT (mode_id: 1):** Sterowanie łagodnymi łukami przy użyciu analogów o małej czułości.
3. **OBRÓT (mode_id: 2):** Obracanie łazika w miejscu wokół własnej osi.
4. **FREESTYLE (mode_id: 3):** Pełna swoboda ruchu. Wykorzystuje zaawansowany algorytm *Square Mapping* oraz nieliniowe skalowanie sześcienne (`x^3`), zapewniając wyjątkowo płynne sterowanie analogami.

---

## Zarządzanie Bazą Danych

Wszystkie konfiguracje są zapisywane w bezpiecznej przestrzeni dyskowej przypisanej do Twojej aplikacji Android. Dane są trwale zapisywane w postaci czytelnych plików JSON:
- `saved_commands.json` (własne komendy i presety)
- `saved_ui_config.json` (konfiguracje rozmieszczenia przycisków w UI)
- `science_layout_{instance}.json` (szablony paneli badawczych)

Pliki te są w pełni niezależne i chronione przed usunięciem w trakcie aktualizacji aplikacji. Wyczyszczenie danych aplikacji w ustawieniach telefonu Android zresetuje bazę do stanu początkowego.
