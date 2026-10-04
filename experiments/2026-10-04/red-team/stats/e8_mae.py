"""E8: can MAE on a 5-level severity scale, n=50, distinguish true MAE 0.4 from 0.6?

STATED ERROR MODEL
  Per item, each classifier's absolute severity error |pred - truth| is drawn from a fixed pmf on {0,1,2,3}:
    main:        A (MAE 0.40): P(0)=.66 P(1)=.28 P(2)=.06          B (MAE 0.60): P(0)=.52 P(1)=.38 P(2)=.08 P(3)=.02
    heavy-tail:  A (MAE 0.40): P(0)=.70 P(1)=.22 P(2)=.06 P(3)=.02  B (MAE 0.60): P(0)=.58 P(1)=.28 P(2)=.10 P(3)=.04
  Dependence between the two classifiers on the same item ("shared difficulty"): with probability r both use the
  SAME uniform draw u (so a hard item is hard for both), otherwise independent draws. r=0 is independence.
  This keeps each classifier's marginal pmf, hence its true MAE, exactly fixed for every r.
TEST: paired t-test on d_i = |err_B,i| - |err_A,i|, two-sided alpha=0.05 (plus an exact sign test on nonzero d_i).
"""

import math
import random

random.seed(8)


# ---- Student t critical value via regularized incomplete beta (standard continued fraction)
def betacf(a, b, x):
    MAXIT, EPS, FPMIN = 300, 3e-14, 1e-300
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1 / d
        de = d * c
        h *= de
        if abs(de - 1) < EPS:
            break
    return h


def betai(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1 - x)
    )
    if x < (a + 1) / (a + b + 2):
        return bt * betacf(a, b, x) / a
    return 1 - bt * betacf(b, a, 1 - x) / b


def t_two_sided_p(t, df):
    return betai(df / 2, 0.5, df / (df + t * t))


def t_crit(df, alpha=0.05):
    lo, hi = 0.0, 50.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if t_two_sided_p(mid, df) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


print(
    "Anchor: t critical values (tables: df=10 -> 2.2281, df=49 -> 2.0096, df=120 -> 1.9799):",
    f"{t_crit(10):.4f} {t_crit(49):.4f} {t_crit(120):.4f}",
)

PMF = {
    "main": ({0: 0.66, 1: 0.28, 2: 0.06}, {0: 0.52, 1: 0.38, 2: 0.08, 3: 0.02}),
    "heavy-tail": (
        {0: 0.70, 1: 0.22, 2: 0.06, 3: 0.02},
        {0: 0.58, 1: 0.28, 2: 0.10, 3: 0.04},
    ),
}


def cum(pmf):
    out, s = [], 0.0
    for k in sorted(pmf):
        s += pmf[k]
        out.append((s, k))
    return out


def draw(c, u):
    for s, k in c:
        if u < s:
            return k
    return c[-1][1]


def moments(pmf):
    m = sum(k * p for k, p in pmf.items())
    v = sum(k * k * p for k, p in pmf.items()) - m * m
    return m, v


def comonotone_cov(ca, cb, ma, mb, grid=200000):
    s = 0.0
    for i in range(grid):
        u = (i + 0.5) / grid
        s += draw(ca, u) * draw(cb, u)
    return s / grid - ma * mb


_sign_cache = {}


def sign_p(k, m):
    if m == 0:
        return 1.0
    key = (min(k, m - k), m)
    if key not in _sign_cache:
        _sign_cache[key] = min(
            1.0, 2 * sum(math.comb(m, i) for i in range(0, key[0] + 1)) / 2**m
        )
    return _sign_cache[key]


