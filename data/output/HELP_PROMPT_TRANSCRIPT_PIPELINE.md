# Help Request — Creator Quality Index : pipeline transcripts YouTube bloque

## Contexte du projet

**Nom** : creator-quality-index (PRJ-063)
**But** : Indexer 346 chaines YouTube educatives, scorer chaque chaine sur 5 dimensions
(research_depth, production, signal_noise, originality, lasting_impact) en analysant
les transcripts de leurs videos via Claude Sonnet.

**Stack** :
- Backend Flask (port 5065), DB SQLite locale (`benchmark.db`) + PostgreSQL Render
- Python 3.10, faster-whisper (CPU int8), yt-dlp 2026.03.17, ffmpeg
- Reuses : ai-video-studio (`library.db` + `media/{video_id}/transcript.json`),
  youtube-transcription (PRJ-026 SharedMediaDB)
- Repo : `/data/projects/creator-quality-index`

**Architecture pipeline 26 videos/chaine** :
1. **Phase 1 — Discovery** : `scripts/batch_discover_videos.py` -- fait, 8101 video IDs collectes
   via yt-dlp `--flat-playlist`
2. **Phase 2a — Transcripts API** : `scripts/batch_fetch_transcripts.py` -- bloque
   (`youtube-transcript-api` retourne IpBlocked sur IP residentielle FR + yt-dlp `--write-subs`
   donne 429)
3. **Phase 2b — Whisper** : `scripts/batch_whisper_transcripts.py` -- en cours, 102 OK / 1414
   tentes, **1312 download_failed (93%)**
4. **Phase 3 — Scoring** : `scripts/batch_score_videos.py` -- pret, 0 video scoree
5. **Phase 3b — Averages** : `scripts/batch_apply_averages.py` -- pret

**Etat scoring chaines (existant, single transcript)** :
- 227/346 (65%) chaines avec ai_score_research, ai_score_signal_noise, etc.
- 119 chaines manquantes (transcripts soit jamais recuperes, soit corrompus low-quality)

## Le probleme principal

