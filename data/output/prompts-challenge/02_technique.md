# Challenge prompt — Architecture technique (Creator Quality Index)

> **Instruction au modele** : adopte une posture de senior engineer / SRE / architecte. Identifie les fragilites, les patterns deja morts a 5x scale, les choix discutables, les couts caches, les dettes techniques deja inscrites dans le design. Pas de complaisance. Termine par un verdict "shipperais-je ca ?" avec justification.

---

## Contexte du projet

**Creator Quality Index (CQI)** — webapp publique qui benchmark 346 chaines YouTube sur 5 criteres de qualite intellectuelle. Live : https://creator-quality-index.onrender.com

Le site affiche un leaderboard, des fiches par chaine avec scores manuels + AI, des ratings communautaires. Trafic actuel : low (qq dizaines visites/jour, debut de cycle). Solo dev (moi).

---

## Stack actuelle

### Frontend
- **HTML/CSS/JS vanilla** (pas de framework). Single Page App "a la mano" avec routes en hash (`/#category`, `/#methodology`).
- **Pas de bundler** (Webpack/Vite). Fichiers servis directement via Flask `/static/<filename>`.
- **Pas de TypeScript**, pas de tests front.

### Backend
- **Python 3.11 + Flask** (pas FastAPI), **gunicorn** sur prod.
- **Blueprint pattern** : `channels`, `categories`, `stats`, `community`, `admin`.
- **Adapter DB dual SQLite/PostgreSQL** :
  ```python
  IS_POSTGRES = DATABASE_URL is not None  # env var detection
  ```
  - Local dev : SQLite via `shared_lib.db` (lib commune a tous mes projets, fournit get_connection avec WAL mode + Row factory)
  - Prod : PostgreSQL via `psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL)` cree au module-load
- **Migrations** : `init_db.py` (SQLite) et `init_pg.py` (PostgreSQL) appelees au boot dans `app.py` :
  ```python
  if IS_POSTGRES:
      from backend.init_pg import init_pg
      init_pg()
  elif not os.path.exists(DB_PATH):
      from backend.init_db import init_db
      init_db()
  ```
  Migrations additives : `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ADD COLUMN` enrobe dans `DO $$ BEGIN ... EXCEPTION WHEN duplicate_column THEN NULL; END $$;` pour PG.
- **Schema** : `categories`, `channels` (346 lignes, 30 colonnes dont 5 scores manuels + 4 AI scores + metadata), `community_ratings`, `comments`, `video_scores` (table normalisee pour scores AI par video).

### Hosting
- **Render free tier** (web service, 512 MB RAM, sleep apres 15 min inactivite, redeploy auto sur push GitHub)
- **DB historique** : Render PostgreSQL free → expire apres 90 jours
- **DB actuelle (post-migration ce matin)** : Neon PostgreSQL free (us-west-2 pooler endpoint) — pas d'expiration, 0.5 GB free.

### Pipeline AI scoring (le gros morceau)

Conçu en **2 phases decouplees** parce que les bottlenecks sont differents :

