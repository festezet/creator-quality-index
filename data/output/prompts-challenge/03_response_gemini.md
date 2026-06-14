# Reponse Gemini — Challenge technique (Creator Quality Index)

> Reponse de Gemini au prompt `02_technique.md` (architecture / SRE).
> Date : 2026-05-06.

---

Voici mon analyse d'architecture technique. Je prends ma casquette d'architecte/SRE : on va regarder les fondations, la scalabilite et la dette technique.

---

### 1. Verdict global

L'architecture actuelle est un MVP "duct-tape" pragmatique pour valider une idee, mais elle est structurellement tres fragile et inadaptee a un produit public voue a grossir. Le grand ecart entre une stack backend bricolee (migrations additives custom, dualite DB) et un frontend obsolete (SPA vanilla en hash-routing) cree une dette technique immediate. C'est un assemblage astucieux de contournements, mais le manque de securite basique et l'absence totale d'optimisation SEO rendent le projet vulnerable et invisible.

---

### 2. Top 5 risques techniques (par criticite)

*   **Securite et abus (Criticite : Extreme)** : L'absence d'authentification sur l'admin et de rate-limiting expose publiquement tes endpoints. Un script basique peut spammer les `community_ratings` ou lancer des requetes lourdes sur l'API, ce qui epuisera instantanement les connexions Neon ou la RAM (512 MB) de Render.
*   **Suicide SEO via Hash-Routing (Criticite : Haute)** : Une application de "benchmark public" vit par sa decouvrabilite. Utiliser du routing type `/#category` en SPA vanilla signifie que les robots d'indexation (Google) ne verront qu'une coquille vide. Tes 346 fiches createurs n'existent pas pour les moteurs de recherche.
*   **La bombe a retardement de la Dual DB (Criticite : Haute)** : Le flag `IS_POSTGRES` couple aux migrations additives via `DO $ BEGIN` (qui masquent les erreurs de colonnes dupliquees) va inevitablement creer un "schema drift" (divergence) entre ton environnement local et la prod. Des que tu vas devoir alterer ou supprimer des donnees, la base va casser en silence.
*   **Perte de taches dans le pipeline MD5 (Criticite : Moyenne)** : Le sharding deterministe via modulo MD5 pour tes instances de telechargement garantit qu'en cas de crash a 50 % d'un slice, les 50 % restants ne seront jamais traites par les autres instances. Ce systeme sans coordination ni "retry" est extremement fragile pour des taches de longue haleine.
*   **Cold starts et Pool de connexions (Criticite : Moyenne)** : Render free s'endort apres 15 minutes. Quand un visiteur reveille l'app, Gunicorn (1 worker) va redemarrer, ouvrir son `SimpleConnectionPool` Neon. Si plusieurs requetes arrivent pendant le cold start, tu vas multiplier les timeouts ou empoisonner ton pool avant meme que Flask ne soit pret.

---

### 3. Top 5 simplifications (Anti over-engineering)

*   **Tue la dualite SQLite/Postgres** : Choisis une seule base. Puisque tu es sur Neon (qui offre du branching), utilise Neon en local aussi, ou deploie un Postgres local via Docker. Arrete de maintenir deux dialectes SQL.
*   **Abandonne Whisper en local CPU** : Faire tourner `faster-whisper` sur CPU pour 9000 videos (26 videos x 346 chaines) est une heresie en termes de temps et d'energie. Utilise une API externe abordable (comme Deepgram, ultra rapide et peu chere) pour la Phase B. Tu passeras de semaines de traitement a quelques heures.
*   **Supprime le fallback de la `shared_lib`** : Le pattern `try: from shared_lib ... except ImportError: ...` est un hack sale. Utilise les Git Submodules, ou fais-en un vrai package Python prive.
*   **Vire la logique SPA vanilla** : Tu utilises Flask. Reviens a de l'hypermedia classique : rends ton HTML cote serveur avec Jinja2. Tu gagnes le SEO instantanement, tu supprimes la complexite de l'etat frontend, et tu n'as pas besoin de framework lourd.
*   **Standardise tes migrations** : Jette `init_pg.py` et ses scripts de creation manuels. Utilise `Alembic` (meme sans SQLAlchemy complet) ou de simples fichiers `.sql` joues par un outil standard.

---

### 4. Reponses ciblees aux choix d'architecture

**Sur le Frontend et l'Indexabilite (Q18, Q20)** :
Le hash-routing n'est pas "OK pour le SEO", c'est un arret de mort pour le projet. Tu dois absolument passer en Server-Side Rendering (SSR). Soit tu utilises Jinja2 avec Flask (le plus simple), soit tu migres vers un framework oriente contenu comme Astro ou Next.js. Vanilla JS est tres bien pour des petits comportements (Alpine.js ou HTMX seraient parfaits ici), mais la donnee doit etre dans le HTML initial.

**Sur la DB et le Schema (Q4, Q5, Q8)** :
Une table `channels` avec 30 colonnes dont la moitie sont des nullable scores (manuel, AI, metadata) sent la dette a plein nez. Mieux vaudrait normaliser cela : une table `channel`, et une table `scores` (ou utiliser une colonne `JSONB` native a Postgres pour les scores AI). Le hard-delete sans historique pour la moderation est dangereux (Q8) ; ajoute un simple booleen `is_deleted` ou une table d'archive. Et oui, l'absence de `ON DELETE CASCADE` (Q7) sur `video_scores` te forcera a nettoyer manuellement en cas de suppression de chaine.

**Sur le Pipeline et l'IA (Q9, Q12)** :
Ton pipeline de queueing `MD5` est malin mais n'est pas resilient (Q9). Puisque tu as une base Postgres, utilise-la comme file d'attente (avec `FOR UPDATE SKIP LOCKED`).
Concernant l'evaluation par l'IA (Q12) : evaluer la "Production Quality" depuis un simple texte brut est impossible. Le LLM va juste halluciner une note basee sur la clarte du texte. Il faut explicitement ignorer ce critere pour l'AI Score ou utiliser des modeles multimodaux (qui coutent tres cher).

**Sur la Securite (Q14, Q15)** :
L'admin publique est une faille reelle (Q14). Pour l'instant, ajoute simplement une "Basic Auth" verifiee via une variable d'environnement dans un middleware Flask. Cela prend 10 lignes de code et stoppe 99 % des curieux. Pour l'API, ajoute l'extension `Flask-Limiter` d'urgence pour bloquer le scraping intensif.

---

### 5. Verdict "Shippe ou refuse"

**Refuse.**

En tant que tech lead, je bloque la merge request pour la mise en production publique. L'idee est geniale, mais l'execution actuelle va crasher au premier pic de trafic ou a la premiere tentative d'abus.

**Ce que tu dois corriger avant de merge** :
1. Proteger `/admin` (Basic Auth) et ajouter un rate-limit sur les requetes front.
2. Remplacer le hash-routing par des routes serveurs (`/channel/ID`) renvoyant du HTML complet pour le SEO.
3. Unifier l'environnement de base de donnees (fin du `IS_POSTGRES`) et mettre en place de vraies migrations.

---

### Question pour avancer :
Concernant la "Phase C" du pipeline (LLM), injecter le contexte de 26 videos entieres par chaine represente un volume de tokens titanesque. As-tu calcule le cout brut des requetes API (Claude ou GPT-4) pour parser toutes ces transcriptions, et as-tu envisage une approche d'echantillonnage semantique plutot que d'envoyer l'integralite du texte ?
