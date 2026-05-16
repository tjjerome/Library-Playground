"""
Controlled vocabularies for the librarian catalog.

Three structures live here:

* `CANONICAL_TASTE_SIGNALS` — public-reception signal IDs the cataloguer
  emits as the per-book `taste_signals` field. Closed vocabulary: the
  cataloguer must pick from this list and never invent new IDs. The
  recommender uses these IDs for cross-book overlap.

* `CANONICAL_THEMES` — concrete recurring concerns of texts. Same
  closed-vocabulary contract.

* `CANONICAL_TASTE_VECTORS` — cross-cutting taste shapes (a bundle of
  signals + themes that together name a recognisable kind of reading
  experience).  Books are tagged with the vectors they exemplify at
  SQLite-export time via `book_taste_vector_matches()` below; the tag
  set is stored in the `book_taste_vectors` table.  Tagging is sparse
  (most books exemplify 2-4 vectors) and is the substrate for the
  recommender's vector-spread sampling and `status`'s vector-coverage
  query (RECOMPOSITION_PLAN.md §3, §4, §6.4).

Each list is a dict mapping a kebab-case ID to a short description shown
to the cataloguer model. The IDs are stable and grow only via deliberate
additions in this file, with a follow-up `--canonicalize-signals` /
`--canonicalize-themes` migration to remap existing entries.

Vocabulary growth was driven by an analysis of the live catalog's
free-form taste_signals/themes columns: the buckets below cover both
the obvious clusters in a fiction library and the recurring nonfiction
forms (memoir, popular science, anthology, tie-in fiction) that the
seed list missed.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Taste signals — what readers respond to in a book
# ---------------------------------------------------------------------------
#
# Organised into rough buckets for the cataloguer to scan. Bucket boundaries
# are not encoded — any signal can be paired with any other.

CANONICAL_TASTE_SIGNALS: dict[str, str] = {
    # Prose & voice
    "lyrical-prose":              "lyrical, image-rich prose; sentence-level beauty",
    "spare-prose":                "spare, stripped-down prose; sentence-level economy",
    "muscular-prose":             "muscular, propulsive prose; momentum from the sentences themselves",
    "ornate-prose":               "ornate, baroque prose; deliberately dense and decorative",
    "experimental-prose":         "formally experimental prose; nonstandard grammar, layout, or structure",
    "witty-prose":                "witty prose; sharp dialogue; cleverness on the page",
    "first-person-voice":         "distinctive first-person voice carries the book",
    "unreliable-narrator":        "narrator's account is unreliable or contested",
    "epistolary-format":          "told via letters, documents, transcripts, or found texts",
    "second-person-voice":        "second-person 'you' narration",

    # Pacing & momentum
    "propulsive-pacing":          "fast, page-turning momentum",
    "slow-burn":                  "deliberate slow build with eventual payoff",
    "meditative-pacing":          "unhurried, contemplative pacing",
    "episodic-structure":         "loosely-connected episodes rather than a single arc",
    "braided-narrative":          "multiple braided POVs or timelines",
    "single-pov":                 "single, sustained POV throughout",
    "nonlinear-timeline":         "deliberately nonlinear chronology",

    # Character work
    "morally-grey-protagonist":   "protagonist morally compromised, neither hero nor villain",
    "ensemble-cast":              "large ensemble cast; no single protagonist",
    "found-family":               "found-family bond at the emotional core",
    "intimate-pov":               "tight, interior, emotionally intimate POV",
    "deep-character-study":       "interior life of a single character (small cast) is the point",
    "character-growth":           "characters grow / change across the book; arc-driven (broader than deep-character-study)",
    "anti-hero":                  "anti-hero or villain protagonist",
    "competence-porn":            "characters who are extraordinarily good at what they do",
    "ordinary-protagonist":       "ordinary person in extraordinary circumstances",
    "female-led-cast":            "female protagonist or strong female ensemble; feminist framing",
    "diverse-cast":               "racially / culturally / queer-diverse cast as a meaningful texture",
    "anthropomorphic-animals":    "animal characters with human cognition / personality",

    # Emotional register
    "humor-with-stakes":          "humor that doesn't undercut serious stakes",
    "darkly-comic":               "darkly comic register; gallows humor",
    "light-tone":                 "light, breezy tone; low-stress register",
    "warm-hopeful":               "warm, hopeful emotional register",
    "melancholy":                 "melancholy or wistful register",
    "grim-bleak":                 "grim, bleak register; little reprieve",
    "cathartic-tragedy":          "tragedy with cathartic emotional payoff",
    "feel-good":                  "feel-good register; comfort read",
    "uneasy-dread":               "register of uneasy, accumulating dread",
    "cosmic-awe":                 "register of cosmic scale or awe",
    "emotional-depth":            "emotionally resonant; sustained emotional weight (not tied to a single character)",
    "philosophical-depth":        "the book itself engages substantively with ideas / questions",

    # Plot shape
    "twisty-plot":                "twisty plot with major reveals or reversals",
    "puzzle-plot":                "puzzle-box plot the reader is invited to solve",
    "high-concept-premise":       "high-concept premise the book is built around",
    "quiet-domestic":             "quiet, domestic-scale stakes",
    "world-shattering-stakes":    "world- or universe-shattering stakes",
    "heist-structure":            "heist or caper structure",
    "quest-structure":            "quest or journey structure",
    "court-intrigue":             "court intrigue, politics, faction maneuvering",
    "war-narrative":              "war or military campaign at the centre",
    "investigation-driven":       "driven by investigation, mystery, or detection",
    "survival-narrative":         "survival narrative; isolation, scarcity, hostile environment",
    "revenge-narrative":          "revenge plot drives the action",
    "monster-hunting":            "monster-hunting / creature-of-the-week structure",
    "series-payoff":              "delivers payoff for prior series investment (epic conclusion / mid-arc resolution)",

    # World & setting
    "richly-built-world":         "world-building is a core attraction (general)",
    "intricate-magic-system":     "magic system itself is a core attraction (rules, mechanics, costs)",
    "atmospheric-setting":        "atmosphere of place is a core attraction",
    "claustrophobic-setting":     "claustrophobic, confined setting",
    "expansive-setting":          "sweeping, geographically expansive setting",
    "alien-setting":              "genuinely alien or non-human setting",
    "historical-immersion":       "deeply researched historical immersion (period detail)",
    "well-researched":            "deeply researched outside the historical bucket (science, craft, profession)",
    "secondary-world-fantasy":    "wholly secondary fantasy world",
    "mythology-folklore":         "mythology / folklore source material is a core attraction",

    # Subgenre flavours — fiction
    "romance-heavy":              "romance is a primary plot engine",
    "romance-subplot":            "romance is a meaningful subplot but not the engine",
    "no-romance":                 "deliberately no romance",
    "horror-elements":            "horror or dread is a meaningful component",
    "cosmic-horror":              "cosmic horror; vast indifferent forces beyond comprehension",
    "southern-gothic":            "southern gothic register",
    "cozy-register":              "cozy register; gentle stakes, warm setting",
    "noir-register":              "noir register; cynicism, moral ambiguity, urban shadow",
    "grimdark":                   "grimdark; moral darkness pushed to extreme",
    "hopepunk":                   "hopepunk; fighting for kindness in a hostile world",
    "literary-genre-blur":        "literary fiction blurring with genre conventions",
    "magical-realism":            "magical realism register",
    "weird-fiction":              "weird fiction; reality askew",
    "hard-sf":                    "hard SF; rigour about scientific premises",
    "soft-sf":                    "soft SF; SF as setting for character / political work",
    "space-opera":                "space opera scope and register",
    "urban-fantasy":              "contemporary urban fantasy register",
    "progression-fantasy":        "progression fantasy / cultivation; protagonist power escalation as a core hook",
    "dark-academia":              "dark academia register",
    "swashbuckling":              "swashbuckling adventure register",
    "legal-procedural":           "legal thriller / courtroom drama / legal procedural",
    "conspiracy-thriller":        "conspiracy thriller register",
    "alternate-history-fiction":  "alternate history as fiction premise",
    "time-travel-fiction":        "time travel as fiction premise",

    # Subgenre flavours — nonfiction
    "popular-science":            "popular science writing for general readers",
    "narrative-nonfiction":       "narrative nonfiction; story-shaped nonfiction",
    "essayistic-form":            "essay collection or essayistic register",
    "memoir-form":                "memoir / personal narrative",
    "case-study-form":            "case-study structure (medical, scientific, anecdotal)",
    "biography-form":             "biographical writing",
    "tech-criticism":             "tech criticism; sceptical engagement with technology",
    "political-writing":          "political / social-issue writing; advocacy nonfiction",
    "craft-and-making":           "craft, making, DIY, vocation as the subject",
    "data-analytics":             "data, analytics, quantitative methods as the subject",
    "true-crime":                 "true crime as the subject",
    "travel-narrative":           "travel writing / travel narrative",
    "food-and-drink-culture":     "food and drink culture as the subject",
    "historical-witness":         "first-hand historical witness; primary-source memoir",

    # Form
    "short-fiction-form":         "short story collection or novella(s); short-fiction form is the shape",
    "anthology-form":             "multi-author anthology; sampler shape",
    "tie-in-fiction":             "media tie-in / shared-universe / novelization / bridge novel",
    "award-recognised":           "broadly award-recognised (Pulitzer, Hugo, Nebula, Booker, SPFBO finalist, etc.)",

    # Reader experience
    "rewards-careful-reading":    "rewards close reading; layered text",
    "high-density":               "high information density per page",
    "demanding-prose":            "demands sustained attention from the reader",
    "accessible-prose":           "accessible, easy-on-ramp prose",
    "discussion-rich":            "rich material for discussion or book-club use",
    "comfort-reread":             "rewards rereading as comfort",

    # Common negative-bucket signals
    "pacing-issues":              "frequently noted pacing issues",
    "info-dumps":                 "extended exposition / info-dumps",
    "flat-characters":            "underdeveloped or flat secondary characters",
    "tonal-whiplash":             "tonal whiplash between registers",
    "unearned-resolution":        "resolution feels unearned by the setup",
    "ambiguous-ending":           "deliberately ambiguous or abrupt ending (note: not always negative — operator's call by polarity)",
    "didactic-register":          "didactic register; tells rather than shows",
    "gratuitous-darkness":        "darkness presented gratuitously rather than purposefully",
    "disturbing-content":         "disturbing or graphic content (use only when the texture itself is the signal — content_flags is for factual content presence)",
    "thin-worldbuilding":         "thin or under-imagined worldbuilding",
    "excessive-length":           "structurally bloated; pages without payoff",
    "convenient-coincidence":     "plot leans on convenient coincidence",
    "underdeveloped-romance":     "romance present but underdeveloped",
    "pedestrian-prose":           "prose competent but unmemorable",
    "formulaic-structure":        "formulaic / predictable plot structure",
    "dated-attitudes":            "dated gender / racial / social attitudes (texture, not content_flag)",
}


# ---------------------------------------------------------------------------
# Themes — concrete recurring concerns of the text
# ---------------------------------------------------------------------------

CANONICAL_THEMES: dict[str, str] = {
    "grief-and-loss":             "grief, mourning, the weight of loss",
    "trauma-and-recovery":        "trauma and the long work of recovery",
    "found-family":               "chosen / found family bonds",
    "blood-family":               "biological family, inheritance, lineage",
    "coming-of-age":              "growing up; identity formation in adolescence",
    "midlife-reckoning":          "midlife reckoning; choices and their costs",
    "ageing-and-mortality":       "ageing and mortality",
    "marriage-and-partnership":   "marriage, long partnership, intimate negotiation",
    "parenthood":                 "parenthood; the work and cost of raising children",
    "friendship":                 "deep friendship as a load-bearing relationship",
    "community":                  "community, neighborhood, the larger social fabric beyond friendship/family",
    "loneliness-and-isolation":   "loneliness, isolation, monastic withdrawal",
    "love-and-desire":            "romantic love and desire",
    "queer-identity":             "queer identity, queer relationship, queer community",
    "race-and-belonging":         "race, ethnicity, belonging across borders",
    "class-and-poverty":          "class, poverty, economic precarity",
    "labour-and-craft":           "labour, craft, vocation; what work means",
    "power-and-authority":        "power, authority, hierarchy",
    "tyranny-and-resistance":     "tyranny and organised resistance",
    "war-and-its-aftermath":      "war and its aftermath; what war does to people",
    "violence-and-its-cost":      "violence and what it costs the people who use it",
    "justice-and-revenge":        "justice, revenge, the line between them",
    "redemption":                 "redemption arc; earning it or failing to",
    "guilt-and-atonement":        "guilt, atonement, living with what you've done",
    "faith-and-doubt":            "religious faith, doubt, deconstruction",
    "morality-in-extremis":       "morality stress-tested in extreme circumstances",
    "courage-and-heroism":        "courage, heroism, sacrifice; the cost of standing up",
    "ambition-and-hubris":        "ambition, hubris, reach exceeding grasp",
    "obsession":                  "obsession; one fixed idea consuming a life",
    "transformation":             "transformation; becoming a different person / thing",
    "fate-and-destiny":           "fate, destiny, prophecy, predestination vs. free will",
    "identity-and-self":          "identity, selfhood, who one is",
    "memory-and-the-past":        "memory and the past's grip on the present",
    "secrets-and-lies":           "secrets, lies, the slow leak of truth",
    "alienation":                 "alienation; not fitting where one is supposed to fit",
    "addiction":                  "addiction and dependency",
    "mental-illness":             "mental illness; psychiatry; mind under strain",
    "abuse":                      "abuse, including childhood, domestic, institutional",
    "exile-and-displacement":     "exile, refugee experience, displacement",
    "immigration":                "immigration, diaspora, generational distance",
    "colonialism":                "colonialism, occupation, the long shadow of empire",
    "environmental-collapse":     "environmental collapse, ecological loss, climate",
    "technology-and-humanity":    "technology and what it does to being human",
    "ai-and-consciousness":       "AI, machine consciousness, the question of personhood",
    "first-contact":              "first contact; encountering the genuinely Other",
    "exploration-and-discovery":  "exploration, discovery, the frontier",
    "civilisation-and-collapse":  "civilisation, its building, its collapse",
    "magic-and-its-cost":         "magic and the cost of using it (incl. magic-systems-as-theme)",
    "monsters-and-the-uncanny":   "monsters, the uncanny, what lurks at the edges",
    "creativity-and-art":         "art, creativity, what it costs to make things",
    "knowledge-and-its-limits":   "knowledge, learning, the limits of knowing",
    "language-and-translation":   "language, translation, the gap between tongues",
    "money-and-greed":            "money, greed, accumulation",
    "loyalty-and-betrayal":       "loyalty and betrayal; the people who stay and the people who don't",
    "duty-and-honor":             "duty, honor, the cost of keeping vows",
    "freedom-and-constraint":     "freedom, constraint, lives lived inside cages",
    "home-and-belonging":         "home, the search for it, the loss of it",
    "survival":                   "survival as a sustained concern (resilience, scarcity, perseverance)",
    "espionage":                  "espionage, intelligence work, double-dealing",
    "crime-and-investigation":    "crime as a recurring concern; the work of investigation",
    "science-and-nature":         "scientific discovery / natural history / ecology as the book's substance",
    "alternate-history-theme":    "what-if history as the book's substance",
    "time-travel-theme":          "time travel as the book's substance / preoccupation",
}


# ---------------------------------------------------------------------------
# Taste vectors — cross-cutting reader-taste shapes (RECOMPOSITION_PLAN §6.4)
# ---------------------------------------------------------------------------
#
# Each vector is a curated bundle of canonical signal IDs + canonical theme
# IDs that together describe one recognisable kind of reading experience.
# Vectors are catalog-level (not per-reader); per-reader profile vectors
# (RECOMPOSITION_PLAN §3) project these onto the reader's log.
#
# The membership rule is a fixed overlap threshold — a book exemplifies a
# vector when at least `TASTE_VECTOR_MATCH_THRESHOLD` of its positive
# signals + themes appear in the vector's member set.  The threshold is
# tuned to keep tagging sparse (most books match 2-4 vectors); see
# `book_taste_vector_matches()` below.
#
# Schema per entry:
#   "label":       short reader-readable label
#   "description": one-line gloss for prompts / introspection
#   "signals":     list of CANONICAL_TASTE_SIGNALS keys
#   "themes":      list of CANONICAL_THEMES keys

CANONICAL_TASTE_VECTORS: dict[str, dict] = {
    "lyrical-literary": {
        "label": "Lyrical literary",
        "description": "prose itself as the attraction; layered, demanding, image-rich",
        "signals": [
            "lyrical-prose", "ornate-prose", "philosophical-depth",
            "rewards-careful-reading", "demanding-prose",
            "meditative-pacing", "literary-genre-blur",
        ],
        "themes": [
            "identity-and-self", "memory-and-the-past",
            "loneliness-and-isolation", "ageing-and-mortality",
            "language-and-translation",
        ],
    },
    "intimate-character-study": {
        "label": "Intimate character study",
        "description": "small-cast interiority; one or two people seen closely",
        "signals": [
            "deep-character-study", "intimate-pov", "single-pov",
            "emotional-depth", "character-growth", "slow-burn",
        ],
        "themes": [
            "identity-and-self", "midlife-reckoning", "friendship",
            "marriage-and-partnership", "parenthood",
        ],
    },
    "structural-cleverness": {
        "label": "Structural cleverness",
        "description": "formal trickery — twists, puzzles, unreliable framing",
        "signals": [
            "twisty-plot", "puzzle-plot", "unreliable-narrator",
            "nonlinear-timeline", "experimental-prose",
            "braided-narrative", "epistolary-format",
        ],
        "themes": [
            "secrets-and-lies", "memory-and-the-past", "identity-and-self",
        ],
    },
    "humor-with-serious-stakes": {
        "label": "Humor with serious stakes",
        "description": "comic register that doesn't undercut real weight",
        "signals": [
            "humor-with-stakes", "witty-prose", "darkly-comic",
            "character-growth", "emotional-depth",
        ],
        "themes": [
            "friendship", "ambition-and-hubris", "identity-and-self",
            "mental-illness", "ageing-and-mortality",
        ],
    },
    "propulsive-thriller": {
        "label": "Propulsive thriller",
        "description": "page-turning thriller mechanics; investigation, conspiracy, pursuit",
        "signals": [
            "propulsive-pacing", "twisty-plot", "conspiracy-thriller",
            "investigation-driven", "legal-procedural", "noir-register",
        ],
        "themes": [
            "crime-and-investigation", "espionage", "secrets-and-lies",
            "justice-and-revenge",
        ],
    },
    "immersive-worldbuilding": {
        "label": "Immersive worldbuilding",
        "description": "world or magic-system itself as the core attraction",
        "signals": [
            "richly-built-world", "intricate-magic-system",
            "secondary-world-fantasy", "expansive-setting",
            "alien-setting", "well-researched",
        ],
        "themes": [
            "magic-and-its-cost", "civilisation-and-collapse",
            "exploration-and-discovery", "knowledge-and-its-limits",
        ],
    },
    "epic-ensemble-fantasy": {
        "label": "Epic ensemble fantasy",
        "description": "sweeping fantasy with large cast and world-shaking stakes",
        "signals": [
            "secondary-world-fantasy", "expansive-setting", "ensemble-cast",
            "court-intrigue", "war-narrative", "world-shattering-stakes",
            "series-payoff",
        ],
        "themes": [
            "war-and-its-aftermath", "power-and-authority",
            "duty-and-honor", "tyranny-and-resistance",
        ],
    },
    "grimdark-moral-weight": {
        "label": "Grimdark moral weight",
        "description": "moral darkness as substance — violence costs, no easy heroes",
        "signals": [
            "grimdark", "morally-grey-protagonist", "grim-bleak",
            "anti-hero", "war-narrative",
        ],
        "themes": [
            "violence-and-its-cost", "morality-in-extremis",
            "guilt-and-atonement", "justice-and-revenge",
        ],
    },
    "hopepunk-warmth": {
        "label": "Hopepunk warmth",
        "description": "comfort registers; warmth, found family, fighting for kindness",
        "signals": [
            "warm-hopeful", "hopepunk", "found-family", "feel-good",
            "cozy-register", "light-tone",
        ],
        "themes": [
            "community", "friendship", "redemption", "courage-and-heroism",
        ],
    },
    "uncanny-dread": {
        "label": "Uncanny dread",
        "description": "atmospheric horror; slow accumulating wrongness",
        "signals": [
            "uneasy-dread", "horror-elements", "atmospheric-setting",
            "southern-gothic", "weird-fiction", "slow-burn",
        ],
        "themes": [
            "monsters-and-the-uncanny", "alienation", "secrets-and-lies",
            "abuse",
        ],
    },
    "cosmic-scale-sf": {
        "label": "Cosmic-scale SF",
        "description": "vastness — first contact, deep time, indifferent universe",
        "signals": [
            "cosmic-awe", "cosmic-horror", "alien-setting", "hard-sf",
            "space-opera", "soft-sf",
        ],
        "themes": [
            "first-contact", "exploration-and-discovery",
            "civilisation-and-collapse", "knowledge-and-its-limits",
        ],
    },
    "noir-cynicism": {
        "label": "Noir cynicism",
        "description": "dark city, cynical voice, money and shadow",
        "signals": [
            "noir-register", "morally-grey-protagonist",
            "investigation-driven", "propulsive-pacing", "urban-fantasy",
        ],
        "themes": [
            "crime-and-investigation", "justice-and-revenge",
            "money-and-greed", "loyalty-and-betrayal",
        ],
    },
    "historical-immersion": {
        "label": "Historical immersion",
        "description": "deeply researched period piece; the past felt as texture",
        "signals": [
            "historical-immersion", "well-researched", "expansive-setting",
            "ensemble-cast",
        ],
        "themes": [
            "war-and-its-aftermath", "colonialism", "class-and-poverty",
            "race-and-belonging", "memory-and-the-past",
        ],
    },
    "mythic-folkloric": {
        "label": "Mythic / folkloric",
        "description": "myth and folklore as source material; transformation, fate",
        "signals": [
            "mythology-folklore", "magical-realism", "lyrical-prose",
            "atmospheric-setting", "secondary-world-fantasy",
        ],
        "themes": [
            "fate-and-destiny", "transformation", "magic-and-its-cost",
            "identity-and-self",
        ],
    },
    "quiet-domestic": {
        "label": "Quiet domestic",
        "description": "small stakes, domestic interiority, slow patient tone",
        "signals": [
            "quiet-domestic", "intimate-pov", "meditative-pacing",
            "emotional-depth", "single-pov",
        ],
        "themes": [
            "marriage-and-partnership", "parenthood", "home-and-belonging",
            "friendship",
        ],
    },
    "adventure-quest": {
        "label": "Adventure quest",
        "description": "heroic-journey shape; movement, companions, stakes ahead",
        "signals": [
            "quest-structure", "propulsive-pacing", "ensemble-cast",
            "swashbuckling", "found-family", "competence-porn",
        ],
        "themes": [
            "courage-and-heroism", "friendship",
            "exploration-and-discovery", "duty-and-honor",
        ],
    },
    "ideas-driven-sf": {
        "label": "Ideas-driven SF",
        "description": "SF as philosophy — high-concept premises pushed for thought",
        "signals": [
            "hard-sf", "soft-sf", "philosophical-depth",
            "high-concept-premise", "well-researched",
        ],
        "themes": [
            "technology-and-humanity", "ai-and-consciousness",
            "knowledge-and-its-limits", "freedom-and-constraint",
        ],
    },
    "survival-isolation": {
        "label": "Survival / isolation",
        "description": "hostile environment, scarce resources, solitary endurance",
        "signals": [
            "survival-narrative", "claustrophobic-setting", "intimate-pov",
            "propulsive-pacing",
        ],
        "themes": [
            "survival", "loneliness-and-isolation", "courage-and-heroism",
            "morality-in-extremis",
        ],
    },
    "memoir-witness": {
        "label": "Memoir / witness",
        "description": "first-person true-life narrative; lived testimony",
        "signals": [
            "memoir-form", "narrative-nonfiction", "historical-witness",
            "emotional-depth",
        ],
        "themes": [
            "identity-and-self", "trauma-and-recovery",
            "exile-and-displacement", "race-and-belonging",
        ],
    },
    "popular-science": {
        "label": "Popular science",
        "description": "narrative nonfiction explaining the natural world",
        "signals": [
            "popular-science", "narrative-nonfiction", "well-researched",
            "philosophical-depth", "accessible-prose",
        ],
        "themes": [
            "science-and-nature", "knowledge-and-its-limits",
            "technology-and-humanity", "exploration-and-discovery",
        ],
    },
    "essayistic-criticism": {
        "label": "Essayistic criticism",
        "description": "argument-shaped nonfiction; cultural / political / tech critique",
        "signals": [
            "essayistic-form", "tech-criticism", "political-writing",
            "philosophical-depth", "witty-prose",
        ],
        "themes": [
            "power-and-authority", "technology-and-humanity",
            "freedom-and-constraint", "race-and-belonging",
            "class-and-poverty",
        ],
    },
    "coming-of-age-arc": {
        "label": "Coming-of-age arc",
        "description": "adolescent identity formation; growing into a self",
        "signals": [
            "character-growth", "found-family", "intimate-pov",
            "emotional-depth",
        ],
        "themes": [
            "coming-of-age", "identity-and-self", "friendship",
            "blood-family",
        ],
    },
    "court-political-intrigue": {
        "label": "Court / political intrigue",
        "description": "power-faction maneuvering, alliances, betrayals",
        "signals": [
            "court-intrigue", "ensemble-cast", "twisty-plot",
            "morally-grey-protagonist",
        ],
        "themes": [
            "power-and-authority", "loyalty-and-betrayal",
            "ambition-and-hubris", "tyranny-and-resistance",
        ],
    },
    "revenge-and-retribution": {
        "label": "Revenge and retribution",
        "description": "the cost of vengeance; justice deferred and personal",
        "signals": [
            "revenge-narrative", "morally-grey-protagonist",
            "propulsive-pacing", "anti-hero",
        ],
        "themes": [
            "justice-and-revenge", "violence-and-its-cost",
            "loyalty-and-betrayal", "guilt-and-atonement",
        ],
    },
}


# Tagging match rule, signal-weighted:
#
#   signal_overlap >= 1 AND (signal_overlap + theme_overlap) >= 2
#
# i.e. at least one positive signal must match the vector AND the
# combined signal+theme overlap is at least two.  Themes alone don't
# qualify because individual themes (power-and-authority,
# loyalty-and-betrayal) are too generic to identify a vector on their
# own — they appear across most fiction.  The two-overlap minimum
# prevents drive-by single-keyword matches.
#
# Tuned against the live catalog (~4600 books): mean ~3.4 vectors per
# book, median 3, ~5% with no tags (genuinely sparse-data entries).
# Matches RECOMPOSITION_PLAN §6.4's "sparse — most books exemplify 2-4."

TASTE_VECTOR_MIN_TOTAL_OVERLAP = 2
TASTE_VECTOR_MIN_SIGNAL_OVERLAP = 1


def book_taste_vector_matches(
    positive_signals: list[str] | tuple[str, ...] | set[str],
    themes: list[str] | tuple[str, ...] | set[str],
    *,
    min_total: int = TASTE_VECTOR_MIN_TOTAL_OVERLAP,
    min_signal: int = TASTE_VECTOR_MIN_SIGNAL_OVERLAP,
) -> list[tuple[str, int]]:
    """Return [(vector_id, overlap_count), ...] for vectors a book exemplifies.

    A vector matches when the book has at least `min_signal` positive
    signal overlaps AND at least `min_total` combined signal+theme
    overlaps with the vector's member set.  `overlap_count` is the
    combined total.  Result sorted by descending overlap then vector_id
    so emit order is deterministic.
    """
    pos_set = set(positive_signals)
    th_set = set(themes)
    if not pos_set and not th_set:
        return []
    out: list[tuple[str, int]] = []
    for vid, vec in CANONICAL_TASTE_VECTORS.items():
        sigs = set(vec.get("signals") or [])
        thms = set(vec.get("themes") or [])
        so = len(pos_set & sigs)
        to = len(th_set & thms)
        if so >= min_signal and (so + to) >= min_total:
            out.append((vid, so + to))
    out.sort(key=lambda t: (-t[1], t[0]))
    return out


def validate_vectors() -> list[str]:
    """Return a list of error strings for any vector that references a
    signal or theme not in the canonical vocabularies.  Empty list = OK.
    Used by tests to guard against drift between vector definitions and
    the canonical vocabularies."""
    errs: list[str] = []
    for vid, vec in CANONICAL_TASTE_VECTORS.items():
        for sig in vec.get("signals") or []:
            if sig not in CANONICAL_TASTE_SIGNALS:
                errs.append(f"{vid}: unknown signal {sig!r}")
        for th in vec.get("themes") or []:
            if th not in CANONICAL_THEMES:
                errs.append(f"{vid}: unknown theme {th!r}")
    return errs


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------

def format_vocab_for_prompt(vocab: dict[str, str]) -> str:
    """Render a vocab dict as a compact bullet list for an LLM prompt."""
    return "\n".join(f"  - {k}: {v}" for k, v in vocab.items())