**Phase A — Download audio** :
- Local, sur disque firecuda 4TB (`/data/fcuda_workspace/youtube/audio_cache`)
- `yt-dlp` avec `--extractor-args "youtube:player_client=android_vr,android,ios"` (bypass du client `tv downgraded` qui ne sert plus l'audio depuis fin 2025)
- Pas de re-encoding : on garde le format natif (opus/m4a)
- **Multi-instance via modulo MD5 deterministe** :
  ```python
  h = int(hashlib.md5(video_id.encode()).hexdigest()[:8], 16)
  if h % args.total != args.instance - 1:
      continue
  ```
  3 instances paralleles (`--total 3 --instance 1|2|3`), pas de coordination, pas de Redis/queue : chaque instance traite son slice du manifest sans collision.
- DB locale `download_progress` (SQLite) tracke status : `downloaded`, `ok`, `download_failed`, `whisper_failed`, `rate_limited`, `timeout`
- Rate-limiting : delai aleatoire 5-15s entre videos, pause 600s + abort si 3 rate limits consecutifs

**Phase B — Transcribe** :
- Container Docker `whisper-cpu:9001` partage entre projets (faster-whisper tiny, CPU-only sur GTX 1080 Compute 6.1 → CUDA pas exploitable)
- `phase_b_loop.sh` : wrapper bash qui boucle, prend un lot de `status='downloaded'`, transcribe, marque `ok`/`whisper_failed`. Exit quand Phase A finie ET pending=0.
- Output : transcript stocke dans la DB (table `transcripts`), feed vers une 3eme phase (AI scoring via LLM, pas encore productionne)

**Phase C — AI scoring (en design)** :
- Pour chaque chaine, 26 videos transcribees → prompt LLM (probablement Anthropic Claude ou OpenAI GPT-4) avec rubric, retourne 4 scores (Research, S/N, Originality, Impact, pas Production qui n'est pas evaluable depuis transcript)
- Stocke dans `video_scores` puis agrege en `channels.ai_score_*`

### Admin pipeline status
- Page `/admin/pipeline` (vanilla HTML + JS) qui pull `/api/admin/pipeline` toutes les N secondes
- Affiche : status counts globaux, breakdown per channel, recent activity (dernieres N rows ou time window), ETA, cache stats (size firecuda)
- **Probleme deja patche** : la table `download_progress` n'existe que sur la SQLite locale (pipeline = local). En prod (Neon PG), elle n'existe pas → endpoint catchait `relation does not exist` et retournait 500 jusqu'a aujourd'hui. Patche pour retourner `{"available": false}` silencieusement + ajout d'un `conn.rollback()` dans `db_query` pour eviter pool poisoning sur PG (sans ca, une exception laisse la connection en `aborted transaction` state, tous les requests suivants crashent).

### Securite / observability
- **Aucune auth**. Page admin `/admin` accessible publiquement (juste pas linkee). A securiser eventuellement.
- **Pas de logging structure** centralise (juste `setup_logger` de shared_lib qui ecrit en local).
- **Pas de monitoring externe** (pas de Sentry, pas de Datadog, pas de healthcheck externe).
- **CORS** ouvert (setup_cors avec defaults).
- **Rate limiting** : aucun. Exposition aux scrapers et abus.

### Deploy
- `render.yaml` blueprint :
  ```yaml
  services:
    - type: web
      name: creator-quality-index
      runtime: python
      plan: free
      buildCommand: pip install -r requirements.txt
      startCommand: gunicorn backend.app:app --bind 0.0.0.0:$PORT
      envVars:
        - key: DATABASE_URL
          sync: false   # set manually in UI (Neon connection string)
  ```
- Push sur main → auto-deploy Render
- Pas de tests CI, pas de staging, pas de blue/green

### shared_lib
- Lib partagee entre tous mes projets (`/data/projects/shared-lib/`), expose `db.get_connection`, `flask_helpers.success/error/setup_cors/register_health/setup_logger`
- En prod, fallback sur `backend/helpers.py` local (shared_lib pas pip-installable car pas package)
- Pattern courant : `try: from shared_lib... except ImportError: from backend.helpers...`

---

## Incidents recents (utiles pour comprendre les fragilites)

1. **2026-05-06 matin** : prod down → "Exited with status 1" → DNS resolution failed sur `dpg-d77sicma2pns73b0fueg-a` → root cause : Render free PG expire (90 jours). Migration vers Neon free en 30 min : creer DB Neon → `render.yaml` change `fromDatabase` → `sync: false` → DATABASE_URL settee en UI → redeploy → init_pg() reseed les 346 channels depuis seed_channels.json. Pertes : 5 community ratings, 1 comment.
2. **Whisper batch stuck** (mai 2026) : transcription tournait sur dl yt-dlp embedded → si yt-dlp throttled, tout le batch stuck. Fix : decouplage Phase A/B (telecharge tout d'abord sur disque, transcribe ensuite depuis cache).
3. **YouTube TV client downgrade** (2026-04-08) : yt-dlp commencait a utiliser `tv downgraded player API JSON` qui ne sert plus d'audio. Workaround : `--extractor-args "youtube:player_client=android_vr,android,ios"`. Cookies firefox avant tested = forcaient web client = pire.
4. **GPU GTX 1080 (sm_61)** : incompatible PyTorch CUDA 12.8+ (sm_70+ requis). Whisper tourne en CPU-only, ~lent. Pas de GPU OCR/Whisper exploitable pour mes projets.

---

## Questions a challenger

### Architecture globale
1. **Flask + vanilla JS + SQLite/PG dual** pour un projet en debut de cycle : choix raisonnable ou condamne quand le projet grossit ? Aurais-tu pousse plutot Next.js + Vercel + Supabase, ou FastAPI + Astro, ou full server-rendered Django ?
2. La **dual DB SQLite/PostgreSQL** via `IS_POSTGRES` flag : pragmatique ou source de bugs caches (les 2 dialectes divergent silencieusement) ? Devrais-je utiliser SQLite partout (Litestream pour persistance) ou PG partout (Supabase local) ?
3. **Render free + Neon free** : combien de temps ce setup tient-il ? Quels sont les pieges de scale (cold start Render, connection limits Neon, pricing cliff) ?

### DB et schema
4. Le schema `channels` a **30+ colonnes** dont beaucoup nullable. Est-ce une dette qui va exploser ou normal pour un projet en exploration ?
5. **Migrations additives uniquement** (`ADD COLUMN` avec exception duplicate_column) : safe sur le court terme, mais **comment je gere une vraie migration destructive** (rename column, change type, supprimer table) sans downtime ?
6. Pas d'**index** sur les colonnes filtrees par le frontend (ex: `WHERE primary_category = ? ORDER BY composite_score DESC`). Index requis ou inutile a 346 lignes ? A partir de quand ca fait mal ?
7. La table `video_scores` a une UNIQUE(channel_id, video_id) mais **pas de FK ON DELETE CASCADE** — voulu ou oubli ?
8. **Pas de soft-delete** sur channels/comments. Si je veux moderer un commentaire abusif, je le hard-delete et perd l'historique. Anti-pattern ?

### Pipeline AI
9. **Modulo MD5 deterministe** pour split multi-instance : elegant mais limite. Si une instance plante apres 50% du slice, les videos restantes ne sont JAMAIS reessayees par les autres (chaque instance ne voit que son slice). Devrais-je passer a une vraie task queue (RQ, Celery, ou meme juste une file SQLite avec lock) ?
10. **Phase A / Phase B / Phase C decouplees** : pragmatique. Mais le couplage par DB locale `download_progress` cree de la friction (status enums implicites, race conditions possibles si Phase A ecrit pendant que Phase B lit). Vrai probleme ou paranoia ?
11. **Whisper local CPU** vs **API externe** (Anthropic Whisper, AssemblyAI, Deepgram) : pour 346 * 26 = ~9000 videos, est-ce que le cout de l'API justifie l'effort vs garder Whisper local sur ce serveur (electricite 24/7, GPU GTX 1080 inutilisable, CPU sature) ?
12. **AI scoring (Phase C)** : le LLM regarde un transcript. Sans contexte visuel ni audio, peut-il vraiment evaluer "Production Quality" ? Si non, le score AI est-il une approximation honnete ou un mensonge poli ?
13. **Re-scoring 6 mois** : faut-il versionner les scores ? Garder un historique (`channel_scores_history` table) ou ecraser ?

### Securite / Robustesse
14. **Pas d'auth admin** sur `/admin` : **vraie faille** ou OK pour un projet d'1 personne avec admin URL non-listee ? Si je dois en mettre, quel mecanisme minimal (basic auth via env var ? magic link mail ? Auth0 free) ?
15. **Pas de rate limiting** sur API publiques : combien de temps avant qu'un script kiddie scrape /api/channels en boucle ou que quelqu'un spam community_ratings avec un visitor_id force ?
16. **`db_query` rollback fix** que j'ai ajoute aujourd'hui : suffisant ou ya d'autres patterns du pool qui peuvent corrompre une connexion en aborted state ?
17. **Connection pool SimpleConnectionPool(1, 10)** : adequate pour Render free (1 worker gunicorn) ? Si je passe a 2 workers, le pool est par-process, donc 20 connexions Neon. Limite Neon free = 100 connections ? OK mais a verifier.

### Frontend
18. **Vanilla JS sans bundler ni typescript** : valide tant que je suis seul, mais je suis mort si je veux du SSR pour SEO ou si la complexite UI augmente ? Quels sont les premiers signes que ca devient un fardeau ?
19. **Pas de tests front** : faux probleme tant que je suis seul, ou dette en cours d'accumulation ?
20. Le mode SPA hash-routing (`/#methodology`) : OK pour SEO ou faut-il vraiment passer en SSR/static-gen pour que les chaines soient indexables sur Google ?

### Coherence/Qualite
21. **shared_lib avec fallback `backend.helpers`** : pratique perso (DRY entre projets), mais source de bugs (versions divergent). Vraie dette ou hack acceptable ?
22. **Pas de CI** : si je casse un test (qui n'existe pas encore), je le decouvre en prod. Acceptable ou je dois mettre minimum un GitHub Actions avec `pytest` + `flake8` ?
23. **Logging non centralise** : sur Render free, les logs disparaissent apres redeploy. Pour un debugging post-mortem, j'ai juste mes screenshots. Sentry free tier (5k events/mois) suffirait-il pour cette taille de projet ?

### Si tu reprenais demain
24. **3 changements prioritaires** que tu ferais en premier semaine, justifies par impact ?
25. **3 choses que tu garderais telles quelles** parce que c'est over-engineering qu'on regretterait sur ce volume ?
26. **1 piege technique** que je vais probablement rencontrer dans les 6 mois et que je n'ai pas prevu ?

---

## Format de reponse attendu

1. **Verdict global** : architecture solide / fragile / dangereuse, et **pourquoi** en 3 phrases
2. **Top 5 risques techniques** classes par criticite (impact x probabilite)
3. **Top 5 simplifications** que je pourrais faire sans perdre de fonctionnalite (anti over-engineering)
4. Reponses ciblees sur les questions 1-26 que tu juges les plus importantes (pas obligation de tout traiter)
5. **Verdict "shippe ou refuse"** : si j'arrivais en code review chez toi avec ce projet en tant que side-project public, qu'est-ce que tu voudrais voir corrige avant de merge ?

Pas de complaisance. Si un choix est nul, dis-le. Si un truc est sur-engineerise, dis-le aussi. Si tu trouves un bug latent en lisant ca, signale-le.
