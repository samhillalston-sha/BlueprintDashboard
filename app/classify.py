"""Milestone 2: classify a fitness post's text into activity categories.

The classifier reads the words (and Slack emoji codes like :flying_disc:)
in a message and tags it with every activity group it mentions. A post can
have several tags — "Throws and tempos" is both throwing and cardio, which
is exactly the "combined" post the team rules allow.

The keyword lists below were built from Blueprint's real channel history,
including the team's own slang ("sprintos", "troes", "leggos").
"""

import re
from dataclasses import dataclass, field

# Phrases that contain an activity word but don't describe a workout.
# "Ran into my son at the gym" means he MET his son, not that he ran.
# These get deleted from the text before we look for keywords.
IGNORE_PHRASES = [
    "ran into",
    "run into",
    "runs into",
    "running into",
]

# Each category maps to the words/phrases that signal it. Matching is
# case-insensitive and whole-word only ("ran" won't match inside "random").
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
    # Playing ultimate — practices, leagues, pickup, tournaments
    "ultimate": [
        "practice", "league", "tournament", "pickup", "mini", "pod",
        "mccarren",  # Brooklyn pickup game the team goes to
        "fli", "worlds", "regionals", "nationals",
    ],
    # Other sports — active, but is it cardio credit? (team policy call)
    "sports": [
        "volleyball", "tennis", "basketball", "hooping", "hoops",
        "soccer", "footy", "pickleball", "disc golf",
        "climbing", "climb", "spikes", "king of the court",
        "person_climbing",  # emoji name
    ],
}

# Pre-build one regex per category. Each keyword becomes a whole-word
# pattern, so "ran" cannot match inside "random".
_PATTERNS = {
    category: re.compile(
        r"\b(?:" + "|".join(re.escape(word) for word in words) + r")\b",
        re.IGNORECASE,
    )
    for category, words in KEYWORDS.items()
}

_IGNORE_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in IGNORE_PHRASES) + r")\b",
    re.IGNORECASE,
)


@dataclass
class Classification:
    tags: set = field(default_factory=set)      # every category the post mentions
    matched_words: dict = field(default_factory=dict)  # category -> words that hit

    @property
    def label(self) -> str:
        """The single headline verdict for this post."""
        if "throwing" in self.tags and "cardio" in self.tags:
            return "combined"          # one post, both boxes ticked
        if "throwing" in self.tags:
            return "throwing"
        if "cardio" in self.tags:
            return "cardio"
        if "ultimate" in self.tags:
            return "ultimate"           # played frisbee — credit is a policy call
        if "sports" in self.tags:
            return "sports"             # other sport — also a policy call
        if self.tags:
            return "strength/recovery"  # active, but neither required category
        return "unclassified"           # we couldn't tell — needs a human look


def classify(text: str) -> Classification:
    """Tag one message's text with every activity category it mentions."""
    cleaned = _IGNORE_PATTERN.sub(" ", text or "")
    result = Classification()
    for category, pattern in _PATTERNS.items():
        hits = pattern.findall(cleaned)
        if hits:
            result.tags.add(category)
            result.matched_words[category] = sorted({h.lower() for h in hits})
    return result