Phase 2b telecharge l'audio de chaque video via yt-dlp (`-x --audio-format mp3
--audio-quality 9`) puis trim a 10min via ffmpeg, puis transcrit avec faster-whisper tiny.

**Realite** : sur 1414 tentatives (`data/fetch_progress.json`):
- 102 OK (toutes via Whisper, langues OK)
- 1312 `download_failed` (yt-dlp returncode != 0)
- Pattern par chaine : 47 chaines /55 ont 100% de DL_FAIL, 5 chaines mixtes, 3 chaines OK only

Extraits du log (`data/whisper_batch.log`) :
```
[1068/7031] #134 Historia Civilis             2-PYwEsTll0 (659/h, ETA 9.0h) DL_FAIL
[1069/7031] #134 Historia Civilis             OPDpj59kkgk (659/h, ETA 9.0h) DL_FAIL
... (tous DL_FAIL pour Historia Civilis, OverSimplified, Fall of Civilizations)
```

Tres probablement : **IP-ban yt-dlp sur l'IP locale** apres trop de requetes consecutives,
OU yt-dlp version trop ancienne qui cache un sous-probleme (PO Token / TV embedded client).

**Test fait juste avant ce prompt** : un seul download en CLI manuel d'une video a echoue
fonctionne (194 MiB telecharges en 7s, conversion mp3 OK). Donc probablement un soft-rate-limit
/ ban temporaire qui se libere mais que le batch retombe dedans des qu'il enchaine.

## Code actuel batch_whisper_transcripts.py (extrait clef)

```python
def download_audio(video_id, output_dir, max_secs=600):
    output_template = os.path.join(output_dir, f"{video_id}.%(ext)s")
    try:
        result = subprocess.run(
            ["yt-dlp", "--js-runtimes", "node",
             "-x", "--audio-format", "mp3", "--audio-quality", "9",
             "--no-warnings", "-q",
             "-o", output_template,
             f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            return None
        mp3_path = os.path.join(output_dir, f"{video_id}.mp3")
        if not os.path.exists(mp3_path):
            return None
        # Trim AFTER full download
        if max_secs:
            trimmed = os.path.join(output_dir, f"{video_id}_trim.mp3")
            subprocess.run(["ffmpeg","-y","-i",mp3_path,"-t",str(max_secs),"-c","copy","-loglevel","error",trimmed],timeout=30)
            if os.path.exists(trimmed):
                os.replace(trimmed, mp3_path)
        return mp3_path
    except (subprocess.TimeoutExpired, OSError):
        return None
```

Boucle :
```python
for i, (entry, vid) in enumerate(work):
    audio_path = download_audio(vid, tmpdir, max_secs=args.max_secs)
    if not audio_path:
        progress["fetched"][vid] = {"channel_id": ch_id, "status": "download_failed"}
        fail_count += 1
        save_progress(progress); continue
    transcript, lang = transcribe_audio(audio_path, model, language=...)
    ...
    if i < len(work) - 1: time.sleep(args.delay)  # default 3s
```

## Tentatives deja faites

1. **Plan B Colab** : notebook `notebooks/colab_fetch_transcripts.ipynb` qui utilise
   `youtube-transcript-api` depuis IP Google. Recupere 1 video/chaine (la plus recente).
   Pas execute pour les 119 chaines restantes (action #282 en pending).

2. **Single transcript fallback** : 227 chaines deja scorees avec une seule video chacune
   via youtube-transcript-api avant que l'IP soit ban.

3. **yt-dlp avec js-runtimes node** : ajoute pour bypasser les nouveaux SABR/PO Token YouTube
   (bypass partiel, semble marcher en CLI manuel).

## Ce que je veux votre aide

Choisir/concevoir la strategie la plus realiste pour obtenir 26 transcripts/chaine sur 346
chaines (~9000 videos), sachant que :

- L'objectif "9000 videos via yt-dlp + Whisper local" semble fragile
- L'IP locale est rate-limitee
- Pas de budget API YouTube Data v3 illimite
- Whisper tiny CPU = ~5-8 min/video, pas teneur
- Compute disponible : 1 PC Linux (Ryzen, GTX 1080 incompatible CUDA 12+ pour Whisper GPU)

### Questions specifiques

1. **Court-terme (debloquer Phase 2b)** :
   - Comment reduire drastiquement le DL_FAIL ? Cookies browser ? Proxy rotation ?
     `--download-sections "*0-600"` pour ne telecharger que 10min (au lieu de full puis trim) ?
     Pause adaptative apres N fails consecutifs ? User-Agent rotation ? Plusieurs comptes
     YouTube en cookies.txt ?
   - yt-dlp 2026.03.17 vs nightly : connaissez-vous des fix recents pour le SABR/PO Token ?
   - Comment detecter en runtime si on est en IP-ban (vs juste une video down) pour faire
     un long sleep au lieu de continuer a brûler des slots ?

2. **Moyen-terme (architecture)** :
   - Vaut-il mieux :
     (a) Continuer Whisper local + ameliorer download (proxy, retry, cookies)
     (b) Tout migrer sur Colab/Cloud Run/Modal (transcripts via youtube-transcript-api,
         IP partagee Google) — combien ca coute pour 9000 videos ?
     (c) Reduire le besoin : 5-10 transcripts/chaine au lieu de 26 (deja statistiquement
         significatif si videos bien choisies)
     (d) Mix : utiliser youtube-transcript-api en premier (1-3 retours sur Colab gratuit),
         tomber sur Whisper local seulement pour les manquants
   - Si Cloud, lequel : Colab Pro ($10/mois), Modal (serverless GPU), AWS Lambda + S3 ?

3. **Strategie scoring** :
   - Le scoring AI Sonnet a deja ete fait sur 227/346 chaines avec 1 transcript chacune.
     Vaut-il mieux :
     (a) Compléter les 119 chaines manquantes en 1-transcript-chacune (rapide)
     (b) Repartir a zero pour scorer 26-videos-chacune sur les 346 (cher en token Sonnet)
     (c) Hybride : 1-transcript pour les 119 manquantes pour avoir un baseline 100%,
         puis upgrade progressif vers 26-videos pour les chaines top tier seulement
   - Comment estimer le cout token Sonnet pour 9000 videos x ~3000 tokens chacune ?

4. **Robustesse** :
   - Le script `batch_whisper_transcripts.py` perd les videos qui timeout (180s) sans retry.
     Comment ajouter une queue retry sans casser la logique progress incrementale ?
   - `tempfile.TemporaryDirectory` est detruit a chaque interruption. OK pour audio
     ephemere, mais que faire pour reprendre un batch ou Whisper a partiellement transcrit ?

5. **Un detail troublant** :
   - Le test CLI manuel d'un video reportee DL_FAIL dans le log a fonctionne (194 MB en 7s).
     Soit l'IP-ban est temporaire et se libere, soit autre chose. Comment investiguer
     proprement (sniffer reponse 403/429 vs vrai fail HLS) ? Le code actuel ne log que
     `returncode != 0` sans capturer stderr.

## Donnees brutes utiles

- DB schema : `channels` (346 rows), `categories` (18), `video_scores` (table prete, 0 rows),
  `comments`, `community_ratings`
- `data/video_manifest.json` : 282 chaines x ~26 video_ids = 8101 IDs
- `data/fetch_progress.json` : 1414 entrees, 102 OK / 1312 DL_FAIL
- `data/whisper_batch.log` : trace complete des essais
- Code : `scripts/batch_whisper_transcripts.py` (380 lignes, full source plus haut)

Produis une recommendation chiffree (cout / temps / robustesse) entre les options ci-dessus,
et propose le snippet de code minimal qui debloque la Phase 2b si l'option a est retenue.
