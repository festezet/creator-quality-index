# SESSION 2026-06-10 — Analyse méthodologie et implémentation PRJ-063

## Objectif

Analyser l'état du projet Creator Quality Index : méthodologie de scoring, implémentation, pipeline de transcription, et proposer des recommandations pour atteindre l'objectif d'index qualitatif.

## Constat central

L'index public actuel repose **entièrement sur des scores éditoriaux** de mars 2026. Les 9768 transcriptions collectées via le pipeline Whisper n'ont pas encore alimenté l'index — `video_scores` est vide, Phase 3 (scoring) n'a jamais tourné.

| Couche | État |
|--------|------|
| Scores manuels (seed mars 2026) | 346/346 — **base de l'index actuel** |
| AI legacy (1 transcript/chaîne) | 227/346 — non intégré |
| Pipeline multi-vidéo (26/chaîne) | 9768 transcripts prêts, **0 scorés** |

## Forces

- **Méthodologie bien construite** : 5 critères pondérés, rubrics détaillées avec exemples, biais reconnus
- **Positionnement clair** : qualité intellectuelle vs popularité (Social Blade) ou marketing (HypeAuditor)
- **Prompt scoring cohérent** avec la doc publique, sortie JSON avec reasoning par critère
- **Pipeline robuste** : 257/346 chaînes à 26+ transcripts (74%), taux succès 98%

## Faiblesses méthodologiques

1. **Production (20%)** non évaluable depuis un transcript — composite AI et manuel pas comparables
2. **Biais temporel** : 26 vidéos les plus récentes, pas documenté dans METHODOLOGY.md
3. **Juge non calibré** : 1 modèle, 1 passe, aucune mesure de variance
4. **89 chaînes incomplètes** sans règle définie (score provisoire ? exclusion ?)
5. **Agrégation non décidée** : moyenne vs médiane sur 26 vidéos

## Recommandations (ordre d'impact)

### 1. Décisions à prendre AVANT scorer en masse

- **Agrégation** : médiane (plus robuste aux outliers) vs moyenne simple
- **Seuil de validité** : ≥10 vidéos = score provisoire, ≥20 = confirmé
- **Production** : sortir du composite AI, repondérer les 4 critères (Research 30%, S/N 30%, Orig 20%, Impact 20%)

### 2. Lancer Phase 3 Scoring

Via subscription Claude (règle LLM-BUDGET-001), par lots de chaînes prioritaires :
```bash
# Lire transcripts depuis ai-video-studio/data/media/
# Générer scores inline dans la conversation
# Persister dans data/ai_scores_v2/ via batch_score_videos.py --from-json
```

Commencer par les 32 chaînes tier S pour valider la convergence avec les scores manuels (écart attendu ≤ 1 point).

### 3. Calibrer le judge

Scorer 20-30 vidéos deux fois (ou modèle vs modèle), mesurer la variance, publier l'intervalle de confiance dans METHODOLOGY.md.

### 4. UX transparence

Badge "scored on N videos" vs "editorial" dans l'interface publique.

### 5. METHODOLOGY.md

Ajouter :
- Biais temporel (vidéos récentes)
- Règle de validité du score (seuil minimal de vidéos)
- Variance mesurée du judge

## Métriques projet au 2026-06-10

- **346 chaînes** (32 S, 180 A, 86 B, 9 C, 39 D)
- **18 catégories** (12 × 25 chaînes, structure d'échantillonnage équilibrée)
- **9768 transcriptions** prêtes (304 en queue Whisper)
- **257 chaînes** à ≥26 transcripts (74%)
- **0 video_scores** — Phase 3 non lancée
- **Production** : https://creator-quality-index.onrender.com
