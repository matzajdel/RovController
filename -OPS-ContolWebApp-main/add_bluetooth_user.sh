#!/bin/bash
# Skrypt do dodania użytkownika do grupy bluetooth
# Użycie: edytuj USERNAME poniżej lub podaj jako argument

USERNAME="arkadiuszubnt"  # <- zmień na właściwego użytkownika
if [ ! -z "$1" ]; then
  USERNAME="$1"
fi

if ! getent group bluetooth > /dev/null; then
  echo "Grupa bluetooth nie istnieje. Tworzę..."
  sudo groupadd bluetooth
fi

echo "Dodaję użytkownika $USERNAME do grupy bluetooth..."
sudo usermod -aG bluetooth "$USERNAME"
echo "Gotowe! Wyloguj się i zaloguj ponownie, aby zmiany zadziałały."
