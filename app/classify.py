"""Milestone 2 (M1/M2/M3: now team_config-aware): classify a fitness post's
text into activity categories.

The classifier reads the words (and Slack emoji codes like :flying_disc:)
in a message and tags it with every activity group it mentions. A post can
have several tags — "Throws and tempos" is both throwing and cardio, which
is exactly the "combined" post the team rules allow.

`Classifier` is the actual engine, parameterized by categories/keywords
and which categories count toward which "box" — this is what
`Classifier.from_team_config()` builds from a team's own `team_config`
row (see supabase/migrations/0001_multi_tenant_foundation.sql), so each
team's slang/categories/rules can differ without editing this file.

The module-level `classify()` function below is a thin wrapper around a
default Classifier built from Blueprint's own keyword lists — kept for
backward compatibility with milestone2-4 (single-team, pre-multi-tenant)
and for anything that hasn't been made org-aware yet. New multi-tenant
code (sync_slack.py) should build a Classifier from the org's real
team_config instead of calling the bare classify() function.
"""

import re
from dataclasses import dataclass, field

# Phrases that contain an activity word but don't describe a workout.
# "Ran into my son at the gym" means he MET his son, not that he ran.
# These get deleted from the text before we look for keywords.
#
# Not yet part of team_config (every team shares this list for now) --
# a reasonable per-team knob to add later if it turns out to matter,
# but that's a product decision, not assumed here.
IGNORE_PHRASES = [
    "ran into",
    "run into",
    "runs into",
    "running into",
    # Mentioning an upcoming event isn't the same as playing in one:
    # "pumped for practice tomorrow", "last lift before worlds"
    "for practice",
    "before worlds",
    "miss practice",
    "practice tomorrow",
]

# Blueprint's own keyword lists, built from its real channel history,
# including the team's own slang ("sprintos", "troes", "leggos"). This is
# the DEFAULT config for the classify() convenience function below --
# other teams get their own version of this dict via team_config.
KEYWORDS = {
    # Throwing the disc — what the weekly throwing selfie should show
    "throwing": [
        "throw", "throws", "throwing", "threw",
        "toss", "tossing", "tossed",
        "troes", "throughs",  # team slang / beloved typos for throws
        "huck", "hucks", "hucking",
        "flick", "flicks", "backhand", "backhands", "forehand", "forehands",
        "hammer", "scoober",
        "disc", "frisbee",
        "marking", "break mark", "catching",
        "flying_disc",  # the 🥏 emoji, as Slack writes it
    ],
    # Cardio — what the weekly cardio selfie should show
    "cardio": [
        "run", "runs", "running", "ran", "jog", "jogging", "jogged",
        "sprint", "sprints", "sprinted", "sprintos",
        "tempo", "tempos", "interval", "intervals",
        "bike", "biked", "biking", "bikes", "ride", "riding", "cycling",
        "soulcycle", "spin",
        "swim", "swimming", "swam",
        "cardio", "conditioning", "hiit",
        "mile", "miles", "5k", "10k", "lap", "laps", "trail",
        "zone 2", "z2",
        "stairs", "stairmaster", "stair master", "treadmill", "elliptical",
        "row", "rowing",
        "cod", "change of direction",
        "field workout", "field work", "fieldwork",
        "runner", "bicyclist", "swimmer",  # emoji names
    ],
    # Strength work — great for you, but not throwing or cardio credit
    "strength": [
        "lift", "lifts", "lifted", "lifting", "gym", "weights", "strength",
        "upper", "uppers", "lower", "leg", "legs", "leggy", "leggos", "leg day",
        "core", "abs", "plank", "planks",
        "squat", "squats", "split squat", "deadlift", "deadlifts",
        "rdl", "rdls", "slrdl", "bench",
        "pull", "push", "pull ups", "pullups", "push ups", "pushups",
        "clean", "cleans", "power cleans",
        "plyo", "plyos", "explosiveness",
        "kettlebell", "bells", "pump", "bulgarians", "calves",
        "posterior chain",
        "muscle", "weight_lifter",  # emoji names
    ],
    # PT / recovery — matters later for the injury-excuse feature
    "recovery": [
        "pt", "rehab", "mobility", "yoga",
        "stretch", "stretching", "stretches",
        "foam roll", "foam rolling", "recovery",
        "isos", "theragun", "theragunning", "massage",
        "sauna", "suana",  # keeping Filip's typo forever
        "blood flow",
    ],
    # Playing ultimate — practices, leagues, pickup, tournaments.
    # Team ruling: counts as fitness (the cardio box), NOT throwing.
    "ultimate": [
        "practice", "league", "tournament", "pickup", "mini", "pod",
        "mccarren",  # Brooklyn pickup game the team goes to
        "fli", "worlds", "regionals", "nationals",
    ],
    # Other sports — team ruling: these count as cardio too
    "sports": [
        "volleyball", "tennis", "basketball", "hooping", "hoops",
        "soccer", "footy", "pickleball", "disc golf",
        "climbing", "climb", "spikes", "king of the court",
        "person_climbing",  # emoji name
    ],
}

