# rov_frontend

Flutterowy frontend (UI) do sterowania ROV, korzystający z pakietu `rov_backend`.

## Uruchomienie

1. Zainstaluj Flutter SDK (i upewnij się, że `flutter` jest w `PATH`).
2. Ten repo jest "minimal" — katalogi platform (`android/`, `ios/`, `web/`, `windows/`, `macos/`, `linux/`) są ignorowane w Gicie.
	Wygeneruj je lokalnie (jednorazowo):

```bash
flutter create .
```

3. W tym folderze uruchom:

```bash
flutter pub get
flutter analyze
flutter run
```

Jeśli chcesz odpalić na Web:

```bash
flutter run -d chrome
```

## Najczęstsze błędy

- `Target of URI doesn't exist: 'package:flutter/material.dart'` / `flutter_test from sdk doesn't exist`:
	- To nie jest błąd w kodzie, tylko w narzędziach/środowisku.
	- Pojawia się gdy uruchamiasz `dart pub get` lub `dart analyze` bez Flutter SDK.
	- Rozwiązanie: używaj `flutter pub get` i `flutter analyze` oraz zainstaluj Flutter.

> Jeśli `flutter run` nie widzi urządzeń, sprawdź `flutter devices`.
