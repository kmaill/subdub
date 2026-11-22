# subdub

[![CI/CD](https://github.com/kmaill/subdub/actions/workflows/ci.yml/badge.svg)](https://github.com/kmaill/subdub/actions/workflows/ci.yml)

> **Lekkie narzędzie CLI i mikroserwis w Pythonie do automatycznego generowania i wtapiania ścieżki lektora AI (TTS) w pliki wideo (`.mkv`, `.mp4`, `.m4v`, `.mov`).**

Zaprojektowane pod niski narzut zasobów oraz pełną automatyzację w ekosystemie **Bazarr / Jellyfin / Plex**.

---

## Główne możliwości

* **Darmowy lektor AI:** Wykorzystuje syntezę Microsoft Edge TTS (`pl-PL-MarekNeural`).
* **Mikroskopijne zużycie RAM:** Przetwarzanie audio w 15-minutowych batchach czasowych z obsługą przenoszenia kwestii na łączeniach.
* **Podwójny tryb pracy:**
  1. Narzędzie terminalowe CLI (`subdub film.mkv` lub `subdub --scan`).
  2. Bezobsługowy serwer webhooków (`subdub --serve`) odbierający powiadomienia z Bazaara.

---

## Szybki start

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
      # WAŻNE: Ścieżki do multimediów muszą być 1:1 identyczne jak w kontenerze Bazarr!
      - /sciezka/do/filmow:/sciezka/do/filmow
      - /sciezka/do/seriali:/sciezka/do/seriali
    deploy:
      resources:
        limits:
          memory: 1200M
```

Uruchom:
```bash
docker compose up -d
```

---

## Integracja z Bazarr

Aby Bazarr po pobraniu napisów automatycznie zlecał wygenerowanie lektora:

1. W Bazarrze przejdź do: **Settings $\to$ Notifications**.
2. Kliknij ikonę plusa **(+)** i wybierz typ dostawcy: **JSON**.
3. W polu **URL** wklej dokładnie poniższy adres:
   ```text
   json://subdub:9999/webhook?:path={bazarr_movie_path}{bazarr_episode_path}&:subtitles={bazarr_movie_subtitles}{bazarr_episode_subtitles}
   ```
4. Zapisz powiadomienie (**Save**).

Gdy Bazarr pobierze napisy do nowego filmu lub odcinka:
1. Bazarr wysyła powiadomienie pod wskazany URL, a `subdub` w ułamku sekundy przetwarza je.
2. Zadanie ląduje w kolejce FIFO, a pojedynczy wątek roboczy w tle syntetyzuje głos Marka, miksuje dźwięk i podmienia plik.
3. Jellyfin otrzymuje powiadomienie o odświeżeniu biblioteki.

---

## Użycie z linii poleceń

### Instalacja lokalna (Python 3.11+)

```bash
git clone https://github.com/kmaill/subdub.git
cd subdub
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Wymagania systemowe: `ffmpeg` oraz opcjonalnie `mkvtoolnix` (`mkvmerge`).

### Przykłady komend

```bash
# Przetworzenie pojedynczego filmu (automatycznie znajdzie napisy obok lub wewnątrz)
subdub "/sciezka/do/film.mkv"

# Przetworzenie filmu z jawnym wskazaniem pliku napisów
subdub "/sciezka/do/film.mkv" --subs "/sciezka/do/napisy.srt"

# Wymuszenie dodania lektora (nawet jeśli film posiada już polską ścieżkę)
subdub "/sciezka/do/film.mkv" --force

# Skanowanie biblioteki (przetwarza 1 brakujący film i kończy – idealne do crona)
subdub --scan "/media/movies"

# Przeskanowanie całej biblioteki i przetworzenie wszystkich filmów po kolei
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
