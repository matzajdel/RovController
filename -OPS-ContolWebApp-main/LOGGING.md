# Rover Activity Logging

## Opis

System automatycznego logowania wszystkich komend wysłanych do łazika, w szczególności:
- **cmd_vel** - komendy prędkości (linear_x, angular_z)
- **array_topic** - komendy przycisków tablic (button_id, value)
- **Joystick** - komendy joysticka
- **Twist** - pełne komendy twist
- **Emergency Stop** - nadzór nad statusem zatrzymania awaryjnego

## Ścieżka do logów

Logi są zapisywane w: `backend/logs/rover_activity.log`

Przykład pełnej ścieżki: `/home/kuba/-OPS-ContolWebApp/backend/logs/rover_activity.log`

## Rotacja pliku logów

- **Maksymalny rozmiar pliku**: ~10 MB
- **Liczba backup'ów**: 5 poprzednich plików
- **Nazewnictwo**: 
  - `rover_activity.log` - aktualny plik
  - `rover_activity.log.1` - poprzedni backup
  - `rover_activity.log.2` - starszy backup
  - itd.

## Format logów

Każdy log zawiera:
- **Timestamp** - czas zdarzenia (YYYY-MM-DD HH:MM:SS)
- **Typ zdarzenia** - CMD_VEL, ARRAY_TOPIC, JOYSTICK, TWIST_FULL, EMERGENCY_STOP, GAMEPAD
- **Dane** - wartości wysłanych komend
- **Źródło** - "api" lub "api_main"

### Przykłady logów:

```
2026-03-06 14:23:45 | INFO | CMD_VEL | linear_x=0.5000 | angular_z=0.2500 | source=api
2026-03-06 14:23:46 | INFO | ARRAY_TOPIC | button_id=1 | value=100.0 | source=api
2026-03-06 14:23:47 | INFO | JOYSTICK | x=0.7500 | y=0.5000 | source=api
2026-03-06 14:23:48 | WARNING | EMERGENCY_STOP | source=api
```

## Jak czytać logi

W terminalu:

```bash
# Ostatnie 50 linii
tail -50 backend/logs/rover_activity.log

# Wyświetlanie w czasie rzeczywistym
tail -f backend/logs/rover_activity.log

# Wyszukiwanie konkretnych komend
grep "CMD_VEL" backend/logs/rover_activity.log
grep "ARRAY_TOPIC" backend/logs/rover_activity.log
grep "EMERGENCY_STOP" backend/logs/rover_activity.log

# Liczba wszystkich komend
wc -l backend/logs/rover_activity.log

# Wyszukiwanie w danym zakreie czasu
grep "14:23" backend/logs/rover_activity.log
```

## Statystyki logów

Aby sprawdzić ile operacji było wykonanych:

```bash
# Ile operacji cmd_vel
grep -c "CMD_VEL" backend/logs/rover_activity.log

# Ile operacji array_topic
grep -c "ARRAY_TOPIC" backend/logs/rover_activity.log

# Ile zatrzymań awaryjnych
grep -c "EMERGENCY_STOP" backend/logs/rover_activity.log
```

## Integracja w kodzie

Logi są automatycznie przychwyotwane w następujących miejscach:

### W `backend/routes/robot.py`:
- `/cmd_vel` - loguje linear_x i angular_z
- `/cmd_vel_full` - loguje pełny twist
- `/joystick` - loguje x i y
- `/stop` - loguje emergency stop
- `/topic_array/button1-3` - loguje naciśniętay przycisk
- `/array_topic/{button_id}` - loguje przycisk i wartość

### W `backend/main.py`:
- Wszystkie powyższe endpoints (ze starego API)

## Import i użycie w nowych modułach

Jeśli dodasz nowy endpoint lub funkcję, możesz dodać logowanie:

```python
from rover_logger import log_cmd_vel, log_array_topic, log_joystick, log_twist, log_stop

# Logowanie cmd_vel
log_cmd_vel(linear_x=0.5, angular_z=0.25, source="moja_funkacja")

# Logowanie array_topic
log_array_topic(button_id=1, value=100.0, source="moja_funkcja")

# Inne
log_joystick(x=0.5, y=0.75, source="moja_funkcja")
log_twist(0.5, 0, 0, 0, 0, 0.25, source="moja_funkcja")
log_stop(source="moja_funkcja")
```

## Czyszczenie logów

Jeśli chcesz wyczyścić logi (być ostrożny!):

```bash
# Usuń wszystkie logi
rm backend/logs/rover_activity.log*

# Lub przesuń do archiwum
mv backend/logs/rover_activity.log* /tmp/rover_logs_backup/
```

## Analiza logów

Przykładowe skrypty do analizy logów:

```bash
# Najczęściej używane komendy
grep -o "CMD_VEL\|ARRAY_TOPIC\|JOYSTICK" backend/logs/rover_activity.log | sort | uniq -c | sort -rn

# średnia wartość linear_x z cmd_vel
grep "CMD_VEL" backend/logs/rover_activity.log | grep -o "linear_x=[0-9.-]*" | cut -d= -f2 | awk '{sum+=$1} END {print "Average: " sum/NR}'
```
