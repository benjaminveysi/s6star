"""V16 architectural tests: one solver engine, independent field and evolution policies."""
import os
import sys
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.simplex_mesh import SimplexMesh2D
from src.simplex_solver import SimplexSolver


def _initial_state(mesh, complex_state):
    r2 = mesh.nodes[:, 0] ** 2 + mesh.nodes[:, 1] ** 2
    u = np.exp(-0.5 * r2)
    if complex_state:
        u = u * np.exp(0.3j * mesh.nodes[:, 0])
    return u / mesh.norm(u)


def test_one_engine_supports_complex_hamiltonian_and_complex_parabolic():
    mesh = SimplexMesh2D(Lx=8.0, Ly=8.0, Nx=8, Ny=8, periodic=True)
    V = 0.05 * np.cos(mesh.nodes[:, 0]) * np.cos(mesh.nodes[:, 1])

    ham = SimplexSolver(mesh, field='complex', evolution='hamiltonian', V=V)
    par = SimplexSolver(mesh, field='complex', evolution='parabolic', V=V)

    unified_c = SimplexSolver(mesh, field='complex', evolution='s6star', V=V)
    unified_r = SimplexSolver(mesh, field='real', evolution='s6star', V=V)

    assert type(ham) is type(par) is type(unified_c) is type(unified_r) is SimplexSolver
    assert ham.mesh is par.mesh is unified_c.mesh is unified_r.mesh
    assert ham.mesh.K is par.mesh.K is unified_c.mesh.K is unified_r.mesh.K
    assert unified_c.policy.name == unified_r.policy.name == 's6star-simplex-unified'
    assert np.array_equal(unified_c.stages_a, unified_r.stages_a)
    assert np.array_equal(unified_c.stages_b, unified_r.stages_b)
    assert np.array_equal(unified_c.stages_c, unified_r.stages_c)
    assert unified_c.policy.generator == -1j
    assert unified_r.policy.generator == -1.0

    psi = _initial_state(mesh, True)
    u = _initial_state(mesh, True)
    psi1 = ham.step_simplex_s6(psi, 0.01, m_krylov=16)
    u1 = par.step_simplex_s6(u, 0.001, m_krylov=16)

    assert np.iscomplexobj(psi1)
    assert np.iscomplexobj(u1)
    assert np.all(np.isfinite(psi1))
    assert np.all(np.isfinite(u1))


def test_one_engine_supports_real_field_specialization():
    mesh = SimplexMesh2D(Lx=8.0, Ly=8.0, Nx=8, Ny=8, periodic=True)
    V = 0.02 * np.cos(mesh.nodes[:, 0]) * np.cos(mesh.nodes[:, 1])
    real_solver = SimplexSolver(mesh, field='real', evolution='s6star', V=V)
    u = _initial_state(mesh, False)
    u1 = real_solver.step_simplex_s6(u, 0.001, m_krylov=16)

    assert isinstance(u1, np.ndarray)
    assert not np.iscomplexobj(u1)
    assert np.all(np.isfinite(u1))
    assert real_solver.last_real_projection_error == 0.0
    assert real_solver.policy.name == 's6star-simplex-unified'
