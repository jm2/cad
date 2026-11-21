"""Assembly-level checks: pairwise interference, contact and clearance.

    python -m tools.assembly MODEL.py|ASSEMBLY.step [--near 2.0] [--per-part]

For every pair of parts:
  overlap  > tol            -> FAIL unless the pair is in ALLOWED_CONTACT
  touching (distance ~ 0)   -> WARN unless the pair is in ALLOWED_CONTACT
  distance < MIN_CLEARANCE  -> FAIL (pairs listed in model.py MIN_CLEARANCE)
Pairs whose bounding boxes are further apart than --near (and that have no
MIN_CLEARANCE rule) are skipped as obviously clear.
--per-part also runs tools.check.report on each part (validity, watertight).
Exit status non-zero on any FAIL.
"""

from __future__ import annotations

import argparse
import itertools
import sys
import time
from dataclasses import dataclass

from tools.model_io import Assembly, load_assembly, volume

import numpy as np

OVERLAP_TOL = 1e-3   # mm^3
CONTACT_TOL = 1e-4   # mm


@dataclass
class PairResult:
    a: str
    b: str
    overlap: float
    distance: float
    allowed: bool
    required: float | None
    status: str           # ok / contact / WARN / FAIL
    note: str = ""


def _bbox_gap(sa, sb) -> float:
    A, B = sa.bounding_box(), sb.bounding_box()
    gaps = [max(B.min.X - A.max.X, A.min.X - B.max.X, 0),
            max(B.min.Y - A.max.Y, A.min.Y - B.max.Y, 0),
            max(B.min.Z - A.max.Z, A.min.Z - B.max.Z, 0)]
    return float(np.linalg.norm(gaps))


def check_pairs(asm: Assembly, near: float = 2.0) -> list[PairResult]:
    out = []
    for a, b in itertools.combinations(asm.parts, 2):
        sa, sb = asm.parts[a], asm.parts[b]
        key = frozenset((a, b))
        allowed = key in asm.allowed_contact
        req = asm.min_clearance.get(key)
        gap = _bbox_gap(sa, sb)
        if gap > max(near, req or 0):
            continue
        overlap = 0.0
        if gap == 0:
            try:
                common = sa & sb
                overlap = volume(common) if common is not None and common.solids() else 0.0
            except Exception as ex:  # boolean failure is itself a finding
                out.append(PairResult(a, b, float("nan"), float("nan"), allowed,
                                      req, "FAIL", f"boolean failed: {ex}"))
                continue
        overlap = overlap if overlap > OVERLAP_TOL else 0.0
        dist = 0.0 if overlap else float(sa.distance_to(sb))
        if overlap:
            status = "contact" if allowed else "FAIL"
            note = f"overlap {overlap:.4f} mm^3"
        elif dist < CONTACT_TOL:
            status = "contact" if allowed else "WARN"
            note = "touching"
        else:
            status, note = "ok", ""
        if req is not None and dist < req and not (allowed and overlap):
            status = "FAIL"
            note = (note + "; " if note else "") + f"clearance {dist:.3f} < {req}"
        out.append(PairResult(a, b, overlap, dist, allowed, req, status, note))
    return out


def format_pairs(rows: list[PairResult]) -> str:
    if not rows:
        return "no part pairs within range"
    w = max(len(r.a) + len(r.b) for r in rows) + 5
    L = [f"{'pair':{w}s} {'overlap mm3':>12s} {'gap mm':>9s} {'req':>6s}  status"]
    for r in rows:
        req = f"{r.required:g}" if r.required is not None else "-"
        L.append(f"{r.a + ' / ' + r.b:{w}s} {r.overlap:12.4f} {r.distance:9.3f} "
                 f"{req:>6s}  {r.status}{'  (allowed)' if r.allowed else ''}"
                 f"{'  ' + r.note if r.note else ''}")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("--near", type=float, default=2.0,
                    help="skip pairs whose bboxes are further apart (mm)")
    ap.add_argument("--per-part", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    asm = load_assembly(a.model)
    print(f"{len(asm)} parts: {', '.join(asm.parts)}")
    bad = 0
    if a.per_part:
        from tools.check import report
        for k, s in asm.parts.items():
            r = report(s)
            bad += not r.ok()
            print(f"  {k:24s} valid={r.valid} watertight={r.watertight} "
                  f"vol={r.volume_mm3:10.2f} mm3  {'PASS' if r.ok() else 'FAIL: ' + '; '.join(r.failures)}")
    rows = check_pairs(asm, a.near)
    print(format_pairs(rows))
    fails = [r for r in rows if r.status == "FAIL"]
    warns = [r for r in rows if r.status == "WARN"]
    bad += len(fails)
    print(f"ASSEMBLY {'PASS' if not bad else 'FAIL'}: {len(fails)} fail, "
          f"{len(warns)} warn, {len(rows)} pairs checked "
          f"[{time.perf_counter() - t0:.1f}s]")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
