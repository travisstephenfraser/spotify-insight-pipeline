"""E1: exact McNemar (= exact two-sided sign test on discordant pairs) power.

Model: each of n items independently falls in one of four cells.
  A = better classifier (accuracy pA), B = worse (pB).
  errors eA~Bern(1-pA), eB~Bern(1-pB), phi = correlation of the two error indicators.
  p00 = P(both wrong) = (1-pA)(1-pB) + phi*sqrt(pA(1-pA)pB(1-pB))
  p10 = P(A right, B wrong) = (1-pB) - p00
  p01 = P(A wrong, B right) = (1-pA) - p00
Test: conditional on d = n10+n01, n10 ~ Bin(d, 1/2) under H0. Two-sided exact p = min(1, 2*min tail).
Power is computed EXACTLY (no simulation): sum over d of Bin(d; n, p10+p01) * P(reject | d).
A Monte Carlo cross-check and a null (type-I) check are included as known-answer anchors.
"""

import math
import random

ALPHA = 0.05


def logC(n, k):
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def binpmf(k, n, p):
    if p <= 0:
        return 1.0 if k == 0 else 0.0
    if p >= 1:
        return 1.0 if k == n else 0.0
    return math.exp(logC(n, k) + k * math.log(p) + (n - k) * math.log(1 - p))


_pcache = {}


def exact_p(a, d):
    """two-sided exact binomial p-value for a successes of d at p=0.5"""
    key = (a, d)
    if key in _pcache:
        return _pcache[key]
    if d == 0:
        return 1.0
    lo = min(a, d - a)
    tail = sum(math.exp(logC(d, k) - d * math.log(2)) for k in range(0, lo + 1))
    p = min(1.0, 2 * tail)
    _pcache[key] = p
    return p


def cells(pA, pB, phi):
    p00 = (1 - pA) * (1 - pB) + phi * math.sqrt(pA * (1 - pA) * pB * (1 - pB))
    p10 = (1 - pB) - p00
    p01 = (1 - pA) - p00
    if p01 < -1e-12 or p10 < -1e-12:
        return None
    p01 = max(p01, 0.0)
    p10 = max(p10, 0.0)
    return p10, p01, p00


def phi_max(pA, pB):
    # max P(both wrong) = min(1-pA, 1-pB)
    p00 = min(1 - pA, 1 - pB)
    return (p00 - (1 - pA) * (1 - pB)) / math.sqrt(pA * (1 - pA) * pB * (1 - pB))


def power(n, pA, pB, phi):
    """returns (power two-sided, power in correct direction, P(obs A > obs B), P(tie), P(obs A < obs B))"""
    c = cells(pA, pB, phi)
    if c is None:
        return None
    p10, p01, _ = c
    pd = p10 + p01
    q = p10 / pd if pd > 0 else 0.5
    pw = pw_dir = win = tie = lose = 0.0
    for d in range(0, n + 1):
        pdn = binpmf(d, n, pd)
        if pdn < 1e-15:
            continue
        for a in range(0, d + 1):
            pa = binpmf(a, d, q)
            w = pdn * pa
            if exact_p(a, d) <= ALPHA:
                pw += w
                if a > d - a:
                    pw_dir += w
            if a > d - a:
                win += w
            elif a == d - a:
                tie += w
            else:
                lose += w
    return pw, pw_dir, win, tie, lose


print(
    "=== Anchor 1: type-I error of the exact test at n=50, equal accuracy 0.80 (must be <= 0.05) ==="
)
for phi in (0.0, 0.3, 0.5):
    r = power(50, 0.80, 0.80, phi)
    print(f"  phi={phi:.1f}  size={r[0]:.4f}")

print(
    "\n=== Anchor 2: Monte Carlo cross-check of the exact power, n=50, 80 vs 70, phi=0.3 ==="
)
random.seed(12345)
c = cells(0.80, 0.70, 0.3)
p10, p01, p00 = c
p11 = 1 - p10 - p01 - p00
REPS = 200000
rej = 0
for _ in range(REPS):
    a = b = 0
    for _ in range(50):
        u = random.random()
        if u < p10:
            a += 1
        elif u < p10 + p01:
            b += 1
    if exact_p(a, a + b) <= ALPHA and a > b:
        rej += 1
ex = power(50, 0.80, 0.70, 0.3)
print(
    f"  exact directional power={ex[1]:.4f}   Monte Carlo ({REPS} reps)={rej / REPS:.4f}"
)