# Blueprint's compliance rules (ruled by the commissioner, July 2026):
# throwing is its own required box; cardio, ultimate, and sports all
# count toward the cardio box; strength/PT/mobility count toward neither.
REQUIRED_CATEGORIES = ["throwing", "cardio"]
CARDIO_CREDIT_CATEGORIES = {"cardio", "ultimate", "sports"}


@dataclass
class Classification:
    tags: set = field(default_factory=set)      # every category the post mentions
    matched_words: dict = field(default_factory=dict)  # category -> words that hit
    label: str = "unclassified"


class Classifier:
    """The classification engine, parameterized per team.

    required_categories: which category keys must be posted weekly for
        compliance, in priority order. Currently supports exactly the
        two-box shape every team so far has used (one single required
        category, one category-with-credits) -- e.g.
        ["throwing", "cardio"]. A team needing a different shape (three+
        required boxes, multiple non-credit-expandable boxes, etc) needs
        a product decision on what that even means before this class
        can support it; don't silently extend this to guess.
    credit_categories: category keys that also satisfy the second
        required box (e.g. {"cardio", "ultimate", "sports"}).
    """

    def __init__(self, categories: dict[str, list[str]], required_categories: list[str],
                 credit_categories: set[str], ignore_phrases: list[str] | None = None):
        if not required_categories:
            raise ValueError("required_categories must list at least one category")
        self.categories = categories
        self.primary_category = required_categories[0]
        self.secondary_category = required_categories[1] if len(required_categories) > 1 else None
        self.credit_categories = credit_categories
        ignore_phrases = IGNORE_PHRASES if ignore_phrases is None else ignore_phrases

        self._patterns = {
            category: re.compile(
                r"\b(?:" + "|".join(re.escape(word) for word in words) + r")\b",
                re.IGNORECASE,
            )
            for category, words in categories.items()
        }
        self._ignore_pattern = (
            re.compile(r"\b(?:" + "|".join(re.escape(p) for p in ignore_phrases) + r")\b", re.IGNORECASE)
            if ignore_phrases else None
        )

    @classmethod
    def from_team_config(cls, config: dict) -> "Classifier":
        """Build a Classifier from a team_config row's `config` JSON
        (see supabase/migrations/0001_multi_tenant_foundation.sql)."""
        categories = {c["key"]: c["keywords"] for c in config["categories"]}
        credit = set(config.get("cardio_credit_categories", []))
        return cls(categories=categories, required_categories=config["required_categories"],
                    credit_categories=credit)

    def classify(self, text: str) -> Classification:
        """Tag one message's text with every activity category it mentions."""
        cleaned = self._ignore_pattern.sub(" ", text or "") if self._ignore_pattern else (text or "")
        tags = set()
        matched_words = {}
        for category, pattern in self._patterns.items():
            hits = pattern.findall(cleaned)
            if hits:
                tags.add(category)
                matched_words[category] = sorted({h.lower() for h in hits})
        return Classification(tags=tags, matched_words=matched_words, label=self._label_for(tags))

    def _label_for(self, tags: set) -> str:
        credit_hit = bool(tags & self.credit_categories) if self.secondary_category else False
        has_primary = self.primary_category in tags
        if has_primary and credit_hit:
            return "combined"          # one post, both boxes ticked
        if has_primary:
            return self.primary_category
        if credit_hit:
            return self.secondary_category
        if tags:
            return "strength/recovery"  # active, but neither required category
        return "unclassified"           # we couldn't tell — needs a human look


_DEFAULT_CLASSIFIER = Classifier(
    categories=KEYWORDS,
    required_categories=REQUIRED_CATEGORIES,
    credit_categories=CARDIO_CREDIT_CATEGORIES,
    ignore_phrases=IGNORE_PHRASES,
)


def classify(text: str) -> Classification:
    """Convenience wrapper using Blueprint's own default rules.

    Kept for milestone2-4 scripts and anything not yet org-aware. New
    multi-tenant code should use Classifier.from_team_config() instead.
    """
    return _DEFAULT_CLASSIFIER.classify(text)
