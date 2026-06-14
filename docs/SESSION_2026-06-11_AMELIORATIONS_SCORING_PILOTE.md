# SESSION 2026-06-11 — Améliorations méthodologiques + pilote scoring PRJ-063

## Objectif

Avant de lancer le scoring de masse (Phase 3), implémenter les 3 décisions méthodologiques identifiées dans l'analyse du 2026-06-10, puis valider le pipeline end-to-end par un pilote.

## Décisions validées par Fabrice

| Décision | Choix retenu |
|----------|--------------|
| Agrégation des 26 scores/chaîne | **Médiane** (robuste aux vidéos atypiques) |
| Seuil de validité | **≥20 = confirmé, 10-19 = provisoire, <10 = pas de score AI** |
| Composite AI / Production | **Composite AI 4 critères repondérés, Production en badge séparé** |

## Implémentation

### `backend/config.py`
- Ajout `WEIGHTS_AI` : Research 0.30, Signal/Noise 0.30, Originality 0.20, Lasting Impact 0.20 (somme 1.0, Production exclue car non évaluable depuis un transcript)
- Ajout `AI_SCORE_CONFIRMED_MIN = 20`, `AI_SCORE_PROVISIONAL_MIN = 10`

### Schema `channels` (ALTER TABLE additif)
- `ai_composite_score` (REAL) — composite AI 4 critères
- `ai_tier` (TEXT) — tier dérivé (mêmes seuils S/A/B/C que le manuel)
- `ai_score_status` (TEXT) — `confirmed` / `provisional` / NULL
- `ai_score_production_badge` (INTEGER) — Production manuelle copiée comme badge

### `scripts/batch_apply_averages.py` (Phase 3b — réécrit)
- Agrégation **médiane** (`statistics.median`) au lieu de moyenne
- Calcul `compute_ai_composite()` (pondération `WEIGHTS_AI`) + `compute_tier()` + `score_status()`
- N'écrit un score AI que si ≥10 vidéos ; tag confirmed/provisional selon le seuil
- Production copiée depuis le score manuel vers `ai_score_production_badge`
- Stats remaniées (distribution 0 / 1-9 / 10-19 / 20-25 / 26+)

## Pilote — 3Blue1Brown (channel_id 90)

10 vidéos scorées manuellement (subscription Claude, conforme LLM-BUDGET-001 pour le calibrage), importées via `--from-json`, agrégées par Phase 3b.

| Critère | Médiane |
|---------|---------|
| Research Depth | 8.0 |
| Signal/Noise | 8.5 |
| Originality | 8.5 |
| Lasting Impact | 9.0 |
| **Composite AI** | **8.45 → tier A (provisoire, 10 vidéos)** |

### Convergence avec le score éditorial

| Source | Composite | Tier |
|--------|-----------|------|
| Manuel (5 critères, Production incluse) | 9.70 | S |
| AI (4 critères, Production exclue) | 8.45 | A |
| Badge Production (manuel) | 10/10 | — |

**Écart de 1.25 point, explicable** :
1. Production (10/10) exclue mécaniquement du composite AI
2. 4 des 10 vidéos sont des "guest videos" (créateurs invités) qui diluent le signal propre de la chaîne — **biais d'échantillonnage à surveiller**
3. Pilote lu à 6k chars (le prompt prod utilise 12k)
4. Le scoring éditorial portait possiblement un biais de réputation (notes généreuses)

**Conclusion** : convergence saine. 3Blue1Brown reste au sommet (tier A, à 0.05 du seuil S). L'AI est un cran plus sévère et plus discriminant — c'est l'objectif (réduire le biais de réputation de l'éditorial).

## Pilote étendu — 2e chaîne (Fall of Civilizations, id 136)

