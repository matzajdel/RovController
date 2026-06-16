# RovController

Kompletny zestaw narzędzi do sterowania ROV i platformami robotycznymi, obejmujący:
- mobilny frontend we Flutterze,
- lekki backend w Dart działający lokalnie na urządzeniu,
- skrypty operacyjne do uruchamiania kamer, usług i mostów komunikacyjnych.

Repozytorium zostało przygotowane jako praktyczne środowisko do budowy i testowania sterowania robotem w warunkach laboratoryjnych oraz terenowych. Nacisk położono na szybkie uruchomienie na urządzeniu mobilnym, stabilną komunikację z warstwą ROS oraz możliwość rozszerzania projektu o nowe moduły (wizja, panele operatorskie, skrypty diagnostyczne).

Projekt sprawdza się zarówno jako baza do zajęć i eksperymentów, jak i jako fundament pod bardziej zaawansowane wdrożenia, w których istotne są: responsywna kontrola, bezpieczeństwo (STOP), czytelna konfiguracja i łatwe odtwarzanie środowiska.

## Spis treści

1. Zakres projektu
2. Architektura
3. Scenariusze użycia
4. Struktura repozytorium
5. Wymagania
6. Szybki start
7. Instrukcje uruchamiania (krok po kroku)
8. Konfiguracja środowiska
9. Testowanie i jakość
10. DevOps i workflowy GitHub Actions
11. Najczęstsze problemy
12. Dalszy rozwój

## Zakres projektu

Główne cele projektu:
- zdalne sterowanie platformą ROV z poziomu aplikacji mobilnej,
- komunikacja z ROS 2 przez lokalny backend i rosbridge,
- obsługa joysticka, komend prędkości i awaryjnego zatrzymania,
- wsparcie kamer, logowania tematów oraz automatyzacji operacyjnej,
- utrzymanie prostego, modularnego układu kodu do dalszej rozbudowy.

## Architektura

System działa warstwowo:
- Backend Mobilny: pakiet Dart uruchamiający lokalny serwer proxy na telefonie.
- Frontend Mobilny: aplikacja Flutter łącząca się z lokalnym backendem Dart.
- Robot/ROV: końcowy odbiorca komend przez ROS/rosbridge.

Przepływ sterowania (wysoki poziom):
- użytkownik generuje komendy w UI,
- komendy trafiają do lokalnego backendu mobilnego,
- backend publikuje wiadomości do ROS topiców,
- robot realizuje ruch i odsyła status.

Kluczowe założenia architektoniczne:
- backend blisko urządzenia operatora (telefon/tablet),
- minimalna liczba zależności pośrednich między UI a robotem,
- możliwość działania offline w sieci lokalnej,
- rozdzielenie warstwy sterowania od warstwy prezentacji.

## Scenariusze użycia

Najczęstsze scenariusze, które pokrywa projekt:
- Sterowanie jazdą robota: joystick, regulacja prędkości, szybki STOP.
- Testy łączności: szybka weryfikacja połączenia mobilnego backendu z robotem.
- Prace rozwojowe: dodawanie nowych akcji sterowania i paneli operatorskich.
- Integracja z wizją: podpinanie strumieni kamer i modułów przetwarzania obrazu.
- Diagnostyka: analiza zachowania systemu przez logi i skrypty testowe.

## Struktura repozytorium

Najważniejsze katalogi:
- rov_frontend: aplikacja Flutter dla urządzeń mobilnych.
- rov_backend: lokalny backend Dart używany przez aplikację Flutter.
- control-panel: pomocniczy panel/serwis sterowania.

Skrócony opis ról:
- rov_frontend: interfejs operatora, logika ekranów i elementów sterowania.
- rov_backend: lokalny serwer i adapter protokołów (warstwa pośrednia do ROS/robota).
- control-panel: alternatywny punkt kontroli i serwisowania.

## Wymagania

Minimalne wymagania:

Mobile (Flutter):
- Flutter SDK
- Dart SDK (z Flutterem)
- Android SDK (dla uruchomienia na urządzeniu/emulatorze)

Komunikacja z robotem:
- ROS 2 (zalecane po stronie robota/infrastruktury)
- rosbridge-suite (typowo port 9090)

