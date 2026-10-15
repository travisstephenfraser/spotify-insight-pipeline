"""Jev 1.14 canary: does a new model version label these reviews differently, and is it better? (validation log entry 44)

TypeSafe released jev-1.14.0 on 2026-10-14. The pipeline pins jev-1.13.0. Three arms per text, sent in one
shuffled order so time of day cannot pass for a model effect:

  a13  jev-1.13.0 now
  b14  jev-1.14.0
  c14  jev-1.14.0 again, for 1.14's own rerun noise

and s13, the stored label from the full run of 2026-10-06 (grading/records.jsonl.gz). Requests are built by the
pipeline's own build_request with the frozen wording; only the `model` field differs between arms.

The texts: 2,000 distinct review texts picked by hash, 300 that a word list marks as not English, and the texts of
the golden 50, the development 150, the blind adjudication 39 and the boycott 60. The golden 50 is not scored: only
its ID and text columns are used, because it is scored once (entry 36). Accuracy is read on the 68 hand labels that
may be reused: the development 29 and the adjudication 39.

These calls do not go through the spend ledger: evals/common.py refuses any reply that names another model than
jev.MODEL, by design. The cap here is an estimate checked before anything is sent.

  python3 experiments/2026-10-15/jev-1.14-canary/canary.py            # plan and cost estimate; nothing sent
  python3 experiments/2026-10-15/jev-1.14-canary/canary.py --go       # send (refuses if calls already exist)
  python3 experiments/2026-10-15/jev-1.14-canary/canary.py --analyze  # report.json from the saved calls; no call

--go and the multilingual listing in --analyze need the 97.4 MB source file; the report itself does not.
"""

import argparse
import csv
import gzip
import hashlib
import heapq
import json
import random
import re
import statistics
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT)]
from pipeline import jev, labels  # noqa: E402

SOURCE = (
    ROOT
    / "feed/Final Assignment - Spotify Reviews Dataset/spotify_reviews_18months.csv"
)
STORED = ROOT / "grading/records.jsonl.gz"
ITEMS, CALLS, REPORT = (
    HERE / "items.json",
    HERE / "calls.jsonl.gz",
    HERE / "report.json",
)
DIFFS = HERE / "multilingual_diffs.json"
ARMS = {"a13": "jev-1.13.0", "b14": "jev-1.14.0", "c14": "jev-1.14.0"}
N_RANDOM, N_MULTI = 2000, 300
PRICE = 0.042 / 1e6  # dollars per input token; output tokens are not billed (entry 41)
CAP_USD = 1.00
RATE, WORKERS = 40, 12  # requests a second, half the documented limit
FIELDS = ("topic", "intent", "severity")
SALT = "canary-1.14-v1"

csv.field_size_limit(sys.maxsize)


class Refused(Exception):
    """A check on the measurement failed. Nothing after it should be read."""


# ---------------------------------------------------------------- which language a text is in, roughly
STOP = set(
    "the and to is it i of my this for you in not on but with so can be are that have was me just very all "
    "it's i'm don't when why what they your its im dont cant can't would will an if or at no".split()
)
# Words common in the file's other languages and rare in English reviews: Hindi in Latin script, Spanish,
# Portuguese, Indonesian, Tagalog, German, French, Turkish. Checked by eye on 20 of the 300: 17 not English.
MARKERS = set(
    "hai nahi nhi bhi kya mein aur karo karne kar raha gana gaane gano gaano accha acha bahut bohot yeh "
    "que não nao muito muy para pero pra porque musica música musicas músicas canciones canción cancion "
    "aplicativo aplicación aplicacion também tambem mucho gracias obrigado está esta "
    "yang tidak bisa saya aplikasi lagu gak nya banget sangat tolong "
    "ang naman mga hindi "
    "ich nicht und das ist sehr "
    "je pas les très c'est "
    "bir çok için güzel".split()
)


