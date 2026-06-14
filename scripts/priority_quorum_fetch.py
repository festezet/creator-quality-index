import json
import subprocess
import os
import sys

PROGRESS_PATH = "/data/projects/creator-quality-index/data/fetch_progress.json"
TARGET_CHANNELS = [90, 91, 93, 100, 115, 137, 148]

def get_status():
    with open(PROGRESS_PATH, "r") as f:
        data = json.load(f)
    fetched = data.get("fetched", {})
    
    stats = {c_id: 0 for c_id in TARGET_CHANNELS}
    pending = []
    
    for vid, info in fetched.items():
        c_id = info.get("channel_id")
        if c_id in TARGET_CHANNELS:
            if info.get("status") == "ok":
                stats[c_id] += 1
            elif info.get("status") == "pending":
                pending.append((vid, c_id))
    
    return stats, pending

def run_fetch():
    print("Demarrage du batch prioritaire pour le quorum...")
    while True:
        stats, pending = get_status()
        
        # Filtrer les pending pour ne garder que ceux des chaines qui n ont pas encore 26 ok
        active_pending = [p for p in pending if stats[p[1]] < 26]
        
        if not active_pending:
            print("Quorum atteint pour toutes les chaines prioritaires !")
            break
            
        vid, c_id = active_pending[0]
        print(f"Traitement prioritaire: Video {vid} (Channel {c_id}) - Progress: {stats[c_id]}/26")
        
        # Lancer le telechargement et la transcription mono-video
        # On utilise le script existant scripts/batch_whisper_transcripts.py pour une video
        cmd = [
            "python3", "scripts/batch_whisper_transcripts.py",
            "--video-id", vid,
            "--channel-id", str(c_id)
        ]
        subprocess.run(cmd)

if __name__ == "__main__":
    run_fetch()