Opcjonalnie:
- Docker i Docker Compose (dla uruchomień kontenerowych)

## Szybki start

### Wariant: aplikacja mobilna Flutter

1. Przejdź do katalogu backendu Dart i pobierz zależności:
	cd rov_backend
	flutter pub get

2. Przejdź do katalogu frontendu Flutter i pobierz zależności:
	cd ../rov_frontend
	flutter pub get

3. Uruchom analizę i aplikację:
	flutter analyze
	flutter run

4. Dla wersji web Flutter (opcjonalnie):
	flutter run -d chrome

Ważne: jeśli pojawią się błędy typu Target of URI doesn't exist, zwykle oznacza to brak pobranych pakietów lub użycie polecenia dart pub get zamiast flutter pub get.

Dodatkowa wskazówka:
- przy zmianach zależności wykonuj flutter pub get osobno w rov_backend i rov_frontend,
- przy problemach z urządzeniem sprawdź flutter devices i flutter doctor.

## Instrukcje uruchamiania (krok po kroku)

Poniższa procedura opisuje pełne uruchomienie mobilnej aplikacji sterującej.

### 1) Przygotowanie narzędzi

1. Zweryfikuj środowisko:
	flutter doctor

2. Potwierdź dostępne urządzenia:
	flutter devices

3. Jeśli pracujesz na emulatorze Android, uruchom go przed startem aplikacji.

### 2) Instalacja zależności projektu

1. Backend Dart:
	cd rov_backend
	flutter pub get

2. Frontend Flutter:
	cd ../rov_frontend
	flutter pub get

3. Jeśli katalogi platform nie istnieją lokalnie:
	flutter create .

### 3) Analiza i testy przed uruchomieniem

1. Analiza statyczna:
	flutter analyze

2. Testy:
	flutter test

### 4) Start aplikacji

1. Uruchomienie na Androidzie (urządzenie/emulator):
	flutter run

2. Uruchomienie na web (opcjonalnie, do testów UI):
	flutter run -d chrome

### 5) Kontrola po uruchomieniu

Checklista uruchomieniowa:
- aplikacja startuje bez błędów kompilacji,
- połączenie z backendem lokalnym jest aktywne,
- konfiguracja IP i portu robota jest poprawna,
- komendy sterowania i STOP są wysyłane,
- logi nie pokazują błędów krytycznych.

### 6) Tryb developerski (codzienna praca)

Rekomendowany cykl:
1. Pobierz zmiany z repozytorium.
2. Uruchom flutter pub get (w rov_backend i rov_frontend, jeśli zmieniały się zależności).
3. Wykonaj flutter analyze.
4. Wykonaj flutter test.
5. Uruchom flutter run i zweryfikuj kluczowe scenariusze sterowania.

## Konfiguracja środowiska

Najważniejsze obszary konfiguracji:
- Adres IP robota/ROV, do którego łączy się backend mobilny.
- Port lokalnego backendu (domyślnie 2137).
- Port rosbridge po stronie robota (typowo 9090).
- Parametry sterowania (m.in. limity prędkości, deadzone, mapowanie osi) w warstwie logiki backendu.

Praktyka operacyjna:
- trzymaj wartości sieciowe w jednym miejscu konfiguracji aplikacji,
- unikaj twardego kodowania adresów IP w wielu plikach,
- po zmianie IP robota wykonaj szybki test połączenia przed jazdą.

## Testowanie i jakość

Zalecany minimalny zestaw kontroli przed wdrożeniem:

Flutter:
- flutter analyze
- flutter test

Backend Dart:
- test uruchomienia serwera lokalnego,
- test połączenia z rosbridge,
- test wysyłki podstawowych komend sterujących.

Skrypty testowe i diagnostyczne są dostępne m.in. w:
- rov_backend
- control-panel
- standalone-vision-app/backend

## DevOps i workflowy GitHub Actions

W repozytorium zdefiniowane są cztery workflowy CI/CD w katalogu .github/workflows.

### 1) verification.yaml