def lang_bucket(text):
    words = re.findall(r"[^\W\d_]+'?[^\W\d_]*", text.lower())
    letters = "".join(words)
    if not letters:
        return "no_letters"
    nonascii = sum(not ("a" <= c <= "z") for c in letters) / len(letters)
    if nonascii > 0.3 or (len(words) >= 2 and any(w in MARKERS for w in words)):
        return "non_english"
    if len(words) >= 4 and not any(w in STOP for w in words):
        return "ascii_unsure"
    return "english" if len(words) >= 4 else "short"


def _hash(text):
    return int(hashlib.sha256(f"{SALT}:{text}".encode()).hexdigest(), 16)


# ---------------------------------------------------------------- the texts
def _sheet(name, encoding="utf-8-sig"):
    with open(ROOT / "evals" / name, encoding=encoding, newline="") as f:
        return list(csv.DictReader(f))


def hand_labels():
    """The 68 hand labels that may be read again: the development 29 and the adjudication 39."""
    rows = _sheet("dev_150_labeled.csv") + _sheet("adjudication_sheet.csv")
    return {
        r["review_id"]: {
            "topic": r["topic"].strip(),
            "intent": r["intent"].strip(),
            "severity": int(r["severity"]),
        }
        for r in rows
        if r["intent"].strip()
    }