def run(pa, pb, r, n, reps, tc):
    ca, cb = cum(pa), cum(pb)
    rnd = random.random
    rej_t = rej_sign = right = tie = wrong = 0
    for _ in range(reps):
        sd_ = sd2 = 0.0
        pos = neg = 0
        for _ in range(n):
            u = rnd()
            a = draw(ca, u)
            b = draw(cb, u) if rnd() < r else draw(cb, rnd())
            d = b - a
            sd_ += d
            sd2 += d * d
            if d > 0:
                pos += 1
            elif d < 0:
                neg += 1
        mean = sd_ / n
        var = (sd2 - n * mean * mean) / (n - 1)
        if mean > 0:
            right += 1
        elif mean == 0:
            tie += 1
        else:
            wrong += 1
        if var > 0:
            t = mean / math.sqrt(var / n)
            if abs(t) > tc and mean > 0:
                rej_t += 1
        if sign_p(pos, pos + neg) <= 0.05 and pos > neg:
            rej_sign += 1
    return rej_t / reps, rej_sign / reps, right / reps, tie / reps, wrong / reps


print(
    "\nAnchor: type-I error (both classifiers use the A pmf, true MAE 0.40 vs 0.40), n=50, two-sided t, counting either direction:"
)
for r in (0.0, 0.5):
    ca = cum(PMF["main"][0])
    tc = t_crit(49)
    rej = 0
    R = 100000
    for _ in range(R):
        s = s2 = 0.0
        for _ in range(50):
            u = random.random()
            a = draw(ca, u)
            b = draw(ca, u) if random.random() < r else draw(ca, random.random())
            d = b - a
            s += d
            s2 += d * d
        m = s / 50
        v = (s2 - 50 * m * m) / 49
        if v > 0 and abs(m / math.sqrt(v / 50)) > tc:
            rej += 1
    print(f"  r={r}: rejection rate {rej / R:.4f} (nominal 0.05)")

print("\nMain result, n=50, 100,000 simulated golden sets per row")
print(
    "  model       r     sd(d)  analytic power  power(paired t)  power(sign test)  P(obs MAE_A<MAE_B)  P(tie)  P(wrong order)  n for 80% power (analytic)"
)
for name, (pa, pb) in PMF.items():
    ma, va = moments(pa)
    mb, vb = moments(pb)
    cc = comonotone_cov(cum(pa), cum(pb), ma, mb)
    for r in (0.0, 0.3, 0.6):
        vd = va + vb - 2 * r * cc
        sdd = math.sqrt(vd)
        z = (mb - ma) * math.sqrt(50) / sdd
        ap = 0.5 * (1 + math.erf((z - 1.959964) / math.sqrt(2)))
        n80 = (1.959964 + 0.841621) ** 2 * vd / (mb - ma) ** 2
        res = run(pa, pb, r, 50, 100000, t_crit(49))
        print(
            f"  {name:10s}  {r:.1f}   {sdd:.3f}  {ap:.3f}           {res[0]:.3f}            {res[1]:.3f}             {res[2]:.3f}               {res[3]:.3f}   {res[4]:.3f}           {math.ceil(n80)}"
        )
    print(
        f"    (check: true MAE A={ma:.2f}, B={mb:.2f}; var A={va:.3f}, var B={vb:.3f}; comonotone cov={cc:.3f})"
    )

print("\nSimulated power of the paired t-test by n (main model, 20,000 reps each)")
print(
    "  r     " + "  ".join(f"n={n:<4d}" for n in (50, 75, 100, 125, 150, 175, 200, 250))
)
for r in (0.0, 0.3, 0.6):
    row = []
    for n in (50, 75, 100, 125, 150, 175, 200, 250):
        res = run(PMF["main"][0], PMF["main"][1], r, n, 20000, t_crit(n - 1))
        row.append(f"{res[0]:.3f} ")
    print(f"  {r:.1f}   " + "  ".join(row))

print(
    "\nSingle-classifier precision: 95% half-width of one MAE estimate at n=50 = 1.96*sd/sqrt(50)"
)
for name, (pa, pb) in PMF.items():
    for lab, p in (("A", pa), ("B", pb)):
        m, v = moments(p)
        print(f"  {name} {lab}: MAE {m:.2f} +/- {1.959964 * math.sqrt(v / 50):.3f}")
