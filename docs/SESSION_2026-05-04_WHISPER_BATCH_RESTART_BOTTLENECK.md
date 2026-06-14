# SESSION 2026-05-04 — Relance batch Whisper PRJ-063 + diagnostic bottleneck

## Contexte

Demande Fabrice : "reprend le chargement des videos (batch) pour le projet PRJ-063".

Le batch `batch_whisper_transcripts.py` etait cense tourner depuis 2026-04-10 mais en realite arrete depuis 3 semaines. Le pgrep initial donnait un faux positif (la commande shell elle-meme matchait "batch_whisper").

## Etat avant session

- DB `download_progress` : 846 OK / 567 download_failed / 1 rate_limited
- AVS `library.db` : 1096 transcripts
- Log `data/whisper_batch.log` : derniere modif 2026-04-10 14:07
- Aucun process python actif

## Actions

### 1. Diagnostic arret batch

- `pgrep -af "python.*batch_whisper"` → aucun match (le process shell ne matche pas le pattern strict)
- `stat data/whisper_batch.log` → mtime 2026-04-10
- `ls -lt data/*.log` → tout fige au 10 avril
- Cause probable d'arret : streak de DL_FAIL (1115 echecs consecutifs en fin de log) sans message d'erreur enregistre. Possible network issue ou kill SIGKILL non-loggue.

### 2. Verification yt-dlp fonctionnel

- Test direct `yt-dlp ...` sur GV2piw94DpM → OK
- Test avec commande exacte du script (`--download-sections "*0-600" --force-keyframes-at-cuts -x mp3`) → OK en 4:53 (re-encode realtime ~2x)
- Conclusion : le probleme du 10 avril est resolu, on peut relancer.

### 3. Relance batch

```bash
cd /data/projects/creator-quality-index
mv data/whisper_batch.log data/whisper_batch.log.archived-2026-04-10
nohup nice -n 19 python3 scripts/batch_whisper_transcripts.py \
  > data/whisper_batch.log 2>&1 &
disown
```

PID 78206 lance a 08:52. Apres 13h30 :
- 205 OK / 6194 (3.3%)
- AVS : 1293 transcripts (+197)
- DB : 1043 OK / 370 DL_FAIL / 1 rate_limited
- Vitesse : 15/h (au lieu des 72/h initialement vises)

### 4. Diagnostic bottleneck performance

`pstree -p 78206` :
```
python3(78206) → yt-dlp → ffmpeg (12 threads actifs)
```

`top -p 78206` :
- CPU python3 : **0.0%** (Whisper inactif, attend l'audio)
- ffmpeg : actif, re-encode realtime

**Identification** : c'est PAS Whisper qui ralentit, c'est le download via ffmpeg.

Cause precise : la flag `--force-keyframes-at-cuts` dans `download_audio()` force ffmpeg a re-encoder integralement l'audio en realtime ~2x → ~5 min pour 10 min d'audio. Whisper tiny CPU int8 = ~30s par video (rapide).

Decomposition par video :
| Etape | Duree | % du total |
|-------|-------|------------|
| yt-dlp + ffmpeg re-encode | ~5 min | **~85%** |
| Whisper tiny transcribe | ~30s | ~10% |
| Anti-bot delay | 5-15s | ~5% |
| **Total** | ~5-6 min | 100% |

## Pistes d'amelioration (a valider avec Fabrice)

### Acceleration download (gain x5 attendu : 15 → 75/h)

1. **Retirer `--force-keyframes-at-cuts`** dans `scripts/batch_whisper_transcripts.py` ligne ~188
   - Effet : download natif quasi-instantane (~10s) au lieu de 5 min
   - Trade-off : possible coupure mid-sample audio, mais sans impact reel pour Whisper
   - **Recommande** — solution la plus simple et impact maximal

2. Telecharger sans `--download-sections` (bestaudio entier puis trim ffmpeg apres)
   - Effet : download natif rapide
   - Trade-off : videos pleines (180MB en test sur GV2piw94DpM), espace disque temporaire

3. Lancer 2-3 instances en parallele avec `--channel-id` differents
   - Effet : x2-x3 throughput
   - Trade-off : risque bot-pattern YouTube, garder delays

### Gestion erreurs

4. Utiliser `--cookies-from-browser firefox` (option deja prevue dans le script via `--cookies`)
   - Effet : debloquer videos age-restricted, members-only, regional locks
   - Vu cette session : 1 RATE_LIMIT (Sign in to confirm age) sur Arvin Ash/XqOWgn1edY4
   - Vu cette session : 1 DL_FAIL members-only sur Sabine Hossenfelder/63i3jvU1nQ0

## Etat apres session

- Batch tourne : PID 78206 en background (`nohup nice -n 19`)
- Restant : ~4710 videos (sur 6194 work items)
- ETA brut : ~16 jours au rythme actuel | ~3 jours apres acceleration

## Fichiers modifies

- `.claude/PROJECT_STATUS.md` — MAJ etat batch + section bottleneck + pistes amelioration
- `data/whisper_batch.log` — log courant du batch
- `data/whisper_batch.log.archived-2026-04-10` — archive ancien log

## Prochaines etapes

1. Decider sur la modification `--force-keyframes-at-cuts` (gain x5)
2. Monitorer le batch courant : `python3 scripts/batch_whisper_transcripts.py --stats`
3. Lancer Phase 3 (scoring Sonnet) une fois ~3000+ transcripts disponibles
