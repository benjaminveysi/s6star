# S6*: Sixth-Order Commutator-Corrected Splitting

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

Reference implementation, high-precision coefficients, and benchmark suites for the **S6* 13-substep symmetric commutator-corrected splitting family**. 

Designed for high-precision Hamiltonian wave dynamics and stiff parabolic flows where standard high-order Yoshida compositions either drift or blow up.

## Why S6*?

- **True 6th-Order in the Free Lie Algebra:** Satisfies all eight order conditions through degree 5 without assuming `[B, [B, [B, A]]] = 0`. Verified local error scales at `O(h^7)`.
- **Exact Nonlinear Phase Integration:** For Gross–Pitaevskii (GPE) systems, the double commutator `G2 = [B, [B, A]]` drops spatial phase dependencies. The nonlinear step integrates via exact pointwise phase rotation—no internal ODE solvers needed.
- **Zero-Overhead Reversible Adaptivity:** Uses a time-reversible harmonic step controller (Hairer–Söderlind) that prevents secular energy and phase drift during soliton collisions. Recycles gradients in-place with **zero extra FFTs** per macro-step.
- **Parabolic Stability via Complex Splitting:** Bypasses the Sheng–Suzuki barrier for diffusion and imaginary-time GPE relaxation using forward-positive complex substeps (`Re(a_j) > 0`, `Re(b_j) > 0`) inside a narrow 18.4° sector. Where standard real-valued 4th/6th-order methods hit backward-heat `NaN` blowups, Complex-S6* stays rock solid.

## Benchmark Snapshot

**1. 1D Focusing GPE Two-Soliton Collision (`T = 12.0`, `N = 2048`)**
- At fixed step `h = 0.0050`, **Real-S6*** hits an L2 error of `3.69e-9` vs. `2.00e-8` for Yoshida-6 (**5.4x more accurate**, `1.78e-9` rad peak phase error).
- Dominates the Pareto frontier for high-precision regimes (errors below `1e-8`).
- Time-reversibility defect sits at `6.63e-14` (double-precision machine floor).

**2. Nonlinear Parabolic Reaction-Diffusion (`T = 0.096`, `N = 512`)**
- Classical Yoshida-4, Yoshida-6, and Real-S6* fail immediately (`NaN`) due to negative substeps.
- **Complex-S6* (Root 11)** remains unconditionally stable, reaching an L2 error of `6.19e-13` at `h = 0.0240`—outperforming BCChM-6 (Blanes et al., 2013) by **2x** across all tested step sizes.

## Quickstart

```bash
git clone https://github.com/benjaminveysi/s6star.git
cd s6star
pip install -r requirements.txt

# Run the reproduction suites
python benchmarks/module1_matrix_audit.py        # Free Lie algebra audit (p_local -> 7.00)
python benchmarks/module2_soliton_gpe.py         # GPE soliton collision & reversibility
python benchmarks/module3_parabolic_diffusion.py # Parabolic stability vs. Yoshida blowup
python benchmarks/module4_grand_suite.py         # Full 6-solver comparison
```
