"""E2 (winner's-curse bias), E3 (CI width), E4 (class counts in a sample of 50). Standard library only."""

import math
import random

random.seed(20261004)


def logC(n, k):
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def binpmf(k, n, p):
    if p <= 0:
        return 1.0 if k == 0 else 0.0
    if p >= 1:
        return 1.0 if k == n else 0.0
    return math.exp(logC(n, k) + k * math.log(p) + (n - k) * math.log(1 - p))


def bincdf(k, n, p):
    return sum(binpmf(i, n, p) for i in range(0, k + 1))


# ---------------------------------------------------------------- E2
print("=" * 78)
print("E2: bias of the selected winner's accuracy when scored on the same 50 labels")
print(
    "Model: per item, error indicators eA~Bern(1-pA), eB~Bern(1-pB), correlation phi."
)
print(
    "Pick the classifier with the higher observed accuracy on the 50 (ties: coin flip)."
)
print(
    "Bias = E[observed accuracy of the picked one - TRUE accuracy of the picked one]."
)
N = 50
REPS = 400000


def cells(pA, pB, phi):
    p00 = (1 - pA) * (1 - pB) + phi * math.sqrt(pA * (1 - pA) * pB * (1 - pB))
    p10 = (1 - pB) - p00  # A right, B wrong
    p01 = (1 - pA) - p00  # A wrong, B right
    p11 = 1 - p00 - p10 - p01
    assert min(p00, p10, p01, p11) >= -1e-12
    return p11, p10, p01, p00


def simulate(pA, pB, phi, reps=REPS, n=N):
    p11, p10, p01, p00 = cells(pA, pB, phi)
    c1, c2, c3 = p11, p11 + p10, p11 + p10 + p01
    sum_bias = 0.0
    sum_obs = 0.0
    picked_worse = 0
    over5 = 0
    rnd = random.random
    for _ in range(reps):
        a = b = 0
        for _ in range(n):
            u = rnd()
            if u < c1:
                a += 1
                b += 1
            elif u < c2:
                a += 1
            elif u < c3:
                b += 1
        if a > b or (a == b and rnd() < 0.5):
            obs, true = a / n, pA
        else:
            obs, true = b / n, pB
            if pB < pA:
                picked_worse += 1
        sum_bias += obs - true
        sum_obs += obs
        if obs - true >= 0.05:
            over5 += 1
    return sum_bias / reps, sum_obs / reps, picked_worse / reps, over5 / reps


def exact_bias_indep(p, n=N):
    """exact E[max(X,Y)]/n - p for X,Y iid Bin(n,p) (phi=0, equal accuracy) as a known-answer anchor"""
    pm = [binpmf(k, n, p) for k in range(n + 1)]
    cdf = []
    s = 0.0
    for k in range(n + 1):
        s += pm[k]
        cdf.append(s)
    e = 0.0
    for k in range(n + 1):
        prev = cdf[k - 1] if k > 0 else 0.0
        e += k * (cdf[k] ** 2 - prev**2)
    return e / n - p


print(
    f"\nAnchor (exact, no simulation): equal 80%/80%, independent errors: bias = {exact_bias_indep(0.80) * 100:+.2f} points"
)
print(
    "Anchor (no selection): a single classifier's accuracy on 50 is unbiased; simulated below as 'no-select'."
)
# no-selection anchor
s = 0.0
for _ in range(200000):
    s += sum(1 for _ in range(N) if random.random() < 0.80) / N - 0.80
print(f"  no-select mean error = {s / 200000 * 100:+.3f} points (should be ~0)")

print(f"\n{REPS} reps each, n=50")
print(
    "  pA    pB    phi   bias(points)  mean reported acc  P(picked truly worse)  P(overstated by >=5 pts)"
)
for pA, pB in ((0.80, 0.80), (0.80, 0.78), (0.80, 0.75), (0.80, 0.70)):
    for phi in (0.0, 0.3, 0.5):
        b, o, w, o5 = simulate(pA, pB, phi)
        print(
            f"  {pA:.2f}  {pB:.2f}  {phi:.1f}   {b * 100:+.2f}         {o * 100:.2f}%             {w:.3f}                  {o5:.3f}"
        )

print(
    "\nMore than two candidates (independent errors, all true accuracy 80%): exact E[max of k]/n - p by simulation"
)
for k in (2, 3, 5, 8):
    s = 0.0
    R = 100000
    for _ in range(R):
        best = 0
        for _ in range(k):
            x = sum(1 for _ in range(N) if random.random() < 0.80)
            if x > best:
                best = x
        s += best / N - 0.80
    print(f"  k={k}: bias = {s / R * 100:+.2f} points")

# ---------------------------------------------------------------- E3
print()
print("=" * 78)
print("E3: 95% CI for accuracy near 80% on n=50")
Z = 1.959963984540054


def wald(x, n):
    p = x / n
    h = Z * math.sqrt(p * (1 - p) / n)
    return p - h, p + h


def wilson(x, n):
    p = x / n
    den = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / den
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / den
    return c - h, c + h


