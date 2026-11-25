# subdub

[![CI/CD](https://github.com/kmaill/subdub/actions/workflows/ci.yml/badge.svg)](https://github.com/kmaill/subdub/actions/workflows/ci.yml)

[English version](README.md) | **Wersja polska**

> **Lekkie narzędzie CLI i mikroserwis w Pythonie do automatycznego generowania i wtapiania ścieżki lektora AI w pliki wideo `.mkv`, `.mp4`, `.m4v` oraz `.mov`.**

Zaprojektowane z myślą o minimalnym zużyciu zasobów oraz pełnej automatyzacji w ekosystemie **Bazarr / Jellyfin**. Działa w oparciu o darmową syntezę Microsoft Edge TTS i obsługuje dowolny język oferowany przez tę usługę, ze szczególnym uwzględnieniem polskiego lektora `pl-PL-MarekNeural`.

---

## Główne możliwości

* **Darmowy lektor AI:** Korzysta z modeli Microsoft Edge TTS. Choć domyślnie skonfigurowany pod polski głos `pl-PL-MarekNeural`, obsługuje dziesiątki innych języków (np. ukraiński, niemiecki, hiszpański, angielski).
* **Minimalne zużycie RAM:** Dźwięk miksowany jest w 15-minutowych oknach czasowych. Płynne przenoszenie kwestii lektora na łączeniach batchy eliminuje ryzyko obcięcia słów i utrzymuje niskie zużycie pamięci nawet przy filmach 4K trwających 3 godziny.
* **Inteligentne ściszanie audio:** Automatyczne ściszanie oryginalnej ścieżki dźwiękowej w momentach, gdy lektor czyta kwestie.
* **Podwójny tryb pracy:**
  1. Narzędzie terminalowe CLI do pojedynczych plików lub wsadowego skanowania biblioteki.
  2. Bezobsługowy serwer webhooków odbierający powiadomienia z Bazaara.

---

## Jak to działa

```text
 +-------------------+      +--------------------+
 |  Bazarr (Webhook) |  lub |  CLI (Ręczne/Scan) |
 +---------+---------+      +---------+----------+
           |                          |
           +-----------> [ Kolejka FIFO ] <---------+
                             |
                     [ Wątek roboczy ]
                             |
          1. Wykrycie lub ekstrakcja napisów SRT i czyszczenie SDH
          2. Równoległa synteza kwestii lektora (Edge TTS)
          3. Miksowanie audio w 15-minutowych batchach z duckingiem
          4. Dwuetapowy, bezpieczny remux do pliku tymczasowego i podmiana
                             |
                             v
                 +-----------------------+
                 | Odświeżenie Jellyfina |
                 +-----------------------+
```

---

## Szybki start (Docker Compose)

Najprostszy sposób na uruchomienie obok Bazaara i Jellyfina:

```yaml
services:
  subdub:
    image: ghcr.io/kmaill/subdub:latest
    container_name: subdub
    restart: unless-stopped
    ports:
      - "9999:9999"
    environment:
      - JELLYFIN_TOKEN=twoj_token_api_jellyfin
    volumes:
      - ./config:/root/.config/subdub
      - ./cache:/root/.cache/subdub
      # Ważne: Ścieżki do multimediów muszą być identyczne jak w kontenerze Bazarr
      - /sciezka/do/filmow:/sciezka/do/filmow
      - /sciezka/do/seriali:/sciezka/do/seriali
    deploy:
      resources:
        limits:
          memory: 1200M
```

Uruchomienie:
```bash
docker compose up -d
```

---

## Integracja z Bazarr

Aby Bazarr po pobraniu napisów automatycznie zlecał wygenerowanie lektora:

1. W Bazarrze przejdź do: **Settings $\to$ Notifications**.
2. Kliknij ikonę plusa **(+)** i wybierz typ dostawcy: **JSON**.
3. W polu **URL** wklej poniższy adres:
   ```text
   json://subdub:9999/webhook?:path={bazarr_movie_path}{bazarr_episode_path}&:subtitles={bazarr_movie_subtitles}{bazarr_episode_subtitles}
   ```
4. Zapisz powiadomienie.

Przebieg zdarzeń:
1. Bazarr pobiera napisy i wysyła powiadomienie pod wskazany URL.
2. `subdub` natychmiast przyjmuje zadanie i odkłada je w kolejce FIFO.
3. Wątek roboczy w tle generuje mowę, miksuje ścieżkę dźwiękową i podmienia plik.
4. Jellyfin otrzymuje sygnał odświeżenia biblioteki.

---

## Użycie z linii poleceń (CLI)

### Instalacja lokalna (Python 3.11+)

```bash
git clone https://github.com/kmaill/subdub.git
cd subdub
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Wymagania w systemie: `ffmpeg` oraz opcjonalnie `mkvtoolnix` (`mkvmerge`).

### Przykłady komend

```bash
# Przetworzenie pojedynczego filmu (automatycznie znajdzie napisy obok lub wewnątrz pliku)
subdub "/sciezka/do/film.mkv"

# Przetworzenie filmu ze wskazaniem konkretnego pliku napisów
subdub "/sciezka/do/film.mkv" --subs "/sciezka/do/napisy.srt"

# Wymuszenie dodania lektora (nawet jeśli film posiada już polską ścieżkę)
subdub "/sciezka/do/film.mkv" --force

# Skanowanie biblioteki (przetwarza jeden brakujący film i kończy działanie)
subdub --scan "/media/movies"

# Przeskanowanie całej biblioteki i przetworzenie wszystkich brakujących filmów po kolei
subdub --scan "/media/movies" --all

# Uruchomienie serwera webhooków na porcie 9999
subdub --serve --port 9999
```

---

## Konfiguracja (`~/.config/subdub/config.toml`)

Przy pierwszym uruchomieniu plik konfiguracyjny tworzy się automatycznie w `~/.config/subdub/config.toml`:

```toml
[tts]
voice = "pl-PL-MarekNeural"
lang = "pol"
rate = "+0%"
volume = "+0%"
max_concurrency = 4

[audio]
sample_rate = 48000
batch_seconds = 900.0
bitrate_51 = "448k"
bitrate_stereo = "256k"
ducking_threshold = 0.025
ducking_ratio = 4.0

[subtitles]
strip_sdh = true

[storage]
temp_dir = ""
scan_dirs = ["/media/movies", "/media/tv"]
exclude_dirs = []

[server]
host = "0.0.0.0"
port = 9999

[jellyfin]
enabled = false
url = "http://localhost:8096"
token = "env:JELLYFIN_TOKEN"
```

---

## Licencja

Ten projekt jest objęty licencją **GNU General Public License v3.0 (GPLv3)**. Szczegóły w pliku LICENSE.
