#!/usr/bin/env python3
"""Receiver-only upgrade: decode an unchanged CCSDS convolutional link with a learned telemetry prior
(pre-registered in bench/discovery/receiver_prior_preregistration.md).

Real Venus Express housekeeping packets (90 bytes) are sent uncompressed through the CCSDS K=7 rate-1/2
convolutional code (generators 171, 133 octal) over BPSK/AWGN. The receiver decodes each packet with
a Viterbi decoder, either plain or with per-bit a-priori log-probabilities from a column model
P(byte | same byte of the previously decoded packet), trained on the first half of the mission.

Usage: receiver_prior.py packets.bin
"""

import sys
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent.parent / "results" / "data"
PKT = 90
NB = PKT * 8
K = 7
NS = 1 << (K - 1)
G = (0o171, 0o133)
RUNS, STEPS = 40, 50  # 40 runs of 50 consecutive packets = 2000 frames per Eb/N0
EBN0 = np.arange(-1.0, 7.01, 0.5)


def parity(x):
    x = np.asarray(x)
    p = np.zeros_like(x)
    while np.any(x):
        p ^= x & 1
        x = x >> 1
    return p


# trellis: state = last K-1 input bits (newest in the LSB); input u -> register r = (state << 1) | u
ST = np.arange(NS)
OUT = np.zeros((NS, 2, 2), np.int64)
NXT = np.zeros((NS, 2), np.int64)
for s in range(NS):
    for u in range(2):
        r = (s << 1) | u
        OUT[s, u] = [parity(r & G[0]), parity(r & G[1])]
        NXT[s, u] = r & (NS - 1)
# predecessors of each next state: (prev state, input)
PREV = [[] for _ in range(NS)]
for s in range(NS):
    for u in range(2):
        PREV[NXT[s, u]].append((s, u))
PS = np.array([[p[0][0], p[1][0]] for p in PREV])
PU = np.array([[p[0][1], p[1][1]] for p in PREV])


def encode(bits):
    """bits: (B, n) -> coded (B, 2(n+K-1)) with zero tail."""
    B, n = bits.shape
    u = np.concatenate([bits, np.zeros((B, K - 1), np.int64)], 1)
    s = np.zeros(B, np.int64)
    out = np.empty((B, 2 * u.shape[1]), np.int64)
    for t in range(u.shape[1]):
        out[:, 2 * t:2 * t + 2] = OUT[s, u[:, t]]
        s = NXT[s, u[:, t]]
    return out


def viterbi(y, sig2, logp):
    """y: (B, 2T) received BPSK values; logp: (B, n, 2) a-priori log-probabilities of the n info bits."""
    B = y.shape[0]
    T = y.shape[1] // 2
    n = logp.shape[1]
    pm = np.full((B, NS), -1e18)
    pm[:, 0] = 0.0
    dec = np.empty((T, B, NS), np.int8)
    x = 1 - 2 * OUT  # (NS, 2, 2)
    for t in range(T):
        y1, y2 = y[:, 2 * t, None, None], y[:, 2 * t + 1, None, None]
        bm = (y1 * x[None, :, :, 0] + y2 * x[None, :, :, 1]) / sig2  # (B, NS, 2)
        if t < n:
            bm = bm + logp[:, t, None, :]
        else:
            bm[:, :, 1] = -1e18  # tail: input 0
        cand = pm[:, PS] + bm[:, PS, PU]  # (B, NS, 2)
        k = np.argmax(cand, axis=2)
        pm = np.take_along_axis(cand, k[..., None], 2)[..., 0]
        dec[t] = k
    s = np.zeros(B, np.int64)
    bits = np.empty((B, T), np.int64)
    rows = np.arange(B)
    for t in range(T - 1, -1, -1):
        k = dec[t, rows, s]
        bits[:, t] = PU[s, k]
        s = PS[s, k]
    return bits[:, :n]


def to_bits(pk):
    return np.unpackbits(pk.astype(np.uint8), axis=1).astype(np.int64)


class ColumnModel:
    """P(byte_k | previous packet's byte_k), KT counts with backoff to the column marginal."""

    def __init__(self, train):
        self.c = np.zeros((PKT, 256, 256))
        prev, cur = train[:-1], train[1:]
        for k in range(PKT):
            np.add.at(self.c[k], (prev[:, k], cur[:, k]), 1)
        m = self.c.sum(1) + 0.5
        self.marg = m / m.sum(1, keepdims=True)

    def probs(self, prev):
        """prev: (B, 90) bytes -> (B, 90, 256) probabilities."""
        cnt = self.c[np.arange(PKT)[None, :], prev]  # (B, 90, 256)
        return (cnt + self.marg[None]) / (cnt.sum(2, keepdims=True) + 1.0)

    def bit_logp(self, prev):
        p = self.probs(prev)
        vb = np.unpackbits(np.arange(256, dtype=np.uint8)[:, None], axis=1).astype(float)  # (256, 8)
        p1 = np.clip(p @ vb, 1e-9, 1 - 1e-9)  # (B, 90, 8)
        lp = np.stack([np.log(1 - p1), np.log(p1)], -1).reshape(p.shape[0], NB, 2)
        return lp

    def surprise(self, prev, cur):
        p = self.probs(prev)
        return -np.log2(np.take_along_axis(p, cur[..., None].astype(np.int64), 2)[..., 0]).sum(1)


