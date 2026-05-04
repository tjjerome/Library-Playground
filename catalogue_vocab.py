"""
Controlled vocabularies for the librarian catalog.

Two lists live here:

* `CANONICAL_TASTE_SIGNALS` — public-reception signal IDs the cataloguer
  emits as the per-book `taste_signals` field. Closed vocabulary: the
  cataloguer must pick from this list and never invent new IDs. The
  recommender uses these IDs for cross-book overlap.

* `CANONICAL_THEMES` — concrete recurring concerns of texts. Same
  closed-vocabulary contract.

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
# Prompt formatting
# ---------------------------------------------------------------------------

def format_vocab_for_prompt(vocab: dict[str, str]) -> str:
    """Render a vocab dict as a compact bullet list for an LLM prompt."""
    return "\n".join(f"  - {k}: {v}" for k, v in vocab.items())
