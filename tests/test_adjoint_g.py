"""
S6*-Adjoint-G verification (Solution 1): the S6* Lie algebra needs NO scalar potential.

System (second order):  qdot = p,  pdot = F_theta(q)
Field (rotational, NON-conservative): F(x,y) = w(r)*(-y, x), w(r) = 1 + 0.3 r^2.
  curl_z = 2 + 1.2 r^2 != 0  -> NO scalar potential V exists.
  G2 (true Lie commutator, JVP) = J_F(q) F(q) = -w^2 * q   [analytic, verified vs FD]
  VJP (old code) = J_F(q)^T F(q) = grad(0.5 ||F||^2)  -- DIFFERENT for this field.
Integrator: S6* Real-Standard-33 coefficients (live, from src.coefficients),
  13-stage palindrome: for k in 0..5: p += h*B[k]*F - 2*h^3*C[k]*G2 ; q += h*A[k]*p,
  then final p += h*B[6]*F - 2*h^3*C[6]*G2.
Asserts: (1) order 6 with JVP-G2, order ~2 with VJP-G2 (the contrast);
         (2) reversibility fwd T then bwd locks at ~1e-15;
         (3) gradcheck: discrete adjoint (exact substep VJPs) matches central FD.
Reference: scipy DOP853 (rtol=1e-13) when available, else fine-h S6* self-reference.
"""
import sys, os
import numpy as np

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from src.coefficients import S6_REAL_A, S6_REAL_B, S6_REAL_C

A = np.asarray(S6_REAL_A, dtype=float)
B = np.asarray(S6_REAL_B, dtype=float)
C = np.asarray(S6_REAL_C, dtype=float)

# ---------------------------------------------------------------- field
def omega(r2):
    return 1.0 + 0.3 * r2

def F(q):
    x, y = q
    w = omega(x * x + y * y)
    return np.array([-w * y, w * x])

def J_F(q):
    x, y = q
    w = omega(x * x + y * y)
    return np.array([[-0.6 * x * y, -0.6 * y * y - w],
                     [0.6 * x * x + w, 0.6 * x * y]])

def G2_jvp(q):
    """True Lie commutator J_F(q) F(q). Analytic: -w^2 * q."""
    w = omega(q @ q)
    return -w * w * q

def G2_vjp(q):
    """Old code: grad(0.5 ||F||^2) = J_F(q)^T F(q)."""
    return J_F(q).T @ F(q)

def D_G2(q):
    """Jacobian of G2_jvp: -w^2 I - 1.2 w q q^T."""
    w = omega(q @ q)
    return -w * w * np.eye(2) - 1.2 * w * np.outer(q, q)

def Gdyn(z):
    return np.concatenate([z[2:], F(z[:2])])

# ---------------------------------------------------------------- S6* step (Solution 1)
def s6_step(z, h, g2_mode="jvp"):
    q = z[:2].copy()
    p = z[2:].copy()
    h3 = h * h * h
    for k in range(6):
        G2v = G2_jvp(q) if g2_mode == "jvp" else G2_vjp(q)
        p = p + (h * B[k]) * F(q) - (2.0 * h3 * C[k]) * G2v
        q = q + (h * A[k]) * p
    G2v = G2_jvp(q) if g2_mode == "jvp" else G2_vjp(q)
    p = p + (h * B[6]) * F(q) - (2.0 * h3 * C[6]) * G2v
    return np.concatenate([q, p])

def integrate(z0, T, h, g2_mode="jvp", store=False):
    n = int(round(T / abs(h)))
    assert abs(n * abs(h) - T) < 1e-12, "T must be a multiple of |h|"
    hs = h if h > 0 else -abs(h)
    z = np.array(z0, dtype=float)
    traj = [z.copy()] if store else None
    for _ in range(n):
        z = s6_step(z, hs, g2_mode)
        if store:
            traj.append(z.copy())
    return (z, traj) if store else z

def reference(z0, T):
    try:
        from scipy.integrate import solve_ivp
        sol = solve_ivp(lambda t, z: Gdyn(z), [0, T], z0, method="DOP853",
                        rtol=1e-13, atol=1e-15)
        return sol.y[:, -1]
    except ImportError:
        return integrate(z0, T, 0.005, g2_mode="jvp")

