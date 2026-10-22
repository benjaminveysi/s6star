# Release v16 — Unified Simplex Architecture

## Goal

V16 removes the implementation boundary between real and complex Simplex fields. `SimplexSolver` is now one common computational engine; scalar field and physical evolution are separate policy inputs.

## Shared core

- `SimplexMesh2D`: geometry, FEM mass/stiffness operators, M-inner product, Delaunay support.
- `SimplexEvolutionPolicy`: coefficient family, evolution generator, and commutator usage.
- `SimplexSolver`: common Krylov/Arnoldi, potential stages, kinetic stages, macro-step integration, and boundary fusion.

## Field/evolution separation

`field ∈ {real, complex}` controls representation. `evolution` controls the mathematical generator and coefficient family. They are not encoded as separate solver classes.

Built-in policies:

- `evolution="hamiltonian"`: canonical real-coefficient S6* commutator map, complex field required.
- `evolution="parabolic"`: forward-positive BCChM-6 baseline on the same engine; complex internal stages.
- `evolution="s6star"`: the same canonical S6* commutator algebra specialized to either scalar field. For the real specialization, negative coefficients imply that it is an algebraic/geometric formulation rather than a forward-positive stiff-diffusion method.

## API invariant

The spatial and numerical infrastructure must not branch on field type. Field-dependent behavior belongs only in the policy layer and final representation formatting.

## Validation

`tests/test_simplex_unified_architecture.py` verifies that the same `SimplexSolver` class uses the same mesh/operator infrastructure for real and complex specializations and for Hamiltonian/parabolic evolution policies.

## Compatibility

The legacy `field_type=` and `scheme=` parameters remain accepted so existing v15 call sites continue to run. New V16 code should prefer the explicit `field=` and `evolution=` arguments.

## Design rule

No numerical algorithm in the shared solver should branch on `field_type` to select a different spatial or stage implementation. Such choices belong in `SimplexEvolutionPolicy`.
