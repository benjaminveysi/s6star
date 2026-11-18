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


def test_shared_mesh_does_not_clobber_commutator():
    """Regression test for BUG-NEW-1: constructing a non-commutator solver on the
    same mesh must not clobber the Hamiltonian solver's discrete commutator C_mat."""
    mesh = SimplexMesh2D(Lx=8.0, Ly=8.0, Nx=8, Ny=8, periodic=True)
    V = 0.2 * np.cos(mesh.nodes[:, 0]) * np.cos(mesh.nodes[:, 1])
    ham = SimplexSolver(mesh, field='complex', evolution='hamiltonian', V=V)
    # Instantiate a non-commutator solver on the exact same mesh instance:
    par = SimplexSolver(mesh, field='complex', evolution='parabolic', V=V)
    assert not par.uses_commutator
    assert ham.uses_commutator and ham.C_mat is not None

    psi = _initial_state(mesh, True)
    mesh.reset_spmv_count()
    _ = ham.step_simplex_s6(psi, 0.02, m_krylov=16)
    assert mesh.get_commutator_spmv_count() > 0, "C-SpMV was clobbered by shared mesh!"




def test_simplex_manifold_policy_and_c_spmv_mb4():
    """Verify S6* Simplex-Manifold (a1=-0.108) policy and GL2 m_krylov_B=4 C-SpMV optimization."""
    from scipy.linalg import expm
    mesh = SimplexMesh2D(Lx=10.0, Ly=10.0, Nx=12, Ny=12, periodic=True, mode='grid')
    x, y = mesh.nodes[:, 0], mesh.nodes[:, 1]
    V = 1.5 * np.cos(x) * np.cos(y) + 0.05 * (x**2 + y**2)
    psi0 = np.exp(-0.5 * (x**2 + y**2)) * np.exp(1j * (0.8 * x + 0.4 * y))
    psi0 /= mesh.norm(psi0)

    A_mat = mesh.K.toarray() / mesh.M_diag[:, None] + np.diag(V)
    psi_ref = expm(-1j * 0.16 * A_mat).dot(psi0)

    s_std = SimplexSolver(mesh, field='complex', evolution='hamiltonian', V=V)
    s_man = SimplexSolver(mesh, field='complex', evolution='hamiltonian', scheme='manifold', V=V)
    s_mb4 = SimplexSolver(mesh, field='complex', evolution='hamiltonian', scheme='manifold', V=V, m_krylov_B=4)

    assert s_man.policy.name == 'hamiltonian-s6-manifold-commutator'
    assert np.isclose(s_man.stages_a[0], -0.108)

    mesh.reset_spmv_count()
    v_std = s_std.integrate_simplex_s6(psi0.copy(), n_steps=4, h=0.04, m_krylov=16, use_fsal=True)
    c_spmv_16 = mesh.get_commutator_spmv_count()

    mesh.reset_spmv_count()
    v_man = s_man.integrate_simplex_s6(psi0.copy(), n_steps=4, h=0.04, m_krylov=16, use_fsal=True)
    err_std = mesh.norm(v_std - psi_ref)
    err_man = mesh.norm(v_man - psi_ref)

    mesh.reset_spmv_count()
    v_mb4 = s_mb4.integrate_simplex_s6(psi0.copy(), n_steps=4, h=0.04, m_krylov=16, use_fsal=True)
    c_spmv_4 = mesh.get_commutator_spmv_count()
    err_mb4 = mesh.norm(v_mb4 - psi_ref)

    # 1. C-SpMV count with m_krylov_B=4 is reduced by exact factor 4x (25 B-stages * 4 = 100 vs 25 * 16 = 400)
    assert c_spmv_16 == 4 * c_spmv_4, f"Expected 4x C-SpMV reduction, got {c_spmv_16} vs {c_spmv_4}"
    # 2. Manifold root significantly reduces error on oscillatory potential
    assert err_man < 0.25 * err_std, f"Expected manifold root improvement, got {err_man} vs {err_std}"
    # 3. GL2 m_B=4 matches m_B=16 to within 1% relative difference
    assert abs(err_mb4 - err_man) / err_man < 0.01, f"m_B=4 error {err_mb4} diverged from m_B=16 error {err_man}"


if __name__ == "__main__":
    test_one_engine_supports_complex_hamiltonian_and_complex_parabolic()
    test_one_engine_supports_real_field_specialization()
    test_shared_mesh_does_not_clobber_commutator()
    test_simplex_manifold_policy_and_c_spmv_mb4()
    print("test_simplex_unified_architecture: ALL PASSED")
