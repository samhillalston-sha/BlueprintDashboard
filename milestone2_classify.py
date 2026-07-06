"""Milestone 2: run the classifier over real channel messages and show results.

Reads data/messages_sample.json (real posts pulled from Slack, kept out of
git) and prints a table of how each post gets classified, plus a summary.

Run it with:  python milestone2_classify.py
Try a single message with:  python milestone2_classify.py "Throws and tempos"
"""

import json
import sys
from collections import Counter
from pathlib import Path

from app.classify import classify

DATA_FILE = Path(__file__).parent / "data" / "messages_sample.json"

# A few generic examples so the script still demonstrates itself even
# without the real (local-only) data file.
BUILT_IN_EXAMPLES = [
    {"date": "-", "user": "example", "text": "Throws and tempos"},
    {"date": "-", "user": "example", "text": "Morning run, 3 miles"},
    {"date": "-", "user": "example", "text": "Leg day at the gym"},
    {"date": "-", "user": "example", "text": "Ran into a friend at the store"},
]


def show(messages: list) -> None:
    counts = Counter()
    print(f"{'DATE':<11} {'WHO':<22} {'VERDICT':<18} MESSAGE")
    print("-" * 100)
    for message in messages:
        result = classify(message["text"])
        counts[result.label] += 1
        text = message["text"].replace("\n", " ")
        if len(text) > 44:
            text = text[:43] + "…"
        print(f"{message['date']:<11} {message['user']:<22} {result.label:<18} {text}")

    print("\nSummary:")
    for label, count in counts.most_common():
        print(f"  {label:<18} {count:>3} posts")


def main() -> None:
    if len(sys.argv) > 1:
        # Classify whatever was typed on the command line.
        text = " ".join(sys.argv[1:])
        result = classify(text)
        print(f"Message:  {text}")
        print(f"Verdict:  {result.label}")
        print(f"Matched:  {result.matched_words or '(no keywords found)'}")
        return

    if DATA_FILE.exists():
        messages = json.loads(DATA_FILE.read_text())
        print(f"Classifying {len(messages)} real posts from {DATA_FILE.name}:\n")
    else:
        messages = BUILT_IN_EXAMPLES
        print("No local data file found — using built-in examples:\n")
    show(messages)


if __name__ == "__main__":
    main()