def build_items(source=SOURCE):
    """[{id, sets, lang, text}]. Needs the source file. The golden sheet's label columns are parsed with each row and never used."""
    corpus, seen = {}, set()
    rand_heap, multi_heap = (
        [],
        [],
    )  # the n smallest hashes of distinct texts, as max-heaps on the negated hash
    with open(source, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rid, text = row["review_id"], row["review_text"]
            corpus[rid] = text
            if not text.strip() or text in seen:
                continue
            seen.add(text)
            entry = (-_hash(text), rid)
            targets = [(rand_heap, N_RANDOM)] + (
                [(multi_heap, N_MULTI)] if lang_bucket(text) == "non_english" else []
            )
            for heap, n in targets:
                if len(heap) < n:
                    heapq.heappush(heap, entry)
                elif entry > heap[0]:
                    heapq.heapreplace(heap, entry)
    items = {}

    def add(rid, setname, text=None):
        text = corpus[rid] if text is None else text
        it = items.setdefault(
            rid, {"id": rid, "sets": [], "lang": lang_bucket(text), "text": text}
        )
        if it["text"] != text:
            raise Refused(f"{rid}: two different texts")
        it["sets"].append(setname)

    for _, rid in rand_heap:
        add(rid, "random")
    for _, rid in multi_heap:
        add(rid, "multilingual")
    for r in _sheet("golden_50_labeled.csv"):
        add(r["review_id"], "golden_text", r["review_text"])
    for r in _sheet("dev_150_labeled.csv"):
        add(r["review_id"], "dev", r["review_text"])
    for r in _sheet("adjudication_sheet.csv"):
        add(r["review_id"], "adjudication", r["review_text"])
    for r in _sheet("boycott_60.csv", "utf-8"):
        add(r["review_id"], "boycott", r["review_text"])
    return list(items.values())


def load_stored(ids, path=STORED):
    """The full run's completed records for these review IDs."""
    out = {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["review_id"] in ids and r.get("status") == "completed":
                out[r["review_id"]] = r
    return out


def load_rows(path=CALLS):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------- sending
class Bucket:
    def __init__(self, rate):
        self.gap, self.next, self.lock = 1.0 / rate, time.monotonic(), threading.Lock()

    def take(self):
        with self.lock:
            now = time.monotonic()
            wait = self.next - now
            self.next = max(now, self.next) + self.gap
        if wait > 0:
            time.sleep(wait)


def send(items, go):
    setup = jev.load_setup(ROOT / "prompts")
    plan = []
    for it in items:
        req = jev.build_request(it["text"], setup.prompt)
        plan += [(it, arm, req) for arm in ARMS]
    est_usd = (
        sum(len(jev.body_bytes(r)) / jev.BYTES_PER_TOKEN for _, _, r in plan) * PRICE
    )
    print(
        f"{len(items)} texts, {len(plan)} requests, about ${est_usd:.3f} (bytes/2.4 tokens, errs high)"
    )
    if est_usd > CAP_USD:
        raise Refused(f"estimate ${est_usd:.2f} is over the ${CAP_USD} cap")
    if not go:
        print("Nothing was sent. Add --go to send.")
        return
    raw = CALLS.with_suffix("")  # calls.jsonl, compressed when the run ends
    if CALLS.exists() or raw.exists():
        raise Refused(
            f"{CALLS.name} already exists; a second run would mix with the first"
        )
    ITEMS.write_text(
        json.dumps([{k: it[k] for k in ("id", "sets", "lang")} for it in items]) + "\n",
        encoding="utf-8",
    )
    random.Random(SALT).shuffle(plan)
    from pipeline import cli

    client = jev.Client(cli._env_key("TYPESAFE_API_KEY"), timeout=30)
    bucket, lock, stop, done, t0 = (
        Bucket(RATE),
        threading.Lock(),
        threading.Event(),
        Counter(),
        time.monotonic(),
    )
    out = raw.open("w", encoding="utf-8")

    def one(job):
        it, arm, req = job
        if stop.is_set():
            return
        row = {"id": it["id"], "arm": arm, "model_sent": ARMS[arm]}
        for attempt in range(5):
            bucket.take()
            sent = time.monotonic()
            try:
                reply = client.label(it["text"], dict(req, model=ARMS[arm]))
            except jev.Temporary as e:
                row.update(status="failed", error=str(e)[:300], attempts=attempt + 1)
                time.sleep(2**attempt)
                continue
            except jev.Rejected as e:
                row.update(status="rejected", error=str(e)[:300], attempts=attempt + 1)
                break
            except jev.Fatal as e:
                row.update(status="fatal", error=str(e)[:300])
                stop.set()
                break
            row.update(
                status="ok", model_reply=reply.model, answer=reply.answer, input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens, seconds=round(time.monotonic() - sent, 4), attempts=attempt + 1,
            )  # fmt: skip
            if (
                reply.model != ARMS[arm]
            ):  # the failure that would read as "1.14 changes nothing"
                row["status"] = "wrong_model"
                stop.set()
                break
            try:
                rec = jev.to_record(
                    it["text"],
                    reply.answer,
                    features=setup.features,
                    cutoff=setup.cutoff,
                    label_config=setup.label_config,
                )
                keep = (
                    "topic",
                    "intent",
                    "severity",
                    "sentiment",
                    "evidence_quote",
                    "needs_review",
                    "min_top_probability",
                )
                row["record"] = {k: rec[k] for k in keep}
            except labels.InvalidAnswer as e:
                row.update(status="invalid", error=str(e)[:300])
            break
        with lock:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            done[row["status"]] += 1

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(one, plan))
    out.close()
    with raw.open("rb") as f, gzip.open(CALLS, "wb") as g:
        g.write(f.read())
    raw.unlink()
    print(f"sent: {dict(done)} in {time.monotonic() - t0:.0f} s")
    if stop.is_set():
        raise Refused(
            "stopped: a fatal error or a reply naming the wrong model; read the calls file"
        )


# ---------------------------------------------------------------- the report
def _changed(x, y, ids, field):
    return sum(str(x[i][field]) != str(y[i][field]) for i in ids)


def _any_changed(x, y, ids):
    return sum(any(str(x[i][f]) != str(y[i][f]) for f in FIELDS) for i in ids)


def analyze(rows, items, hand, stored):
    """The report as a dict. Raises Refused when a check on the measurement itself fails."""
    status = Counter((r["arm"], r["status"]) for r in rows)
    bad = [
        r
        for r in rows
        if r["status"] in ("wrong_model", "fatal")
        or (r["status"] == "ok" and r["model_reply"] != r["model_sent"])
    ]
    if bad:
        raise Refused(
            f"{len(bad)} calls name another model or failed fatally; the first is for {bad[0]['id']}"
        )
    arm, raw, meta = ({a: {} for a in ARMS} for _ in range(3))
    for r in rows:
        if r["status"] == "ok":
            arm[r["arm"]][r["id"]] = r["record"]
            raw[r["arm"]][r["id"]] = r["answer"]
            meta[r["arm"]][r["id"]] = (r["input_tokens"], r["seconds"])
    arm["s13"] = stored

    # The comparison must count exactly the flips planted in a copy, and none between a set and itself.
    a = arm["a13"]
    ids_a = sorted(a)
    planted = {i: dict(a[i]) for i in ids_a}
    flips = ids_a[:: max(1, len(ids_a) // 7)][:7]
    for i in flips:
        planted[i]["topic"] = "zz_planted"
    if _changed(a, planted, ids_a, "topic") != len(flips) or _any_changed(a, a, ids_a):
        raise Refused("the comparison does not count planted flips correctly")

    sets = defaultdict(list)
    for it in items:
        for s in it["sets"]:
            sets[s].append(it["id"])
        if "random" in it["sets"]:
            sets[f"random:{it['lang']}"].append(it["id"])

    def common(*names, within=None):
        ids = set.intersection(*(set(arm[n]) for n in names))
        return sorted(ids & set(within)) if within is not None else sorted(ids)

    pairs = [
        ("s13", "a13"),
        ("b14", "c14"),
        ("a13", "b14"),
        ("a13", "c14"),
        ("s13", "b14"),
    ]
    report = {
        "status": {f"{k[0]}:{k[1]}": v for k, v in sorted(status.items())},
        "pairs": {},
        "sets": {k: len(v) for k, v in sets.items()},
    }
    for setname, members in sorted(sets.items()):
        for x, y in pairs:
            ids = common(x, y, within=members)
            if ids:
                n, changed = len(ids), _any_changed(arm[x], arm[y], ids)
                report["pairs"][f"{setname}|{x}-{y}"] = {
                    "n": n,
                    **{f: _changed(arm[x], arm[y], ids, f) for f in FIELDS},
                    "any": changed,
                    "any_pct": round(100 * changed / n, 2),
                }

    # Known answer: 1.13 now must reproduce the stored full run within rerun noise. Reruns so far changed 2.6% to 4%
    # (entries 33 and 35); 6% leaves room for that and stops well short of a version's effect.
    # If it does not, this script is not the pipeline, or 1.13 itself has moved, and no 1.14 figure means anything.
    anchor = report["pairs"]["random|s13-a13"]
    report["anchor"] = anchor
    if anchor["any_pct"] > 6:
        raise Refused(
            f"1.13 now differs from the stored run on {anchor['any_pct']}% of the random texts"
        )

    # No arm may collapse onto one answer.
    report["dist"] = {}
    for name in ("s13", "a13", "b14", "c14"):
        ids = common(name, within=sets["random"])
        d = {f: Counter(str(arm[name][i][f]) for i in ids) for f in FIELDS}
        report["dist"][name] = {f: dict(c.most_common()) for f, c in d.items()}
        if not (
            d["topic"].most_common(1)[0][1] < 0.8 * len(ids)
            and d["intent"].most_common(1)[0][1] < 0.85 * len(ids)
            and len(d["topic"]) >= 5
            and len(d["intent"]) >= 4
        ):
            raise Refused(f"{name} answers look degenerate")

    # Two names, one model: answers identical to the last digit on most texts would say so.
    ids = common("a13", "b14")
    same = sum(
        json.dumps(raw["a13"][i], sort_keys=True)
        == json.dumps(raw["b14"][i], sort_keys=True)
        for i in ids
    )
    report["identical_raw_a13_b14"] = {"n": len(ids), "identical": same}
    if same >= 0.9 * len(ids):
        raise Refused("1.14 answers are identical to 1.13's on most texts")

    report["hand"] = {}
    for name in ("s13", "a13", "b14", "c14"):
        ids = [i for i in hand if i in arm[name]]
        for reading in ("as_written", "by_rule"):
            got = Counter()
            for i in ids:
                g = dict(hand[i])
                if reading == "by_rule":
                    g["severity"] = labels.by_rule(g["intent"], g["severity"])
                wrong = [f for f in FIELDS if str(arm[name][i][f]) != str(g[f])]
                for f in FIELDS:
                    got[f] += f not in wrong
                got["all_three"] += not wrong
            report["hand"][f"{name}|{reading}"] = {"n": len(ids), **got}

    moves, shift = Counter(), []
    for i in common("a13", "b14"):
        x, y = arm["a13"][i], arm["b14"][i]
        for f in FIELDS:
            if str(x[f]) != str(y[f]):
                moves[f"{f}: {x[f]} -> {y[f]}"] += 1
        shift.append(y["severity"] - x["severity"])
    report["moves_a13_to_b14"] = dict(moves.most_common(25))
    report["severity_mean_shift_b14_minus_a13"] = round(statistics.mean(shift), 4)

    report["arm_stats"] = {}
    for name in ARMS:
        toks = [t for t, _ in meta[name].values() if t is not None]
        secs = sorted(s for _, s in meta[name].values())
        stats = {
            "ok": len(arm[name]),
            "input_tokens_mean": round(statistics.mean(toks), 1),
            "seconds_median": round(statistics.median(secs), 3),
            "seconds_p95": round(secs[int(0.95 * len(secs))], 3),
        }
        for setname in ("random", "multilingual", "random:non_english", "boycott"):
            ids = common(name, within=sets[setname])
            stats[setname] = {
                "n": len(ids),
                "needs_review": sum(arm[name][i]["needs_review"] for i in ids),
                "min_top_p_mean": round(
                    statistics.mean(arm[name][i]["min_top_probability"] for i in ids), 4
                ),
                "intent_unclear": sum(arm[name][i]["intent"] == "unclear" for i in ids),
            }
        report["arm_stats"][name] = stats
    ok = [r for r in rows if r["status"] == "ok"]
    tok_in, tok_out = (
        sum(r["input_tokens"] for r in ok),
        sum(r["output_tokens"] for r in ok),
    )
    report["spend"] = {
        "requests_ok": len(ok),
        "input_tokens": tok_in,
        "output_tokens": tok_out,
        "usd": round(tok_in * PRICE, 4),
    }
    return report


def multilingual_diffs(rows, items):
    """The non-English texts that 1.14 labels differently from 1.13 now, with their text, for a read by eye."""
    rec = {(r["id"], r["arm"]): r["record"] for r in rows if r["status"] == "ok"}
    out = []
    for it in items:
        x, y = rec.get((it["id"], "a13")), rec.get((it["id"], "b14"))
        if (
            "multilingual" in it["sets"]
            and x
            and y
            and any(str(x[f]) != str(y[f]) for f in FIELDS)
        ):
            z = rec.get((it["id"], "c14"))
            out.append(
                {
                    "id": it["id"],
                    "text": it["text"][:400],
                    **{
                        k: {f: v[f] for f in FIELDS} if v else None
                        for k, v in (("a13", x), ("b14", y), ("c14", z))
                    },
                }
            )
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--go", action="store_true", help="really call Jev")
    ap.add_argument(
        "--analyze",
        action="store_true",
        help="write report.json from the saved calls; no call",
    )
    ap.add_argument("--source", default=str(SOURCE), help="the 97.4 MB review file")
    a = ap.parse_args(argv)
    if not a.analyze:
        send(build_items(Path(a.source)), a.go)
        return 0
    items = json.loads(ITEMS.read_text(encoding="utf-8"))
    rows = load_rows()
    report = analyze(
        rows, items, hand_labels(), load_stored({it["id"] for it in items})
    )
    REPORT.write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if Path(a.source).exists():
        texts = {it["id"]: it["text"] for it in build_items(Path(a.source))}
        diffs = multilingual_diffs(
            rows, [dict(it, text=texts[it["id"]]) for it in items]
        )
        DIFFS.write_text(
            json.dumps(diffs, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            {
                k: report[k]
                for k in ("status", "anchor", "identical_raw_a13_b14", "spend")
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
