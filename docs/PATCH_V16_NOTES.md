# Release v16 patch notes — Unified Simplex Engine

## Architectural objective

V16 removes the real/complex implementation boundary from Simplex. There is one `SimplexSolver`; scalar field (`real` or `complex`) and evolution policy (`hamiltonian`, `parabolic`, or unified `s6star`) are separate inputs.

## Core changes

- Added `src/simplex_policy.py` with `SimplexEvolutionPolicy` and `make_policy`.
- `SimplexSolver` now routes geometry, FEM operators, discrete commutators, Krylov/Arnoldi, and stage execution through the same code regardless of field.
- Added explicit V16 API: `field=` and `evolution=`.
- Preserved `field_type=` and legacy `scheme=` compatibility.
- Added `evolution="s6star"`, which uses the same canonical S6* commutator coefficients for both R and C; only the generator/dtype specialization changes.
- Added explicit tests proving that the R/C specializations share the same solver class, mesh/operator objects, and coefficient arrays.
- Updated Module 8 and certification call sites to use the explicit V16 API.
- Regenerated Module 8 data/figure outputs with V16 metadata.

## Mathematical scope

The real `s6star` specialization is an algebraic/geometric specialization of the canonical real-coefficient S6* commutator scheme. Because its real coefficients include negative stages, it is not advertised as a forward-positive stiff-diffusion method. Stable high-order parabolic propagation remains provided by the complex forward-positive BCChM-6 policy.

## Post-v16 performance & hardening enhancements

Same enhancement batch as the S6*-Adjoint Simplex backend, adapted to the NumPy/SciPy stack:

- **Adaptive-check cadence** (`adaptive_check_every`, default 1): the adaptive
  early-termination test in `kinetic_step_lanczos` evaluates a dense sub-expm
  at each checked iteration; the cadence evaluates it every N-th iteration
  past j=8.  Default 1 reproduces the original behavior exactly; checking less
  often can only delay termination slightly, never make it less accurate.
  (The torch-side host-sync cadence has no NumPy analog — there are no
  device syncs on CPU.)
- **Vectorized basis recombination**: `kinetic_step_lanczos` now combines the
  Krylov basis with a single BLAS matvec (`coeffs @ basis`) instead of a
  Python-level axpy loop; `h^2*c_val` hoisted out of the per-iterate
  `apply_B` closure in `commutator_potential_step`.  Results agree with the
  original to ~3e-16 (BLAS summation order).
- **Scaling benchmark** (`benchmarks/bench_simplex_scaling.py`): sweeps grid
  resolution and Krylov depth, reporting ms/step and the instrumented
  SpMV/step counts.  Sample: 1,024 nodes / krylov-16 -> ~199 ms/step at
  200 SpMVs/step.
- **Invariant documentation**: `integrate_simplex_s6` docstring pins the FSAL
  boundary-fusion exactness (the 2.0 factors are exact, not approximate);
  `commutator_potential_step` documents why complex stage coefficients force
  full Arnoldi instead of three-term Lanczos.
- **Field/dtype contract tests** (`tests/test_simplex_field_dtype.py`, 8 tests):
  complex128/float64 output contracts, V-shape and unknown-field errors,
  the theta!=0 commutator guard, and adaptive-cadence agreement.
- (`torch.compile` and the `retain_graph` pinning are torch/autograd-specific
  and do not apply to this NumPy engine.)

Validation: full pytest suite passes (28 tests), the 13-point certification
audit passes with the Simplex-Commutator at observed order p=5.99, and
enhanced-vs-original outputs agree to ~3e-16 across hamiltonian, parabolic,
and real s6star evolutions.
