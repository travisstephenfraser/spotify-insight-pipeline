"""Extras: (a) McNemar mid-p variant power (less conservative than exact) for E1; (b) E8 power at very high dependence."""
import math, random, importlib.util, io, contextlib
spec = importlib.util.spec_from_file_location("e1", "e1_mcnemar.py")
e1 = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()):
    spec.loader.exec_module(e1)

def midp(a, d):
    if d == 0: return 1.0
    lo = min(a, d - a)
    tail = sum(math.comb(d, k) for k in range(0, lo)) / 2**d + 0.5 * math.comb(d, lo) / 2**d
    return min(1.0, 2 * tail)

def power_midp(n, pA, pB, phi):
    p10, p01, _ = e1.cells(pA, pB, phi)
    pd = p10 + p01; q = p10 / pd
    pw = 0.0
    for d in range(n + 1):
        pdn = e1.binpmf(d, n, pd)
        for a in range(d // 2 + 1, d + 1):
            if midp(a, d) <= 0.05:
                pw += pdn * e1.binpmf(a, d, q)
    return pw
print("E1 mid-p McNemar (not the exact test; shown as the most favourable common variant), n=50, 80% vs 70%")
for phi in (0.0, 0.3, 0.5, 0.6, e1.phi_max(0.8, 0.7)):
    size = 2 * power_midp(50, 0.8, 0.8, min(phi, 0.99)) if phi < 0.99 else float('nan')
    print(f"  phi={phi:.3f}: power={power_midp(50, 0.8, 0.7, phi):.3f}   (size at 80/80, both directions: {size:.3f})")

spec8 = importlib.util.spec_from_file_location("e8", "e8_mae.py")
e8 = importlib.util.module_from_spec(spec8)
with contextlib.redirect_stdout(io.StringIO()):
    spec8.loader.exec_module(e8)
random.seed(99)
print("\nE8 main model at high shared-difficulty r, n=50, 40,000 reps: paired-t power, P(correct order)")
pa, pb = e8.PMF["main"]
for r in (0.8, 0.87, 0.9, 1.0):
    res = e8.run(pa, pb, r, 50, 40000, e8.t_crit(49))
    print(f"  r={r:.2f}: power={res[0]:.3f}  P(obs MAE_A<MAE_B)={res[2]:.3f}")
