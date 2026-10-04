"""E4 extra: ROUGH keyword proxies for every non-'other' topic, in the actual golden 50 and the 10,000 dev sample.
A keyword hit is a mention, not a primary-topic label. Read-only."""
import csv, sys
csv.field_size_limit(sys.maxsize)
D = "/Users/travis/Developer/pepeclass/assign5-multiagent/feed/Final Assignment - Spotify Reviews Dataset/"
def load(fn):
    with open(D + fn, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
gold, ana = load("golden_50_to_label.csv"), load("analysis_10000.csv")
assert all(not r["topic"] and not r["intent"] and not r["severity"] for r in gold), "feed copy must have blank labels"
KW = {
 "access":   ["log in", "login", "password", "sign in", "account", "logged", "sign up"],
 "support":  ["customer service", "support team", "customer support", "customer care", "contact support"],
 "downloads":["download", "offline"],
 "billing":  ["premium", "subscription", "subscrib", "pay", "price", "charge", "refund", "money", "expensive"],
 "playback": ["crash", "stops", "stop playing", "won't play", "wont play", "not playing", "lag", "buffer", "freez", "pause", "glitch", "bug"],
 "catalog":  ["lyrics", "search", "recommend", "podcast", "artist", "songs i", "discover"],
 "usability":["ads", "shuffle", "queue", "playlist", "interface", "ui ", "layout", "skip", "update"],
}
print("topic       golden-50 hits   analysis_10000 hits (%)")
for k, kws in KW.items():
    g = sum(1 for r in gold if any(w in r["review_text"].lower() for w in kws))
    a = sum(1 for r in ana if any(w in r["review_text"].lower() for w in kws))
    print(f"{k:10s}  {g:3d}              {a:5d} ({a/100:.2f}%)")
nohit = sum(1 for r in gold if not any(w in r["review_text"].lower() for ws in KW.values() for w in ws))
print(f"golden-50 reviews matching none of these keyword sets (candidate 'other'/general praise or criticism): {nohit}")
short = sum(1 for r in gold if len(r["review_text"]) <= 30)
print(f"golden-50 reviews of 30 characters or fewer: {short}")
from collections import Counter
print("golden-50 star ratings:", dict(sorted(Counter(r["review_rating"] for r in gold).items())))
