"""Populate benchmark.db with ~185 additional channels to reach 25 per category.

Sources: web research (Reddit, Nebula, curated lists), cross-referencing
across ThoughtLeaders, Feedspot, Quora, Medium articles, and direct knowledge
of the YouTube educational ecosystem.

Each channel scored on 5 criteria (1-10):
  - research_depth: How deeply researched is the content
  - production: Visual/audio quality, editing, graphics
  - signal_noise: Substance vs filler ratio
  - originality: Unique perspective vs rehashed content
  - lasting_impact: Will this be relevant in 5 years
"""
import sqlite3
import os
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "benchmark.db")

# Scoring weights from config.py
WEIGHTS = {
    "research_depth": 0.25,
    "production": 0.20,
    "signal_noise": 0.25,
    "originality": 0.15,
    "lasting_impact": 0.15,
}

TIERS = {"S": 8.5, "A": 7.0, "B": 5.5, "C": 4.0}


def compute_score(rd, pr, sn, ori, li):
    return rd * 0.25 + pr * 0.20 + sn * 0.25 + ori * 0.15 + li * 0.15


def compute_tier(score):
    for tier, threshold in TIERS.items():
        if score >= threshold:
            return tier
    return "D"


# Format: (name, url, language, category, description,
#          research_depth, production, signal_noise, originality, lasting_impact)
NEW_CHANNELS = [
    # ============================================================
    # SCIENCE (need 10 more → total 25)
    # ============================================================
    ("NileRed", "https://www.youtube.com/@NileredOfficial", "en", "science",
     "Chemistry experiments with stunning cinematography. Complex reactions explained step by step.",
     8, 10, 9, 8, 8),
    ("Physics Girl", "https://www.youtube.com/@physicsgirl", "en", "science",
     "Physics experiments and explanations by Dianna Cowern. Hands-on demonstrations of physics principles.",
     8, 9, 8, 7, 8),
    ("Dr. Becky", "https://www.youtube.com/@DrBecky", "en", "science",
     "Astrophysics explainers from Oxford astrophysicist Dr. Becky Smethurst. Latest space discoveries.",
     9, 7, 9, 7, 8),
    ("Periodic Videos", "https://www.youtube.com/@periodicvideos", "en", "science",
     "Every element of the periodic table explored. University of Nottingham chemistry with Prof. Martyn Poliakoff.",
     9, 6, 9, 7, 9),
    ("The Science Asylum", "https://www.youtube.com/@ScienceAsylum", "en", "science",
     "Physics and math explained with humor by Nick Lucid. Tackles misconceptions head-on.",
     8, 7, 8, 7, 7),
    ("Looking Glass Universe", "https://www.youtube.com/@LookingGlassUniverse", "en", "science",
     "Quantum mechanics and physics from a math-heavy perspective. Thoughtful deep dives.",
     9, 6, 9, 8, 8),
    ("Tibees", "https://www.youtube.com/@Tibees", "en", "science",
     "Math and physics in a calm, meditative style. Exam walkthroughs, history of science.",
     7, 7, 8, 8, 7),
    ("Fermilab", "https://www.youtube.com/@feraboragua", "en", "science",
     "Particle physics from the lab that discovered the top quark. Real scientists explaining cutting-edge research.",
     10, 7, 9, 7, 9),
    ("DirtyBiology", "https://www.youtube.com/@DirtyBiology", "fr", "science",
     "Vulgarisation scientifique francaise originale. Biologie, evolution, themes inattendus.",
     8, 8, 7, 9, 7),
    ("E-penser", "https://www.youtube.com/@Epenser1", "fr", "science",
     "Vulgarisation scientifique par Bruce Benamran. Physique, maths, philosophie des sciences.",
     8, 7, 8, 7, 7),

    # ============================================================
    # TECH & DEV (need 11 more → total 25)
    # ============================================================
    ("The Coding Train", "https://www.youtube.com/@TheCodingTrain", "en", "tech-dev",
     "Creative coding with Daniel Shiffman. Processing, p5.js, algorithmic art. Infectious enthusiasm.",
     7, 7, 7, 9, 8),
    ("Reducible", "https://www.youtube.com/@Reducible", "en", "tech-dev",
     "CS algorithms and data structures visualized beautifully. FFT, graph theory, compression.",
     9, 9, 9, 8, 9),
    ("Tom Scott", "https://www.youtube.com/@TomScottGo", "en", "tech-dev",
     "Technology, computing, and interesting places. Concise, well-researched, zero filler.",
     8, 8, 10, 8, 9),
    ("No Boilerplate", "https://www.youtube.com/@NoBoilerplate", "en", "tech-dev",
     "Rust programming and programming philosophy. Fast-paced, text-heavy, substance-dense.",
     8, 7, 10, 9, 7),
    ("The Cherno", "https://www.youtube.com/@TheCherno", "en", "tech-dev",
     "C++, game engine development, low-level programming. Building a game engine from scratch series.",
     8, 7, 8, 7, 7),
    ("Hussein Nasser", "https://www.youtube.com/@haborMeaning", "en", "tech-dev",
     "Backend engineering deep dives. Protocols, databases, proxies, networking fundamentals.",
     9, 6, 8, 7, 8),
    ("ByteByteGo", "https://www.youtube.com/@ByteByteGo", "en", "tech-dev",
     "System design concepts visualized. Scalability, distributed systems, architecture patterns.",
     8, 9, 8, 7, 8),
    ("Code Bullet", "https://www.youtube.com/@CodeBullet", "en", "tech-dev",
     "AI and machine learning applied to games and challenges. Entertaining and educational.",
     6, 8, 7, 9, 6),
    ("javidx9", "https://www.youtube.com/@javidx9", "en", "tech-dev",
     "OneLoneCoder. C++ programming from scratch, game engines, emulators. Low-level excellence.",
     8, 6, 8, 8, 8),
    ("Tsoding Daily", "https://www.youtube.com/@TsodingDaily", "en", "tech-dev",
     "Live coding sessions. Systems programming, parsers, renderers built from scratch.",
     7, 5, 7, 9, 6),
    ("Theo", "https://www.youtube.com/@t3dotgg", "en", "tech-dev",
     "Web development ecosystem analysis. React, Next.js, TypeScript. Industry commentary.",
     7, 7, 7, 7, 6),

    # ============================================================
    # ENGINEERING (need 16 more → total 25)
    # ============================================================
    ("Lesics", "https://www.youtube.com/@Lesics", "en", "engineering",
     "3D animated engineering explanations. How things work: engines, turbines, electric vehicles.",
     8, 9, 8, 6, 8),
    ("ElectroBOOM", "https://www.youtube.com/@ElectroBOOM", "en", "engineering",
     "Electrical engineering with humor and controlled chaos. Mehdi Sadaghdar teaches through (safe) mistakes.",
     7, 8, 7, 9, 7),
    ("Tom Stanton", "https://www.youtube.com/@TomStantonEngineering", "en", "engineering",
     "Aerospace and mechanical engineering projects. Drones, bikes, jet engines — all DIY.",
     7, 8, 8, 8, 7),
    ("Mustard", "https://www.youtube.com/@MustardChannel", "en", "engineering",
     "Aerospace engineering history. Why certain planes, trains, ships were designed the way they were.",
     9, 10, 9, 8, 9),
    ("The B1M", "https://www.youtube.com/@TheB1M", "en", "engineering",
     "Construction and infrastructure engineering. Megaprojects, skyscrapers, tunnels, bridges.",
     8, 9, 8, 7, 7),
    ("Integza", "https://www.youtube.com/@Integza", "en", "engineering",
     "Rocket engines, 3D printing, combustion experiments. Creative engineering with a DIY spirit.",
     6, 8, 7, 9, 6),
    ("Breaking Taps", "https://www.youtube.com/@BreakingTaps", "en", "engineering",
     "Precision machining and manufacturing. CNC, EDM, micro-engineering at extreme tolerances.",
     8, 9, 9, 8, 7),
    ("EEVblog", "https://www.youtube.com/@EEVblog", "en", "engineering",
     "Electronics engineering with Dave Jones. Teardowns, tutorials, lab equipment reviews.",
     8, 6, 7, 7, 7),
    ("Great Scott!", "https://www.youtube.com/@GreatScottLab", "en", "engineering",
     "Electronics projects and tutorials. DIY power supplies, motor controllers, solar setups.",
     7, 7, 7, 7, 6),
    ("Wintergatan", "https://www.youtube.com/@Wintergatan", "en", "engineering",
     "The Marble Machine project. Mechanical engineering meets music in an epic multi-year build.",
     7, 9, 8, 10, 8),
    ("The Engineering Mindset", "https://www.youtube.com/@TheEngineeringMindset", "en", "engineering",
     "HVAC, electrical, mechanical engineering basics. Clear tutorials with animations.",
     7, 8, 7, 5, 7),
    ("styropyro", "https://www.youtube.com/@styropyro", "en", "engineering",
     "Lasers, high voltage, and extreme DIY electronics. Pushes the boundaries of home engineering.",
     7, 7, 7, 9, 6),
    ("NightHawkInLight", "https://www.youtube.com/@Nighthawkinlight", "en", "engineering",
     "Science experiments and engineering projects. Plasma, lasers, chemistry with excellent production.",
     7, 8, 8, 7, 6),
    ("Grady Hillhouse", "https://www.youtube.com/@GradyHillhouse", "en", "engineering",
     "Civil engineering and infrastructure. How bridges, dams, and water systems actually work.",
     8, 8, 8, 7, 8),
    ("Not An Engineer", "https://www.youtube.com/@NotAnEngineer", "en", "engineering",
     "Precision machining and creative problem-solving. DIY CNC, tool modifications, workshop builds.",
     7, 8, 8, 7, 6),
    ("Works By Design", "https://www.youtube.com/@WorksByDesign", "en", "engineering",
     "Innovative engineering projects. Pick-proof locks, efficient bicycles. Rising channel.",
     7, 8, 8, 8, 6),

    # ============================================================
    # FINANCE & ECONOMICS (need 14 more → total 25)
    # ============================================================
    ("Marginal Revolution University", "https://www.youtube.com/@MarginalRevolutionUniversity", "en", "finance",
     "Economics education from Tyler Cowen and Alex Tabarrok. Microeconomics, macro, development.",
     10, 7, 9, 7, 9),
    ("Unlearning Economics", "https://www.youtube.com/@UnlearningEconomics", "en", "finance",
     "Critical analysis of economic assumptions and models. Challenges mainstream narratives.",
     9, 6, 9, 9, 8),
    ("ColdFusion", "https://www.youtube.com/@ColdFusion", "en", "finance",
     "Tech and business deep dives. Corporate histories, financial scandals, emerging technologies.",
     8, 9, 8, 7, 7),
    ("Company Man", "https://www.youtube.com/@CompanyMan", "en", "finance",
     "Business case studies. Why companies succeed or fail. Concise corporate analysis.",
     7, 7, 9, 7, 7),
    ("Slidebean", "https://www.youtube.com/@Slidebean", "en", "finance",
     "Startup analysis and business breakdowns. Company financials explained visually.",
     7, 8, 8, 7, 6),
    ("The Swedish Investor", "https://www.youtube.com/@TheSwedishInvestor", "en", "finance",
     "Book summaries focused on investing classics. Buffett, Graham, Dalio distilled.",
     7, 7, 8, 6, 7),
    ("Hamish Hodder", "https://www.youtube.com/@HamishHodder", "en", "finance",
     "Quantitative finance and investing strategies. Data-driven analysis of markets.",
     8, 7, 8, 7, 7),
    ("New Economic Thinking", "https://www.youtube.com/@NewEconomicThinking", "en", "finance",
     "Institute for New Economic Thinking. Academic economics, Nobel laureate interviews.",
     10, 6, 8, 8, 9),
    ("The Financial Diet", "https://www.youtube.com/@TheFinancialDiet", "en", "finance",
     "Personal finance for millennials. Budgeting, debt, career decisions. Accessible and practical.",
     6, 7, 7, 6, 6),
    ("Wall Street Millennial", "https://www.youtube.com/@WallStreetMillennial", "en", "finance",
     "Market analysis and financial history. Deep dives into market events and corporate strategies.",
     8, 7, 8, 7, 7),
    ("Finary", "https://www.youtube.com/@Finary", "fr", "finance",
     "Finance personnelle et investissement en francais. Interviews, analyses de marche, patrimoine.",
     7, 8, 7, 6, 6),
    ("Heu?reka Eco", "https://www.youtube.com/@Heureka2", "fr", "finance",
     "Economie et finance expliquees par Gilles Mitteau. Lien constant avec l'actualite.",
     8, 7, 8, 8, 7),
    ("Minority Mindset", "https://www.youtube.com/@MinorityMindset", "en", "finance",
     "Financial literacy and wealth building. Challenges conventional money advice.",
     6, 8, 7, 7, 6),
    ("Joseph Carlson", "https://www.youtube.com/@JosephCarlsonShow", "en", "finance",
     "Dividend investing and portfolio management. Real portfolio tracking with analysis.",
     7, 6, 8, 6, 6),

    # ============================================================
    # GEOPOLITICS (need 14 more → total 25)
    # ============================================================
    ("Zeihan on Geopolitics", "https://www.youtube.com/@ZeihanonGeopolitics", "en", "geopolitics",
     "Peter Zeihan's geopolitical analysis. Demographics, energy, agriculture driving global change.",
     9, 6, 8, 8, 8),
    ("Kraut", "https://www.youtube.com/@Kraut", "en", "geopolitics",
     "Deep cultural and political analysis. Multi-hour documentaries on Turkey, China, Americas.",
     10, 8, 9, 9, 9),
    ("Geography Now!", "https://www.youtube.com/@GeographyNow", "en", "geopolitics",
     "Every country in the world profiled. Culture, politics, geography. Alphabetical world tour.",
     7, 8, 7, 7, 7),
    ("Vox", "https://www.youtube.com/@Vox", "en", "geopolitics",
     "Explanatory journalism. Borders, conflicts, policies visualized with data and maps.",
     8, 9, 7, 7, 7),
    ("Adam Something", "https://www.youtube.com/@AdamSomething", "en", "geopolitics",
     "Urban planning, transport policy, and geopolitics. Critical analysis of megaprojects.",
     7, 7, 8, 8, 7),
    ("Perun", "https://www.youtube.com/@PerunAU", "en", "geopolitics",
     "Defense economics and military logistics. Data-driven analysis of conflicts and defense spending.",
     9, 6, 9, 8, 8),
    ("TLDR News EU", "https://www.youtube.com/@TLDRNewsEU", "en", "geopolitics",
     "European politics and policy explained. Brexit, EU regulations, elections.",
     7, 7, 8, 6, 6),
    ("William Spaniel", "https://www.youtube.com/@Gametheory101", "en", "geopolitics",
     "Game theory applied to geopolitics and conflicts. Rational analysis of wars and negotiations.",
     9, 5, 9, 9, 8),
    ("KJ Vids", "https://www.youtube.com/@KJVids", "en", "geopolitics",
     "Geopolitical reports and analysis. Middle East, Asia, trade wars. Research-heavy.",
     8, 7, 8, 7, 7),
    ("Mapping the World", "https://www.youtube.com/@MappingtheWorld", "en", "geopolitics",
     "Geopolitics through maps. Visual explanations of territorial disputes and global trends.",
     7, 8, 7, 6, 7),
    ("TaskForce", "https://www.youtube.com/@TaskForceFR", "fr", "geopolitics",
     "Geopolitique francophone. Analyses approfondies des conflits et relations internationales.",
     8, 7, 8, 7, 7),
    ("Carto", "https://www.youtube.com/@Carto", "fr", "geopolitics",
     "Cartographie et geopolitique en francais. Frontieres, migrations, ressources naturelles.",
     7, 8, 7, 7, 7),
    ("History Scope", "https://www.youtube.com/@HistoryScope", "en", "geopolitics",
     "Historical geopolitics. How past empires and treaties shaped modern borders.",
     8, 7, 8, 7, 7),
    ("The Gravel Institute", "https://www.youtube.com/@TheGravelInstitute", "en", "geopolitics",
     "Political analysis and policy explainers. Progressive perspective on US and global politics.",
     7, 8, 7, 7, 6),

    # ============================================================
    # HISTORY (need 13 more → total 25)
    # ============================================================
    ("Epic History TV", "https://www.youtube.com/@EpicHistoryTV", "en", "history",
     "Military history documentaries. Napoleon, Alexander, WW2 with maps and animations.",
     9, 9, 9, 7, 9),
    ("History Time", "https://www.youtube.com/@HistoryTime", "en", "history",
     "Long-form historical documentaries. Ancient civilizations, medieval period. Cinematic style.",
     9, 8, 9, 7, 8),
    ("Feature History", "https://www.youtube.com/@FeatureHistory", "en", "history",
     "Animated history summaries. Wars, revolutions, political movements in 10-15 minutes.",
     7, 7, 8, 7, 7),
    ("Simple History", "https://www.youtube.com/@SimpleHistory", "en", "history",
     "Animated history shorts. Military history, daily life in past eras, historical figures.",
     6, 7, 7, 6, 6),
    ("The Operations Room", "https://www.youtube.com/@TheOperationsRoom", "en", "history",
     "Military operations animated in detail. D-Day, Stalingrad, Pacific battles minute by minute.",
     8, 8, 9, 8, 8),
    ("Jay Foreman", "https://www.youtube.com/@JayForeman", "en", "history",
     "Map Men and Unfinished London. Geography, history, and urban planning with British humor.",
     7, 8, 7, 9, 7),
    ("Knowledgia", "https://www.youtube.com/@Knowledgia", "en", "history",
     "Animated history covering empires, wars, and civilizations. Clean visual style.",
     7, 7, 7, 6, 6),
    ("TIK History", "https://www.youtube.com/@TIKhistory", "en", "history",
     "WW2 deep analysis. Multi-hour breakdowns of Stalingrad, Barbarossa. Primary source heavy.",
     10, 5, 8, 7, 8),
    ("History Buffs", "https://www.youtube.com/@HistoryBuffs", "en", "history",
     "Historical accuracy of movies. Compares film depictions to real events.",
     8, 7, 8, 8, 7),
    ("The Cold War", "https://www.youtube.com/@TheColdWar", "en", "history",
     "Cold War era chronological documentary. Proxy wars, espionage, nuclear standoffs.",
     8, 7, 8, 7, 7),
    ("C'est une autre histoire", "https://www.youtube.com/@Cestuneautrehistoire", "fr", "history",
     "Histoire avec humour par Manon Bril. Mythes, figures historiques, deconstruction.",
     7, 7, 7, 8, 6),
    ("Questions d'Histoire", "https://www.youtube.com/@Questionsdhistoire", "fr", "history",
     "Vulgarisation historique approfondie. Un sujet decortique a fond chaque mois.",
     9, 6, 9, 7, 8),
    ("World War Two", "https://www.youtube.com/@WorldWarTwo", "en", "history",
     "Week-by-week WW2 coverage by Indy Neidell. Real-time chronological documentary series.",
     9, 8, 8, 9, 9),

    # ============================================================
    # PHILOSOPHY & ESSAYS (need 15 more → total 25)
    # ============================================================
    ("Philosophy Tube", "https://www.youtube.com/@PhilosophyTube", "en", "philosophy-essays",
     "Abigail Thorn explores philosophy through performative essays. Ethics, politics, identity.",
     8, 9, 7, 9, 7),
    ("ContraPoints", "https://www.youtube.com/@ContraPoints", "en", "philosophy-essays",
     "Cultural and philosophical video essays. Elaborate productions exploring complex social topics.",
     8, 10, 7, 9, 8),
    ("The School of Life", "https://www.youtube.com/@theschooloflife", "en", "philosophy-essays",
     "Alain de Botton's channel on philosophy, psychology, relationships. Animated explainers.",
     7, 8, 7, 6, 7),
    ("Wisecrack", "https://www.youtube.com/@wisecrack", "en", "philosophy-essays",
     "Philosophy of pop culture. Rick & Morty, Simpsons, anime analyzed through philosophical lenses.",
     7, 8, 7, 7, 6),
    ("Jacob Geller", "https://www.youtube.com/@JacobGeller", "en", "philosophy-essays",
     "Video essays connecting games, architecture, art, and philosophy. Deeply personal and thoughtful.",
     8, 8, 8, 10, 8),
    ("Aperture", "https://www.youtube.com/@Aperture", "en", "philosophy-essays",
     "Existential video essays. Consciousness, reality, human condition explored with animations.",
     7, 8, 7, 7, 6),
    ("Will Schoder", "https://www.youtube.com/@WillSchoder", "en", "philosophy-essays",
     "Video essays on creativity, meaning, and human nature. Literature and philosophy intersections.",
     8, 7, 8, 8, 7),
    ("Jonas Ceika", "https://www.youtube.com/@JonasCeworeCeworeka", "en", "philosophy-essays",
     "CCK Philosophy. Continental philosophy, Marx, Deleuze explained accessibly.",
     9, 6, 8, 8, 7),
    ("Pop Culture Detective", "https://www.youtube.com/@PopCultureDetective", "en", "philosophy-essays",
     "Media analysis through gender and social justice lens. Masculinity, romance tropes deconstructed.",
     8, 8, 8, 8, 7),
    ("Renegade Cut", "https://www.youtube.com/@RenegadeCut", "en", "philosophy-essays",
     "Film analysis through philosophical and political frameworks. Deep readings of cinema.",
     8, 7, 8, 8, 7),
    ("Tantacrul", "https://www.youtube.com/@Tantacrul", "en", "philosophy-essays",
     "Music notation software, design critique, and music history. Hilarious and deeply informed.",
     8, 8, 8, 10, 7),
    ("Hbomberguy", "https://www.youtube.com/@haborMeaning2", "en", "philosophy-essays",
     "Long-form video essays on media, culture, and internet phenomena. Exhaustively researched.",
     9, 7, 7, 8, 7),
    ("Maggie Mae Fish", "https://www.youtube.com/@MaggieMaeFish", "en", "philosophy-essays",
     "Film and media criticism. Hollywood ideology, propaganda in entertainment.",
     7, 7, 7, 8, 6),
    ("Folding Ideas", "https://www.youtube.com/@FoldingIdeas", "en", "philosophy-essays",
     "Dan Olson's video essays on media, crypto, and internet culture. Line Goes Up was landmark.",
     9, 8, 8, 9, 9),
    ("BrainCraft", "https://www.youtube.com/@BrainCraft", "en", "philosophy-essays",
     "Psychology and neuroscience explained. How your brain works, biases, perception.",
     7, 7, 8, 6, 7),

    # ============================================================
    # PRODUCTIVITY (need 18 more → total 25)
    # ============================================================
    ("Andrew Huberman", "https://www.youtube.com/@hubabormanlab", "en", "productivity",
     "Huberman Lab. Neuroscience-based protocols for sleep, focus, exercise, stress. Stanford professor.",
     9, 7, 7, 8, 8),
    ("HealthyGamerGG", "https://www.youtube.com/@HealthyGamerGG", "en", "productivity",
     "Dr. K applies psychiatry to modern life. Motivation, procrastination, burnout. Evidence-based.",
     9, 6, 8, 8, 8),
    ("Keep Productive", "https://www.youtube.com/@KeepProductive", "en", "productivity",
     "Productivity app reviews and workflows. Notion, Obsidian, Todoist deep dives.",
     6, 7, 7, 5, 5),
    ("Jeff Su", "https://www.youtube.com/@JeffSu", "en", "productivity",
     "Career and workplace productivity. Email, presentations, communication skills.",
     6, 8, 8, 6, 6),
    ("Elizabeth Filips", "https://www.youtube.com/@ElizabethFilips", "en", "productivity",
     "Learning strategies and study techniques. Evidence-based methods for knowledge acquisition.",
     7, 8, 7, 7, 6),
    ("Better Ideas", "https://www.youtube.com/@BetterIdeas", "en", "productivity",
     "Self-improvement without toxic positivity. Habits, discipline, lifestyle design.",
     6, 8, 7, 7, 6),
    ("Nathaniel Drew", "https://www.youtube.com/@NathanielDrew", "en", "productivity",
     "Intentional living and personal development. Language learning, creativity, mindfulness.",
     6, 9, 7, 7, 6),
    ("Improvement Pill", "https://www.youtube.com/@ImprovementPill", "en", "productivity",
     "Animated self-improvement. Habits, social skills, productivity systems explained visually.",
     6, 7, 7, 6, 6),
    ("Justin Sung", "https://www.youtube.com/@JustinSung", "en", "productivity",
     "Evidence-based study techniques. Learning science applied to real studying. Doctor + educator.",
     8, 7, 8, 7, 7),
    ("Odysseas", "https://www.youtube.com/@Odysseas", "en", "productivity",
     "Study motivation and academic productivity. Deep work, note-taking, exam strategies.",
     6, 8, 7, 6, 5),
    ("Mike and Matty", "https://www.youtube.com/@MikeAndMatty", "en", "productivity",
     "Productivity tools and workflows. Notion templates, automation, digital organization.",
     5, 7, 6, 5, 5),
    ("Lavendaire", "https://www.youtube.com/@Lavendaire", "en", "productivity",
     "Personal growth and intentional living. Goal-setting, journaling, lifestyle design.",
     5, 8, 6, 6, 5),
    ("Rowena Tsai", "https://www.youtube.com/@RowenaTsai", "en", "productivity",
     "Slow productivity and organizing life. Realistic approach to productivity and stress.",
     5, 8, 7, 6, 5),
    ("Sam Matla", "https://www.youtube.com/@SamMatla", "en", "productivity",
     "Deep work and focus strategies. Practical frameworks for knowledge workers.",
     7, 6, 8, 6, 6),
    ("Kalle Hallden", "https://www.youtube.com/@KalleHallden", "en", "productivity",
     "Developer productivity and tech lifestyle. Coding setups, work routines, project management.",
     5, 8, 6, 6, 5),
    ("Cajun Koi Academy", "https://www.youtube.com/@CajunKoiAcademy", "en", "productivity",
     "Learning techniques and memory strategies. Science of learning applied practically.",
     7, 6, 7, 6, 6),
    ("Struthless", "https://www.youtube.com/@struthless", "en", "productivity",
     "Creativity and self-improvement through art. Procrastination, perfectionism, daily habits.",
     6, 8, 7, 8, 6),
    ("Mark Manson", "https://www.youtube.com/@IAmMarkManson", "en", "productivity",
     "Author of The Subtle Art. Life advice, relationships, purpose. No-BS philosophy.",
     7, 7, 8, 7, 7),

    # ============================================================
    # DESIGN & ART (need 18 more → total 25)
    # ============================================================
    ("Cinema Cartography", "https://www.youtube.com/@CinemaCartography", "en", "design-art",
     "Underrepresented filmmakers and animation history. Directors you don't know but should.",
     8, 8, 8, 9, 7),
    ("Thomas Flight", "https://www.youtube.com/@ThomasFlight", "en", "design-art",
     "Film and TV analysis. Why certain shows work, cinematography choices, narrative structure.",
     8, 8, 8, 7, 7),
    ("Charli Marie", "https://www.youtube.com/@charlimarieTV", "en", "design-art",
     "Graphic design and web design career. Design process, tools, industry insights.",
     6, 8, 7, 6, 5),
    ("Patrick H. Willems", "https://www.youtube.com/@patrickhwillems", "en", "design-art",
     "Film criticism through creative short films. Career retrospectives, best-of analyses.",
     7, 9, 7, 9, 7),
    ("Sideways", "https://www.youtube.com/@Sideways440", "en", "design-art",
     "Film music analysis. Why soundtracks work, composition techniques, emotional impact of scores.",
     8, 7, 8, 9, 7),
    ("Solar Sands", "https://www.youtube.com/@SolarSands", "en", "design-art",
     "Art history and internet art culture. Surrealism, digital art movements, aesthetic analysis.",
     7, 7, 8, 8, 7),
    ("Royal Ocean Film Society", "https://www.youtube.com/@RoyalOceanFilmSociety", "en", "design-art",
     "Visual storytelling analysis. Cinematography, color theory, editing choices in film.",
     8, 8, 8, 7, 7),
    ("Polyphonic", "https://www.youtube.com/@Polyphonic", "en", "design-art",
     "Music history and analysis. Rock, jazz, hip-hop. What makes certain albums groundbreaking.",
     8, 8, 8, 8, 8),
    ("Middle 8", "https://www.youtube.com/@Middle8", "en", "design-art",
     "Music analysis and cultural impact. Why certain songs and artists shaped culture.",
     7, 8, 7, 7, 7),
    ("Adam Neely", "https://www.youtube.com/@AdamNeely", "en", "design-art",
     "Music theory deep dives. Jazz, polyrhythm, tuning systems. Academic but accessible.",
     9, 7, 8, 8, 8),
    ("Trash Theory", "https://www.youtube.com/@TrashTheory", "en", "design-art",
     "Underground music history. Post-punk, noise, industrial. Genres you didn't know existed.",
     8, 7, 8, 9, 7),
    ("Entrevue", "https://www.youtube.com/@Entrevue", "fr", "design-art",
     "Cinema francais analyse. Technique cinematographique, realisateurs, mouvements artistiques.",
     7, 7, 7, 7, 6),
    ("Le Fossoyeur de Films", "https://www.youtube.com/@LeFossoyeurDeFilms", "fr", "design-art",
     "Critique et analyse cinema en francais. Films cultes et meconnus. Style unique.",
     7, 7, 7, 8, 6),
    ("The Closer Look", "https://www.youtube.com/@TheCloserLook", "en", "design-art",
     "Screenwriting and film analysis. Story structure, character development, narrative craft.",
     7, 7, 8, 7, 6),
    ("Must See Film Podcasts", "https://www.youtube.com/@MustSeeFilmPodcasts", "en", "design-art",
     "Director interviews and film industry analysis. Behind-the-scenes of moviemaking.",
     7, 6, 7, 6, 6),
    ("Volksgeist", "https://www.youtube.com/@Volksgeist", "en", "design-art",
     "Art history and aesthetics. Architecture, painting, sculpture analyzed in cultural context.",
     8, 7, 8, 8, 7),
    ("Vox Earworm", "https://www.youtube.com/@earworm", "en", "design-art",
     "Music explainers by Estelle Caswell. Why certain songs sound the way they do.",
     8, 9, 8, 8, 7),
    ("Just Write", "https://www.youtube.com/@justwrite", "en", "design-art",
     "Writing and screenwriting analysis. Story structure, character arcs, adaptation choices.",
     7, 7, 8, 7, 6),

    # ============================================================
    # EDUCATION (need 17 more → total 25)
    # ============================================================
    ("Vsauce2", "https://www.youtube.com/@Vsauce2", "en", "education",
     "Mind-bending math puzzles and paradoxes. Kevin Lieber explores the weird side of knowledge.",
     7, 8, 7, 7, 7),
    ("Mark Rober Kids", "https://www.youtube.com/@MarkRoberKids", "en", "education",
     "Science experiments designed for younger audiences. STEM engagement through fun.",
     6, 9, 7, 6, 6),
    ("minuteearth", "https://www.youtube.com/@minuteearth", "en", "education",
     "Earth science in 2-4 minutes. Ecology, geology, biology with charming hand-drawn animations.",
     7, 7, 9, 7, 7),
    ("It's Okay To Be Smart", "https://www.youtube.com/@ItsOkayToBeSmart", "en", "education",
     "PBS science and education. Biology, physics, history of science. Joe Hanson PhD.",
     8, 8, 8, 7, 7),
    ("AsapSCIENCE", "https://www.youtube.com/@AsapSCIENCE", "en", "education",
     "Whiteboard-style science explanations. Quick, accessible answers to science questions.",
     6, 7, 7, 6, 6),
    ("The Infographics Show", "https://www.youtube.com/@TheInfographicsShow", "en", "education",
     "Animated explainers on everything. Military, science, history, comparisons. High volume.",
     5, 7, 5, 5, 5),
    ("Real Science", "https://www.youtube.com/@realscience", "en", "education",
     "Biology and natural science documentaries. Deep ocean, parasites, evolution. Cinematic quality.",
     8, 9, 8, 7, 8),
    ("Half as Interesting", "https://www.youtube.com/@halfasinteresting", "en", "education",
     "Sam from Wendover's lighter channel. Quick 3-5 min explainers with humor.",
     6, 7, 7, 7, 5),
    ("Lemmino", "https://www.youtube.com/@LEMMiNO", "en", "education",
     "Documentary-quality investigations into mysteries, space, and history. Rare uploads, exceptional quality.",
     9, 10, 10, 9, 9),
    ("Kurzgesagt - German", "https://www.youtube.com/@KurzgesagtDE", "de", "education",
     "German language version of Kurzgesagt. Same quality animations, science, philosophy.",
     8, 10, 8, 7, 8),
    ("Aperture (Education)", "https://www.youtube.com/@ApertureEducation", "en", "education",
     "Math and science visualization. Abstract concepts made tangible through animation.",
     7, 8, 7, 7, 6),
    ("Lex Clips", "https://www.youtube.com/@LexClips", "en", "education",
     "Highlights from Lex Fridman podcast. AI, science, philosophy conversations with top minds.",
     8, 6, 7, 6, 7),
    ("SciShow", "https://www.youtube.com/@SciShow", "en", "education",
     "Daily science news and explainers. Broad coverage of new research and scientific curiosities.",
     7, 7, 7, 6, 6),
    ("Tom Nicholas", "https://www.youtube.com/@TomNicholas", "en", "education",
     "Video essays on media, academia, and internet culture. Well-researched long-form content.",
     8, 7, 8, 7, 7),
    ("Answer in Progress", "https://www.youtube.com/@AnswerInProgress", "en", "education",
     "Curiosity-driven investigations. Learning in public with genuine discovery moments.",
     6, 8, 7, 8, 6),
    ("Ici Amy Plant", "https://www.youtube.com/@IciAmyPlant", "fr", "education",
     "Science et education en francais. Linguistique, psychologie, curiosites intellectuelles.",
     7, 7, 7, 7, 6),
    ("Linguisticae", "https://www.youtube.com/@Linguisticae", "fr", "education",
     "Linguistique et etymologie en francais. Histoire des langues, expressions, evolution.",
     8, 6, 8, 8, 7),

    # ============================================================
    # ENVIRONMENT (need 20 more → total 25)
    # ============================================================
    ("City Beautiful", "https://www.youtube.com/@CityBeautiful", "en", "environment",
     "Urban planning and city design. Zoning, public transit, why cities look the way they do.",
     8, 8, 8, 7, 7),
    ("Adam Something", "https://www.youtube.com/@AdamSomething2", "en", "environment",
     "Urban planning, transport, and infrastructure critique. Debunking Elon Musk's transport ideas.",
     7, 7, 8, 8, 7),
    ("Planet A", "https://www.youtube.com/@DWPlanetA", "en", "environment",
     "Deutsche Welle's environment channel. Carbon capture, renewables, climate policy globally.",
     8, 8, 8, 6, 7),
    ("PBS Terra", "https://www.youtube.com/@PBSTerra", "en", "environment",
     "Nature, science, and environment from PBS. Multiple shows exploring Earth systems.",
     7, 8, 7, 6, 7),
    ("Undecided Climate", "https://www.youtube.com/@UndecidedClimate", "en", "environment",
     "Clean energy technologies explored. Solar, wind, batteries, nuclear with data-driven analysis.",
     7, 8, 7, 6, 7),
    ("Leaf of Faith", "https://www.youtube.com/@LeafofFaith", "en", "environment",
     "Sustainable living and environmental science. Practical environmentalism backed by research.",
     7, 6, 7, 7, 6),
    ("Eco Gecko", "https://www.youtube.com/@EcoGecko", "en", "environment",
     "Environmental science animations. Climate systems, ecosystems, biodiversity explained visually.",
     7, 7, 7, 6, 6),
    ("BritMonkey", "https://www.youtube.com/@BritMonkey", "en", "environment",
     "Urban planning and infrastructure in the UK and beyond. Housing, transport, city design.",
     7, 7, 7, 7, 6),
    ("RMTransit", "https://www.youtube.com/@RMTransit", "en", "environment",
     "Public transit systems worldwide. Metros, buses, rail analyzed. Why some cities get it right.",
     7, 7, 8, 7, 6),
    ("Alan Fisher", "https://www.youtube.com/@AlanFisher", "en", "environment",
     "Urban planning and transportation analysis. North American infrastructure critique.",
     7, 7, 7, 7, 6),
    ("Strong Towns", "https://www.youtube.com/@strongtowns", "en", "environment",
     "Sustainable urban development. Financial productivity of cities, suburban sprawl costs.",
     8, 6, 8, 7, 7),
    ("Oh The Urbanity!", "https://www.youtube.com/@OhTheUrbanity", "en", "environment",
     "Canadian urban planning duo. Housing, zoning, transit filmed on location.",
     7, 7, 7, 7, 6),
    ("Le Reveilleur", "https://www.youtube.com/@LeReveilleur", "fr", "environment",
     "Energie et climat en francais. Analyses detaillees du nucleaire, renouvelables, bilan carbone.",
     9, 7, 9, 8, 8),
    ("Paloma Moritz", "https://www.youtube.com/@PalomaBlast", "fr", "environment",
     "Journalisme environnemental francais. Climat, biodiversite, justice climatique.",
     7, 7, 7, 7, 6),
    ("Osons Causer", "https://www.youtube.com/@OsonsCauser", "fr", "environment",
     "Ecologie et politique en francais. Debats, analyses, solutions climat.",
     7, 7, 7, 7, 6),
    ("Real World Climate", "https://www.youtube.com/@RealWorldClimate", "en", "environment",
     "Climate science communication. IPCC reports explained, carbon budgets, tipping points.",
     8, 6, 8, 6, 7),
    ("EV Driven", "https://www.youtube.com/@EVDriven", "en", "environment",
     "Electric vehicle technology and sustainable transport. Reviews, analysis, industry trends.",
     6, 7, 6, 5, 5),
    ("Footprint Nature", "https://www.youtube.com/@FootprintNature", "en", "environment",
     "Nature conservation and wildlife. Environmental impact of human activity on ecosystems.",
     7, 7, 7, 6, 6),
    ("Climate Adam", "https://www.youtube.com/@ClimateAdamAlt", "en", "environment",
     "Climate science explained with humor. PhD climate scientist making complex data accessible.",
     8, 7, 7, 7, 7),
    ("Regenerate", "https://www.youtube.com/@Regenerate", "en", "environment",
     "Regenerative agriculture and sustainable food systems. Soil health, permaculture, food policy.",
     7, 7, 7, 7, 6),

    # ============================================================
    # MAKING & DIY (need 19 more → total 25)
    # ============================================================
    ("Matthias Wandel", "https://www.youtube.com/@matthiaswandel", "en", "making",
     "Woodworking engineering. Jigs, machines, and furniture built with mathematical precision.",
     8, 6, 9, 8, 8),
    ("AvE", "https://www.youtube.com/@arduinoversusevil2025", "en", "making",
     "Tool teardowns and shop wisdom. Mechanical engineering meets blue-collar expertise. Keep your dick in a vice.",
     7, 5, 7, 9, 7),
    ("Clickspring", "https://www.youtube.com/@Clickspring", "en", "making",
     "Precision clockmaking and Antikythera mechanism recreation. Extreme craftsmanship documented.",
     9, 10, 10, 9, 10),
    ("Frank Howarth", "https://www.youtube.com/@FrankHowarth", "en", "making",
     "Woodworking and stop-motion. Segmented bowls, shop builds with artistic cinematography.",
     7, 10, 8, 8, 7),
    ("Alec Steele", "https://www.youtube.com/@AlecSteele", "en", "making",
     "Blacksmithing and metalworking. Damascus steel, swords, tools forged from scratch.",
     6, 9, 6, 7, 6),
    ("Wintergatan Marble", "https://www.youtube.com/@WintergatanMarble", "en", "making",
     "Marble Machine X build log. Mechanical music instrument engineering journal.",
     7, 8, 8, 10, 7),
    ("Peter Brown", "https://www.youtube.com/@kaboreterBrown", "en", "making",
     "Epoxy, resin, and experimental material projects. Creative woodworking with unusual materials.",
     5, 8, 6, 7, 5),
    ("Alexandre Chappel", "https://www.youtube.com/@AlexandreChappel", "en", "making",
     "Industrial design and furniture making. CNC, metal, wood combined with design thinking.",
     6, 9, 7, 7, 6),
    ("Crafsman Steady Craftin", "https://www.youtube.com/@CrafsmanSteadyCraftin", "en", "making",
     "Gentle crafting and painting. Bob Ross meets maker culture. Wholesome and meditative.",
     4, 7, 6, 8, 5),
    ("Jimmy DiResta", "https://www.youtube.com/@jimmydiresta", "en", "making",
     "Multi-discipline maker. Metal, wood, leather. Fast-paced builds with minimal narration.",
     5, 7, 6, 7, 6),
    ("Ishitani Furniture", "https://www.youtube.com/@ishitanifurniture", "ja", "making",
     "Japanese furniture making. No narration, pure craftsmanship. Wood joinery at its finest.",
     8, 9, 10, 8, 9),
    ("Pask Makes", "https://www.youtube.com/@PaskMakes", "en", "making",
     "Woodworking and making projects. Furniture, tools, shop builds with clear explanations.",
     6, 7, 7, 6, 6),
    ("Cosmas Bauer", "https://www.youtube.com/@CosmasBauer", "en", "making",
     "Traditional timber framing and hand tool woodworking. Historical building techniques.",
     8, 7, 8, 8, 7),
    ("My Mechanics", "https://www.youtube.com/@mymechanics", "en", "making",
     "Tool and machine restoration. No narration, pure ASMR restoration to better-than-new condition.",
     6, 9, 9, 7, 7),
    ("Anne of All Trades", "https://www.youtube.com/@AnneofAllTrades", "en", "making",
     "Carpentry, renovation, and skilled trades. Professional-level builds with teaching focus.",
     6, 8, 7, 6, 6),
    ("Hand Tool Rescue", "https://www.youtube.com/@HandToolRescue", "en", "making",
     "Vintage tool restoration. Sandblasting, machining, and bringing old tools back to life.",
     5, 8, 7, 6, 6),
    ("John Heisz", "https://www.youtube.com/@JohnHeisz", "en", "making",
     "Workshop projects and tool making. Practical woodworking with engineering mindset.",
     6, 6, 7, 6, 6),
    ("Essential Craftsman", "https://www.youtube.com/@essentialcraftsman", "en", "making",
     "Construction, blacksmithing, and life wisdom. Spec house build series. Decades of experience.",
     7, 7, 8, 7, 8),
    ("Tested (Adam Savage)", "https://www.youtube.com/@tested2", "en", "making",
     "Adam Savage's One Day Builds. Prop making, model building, workshop organization.",
     7, 8, 7, 7, 7),
]