def clopper(x, n, alpha=0.05):
    def solve(f, target):
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(mid) > target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    # lower: P(X >= x | p) = alpha/2 ; upper: P(X <= x | p) = alpha/2
    lower = (
        0.0 if x == 0 else solve(lambda p: 1 - (1 - bincdf(x - 1, n, p)), 1 - alpha / 2)
    )
    upper = 1.0 if x == n else solve(lambda p: bincdf(x, n, p), alpha / 2)
    return lower, upper


print(
    "  x/50   acc    Wald (lo,hi) half     Wilson (lo,hi) half    Clopper-Pearson exact (lo,hi) half"
)
for x in (38, 39, 40, 41, 42):
    w = wald(x, 50)
    wi = wilson(x, 50)
    cp = clopper(x, 50)
    print(
        f"  {x}/50  {x / 50:.2f}   ({w[0]:.3f},{w[1]:.3f}) ±{(w[1] - w[0]) / 2 * 100:.1f}   ({wi[0]:.3f},{wi[1]:.3f}) ±{(wi[1] - wi[0]) / 2 * 100:.1f}    ({cp[0]:.3f},{cp[1]:.3f}) ±{(cp[1] - cp[0]) / 2 * 100:.1f}"
    )
print(
    "  Known-answer anchor: Clopper-Pearson for 0/50 upper bound should be 1-0.025^(1/50) =",
    f"{1 - 0.025 ** (1 / 50):.4f}",
    "->",
    f"{clopper(0, 50)[1]:.4f}",
)
print(
    "  Smallest n whose 95% half-width is < 10 points at observed accuracy closest to 80%:"
)
for name, f in (("Wald", wald), ("Wilson", wilson), ("Clopper-Pearson", clopper)):
    for n in range(30, 200):
        x = round(0.8 * n)
        lo, hi = f(x, n)
        # require it to hold for this n and the next 4 (avoid lattice flukes)
        ok = True
        for m in range(n, n + 5):
            xm = round(0.8 * m)
            l2, h2 = f(xm, m)
            if (h2 - l2) / 2 >= 0.10:
                ok = False
        if ok:
            print(
                f"    {name}: n={n} (x={x}, half-width {((hi - lo) / 2) * 100:.2f} pts)"
            )
            break
print(
    "  Half-width at 80% for n=50,100,200,400 (Wald):",
    ", ".join(
        f"n={n}: ±{Z * math.sqrt(0.16 / n) * 100:.1f}" for n in (50, 100, 200, 400)
    ),
)

# ---------------------------------------------------------------- E4
print()
print("=" * 78)
print("E4: P(a class with prevalence p has >=5 examples in a uniform sample of 50)")
for p in (0.02, 0.05, 0.10, 0.125, 0.20):
    pr = 1 - bincdf(4, 50, p)
    p0 = binpmf(0, 50, p)
    print(
        f"  p={p:.3f}: expected count={50 * p:.2f}  P(X>=5)={pr:.4f}  P(X=0)={p0:.4f}  P(X>=1)={1 - p0:.4f}"
    )

# hypergeometric check (sampling without replacement from 660,609) for p=0.05
Npop = 660609


def hyper_ge5(K, Npop=Npop, n=50):
    def lc(a, b):
        return math.lgamma(a + 1) - math.lgamma(b + 1) - math.lgamma(a - b + 1)

    s = 0.0
    for k in range(0, 5):
        s += math.exp(lc(K, k) + lc(Npop - K, n - k) - lc(Npop, n))
    return 1 - s


print(
    f"  anchor: exact hypergeometric (without replacement, N=660,609) for 5%: {hyper_ge5(round(0.05 * Npop)):.4f} (binomial above should match)"
)


def multinomial_all_ge(prev, m=5, n=50, reps=300000):
    cum = []
    s = 0.0
    for q in prev:
        s += q
        cum.append(s)
    k = len(prev)
    ok = 0
    minc = 0
    for _ in range(reps):
        cnt = [0] * k
        for _ in range(n):
            u = random.random()
            for j in range(k):
                if u < cum[j]:
                    cnt[j] += 1
                    break
            else:
                cnt[k - 1] += 1
        if min(cnt) >= m:
            ok += 1
        minc += min(cnt)
    return ok / reps, minc / reps


print("\n  Joint: P(ALL 8 classes have >=5 of 50), by simulation (300k reps)")
u = [1 / 8] * 8
pr, mc = multinomial_all_ge(u)
print(
    f"    best case, perfectly uniform prevalence (12.5% each): P={pr:.4f}, mean smallest-class count={mc:.2f}"
)
sk = [0.30, 0.20, 0.15, 0.10, 0.10, 0.08, 0.05, 0.02]
pr, mc = multinomial_all_ge(sk)
print(f"    stated skewed vector {sk}: P={pr:.5f}, mean smallest-class count={mc:.2f}")
print(
    "  n needed so one class of prevalence p has >=5 with probability >=0.90 / >=0.95:"
)
for p in (0.02, 0.05, 0.10):
    res = []
    for target in (0.90, 0.95):
        n = 5
        while 1 - bincdf(4, n, p) < target:
            n += 1
        res.append(n)
    print(f"    p={p:.2f}: n={res[0]} (90%), n={res[1]} (95%)")
