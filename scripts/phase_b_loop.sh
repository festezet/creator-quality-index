#!/bin/bash
# Boucle Phase B : relance whisper_from_cache.py tant que des audios attendent.
# Pause 60s entre les passes si rien a faire (Phase A ralenti ou termine).
set -u

CQI_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$CQI_DIR/data/logs/phase/phase_b_loop.log"
MODEL="${1:-tiny}"
DELETE_AUDIO="${2:-}"

cd "$CQI_DIR"
echo "[$(date)] Phase B loop start (model=$MODEL)" >> "$LOG"

while true; do
    # Compte les audios en attente
    pending=$(python3 -c "
import sqlite3
conn = sqlite3.connect('data/benchmark.db')
cur = conn.cursor()
cur.execute(\"SELECT COUNT(*) FROM download_progress WHERE status='downloaded' AND audio_path IS NOT NULL\")
print(cur.fetchone()[0])
" 2>/dev/null || echo "0")

    if [ "$pending" -eq 0 ]; then
        # Verifier si Phase A tourne encore
        if pgrep -f "download_audio_to_disk.py" > /dev/null; then
            echo "[$(date)] Pending=0, Phase A still running, sleep 60s" >> "$LOG"
            sleep 60
            continue
        else
            echo "[$(date)] Pending=0 + Phase A finished, exit" >> "$LOG"
            break
        fi
    fi

    echo "[$(date)] Pending=$pending, run Whisper batch" >> "$LOG"
    python3 -u scripts/whisper_from_cache.py --model "$MODEL" $DELETE_AUDIO >> "$LOG" 2>&1
    sleep 5
done

echo "[$(date)] Phase B loop end" >> "$LOG"