print("\n=== E1 main: n=50, true accuracy 80% vs 70% ===")
pm = phi_max(0.80, 0.70)
print(
    f"  phi_max (errors of the better one are a subset of the worse one's) = {pm:.3f}"
)
print(
    "  phi   p10    p01    E[discordant]  power(2-sided)  power(correct dir)  P(obsA>obsB)  P(tie)  P(obsA<obsB)"
)
for phi in (0.0, 0.2, 0.3, 0.5, 0.6, pm):
    p10, p01, _ = cells(0.80, 0.70, phi)
    r = power(50, 0.80, 0.70, phi)
    print(
        f"  {phi:.3f} {p10:.3f}  {p01:.3f}  {50 * (p10 + p01):6.2f}         {r[0]:.3f}           {r[1]:.3f}               {r[2]:.3f}         {r[3]:.3f}   {r[4]:.3f}"
    )

print(
    "\n=== Smallest true difference with >=80% power at n=50 (better classifier fixed at 80%) ==="
)
for phi in (0.0, 0.3, 0.5):
    found = None
    for k in range(1, 61):
        delta = k / 100
        pB = 0.80 - delta
        if cells(0.80, pB, phi) is None:
            continue
        r = power(50, 0.80, pB, phi)
        if r[1] >= 0.80:
            found = (delta, r[1])
            break
    print(
        f"  phi={phi:.1f}: smallest delta (1-pt grid) = {found[0] * 100:.0f} points (80% vs {80 - found[0] * 100:.0f}%), power={found[1]:.3f}"
    )

print("\n=== Same, worse classifier fixed at 70% (better = 70% + delta) ===")
for phi in (0.0, 0.3, 0.5):
    found = None
    for k in range(1, 30):
        delta = k / 100
        pA = 0.70 + delta
        if pA >= 1.0 or cells(pA, 0.70, phi) is None:
            continue
        r = power(50, pA, 0.70, phi)
        if r[1] >= 0.80:
            found = (delta, r[1])
            break
    if found:
        print(
            f"  phi={phi:.1f}: smallest delta = {found[0] * 100:.0f} points (70% vs {70 + found[0] * 100:.0f}%), power={found[1]:.3f}"
        )
    else:
        print(f"  phi={phi:.1f}: not reached below 100%")

print("\n=== n needed for 80% power, 80% vs 70% ===")


def n_needed(pA, pB, phi, target=0.80, nmax=900):
    p10, p01, _ = cells(pA, pB, phi)
    pd = p10 + p01
    q = p10 / pd
    # P(reject in correct direction | d)
    R = []
    for d in range(0, nmax + 1):
        s = 0.0
        # find smallest a (a > d/2) with exact p <= alpha: rejection region is upper tail a >= a*
        for a in range(d, d // 2, -1):
            if exact_p(a, d) <= ALPHA:
                s += binpmf(a, d, q)
            else:
                break
        R.append(s)
    first = None
    stable = None
    pw_by_n = {}
    for n in range(10, nmax + 1):
        pw = 0.0
        mu = n * pd
        sd = math.sqrt(n * pd * (1 - pd))
        lo = max(0, int(mu - 10 * sd))
        hi = min(n, int(mu + 10 * sd) + 1)
        for d in range(lo, hi + 1):
            pw += binpmf(d, n, pd) * R[d]
        pw_by_n[n] = pw
        if pw >= target and first is None:
            first = n
    # stable n: smallest n such that power >= target for all larger n in range
    for n in range(nmax, 9, -1):
        if pw_by_n[n] < target:
            stable = n + 1
            break
    return first, stable, pw_by_n


for phi in (0.0, 0.2, 0.3, 0.5, 0.6):
    first, stable, pw = n_needed(0.80, 0.70, phi)
    print(
        f"  phi={phi:.1f}: first n with power>=0.80: {first};  n from which it stays >=0.80: {stable};  power at n=50: {pw[50]:.3f}, n=100: {pw[100]:.3f}, n=200: {pw[200]:.3f}"
    )

print(
    "\n=== n needed for P(observed winner is the truly better one) >= 0.95, 80% vs 70% (no significance test) ==="
)
for phi in (0.0, 0.3, 0.5):
    for n in range(10, 400):
        r = power(n, 0.80, 0.70, phi)
        if r[2] >= 0.95:
            print(f"  phi={phi:.1f}: n={n}  P(obsA>obsB)={r[2]:.3f}, tie={r[3]:.3f}")
            break
