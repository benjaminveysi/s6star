"""Field / dtype / shape contract tests for the S6* Simplex solver engine.

These pin down the input contract of SimplexSolver so that a dtype, shape,
or policy mistake fails loudly at the boundary instead of deep inside the
Krylov loop.
"""
import os
import sys

import numpy as np
import pytest

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from src.simplex_mesh import SimplexMesh2D
from src.simplex_solver import SimplexSolver


@pytest.fixture(scope="module")
def mesh():
    return SimplexMesh2D(Lx=8.0, Ly=8.0, Nx=8, Ny=8, periodic=True)


@pytest.fixture(scope="module")
def V(mesh):
    return 0.05 * np.cos(mesh.nodes[:, 0]) * np.cos(mesh.nodes[:, 1])


def test_complex_field_returns_complex128(mesh, V):
    solver = SimplexSolver(mesh, field="complex", evolution="hamiltonian", V=V)
    assert solver.scalar_dtype == np.dtype(np.complex128)
    rng = np.random.RandomState(1)
    psi0 = rng.randn(mesh.N_nodes) + 1j * rng.randn(mesh.N_nodes)
    out = solver.integrate_simplex_s6(psi0, 2, 0.01, m_krylov=16)
    assert out.dtype == np.dtype(np.complex128)
    assert np.all(np.isfinite(out))


def test_real_field_returns_float64(mesh, V):
    solver = SimplexSolver(mesh, field="real", evolution="s6star", V=V)
    assert solver.scalar_dtype == np.dtype(np.float64)
    rng = np.random.RandomState(2)
    u0 = rng.randn(mesh.N_nodes)
    out = solver.integrate_simplex_s6(u0, 2, 0.001, m_krylov=16)
    assert out.dtype == np.dtype(np.float64)
    assert np.all(np.isfinite(out))
    assert solver.last_real_projection_error == 0.0


def test_v_wrong_shape_raises(mesh):
    with pytest.raises(ValueError, match="V must have shape"):
        SimplexSolver(mesh, field="complex", evolution="hamiltonian",
                      V=np.zeros(mesh.N_nodes + 1))


def test_unknown_field_raises(mesh):
    with pytest.raises(ValueError, match="Unknown field"):
        SimplexSolver(mesh, field="quaternion", evolution="hamiltonian")


def test_hamiltonian_requires_complex_field(mesh, V):
    with pytest.raises(ValueError, match="requires a complex field"):
        SimplexSolver(mesh, field="real", evolution="hamiltonian", V=V)


def test_nonlinear_commutator_guard(mesh, V):
    # theta != 0 with the commutator policy is explicitly unsupported and
    # must fail loudly, not silently drop the nonlinearity.
    solver = SimplexSolver(mesh, field="complex", evolution="hamiltonian",
                           theta=0.5, V=V)
    rng = np.random.RandomState(3)
    u0 = rng.randn(mesh.N_nodes) + 1j * rng.randn(mesh.N_nodes)
    with pytest.raises(ValueError, match="theta=0"):
        solver.commutator_potential_step(u0, solver.stages_b[0], 0.01,
                                         c_val=solver.stages_c[0], m=16)


def test_adaptive_check_cadence_matches_every_iteration(mesh, V):
    # adaptive_check_every=2 must agree with the original every-iteration
    # check to well within the adaptive tolerance.
    solver = SimplexSolver(mesh, field="complex", evolution="hamiltonian", V=V)
    rng = np.random.RandomState(4)
    u0 = rng.randn(mesh.N_nodes) + 1j * rng.randn(mesh.N_nodes)
    ref = solver.integrate_simplex_s6(u0.copy(), 3, 0.02, m_krylov=24,
                                      adaptive=True, adaptive_check_every=1)
    opt = solver.integrate_simplex_s6(u0.copy(), 3, 0.02, m_krylov=24,
                                      adaptive=True, adaptive_check_every=2)
    assert np.all(np.isfinite(opt))
    assert mesh.norm(ref - opt) < 1e-8


def test_empty_integration_returns_input(mesh, V):
    solver = SimplexSolver(mesh, field="complex", evolution="hamiltonian", V=V)
    rng = np.random.RandomState(5)
    u0 = rng.randn(mesh.N_nodes) + 1j * rng.randn(mesh.N_nodes)
    out = solver.integrate_simplex_s6(u0, 0, 0.01)
    assert np.array_equal(out, u0.astype(np.complex128))
