"""THROWAWAY re-score. Scores label fields on every labeled row; an obvious intent typo is
read as its intended value and reported; quote overlap is scored only where the human quote is an exact copy."""
import csv, re, sys
from collections import Counter
from score_spike import simple_records, sentence_records, LABELS, TOPICS, INTENTS

ALIAS = {"compliant": "complaint"}
rows = list(csv.DictReader(open(LABELS, encoding="utf-8-sig", newline="")))[: int(sys.argv[1]) if len(sys.argv) > 1 else 30]
rows = [(n, r) for n, r in enumerate(rows, 2) if (r["intent"] or r["topic"] or r["severity"]).strip()]
typos = [n for n, r in rows if r["intent"] in ALIAS]
bad_quote = [n for n, r in rows if not r["evidence_quote"].strip() or r["evidence_quote"].strip() not in r["review_text"]]
print(f"labeled rows: {len(rows)} | intent typo read as 'complaint' in rows {typos} | quote not an exact copy in rows {bad_quote}")
for n, r in rows:
    r["intent"] = ALIAS.get(r["intent"], r["intent"])
    assert r["intent"] in INTENTS and r["topic"] in TOPICS and r["severity"] in list("12345"), f"row {n} still has an invalid label"
print("your labels: intent", dict(Counter(r["intent"] for _, r in rows)), "| topic", dict(Counter(r["topic"] for _, r in rows)), "| severity", dict(sorted(Counter(r["severity"] for _, r in rows).items())))
for name, recs in (("simple", simple_records()), ("sentence", sentence_records())):
    hits = Counter(); sev_err = sen_err = 0.0; qn = 0; misses = []; all3 = 0
    sub = {"complaint_or_cancel": [0, 0, 0, 0], "other_rows": [0, 0, 0, 0]}
    for n, r in rows:
        j = recs[r["review_id"]]
        alt = (r.get("notes") or "").lower()
        t = j["topic"] == r["topic"] or f"alt topic: {j['topic']}" in alt
        i = j["intent"] == r["intent"] or f"alt intent: {j['intent']}" in alt
        s = j["severity"] == int(r["severity"])
        hits.update(topic=t, intent=i, severity=s); all3 += t and i and s
        sev_err += abs(j["severity"] - int(r["severity"])); sen_err += abs(j["sentiment"] - float(r["sentiment"]))
        if n not in bad_quote:
            qn += 1; hq = r["evidence_quote"].strip(); hits.update(quote=hq in j["quote"] or j["quote"] in hq)
        g = sub["complaint_or_cancel" if r["intent"] in ("complaint", "cancellation") else "other_rows"]
        g[0] += 1; g[1] += t; g[2] += i; g[3] += s
        if not (t and i and s):
            misses.append((n, r, j))
    k = len(rows)
    print(f"\n=== {name} ===  n={k}")
    print(f"topic {hits['topic']}/{k}  intent {hits['intent']}/{k}  severity exact {hits['severity']}/{k}  all three right {all3}/{k}  "
          f"severity mean error {sev_err / k:.2f}  sentiment mean error {sen_err / k:.2f}  quote overlaps yours {hits['quote']}/{qn}")
    for g, (cnt, t, i, s) in sub.items():
        print(f"   {g:<20} n={cnt}: topic {t}/{cnt}  intent {i}/{cnt}  severity {s}/{cnt}")
    for n, r, j in misses:
        print(f"  row {n}: you {r['topic']}/{r['intent']}/{r['severity']}  jev {j['topic']}/{j['intent']}/{j['severity']}  | {re.sub(chr(10), ' ', r['review_text'])[:100]}")