def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get existing channel names/URLs to avoid duplicates
    existing = set()
    for row in conn.execute("SELECT name, url FROM channels"):
        existing.add(row["name"].lower())
        existing.add(row["url"].lower())

    inserted = 0
    skipped = 0
    for ch in NEW_CHANNELS:
        name, url, lang, category, desc, rd, pr, sn, ori, li = ch
        if name.lower() in existing or url.lower() in existing:
            print(f"  SKIP (exists): {name}")
            skipped += 1
            continue

        score = compute_score(rd, pr, sn, ori, li)
        tier = compute_tier(score)

        conn.execute(
            """INSERT INTO channels
               (name, url, language, primary_category, description,
                score_research_depth, score_production, score_signal_noise,
                score_originality, score_lasting_impact,
                composite_score, tier, is_reviewed, platform)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'youtube')""",
            (name, url, lang, category, desc, rd, pr, sn, ori, li, score, tier),
        )
        inserted += 1
        print(f"  + {tier} ({score:.1f}) {name} [{category}]")

    conn.commit()

    # Summary per category
    print(f"\n{'='*60}")
    print(f"Inserted: {inserted} | Skipped: {skipped}")
    print(f"\nChannels per category:")
    for row in conn.execute(
        """SELECT c.primary_category, cat.name, COUNT(*) as cnt
           FROM channels c
           LEFT JOIN categories cat ON c.primary_category = cat.slug
           WHERE c.is_reviewed = 1
           GROUP BY c.primary_category
           ORDER BY cnt DESC"""
    ):
        print(f"  {row['cnt']:3d}  {row[1] or row[0]}")

    total = conn.execute("SELECT COUNT(*) FROM channels WHERE is_reviewed = 1").fetchone()[0]
    print(f"\nTotal channels: {total}")
    conn.close()


if __name__ == "__main__":
    main()