def simulate(P, model, starts, ebn0, use_prior, rng):
    """Sequential decoding of RUNS runs of STEPS consecutive packets. Returns per-frame error flags."""
    R = 0.5 * NB / (NB + K - 1)
    sig2 = 1.0 / (2 * R * 10 ** (ebn0 / 10))
    prev_dec = P[starts - 1].copy()
    errs = np.zeros((STEPS, len(starts)), bool)
    for i in range(STEPS):
        cur = P[starts + i]
        bits = to_bits(cur)
        y = (1 - 2 * encode(bits)) + rng.normal(0, np.sqrt(sig2), (len(starts), 2 * (NB + K - 1)))
        lp = model.bit_logp(prev_dec) if use_prior else np.full((len(starts), NB, 2), np.log(0.5))
        d = viterbi(y, sig2, lp)
        errs[i] = np.any(d != bits, 1)
        prev_dec = np.packbits(d.astype(np.uint8), axis=1).astype(np.int64)
    return errs.T.ravel()


def ebn0_at(fer, target=1e-2):
    """Eb/N0 where FER crosses target (log-linear interpolation); NaN if never."""
    lf = np.log10(np.maximum(fer, 1e-6))
    for i in range(1, len(fer)):
        if fer[i - 1] > target >= fer[i]:
            a = (np.log10(target) - lf[i - 1]) / (lf[i] - lf[i - 1])
            return EBN0[i - 1] + a * (EBN0[i] - EBN0[i - 1])
    return float("nan")


def main():
    P = np.fromfile(sys.argv[1], np.uint8).reshape(-1, PKT).astype(np.int64)
    half = len(P) // 2
    model = ColumnModel(P[:half])
    rng = np.random.default_rng(0)
    starts = rng.choice(np.arange(half + 1, len(P) - STEPS), RUNS, replace=False)
    frames = np.stack([P[s:s + STEPS] for s in starts])  # (RUNS, STEPS, 90)
    prevs = np.stack([P[s - 1:s - 1 + STEPS] for s in starts])
    surp = model.surprise(prevs.reshape(-1, PKT), frames.reshape(-1, PKT))
    top = surp >= np.quantile(surp, 0.95)
    rows = []
    fer = {False: [], True: []}
    for e in EBN0:
        for up in (False, True):
            err = simulate(P, model, starts, e, up, np.random.default_rng(1000 + int(e * 10)))
            fer[up].append(err.mean())
            rows.append((e, up, err.mean(), err[top].mean(), err[~top].mean()))
            print(f"Eb/N0 {e:4.1f} dB  prior={up!s:5}  FER {err.mean():.4f}  (top-5% surprise {err[top].mean():.3f}, "
                  f"rest {err[~top].mean():.4f})", flush=True)
    import pandas as pd
    pd.DataFrame(rows, columns=["ebn0", "prior", "fer", "fer_top5_surprise", "fer_rest"]).to_csv(
        DATA / "receiver_prior.csv", index=False)
    e0, e1 = ebn0_at(np.array(fer[False])), ebn0_at(np.array(fer[True]))
    gain = e0 - e1
    print(f"\nEb/N0 for FER = 1e-2: plain {e0:.2f} dB, with prior {e1:.2f} dB -> gain {gain:.2f} dB")
    print(f"G1 (gain >= 1.0 dB): {'HOLDS' if gain >= 1.0 else 'REFUTED'}")
    i = int(np.nanargmin(np.abs(EBN0 - e1))) if np.isfinite(e1) else None
    if i is not None:
        r = [x for x in rows if x[0] == EBN0[i] and x[1]][0]
        q = [x for x in rows if x[0] == EBN0[i] and not x[1]][0]
        print(f"At {EBN0[i]:.1f} dB with prior: FER top-5% surprise {r[3]:.3f} vs rest {r[4]:.4f}; "
              f"plain decoder there: top {q[3]:.3f}, rest {q[4]:.4f}")
        print(f"G2 (risk concentrates on surprises: top-5% FER >= 5x the rest, with prior): "
              f"{'HOLDS' if r[3] >= 5 * max(r[4], 1e-9) else 'REFUTED'}")
        print(f"G3 (surprising packets are decoded worse with the prior than without, same Eb/N0): "
              f"{'HOLDS' if r[3] > q[3] else 'REFUTED'}")


if __name__ == "__main__":
    main()
