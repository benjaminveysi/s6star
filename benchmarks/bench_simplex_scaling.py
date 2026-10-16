#!/usr/bin/env python3
"""Scaling benchmark for the S6* Simplex solver engine (NumPy/SciPy).

Sweeps mesh resolution and Krylov subspace depth, timing macro-steps and
reporting the instrumented sparse-matvec counts (K-SpMVs + C-SpMVs) that the
mesh tracks.  Run this on the target machine before quoting throughput.

Example:
    python benchmarks/bench_simplex_scaling.py --grids 16,32,64 --m-krylov 8,16 --steps 4
    python benchmarks/bench_simplex_scaling.py --grids 64,128 --m-krylov 16 --steps 4 --csv scaling.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.simplex_mesh import SimplexMesh2D
from src.simplex_solver import SimplexSolver


def _parse_int_list(s: str):
    return [int(x) for x in s.split(",") if x.strip()]


def bench_one(n, m_krylov, steps, repeats, adaptive_check_every):
    mesh = SimplexMesh2D(Lx=6.0, Ly=6.0, Nx=n, Ny=n, periodic=True)
    V = 0.05 * (mesh.nodes[:, 0] ** 2 + mesh.nodes[:, 1] ** 2) + 0.02
    solver = SimplexSolver(mesh, field="complex", evolution="hamiltonian",
                           theta=0.0, V=V)
    rng = np.random.RandomState(0)
    u0 = rng.randn(mesh.N_nodes) + 1j * rng.randn(mesh.N_nodes)
    u0 /= mesh.norm(u0)
    h = 0.02

    # Warmup.
    solver.integrate_simplex_s6(u0.copy(), 1, h, m_krylov=m_krylov,
                                adaptive_check_every=adaptive_check_every)

    times = []
    spmv_totals = []
    for _ in range(repeats):
        mesh.reset_spmv_count()
        t0 = time.perf_counter()
        v = solver.integrate_simplex_s6(u0.copy(), steps, h, m_krylov=m_krylov,
                                        adaptive_check_every=adaptive_check_every)
        times.append(time.perf_counter() - t0)
        spmv_totals.append(mesh.get_total_sparse_mv_count())
        assert np.isfinite(mesh.norm(v))

    return {
        "grid": n,
        "nodes": mesh.N_nodes,
        "triangles": mesh.N_elements,
        "nnz_K": int(mesh.K.nnz),
        "m_krylov": m_krylov,
        "steps": steps,
        "ms_per_step": 1000.0 * min(times) / steps,
        "spmv_per_step": min(spmv_totals) / steps,
    }


def main():
    ap = argparse.ArgumentParser(description="S6* Simplex solver scaling benchmark")
    ap.add_argument("--grids", default="16,32,64",
                    help="comma-separated Nx=Ny grid resolutions")
    ap.add_argument("--m-krylov", default="8,16",
                    help="comma-separated Krylov depths")
    ap.add_argument("--steps", type=int, default=4)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--adaptive-check-every", type=int, default=1)
    ap.add_argument("--csv", default=None, help="write results to CSV file")
    args = ap.parse_args()

    rows = []
    for n in _parse_int_list(args.grids):
        for m in _parse_int_list(args.m_krylov):
            row = bench_one(n, m, args.steps, args.repeats,
                            args.adaptive_check_every)
            rows.append(row)
            print(
                f"grid {n:4d} | nodes {row['nodes']:6d} | tri {row['triangles']:6d} "
                f"| nnz_K {row['nnz_K']:7d} | krylov {m:2d} | "
                f"{row['ms_per_step']:8.1f} ms/step | "
                f"{row['spmv_per_step']:7.0f} SpMV/step",
                flush=True,
            )

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {args.csv}")


if __name__ == "__main__":
    main()
