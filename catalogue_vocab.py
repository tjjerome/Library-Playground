"""
Controlled vocabularies for the librarian catalog.

Two lists live here:

* `CANONICAL_TASTE_SIGNALS` — public-reception signal IDs used by the
  recommender to compute cross-book overlap reliably. Free-form
  `taste_signals` strings stay for human readability; canonical IDs are
  the machine-comparable form.

* `CANONICAL_THEMES` — concrete recurring concerns of texts.

Each list is a dict mapping a kebab-case ID to a short description shown
to the cataloguer model. The IDs are stable and grow only via deliberate
additions — see `catalogue.py --canonicalize-signals` /
`--canonicalize-themes` for the data-driven backfill that promotes
recurring free-form values into new canonical entries.

Seed lists were written to cover the obvious clusters in a general fiction
library; the canonicalization pipeline can extend them once real free-form
data is in hand.
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
    "deep-character-study":       "interior life and growth of a single character is the point",
    "anti-hero":                  "anti-hero or villain protagonist",
    "competence-porn":            "characters who are extraordinarily good at what they do",
    "ordinary-protagonist":       "ordinary person in extraordinary circumstances",

    # Emotional register
    "humor-with-stakes":          "humor that doesn't undercut serious stakes",
    "darkly-comic":               "darkly comic register; gallows humor",
    "warm-hopeful":               "warm, hopeful emotional register",
    "melancholy":                 "melancholy or wistful register",
    "grim-bleak":                 "grim, bleak register; little reprieve",
    "cathartic-tragedy":          "tragedy with cathartic emotional payoff",
    "feel-good":                  "feel-good register; comfort read",
    "uneasy-dread":               "register of uneasy, accumulating dread",
    "cosmic-awe":                 "register of cosmic scale or awe",

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

    # World & setting
    "richly-built-world":         "world-building is a core attraction",
    "atmospheric-setting":        "atmosphere of place is a core attraction",
    "claustrophobic-setting":     "claustrophobic, confined setting",
    "expansive-setting":          "sweeping, geographically expansive setting",
    "alien-setting":              "genuinely alien or non-human setting",
    "historical-immersion":       "deeply researched historical immersion",
    "secondary-world-fantasy":    "wholly secondary fantasy world",

    # Subgenre flavours
    "romance-heavy":              "romance is a primary plot engine",
    "romance-subplot":            "romance is a meaningful subplot but not the engine",
    "no-romance":                 "deliberately no romance",
    "horror-elements":            "horror or dread is a meaningful component",
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
    "didactic-register":          "didactic register; tells rather than shows",
    "gratuitous-darkness":        "darkness presented gratuitously rather than purposefully",
    "thin-worldbuilding":         "thin or under-imagined worldbuilding",
    "excessive-length":           "structurally bloated; pages without payoff",
    "convenient-coincidence":     "plot leans on convenient coincidence",
    "underdeveloped-romance":     "romance present but underdeveloped",
    "pedestrian-prose":           "prose competent but unmemorable",
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
    "magic-and-its-cost":         "magic and the cost of using it",
    "monsters-and-the-uncanny":   "monsters, the uncanny, what lurks at the edges",
    "creativity-and-art":         "art, creativity, what it costs to make things",
    "knowledge-and-its-limits":   "knowledge, learning, the limits of knowing",
    "language-and-translation":   "language, translation, the gap between tongues",
    "money-and-greed":            "money, greed, accumulation",
    "loyalty-and-betrayal":       "loyalty and betrayal; the people who stay and the people who don't",
    "duty-and-honor":             "duty, honor, the cost of keeping vows",
    "freedom-and-constraint":     "freedom, constraint, lives lived inside cages",
    "home-and-belonging":         "home, the search for it, the loss of it",
}


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------

def format_vocab_for_prompt(vocab: dict[str, str]) -> str:
    """Render a vocab dict as a compact bullet list for an LLM prompt."""
    return "\n".join(f"  - {k}: {v}" for k, v in vocab.items())
