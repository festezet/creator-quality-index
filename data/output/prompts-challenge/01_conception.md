# Challenge prompt — Conception (Creator Quality Index)

> **Instruction au modele** : adopte une posture critique d'investisseur / chercheur / utilisateur expert. Identifie les failles methodologiques, les biais, les angles morts, les hypotheses non verifiees, et les concurrents oublies. Sois direct, pas de flatterie. Termine par une note d'investabilite (1-10) avec justification.

---

## Contexte du projet

Je construis le **Creator Quality Index (CQI)**, un benchmark public et gratuit qui evalue la qualite intellectuelle de createurs YouTube long-form (vulgarisation, education, analyse). Site live : https://creator-quality-index.onrender.com

**Pitch en une phrase** : "TripAdvisor-meets-Pitchfork pour YouTube educatif — on note les chaines sur 5 criteres ponderes, on classe en tiers S/A/B/C/D, on documente la methodo en clair, on accepte les contre-arguments."

**Mon hypothese centrale** : la decouverte de chaines YouTube de qualite est cassee. L'algo YT optimise pour le watch-time. Les agregateurs existants (HypeAuditor, Social Blade, P-Score) mesurent la performance marketing ou la popularite. Aucun outil ne repond a la question : *"Est-ce que ce createur vaut mon temps si je veux apprendre quelque chose ?"*

---

## Methodologie complete

### 5 criteres notes 1-10

| # | Critere | Poids | Question centrale |
|---|---------|-------|-------------------|
| 1 | **Research Depth** | 25% | Sources primaires, papiers academiques, expertise reelle ? |
| 2 | **Production Quality** | 20% | Editing, audio, structure servent-ils la comprehension ? |
| 3 | **Signal-to-Noise Ratio** | 25% | % de contenu reel vs filler, sponsors, clickbait |
| 4 | **Originality** | 15% | Format/angle/voix unique ou imitation ? |
| 5 | **Lasting Impact** | 15% | Toujours pertinent dans 5 ans ? Change-t-il la facon de penser ? |

**Composite** = R*0.25 + P*0.20 + S*0.25 + O*0.15 + I*0.15

**Tiers** : S (>=8.5) / A (7.0-8.4) / B (5.5-6.9) / C (4.0-5.4) / D (<4.0)

### Couverture actuelle
- **346 chaines** scoree en v1
- **18 categories** : Science, Tech & Dev, Engineering, Finance, History, Geopolitics, Productivity, Philosophy, Design & Art, Education, Environment, Making/DIY, Entertainment, Music, Kids, Sports, Gaming, Lifestyle
- **Langues** : majoritairement EN, sous-representation francais/autres

### Ce que CQI **ne mesure pas** (assume)
- Valeur de divertissement (comedie peut etre brillante sans scorer haut)
- Popularite (subscribers = 0 weight)
- Frequence d'upload
- Personnalite/charisme
- Accord ideologique (raisonnement solide > conclusion preferee)

### Biais reconnus
1. Bias linguistique (EN/FR overrepresentes)
2. Bias format (long-form educatif favorise — "feature, not bug" selon ma methodo, mais defendable ?)
3. Bias recence (chaines anciennes scorent mieux sur "Lasting Impact" mecaniquement)
4. Subjectivite (humans differ +/- 1-2 pts par critere)

### Pipeline de scoring (en construction)
- **Phase 1 (manuel)** : 346 chaines scorees a la main par moi (V1)
- **Phase 2 (AI augmented)** : pipeline qui telecharge les transcriptions de ~26 videos par chaine, fait passer un LLM sur les transcripts, genere un AI score (les 4 criteres "lisibles" depuis transcript : Research, Signal/Noise, Originality, Impact — pas Production), affiche cote-a-cote avec le score humain pour validation/contestation
- **Phase 3 (community)** : visiteurs peuvent rate (1-10) chaque critere, poster des commentaires, suggerer des chaines

---

## Questions a challenger (ne te limite pas a celles-ci)

