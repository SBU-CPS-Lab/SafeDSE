#!/usr/bin/env python3
"""Synthetic pipelined-HSDF instance generator for SafeDSE.

Produces a chain 1->2->...->n with per-actor self-loops (auto-concurrency 1)
plus a few random forward dependencies.  Self-loops matter: without them the
single back-edge makes the whole graph one cycle and MCM = sum(T) regardless
of the mapping, which makes the instance trivially uninteresting.
"""
import argparse, random

def gen(n, P, seed=11, extra_frac=0.25, hi_frac=0.4):
    rnd = random.Random(seed)
    tok = [[-1] * n for _ in range(n)]
    for i in range(n - 1):
        tok[i][i + 1] = 0
    for i in range(n):
        tok[i][i] = 1                       # auto-concurrency 1
    for _ in range(int(n * extra_frac)):
        i, j = sorted(rnd.sample(range(n), 2))
        if tok[i][j] == -1:
            tok[i][j] = 0
    T = [rnd.randint(2, 9) for _ in range(n)]
    sil = [3 if rnd.random() < hi_frac else 1 for _ in range(n)]
    rows = " | ".join(",".join(map(str, r)) for r in tok)
    return (
        f"n={n};\nP={P};\n"
        f"tok=[|{rows}|];\n"
        f"T={T};\n"
        f"sil_req={sil};\n"
        f"pcost=[{','.join(['10'] * P)}];\n"
        f"dev_base=[{','.join(['10'] * n)}];\n"
        f"dev_k=array1d(0..4,[10,10,14,22,35]);\n"
        f"% suggested: mu_max={sum(T) * 4 // 10}  (40% of sum WCET)\n"
    )

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("-P", type=int, default=6)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("-o", default="-")
    a = ap.parse_args()
    s = gen(a.n, a.P, a.seed)
    print(s) if a.o == "-" else open(a.o, "w").write(s)