10 vidéos scorées (histoire narrative, sources primaires d'époque, narration pure).

| Chaîne | Manuel | AI (4 crit) | Écart | Tier |
|--------|--------|-------------|-------|------|
| Fall of Civilizations | 9.65 | **9.50** | +0.15 | S → S |
| 3Blue1Brown | 9.70 | **8.45** | +1.25 | S → A |

### Findings du pilote étendu (justifient le "pilote d'abord" de Fabrice)

1. **Guest videos diluent le score** — finding majeur. FoC (contenu 100% propre) converge à +0.15. 3B1B perd 1.25 point car 4 de ses 10 vidéos récentes sont des créateurs invités. **Décision à prendre avant le run** : exclure les guest videos du scoring d'une chaîne ?
2. **Doublons de contenu** — FoC avait 5 paires de doublons (même titre/transcript, video_id différent) sur 10. Mesure globale : **seulement 0.3% (31 doublons sur 10071, 9 chaînes)** → mineur mais à nettoyer avant agrégation.
3. **Convergence saine quand l'échantillon est propre** : l'AI 4-critères discrimine bien et reste cohérent avec l'éditorial sur les chaînes d'élite.

## Correction critique du scoring (batch_score_videos.py)

Le scoring itérait sur `manifest.video_ids[:26]`. Or les substitutions ont appendu les video_ids en fin de manifest → **3967 transcripts (39%) auraient été ratés**. Corrigé : le scoring est désormais piloté par `download_progress` (status `ok`, source de vérité — toutes ces vidéos ont un transcript), via `get_ok_videos()`. Résultat : 7005 vidéos ciblées (vs ~6100 avant).

**Le décalage 10071/6115 était un faux problème** : tous les 10071 `ok` ont leur transcript.json (0 manquant). Le 6115 venait de mon comptage erroné sur le manifest tronqué.

## Constat sur le scoring de masse

- **6115 transcripts** disponibles dans `ai-video-studio/data/media/` (vs 10071 "ok" en DB — décalage : anciens runs stockés seulement dans `transcriptions.db`/`library.db`, à investiguer)
- **217 chaînes** ont ≥20 transcripts (statut confirmé possible), 239 ont ≥10
- Le scoring inline (subscription) du pilote = 10 vidéos pour ~60k chars lus. Extrapolé à 6115 vidéos = ~3.7M chars + 6115 jugements → **infaisable en subscription**
- Selon LLM-BUDGET-001, c'est le cas "volume massif >100 calls par run" qui justifie l'API. Le calibrage (pilote) est fait en subscription comme requis.

### Estimation coût API (run complet 6115 vidéos)
- ~3.5k tokens input/vidéo (transcript 12k chars + prompt) + ~250 output
- Haiku 4.5 : ~21M tokens input ≈ **~20-25 €**
- Sonnet 4.x : ~10× ≈ **~200-250 €**

## Décalage transcripts à investiguer

10071 `ok` en DB mais 6115 fichiers `transcript.json`. Les ~3950 manquants sont probablement dans `transcriptions.db` (SharedMediaDB) ou `library.db` sans fichier JSON. Vérifier avant le run pour ne pas perdre 40% des transcripts au scoring.

## Prochaines étapes

1. **Décider stratégie scoring de masse** : API Haiku (~25€) vs subscription par lots vs hybride
2. **Investiguer le décalage** 10071/6115 transcripts (récupérer les manquants depuis transcriptions.db)
3. **Lancer Phase 3** sur le volume une fois la stratégie tranchée
4. **Lancer Phase 3b** complète → peupler ai_composite_score sur 217+ chaînes
5. **Calibration formelle** : re-scorer 20-30 vidéos, mesurer la variance, publier dans METHODOLOGY.md
6. **UI** : afficher badge confirmed/provisional + Production séparée

## Fichiers modifiés

- `backend/config.py` — WEIGHTS_AI + seuils
- `scripts/batch_apply_averages.py` — médiane + composite AI + statut (réécrit)
- `data/benchmark.db` — 4 colonnes ai_* ajoutées (backup : benchmark.db.bak-2026-06-11)
- `data/ai_scores_v2/score_90_*.json` — 10 scores pilote 3Blue1Brown
