# SESSION 2026-05-06/07 — Phase 0 Sécurité : Basic Auth + Flask-Limiter

**PRJ-063 creator-quality-index**  
**Contexte** : Réponses critiques Gemini + ChatGPT au challenge "Refuse de travailler sur ce projet" → plan 7-phase de remédiation. Démarrage par Phase 0 (Security).

## Objectif
Sécuriser les endpoints admin et limiter l'abus public (bots, spam) sur l'API publique en production.

## Actions réalisées

### 1. Sauvegarde réponses challenge (préalable)
- `data/output/prompts-challenge/03_response_gemini.md` : verdict "Refused", top 5 risks
- `data/output/prompts-challenge/04_response_chatgpt.md` : verdict "Yes side-project, No production-grade", investability 4.5/10
- `data/output/prompts-challenge/INDEX.md` : récapitulatif convergences/divergences + plan 4 horizons

### 2. Plan 7-phase élaboré
| Phase | Description | ROI/Criticité |
|-------|-------------|---------------|
| 0 | Security (Basic Auth, Flask-Limiter, ~~Sentry~~, Backup Neon) | CRITIQUE |
| 1 | Kill dual DB (migrate tout vers Postgres) | HIGH |
| 2 | SEO SSR (Jinja2 templates pages publiques) | MEDIUM |
| 3 | Methodology (Production out of AI score) | MEDIUM |
| 4 | Tests + Alembic migrations | LOW |
| 5 | Pipeline jobs table (audit logs) | LOW |
| 6 | Editorial repositioning | NICE-TO-HAVE |

### 3. Phase 0 Step 1 — Basic Auth (commit f123867)
**Fichier créé** : `backend/auth.py`
- Decorator `@require_admin_auth` : vérifie `request.authorization` contre `ADMIN_USERNAME` ("admin") et `ADMIN_PASSWORD` (env var)
- **Fail closed** : si `ADMIN_PASSWORD` absent → 503 "Authentication not configured" (safer que servir l'admin sans auth)
- Realm HTTP : `'Basic realm="CQI Admin", charset="UTF-8"'`

**Fichiers modifiés** :
- `backend/app.py` : decorator sur `/admin` et `/admin/pipeline`
- `backend/routes/admin.py` : decorator sur `/api/admin/synthesis` et `/api/admin/pipeline`

**Tests locaux** :
- Sans auth → 401 Unauthorized + WWW-Authenticate header
- Avec credentials valides → 200
- Sans `ADMIN_PASSWORD` env → 503

**Deploy prod** :
- Password généré : `8_zUZE1OjiVugwB5oBKT4KMHhbk5cjDR` (sauvé dans Render env vars)
- Commit `f123867` + push → deploy Render
- Validation prod : 401/200 sur les 4 routes admin, public routes 200

### 4. Phase 0 Step 2 — Flask-Limiter (commit bac120b)
**Fichier créé** : `backend/limiter.py`
```python
limiter = Limiter(
    key_func=get_remote_address,  # IP-level
    default_limits=["200 per hour"],
    storage_uri="memory://",  # acceptable free tier 1 worker
    headers_enabled=True,  # X-RateLimit-* exposés
    strategy="fixed-window",
)
```

**Fichiers modifiés** :
- `requirements.txt` : ajout `flask-limiter`
- `backend/app.py` : `limiter.init_app(app)` + exempt `/health` et `/static/*`
- `backend/routes/community.py` :
  - `@limiter.limit("10 per hour")` sur POST `/api/channels/<id>/comments`
  - `@limiter.limit("60 per hour")` sur POST `/api/comments/<id>/upvote`
- `backend/routes/channels.py` :
  - `@limiter.limit("120 per hour")` sur GET `/api/channels`
  - `@limiter.limit("300 per hour")` sur GET `/api/channels/<int>`

**Tests locaux** :
- Headers X-RateLimit-Limit=120, Remaining=119 visibles sur `/api/channels`
- Burst 12 POST comments → requêtes 11-12 rejetées avec 429 (limite 10/h confirmée)

**Deploy prod** :
- Commit `bac120b` + push → deploy Render
- Validation prod : X-RateLimit headers présents, Remaining décrémente correctement
- Admin auth (Phase 0 step 1) toujours fonctionnel

### 5. Phase 0 Step 3 — Sentry (SKIPPÉ)
Utilisateur choix C : skip Sentry pour Phase 0 (free tier non prioritaire).

### 6. Phase 0 Step 4 — Backup Neon (PENDING)
Non commencé. Prochaine étape : vérifier Point-in-Time Recovery actif + documenter restore procedure.

## Décisions

1. **Basic Auth avec ADMIN_PASSWORD env var** : fail closed si absent (503 vs servir sans auth)
2. **Flask-Limiter memory storage** : acceptable free tier 1 worker (reset au restart toléré)
3. **Skip Sentry Phase 0** : utilisateur choix C (monitoring non critique pour MVP)
4. **Plan 7-phase validé** : P0=Security, P1=Kill dual DB, P2=SEO SSR, P3=Methodology, P4=Tests, P5=Pipeline, P6=Editorial

## État final
- **Basic Auth** : ✅ déployé prod (commit f123867)
- **Flask-Limiter** : ✅ déployé prod (commit bac120b)
- **Sentry** : ❌ skippé
- **Backup Neon** : ⏳ pending

## Prochaines étapes
1. **Phase 0 step 4** : Vérifier backup Neon (PITR actif + doc restore procedure)
2. **Phase 1** : Kill dual DB — migrate tout vers Postgres, supprimer `IS_POSTGRES` flag
3. **Phase 2** : SEO SSR — templates Jinja2 pour pages publiques statiques
4. **Phase 3** : Methodology — sortir Production du composite_score AI

## Leçons apprises
- **Fail closed > fail open** : 503 sans ADMIN_PASSWORD évite de servir des endpoints admin non protégés en production
- **Defense-in-depth** : Basic Auth (authentification) + Flask-Limiter (rate limiting) = protection 2 couches
- **Memory storage acceptable free tier** : 1 worker = pas de concurrence = pas de Redis nécessaire (reset rate limits au restart toléré pour MVP)
- **X-RateLimit headers exposés** : permet aux clients légitimes de voir leurs quotas et d'implémenter retry intelligents

## Commits
- `f123867` : feat(security): add HTTP Basic Auth on admin routes (Phase 0/1)
- `bac120b` : feat(security): add Flask-Limiter IP rate limiting (Phase 0/2)