### Pertinence du concept
1. Le probleme "decouverte cassee" est-il **reel** ou est-ce que la frustration est marginale ? Les utilisateurs YT educatif ont-ils deja leurs propres mecanismes (sub box, recos amis, Reddit) qui suffisent ?
2. Y'a-t-il une **demande payante** quelque part (B2B education ? curation pour profs ? brand safety pour annonceurs intelligents ?) ou est-ce condamne au "labour-of-love" gratuit ?
3. Le format **leaderboard/tier list** est-il le bon ? Ou est-ce que ca biaise vers la competition au detriment de la decouverte par centre d'interet ?

### Methodologie
4. Les **5 criteres** captent-ils l'essentiel ou en oublie-t-on ? Candidats absents : pedagogie/clarte d'explication, honnetete intellectuelle (admettre quand on ne sait pas), diversite des points de vue cites, ethique editoriale (correction d'erreurs publiquement), accessibilite (sous-titres, langue), reproductibilite (montrer son travail).
5. Les **poids** (25/20/25/15/15) sont-ils defendables ou arbitraires ? Faudrait-il differencier les poids par categorie (ex: Science = 30% Research, Music = 30% Production) ?
6. La rubric 1-10 par critere est-elle suffisamment **discriminante** ? Risque de tassement vers 6-8.
7. **Production Quality** est le seul critere non-evaluable depuis transcript. Est-ce un probleme pour le scaling AI ? Faut-il l'extraire du score "intellectuel" et en faire un score parallele ?
8. Le tier S/A/B/C/D est-il **utile** ou simplement gamifie ? Une echelle continue serait-elle plus honnete ?

### Concurrents et marche
9. Concurrents que j'oublie : qui d'autre tente ca ? Newsletters de curation (Stratechery-style), Patreon-only critiques, communautes de niche (HackerNews edu sub, Lobste.rs equivalents YT) ? Existe-t-il un equivalent academique (CommonSense Media pour adultes) ?
10. Si **YouTube lui-meme** sortait un "quality score" demain, qu'est-ce qui differencie CQI ?

### Biais et ethique
11. Le bias **long-form/educatif assume** est-il defendable ou elitiste ? Risque-t-on de reproduire un canon culturel etroit (occidental, anglophone, "intellectuel") ?
12. Comment gerer les **conflits d'interet** quand le projet grossit (annonceurs, sponsors de chaines notees, ressentiment des createurs mal classes) ?
13. **Mecanisme de plainte** : un createur conteste son tier — quel process est equitable ? Comment eviter les guerres de review-bombing ?

### Scalabilite et durabilite
14. 346 chaines scoree a la main. Pour passer a **5000 ou 50000**, la methodo tient-elle ? L'AI scoring est-il assez fiable pour ne plus avoir d'humain dans la boucle, ou doit-on rester en "AI suggests, human validates" pour preserver la legitimite ?
15. **Re-scoring tous les 6 mois** : drift naturel (chaines qui changent de format, baisse/hausse de qualite). Comment tracker l'evolution sans noyer le visiteur dans des historiques ?
16. **Modele de durabilite** sans pub : donations Patreon ? Premium tier (acces API, exports) ? Sponsoring institutionnel (universites, fondations) ? Ou condamne au benevolat ?

### Failles
17. Quelles **objections** les detracteurs vont-ils me jeter en premier ? Qu'est-ce que je ne vois pas ?
18. Si tu devais convaincre un **utilisateur novice** que CQI vaut son temps versus juste regarder ce que recommandent ses amis, quel argument utiliserais-tu ? Et inversement, comment le dissuaderais-tu ?

---

## Format de reponse attendu

1. **Critique structuree** des points 1-18 (pas besoin de tout traiter, focus sur les plus impactants selon toi)
2. **3-5 risques majeurs** non identifies dans ma liste
3. **Concurrents/precedents** que je devrais etudier (livres, articles, outils existants ou disparus)
4. **Recommandations concretes** : que ferais-tu differemment si tu reprenais le projet from scratch ?
5. **Note d'investabilite** (1-10) avec breakdown : utilite reelle / defensibilite / monetisation potentielle / executabilite par 1 personne / fit marche

Sois brutal. Si le concept est bancal, dis-le. Si la methodo a un trou logique, pointe-le. Pas de "c'est interessant" creux.
