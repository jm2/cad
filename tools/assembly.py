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


def _manifold(shape):
    """Closed mesh of a part as a manifold3d Manifold (None if not manifold)."""
    import manifold3d as m3
    import trimesh

    from tools.model_io import mesh_arrays

    v, f = mesh_arrays(shape)
    tm = trimesh.Trimesh(v, f, process=True)
    tm.merge_vertices()
    try:
        m = m3.Manifold(m3.Mesh(vert_properties=np.asarray(tm.vertices, np.float32),
                                tri_verts=np.asarray(tm.faces, np.uint32)))
    except Exception:
        return None
    return m if m.status() == m3.Error.NoError and not m.is_empty() else None


def check_pairs(asm: Assembly, near: float = 2.0, exact: bool = False) -> list[PairResult]:
    """Mesh-first pair check: manifold3d booleans and min_gap screen every
    pair in milliseconds; exact BRep booleans / distances run only to confirm
    pairs the mesh flags (overlap, near-contact, or a clearance rule within
    reach). exact=True forces the BRep path for every pair."""
    mans = {} if exact else {k: _manifold(s) for k, s in asm.parts.items()}
    out = []
    for a, b in itertools.combinations(asm.parts, 2):
        sa, sb = asm.parts[a], asm.parts[b]
        key = frozenset((a, b))
        allowed = key in asm.allowed_contact
        req = asm.min_clearance.get(key)
        gap = _bbox_gap(sa, sb)
        if gap > max(near, req or 0):
            continue
        ma, mb = mans.get(a), mans.get(b)
        need_exact = exact or ma is None or mb is None
        if not need_exact:
            m_overlap = (ma ^ mb).volume() if gap == 0 else 0.0
            m_gap = 0.0 if m_overlap > 1e-3 else ma.min_gap(mb, max(near, (req or 0) + 0.5))
            # mesh chordal error is ~0.03 mm: confirm anything close exactly
            if m_overlap > 1e-3 or m_gap < 0.1 or (req is not None and m_gap < req + 0.1):
                need_exact = True
            else:
                out.append(PairResult(a, b, 0.0, float(m_gap), allowed, req, "ok", "mesh"))
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
    ap.add_argument("--exact", action="store_true",
                    help="BRep booleans/distances for every pair (slow)")
    ap.add_argument("--quiet", action="store_true", help="only print non-ok pairs")
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
    rows = check_pairs(asm, a.near, a.exact)
    shown = [r for r in rows if r.status in ("FAIL", "WARN")] if a.quiet else rows
    if a.quiet and not shown:
        n_c = sum(r.status == "contact" for r in rows)
        print(f"all {len(rows)} near pairs clear ({n_c} declared contacts)")
    else:
        print(format_pairs(shown))
    fails = [r for r in rows if r.status == "FAIL"]
    warns = [r for r in rows if r.status == "WARN"]
    bad += len(fails)
    print(f"ASSEMBLY {'PASS' if not bad else 'FAIL'}: {len(fails)} fail, "
          f"{len(warns)} warn, {len(rows)} pairs checked "
          f"[{time.perf_counter() - t0:.1f}s]")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
