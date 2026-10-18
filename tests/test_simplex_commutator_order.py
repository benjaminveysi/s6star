"""Independent validation of the discrete commutator realization.

The B stage must be realized as one exponential of b*V + h^2*c*C. Splitting
that stage into V/C exponentials lowers the temporal order when [V,C] != 0.
"""
import os, sys
import numpy as np
from scipy.linalg import expm

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from src.simplex_mesh import SimplexMesh2D
from src.simplex_solver import SimplexSolver


def _run(mesh, V, u0, T, hs):
    K = mesh.K.toarray()
    H = K / mesh.M_diag[:, None] + np.diag(V)
    exact = expm(-1j * T * H).dot(u0)
    errs = []
    for h in hs:
        solver = SimplexSolver(mesh, field='complex', evolution='hamiltonian', theta=0.0, V=V)
        v = solver.integrate_simplex_s6(u0.copy(), n_steps=round(T / h), h=h,
                                        m_krylov=16, use_fsal=True, adaptive=False)
        errs.append(mesh.norm(v - exact))
    return errs


def test_simplex_commutator_sixth_order_grid():
    mesh = SimplexMesh2D(Lx=10.0, Ly=10.0, Nx=16, Ny=16, periodic=True)
    V = 0.2 * np.cos(mesh.nodes[:, 0]) * np.cos(mesh.nodes[:, 1])
    r2 = mesh.nodes[:, 0] ** 2 + mesh.nodes[:, 1] ** 2
    u0 = np.exp(-0.5 * r2) * np.exp(1j * 0.5 * mesh.nodes[:, 0])
    u0 /= mesh.norm(u0)
    hs = [0.16, 0.08, 0.04, 0.02]
    errs = _run(mesh, V, u0, 0.16, hs)
    orders = [np.log2(errs[i-1] / errs[i]) for i in range(1, len(errs))]
    # First three asymptotic refinements should exhibit sixth-order behavior.
    assert min(orders[:3]) > 5.5, f"Observed orders too low: {orders}"
    assert max(abs(o - 6.0) for o in orders[:3]) < 0.4, f"Observed orders: {orders}"


def test_simplex_commutator_boundary_fusion_is_exact():
    mesh = SimplexMesh2D(Lx=8.0, Ly=8.0, Nx=8, Ny=8, periodic=True)
    V = 0.1 * np.cos(mesh.nodes[:, 0]) * np.cos(mesh.nodes[:, 1])
    np.random.seed(123)
    u0 = np.random.randn(mesh.N_nodes) + 1j * np.random.randn(mesh.N_nodes)
    u0 /= mesh.norm(u0)
    solver = SimplexSolver(mesh, field='complex', evolution='hamiltonian', theta=0.0, V=V)
    v_fused = solver.integrate_simplex_s6(u0.copy(), n_steps=2, h=0.02, m_krylov=16,
                                          use_fsal=True, adaptive=False)
    v_plain = solver.integrate_simplex_s6(u0.copy(), n_steps=2, h=0.02, m_krylov=16,
                                          use_fsal=False, adaptive=False)
    assert mesh.norm(v_fused - v_plain) < 1e-13