# ---------------------------------------------------------------- discrete adjoint (exact substep VJPs)
def discrete_adjoint(z0, T, h, q_target):
    zT, traj = integrate(z0, T, h, g2_mode="jvp", store=True)
    lam_q = zT[:2] - q_target
    lam_p = np.zeros(2)
    n = len(traj) - 1
    h3 = h * h * h
    for i in range(n, 0, -1):
        q, p = traj[i - 1][:2].copy(), traj[i - 1][2:].copy()
        sub = []
        for k in range(6):
            sub.append(("B", q.copy(), B[k], C[k]))
            p = p + (h * B[k]) * F(q) - (2.0 * h3 * C[k]) * G2_jvp(q)
            sub.append(("A", A[k]))
            q = q + (h * A[k]) * p
        sub.append(("B", q.copy(), B[6], C[6]))
        for item in reversed(sub):
            if item[0] == "A":
                lam_p = lam_p + (h * item[1]) * lam_q
            else:
                _, qq, bk, ck = item
                DM = (h * bk) * J_F(qq) - (2.0 * h3 * ck) * D_G2(qq)
                lam_q = lam_q + DM.T @ lam_p
    return np.concatenate([lam_q, lam_p])

# ---------------------------------------------------------------- tests
def main():
    q0 = np.array([0.7, -0.4])
    eps = 1e-7
    # self-check: Jacobian and G2 (JVP) vs finite differences
    Jfd = np.zeros((2, 2))
    for j in range(2):
        dq = np.zeros(2); dq[j] = eps
        Jfd[:, j] = (F(q0 + dq) - F(q0 - dq)) / (2 * eps)
    assert np.max(np.abs(J_F(q0) - Jfd)) < 1e-7, "Jacobian mismatch"
    Fv = F(q0)
    g2_fd = (F(q0 + eps * Fv) - F(q0 - eps * Fv)) / (2 * eps)
    assert np.max(np.abs(G2_jvp(q0) - g2_fd)) < 1e-7, "G2 (JVP) mismatch"
    assert np.max(np.abs(G2_jvp(q0) - G2_vjp(q0))) > 0.1, \
        "JVP and VJP coincide -- field is conservative, test is vacuous"
    assert abs(2.0 + 1.2 * (q0 @ q0)) > 1.0, "curl is zero -- field is conservative"

    T = 1.0
    z0 = np.array([0.7, -0.4, 0.3, 0.9])
    z_ref = reference(z0, T)

    # (1) order: JVP -> 6, VJP -> ~2
    hs = [0.2, 0.1, 0.05]
    errs_jvp, errs_vjp = [], []
    for h in hs:
        errs_jvp.append(np.max(np.abs(integrate(z0, T, h, "jvp") - z_ref)))
        errs_vjp.append(np.max(np.abs(integrate(z0, T, h, "vjp") - z_ref)))
    p_jvp = [np.log2(errs_jvp[i - 1] / errs_jvp[i]) for i in (1, 2)]
    p_vjp = [np.log2(errs_vjp[i - 1] / errs_vjp[i]) for i in (1, 2)]
    print(f"[Adjoint-G] order JVP-G2: {p_jvp[0]:.2f}, {p_jvp[1]:.2f} "
          f"(errs {errs_jvp[0]:.2e} {errs_jvp[1]:.2e} {errs_jvp[2]:.2e})")
    print(f"[Adjoint-G] order VJP-G2: {p_vjp[0]:.2f}, {p_vjp[1]:.2f} "
          f"(errs {errs_vjp[0]:.2e} {errs_vjp[1]:.2e} {errs_vjp[2]:.2e})")
    assert min(p_jvp) >= 5.5, f"JVP-G2 order {p_jvp} < 5.5"
    assert max(p_vjp) <= 2.5, f"VJP-G2 order {p_vjp} not broken as expected"

    # (2) reversibility locks at ~1e-15
    for h in (0.05, 0.1):
        z_fwd = integrate(z0, T, h, "jvp")
        z_back = integrate(z_fwd, T, -h, "jvp")
        rev = np.max(np.abs(z_back - z0))
        print(f"[Adjoint-G] reversibility h={h}: ||z_rec - z0||_inf = {rev:.3e}")
        assert rev < 1e-14, f"reversibility {rev:.2e} >= 1e-14"

    # (3) gradcheck: discrete adjoint vs central FD
    q_target = np.array([0.5, -0.3])
    h = 0.05

    def J_of_z0(z0v):
        zT = integrate(z0v, T, h, "jvp")
        d = zT[:2] - q_target
        return 0.5 * (d @ d)

    grad_adj = discrete_adjoint(z0, T, h, q_target)
    eps_fd = 1e-6
    grad_fd = np.zeros(4)
    for j in range(4):
        dz = np.zeros(4); dz[j] = eps_fd
        grad_fd[j] = (J_of_z0(z0 + dz) - J_of_z0(z0 - dz)) / (2 * eps_fd)
    rel = np.max(np.abs(grad_adj - grad_fd) / np.maximum(np.abs(grad_fd), 1e-12))
    print(f"[Adjoint-G] gradcheck max rel diff: {rel:.3e}")
    assert rel < 1e-7, f"gradcheck rel diff {rel:.2e} >= 1e-7"
    print("[Adjoint-G] ALL CHECKS PASSED")

if __name__ == "__main__":
    main()