Cel:
- walidacja Pull Requestów kierowanych do gałęzi main,
- wymuszenie standardu nazewnictwa PR,
- uruchomienie jakości kodu i weryfikacji builda,
- automatyczne etykietowanie PR.

Kiedy się uruchamia:
- pull_request (opened, synchronize, reopened, ready_for_review) na main.

Najważniejsze kroki:
- sprawdzenie tytułu PR (musi zaczynać się od numeru zadania, np. #42),
- weryfikacja, czy zadanie istnieje na tablicy GitHub Project,
- wykrywanie zmian w pakietach rov_frontend i rov_backend,
- uruchomienie reusable-code-quality.yaml,
- build APK debug dla rov_frontend,
- dodanie etykiet frontend/backend/verified.

Wymagane sekrety:
- PROJECT_PAT (do odczytu Project Board).

### 2) reusable-code-quality.yaml

Cel:
- wspólna definicja kontroli jakości, używana przez inne workflowy.

Kiedy się uruchamia:
- workflow_call (reusable workflow), z parametrem upload_to_grafana.

Najważniejsze kroki:
- flutter analyze i zapis metryk (infos, warnings, errors),
- flutter test --coverage,
- wyliczenie pokrycia kodu na podstawie lcov,
- publikacja metryk jako artifact JSON,
- opcjonalna wysyłka metryk do Grafany.

Wymagane sekrety (gdy upload_to_grafana=true):
- GRAFANA_USER
- GRAFANA_PASS
- GRAFANA_URL

### 3) release.yaml

Cel:
- ręczne tworzenie wydania aplikacji Android i publikacja paczki AAB.

Kiedy się uruchamia:
- workflow_dispatch (manualnie) z parametrem version (np. 1.2.0+5).

Najważniejsze kroki:
- aktualizacja wersji w rov_frontend/pubspec.yaml,
- flutter pub get i flutter create .,
- wygenerowanie pliku android/key.properties z sekretów,
- build appbundle --release,
- utworzenie GitHub Release i dołączenie app-release.aab.

Wymagane sekrety:
- KEY_ALIAS
- KEY_PASSWORD
- STORE_PASSWORD

### 4) nightly.yaml

Cel:
- cykliczne, nocne uruchamianie kontroli jakości i eksport metryk.

Kiedy się uruchamia:
- harmonogram cron: codziennie o 02:00 UTC,
- workflow_dispatch (manualnie).

Działanie:
- wywołuje reusable-code-quality.yaml z upload_to_grafana=true.

### Praktyka pracy z CI/CD

Rekomendowany workflow zespołowy:
1. Twórz PR z tytułem zaczynającym się od numeru zadania (np. #123).
2. Przed push uruchamiaj lokalnie flutter analyze i flutter test.
3. Po przejściu verification sprawdź etykietę verified.
4. Release uruchamiaj tylko z gałęzi stabilnej, po zielonym CI.
5. Nightly traktuj jako sygnał trendu jakości, nie jako zamiennik testów lokalnych.

## Najczęstsze problemy

1. Brak połączenia frontend-backend
- sprawdź adres IP robota i port rosbridge,
- upewnij się, że lokalny backend działa przed frontendem,
- sprawdź zaporę systemową.

2. Problemy z ROS 2
- zweryfikuj instalację ROS,
- sprawdź poprawność nazw topiców,
- upewnij się, że rosbridge działa na właściwym porcie.

3. Błędy importów Flutter/Dart
- uruchom flutter pub get osobno w rov_backend i rov_frontend,
- sprawdź wersję Fluttera i aktywne SDK w IDE.

4. Brak odpowiedzi robota na komendy
- zweryfikuj sieć WiFi i adres IP urządzenia docelowego,
- sprawdź, czy watchdog i kanały sterowania są aktywne,
- przeanalizuj logi backendu i komunikaty po stronie ROS.

5. Niestabilne sterowanie (szarpanie, opóźnienia)
- zmniejsz częstotliwość wysyłania dodatkowych zdarzeń UI,
- sprawdź jakość sieci i opóźnienia,
- zweryfikuj ustawienia deadzone i limitów prędkości.

---

Projekt rozwijany jako środowisko sterowania i eksperymentów dla zastosowań ROV/robotycznych.
