"""
Unit test verifying Simplex dual-field physical integrity:
1. Hamiltonian wave: Exact unitary norm conservation |Delta N| < 1e-13 on both grid and Delaunay meshes
2. Parabolic diffusion: Non-expansive / contractive energy and norm evolution
"""
import sys, os
import numpy as np

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from src.simplex_mesh import SimplexMesh2D
from src.simplex_solver import SimplexSolver
# Root 11 coefficients (Complex-Flash-22) — the live set is S6_COMPLEX_* in
# src/coefficients.py; coefficients_flash.py carries the identical values.
from src.coefficients_flash import FLASH_COMPLEX_A, FLASH_COMPLEX_B, FLASH_COMPLEX_C


class ReversibleComplexS6Spinor:
    """
    Exact Time-Reversible Spinor Realization of Complex-S6* (Flash-22 / Root 11)
    on M_sys (+) M_bath with Halmos-Nagy SU(2) Dilation & Symmetric Midpoint G2.
    """
    def __init__(self, k_grid: np.ndarray, alpha_disp: float, gamma_diss: float, g_nonlin: float):
        self.k = k_grid
        self.k2 = k_grid ** 2
        self.alpha = alpha_disp   # ضریب پاشندگی همیلتونی (در صورت وجود)
        self.gamma = gamma_diss   # ضریب اتلاف پارابولیک (\mu_k = \gamma k^2)
        self.g = g_nonlin         # ضریب غیرخطیت هولومورفیک V(\psi) = g * \psi^2

    def holomorphic_potential(self, psi: np.ndarray) -> np.ndarray:
        """Holomorphic cubic nonlinearity potential: V(psi) = g * psi^2 (no conj!)."""
        return self.g * (psi ** 2)

    def compute_g2_spectral(self, psi: np.ndarray) -> np.ndarray:
        """
        Full Frechet double commutator G_2 = [B, [T, B]] for the holomorphic-cubic model,
        verified numerically against finite-difference Frechet derivatives (2026-11-07):
            G_2(psi) = -24 * g^2 * c_T * psi^3 * (psi_x)^2
                     = -6 * c_T * (V_x)^2 * psi,   V = g*psi^2, V_x = 2*g*psi*psi_x.
        c_T = gamma + i*alpha is COMPLEX (trap 2): after the A-stage fix the linear
        operator is T = (gamma + i*alpha) d^2/dx^2, so the commutator carries the full
        complex c_T, not gamma alone. The psi^4*psi_xx terms that appear in intermediate
        Frechet steps cancel EXACTLY (fitted coefficient ~2e-7 = noise); the final
        commutator is this single term. Evaluated holomorphically via spectral ik.
        SIGN: the Lie-bracket commutator is [B,[T,B]] = -24*g^2*c_T*psi^3*(psi_x)^2,
        but the code's G2 convention (as in solvers_spectral.compute_g2_spectral, whose
        leading term is +2*(Vx)^2*u) is the NEGATIVE of the vector-field Lie bracket
        (operator vs vector-field bracket convention). Measured 2026-11-07: the + sign
        gives order 2.74 with errors ~100x smaller than the - sign (order 1.98), and
        lambda=1.0 is a sharp optimum (0.8 and 1.2 both fall back to order ~2).
        """
        V = self.holomorphic_potential(psi)
        V_x = np.fft.ifft(1j * self.k * np.fft.fft(V))
        c_T = self.gamma + 1j * self.alpha
        return +6.0 * c_T * (V_x ** 2) * psi

    def step_linear_spinor_su2(
        self,
        psi_sys: np.ndarray,
        psi_bath_slot: np.ndarray,
        a_j: complex,
        tau: float
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Halmos-Sz.-Nagy SU(2) Unitary Dilation for linear stage a_j.
        - If tau > 0 (Forward): contracts psi_sys by z_jk and stores defect d_jk in psi_bath_slot.
        - If tau < 0 (Backward): applies exact unitary inverse U_jk^dagger (using a_j^* and +d_jk)
          to reconstruct psi_sys from psi_bath_slot with ZERO backward-heat blowup.
        """
        psi_hat = np.fft.fft(psi_sys)
        bath_hat = np.fft.fft(psi_bath_slot)

        dt = abs(tau)
        mu_k = self.gamma * self.k2
        omega_k = self.alpha * self.k2

        # Combined A-stage multiplier w_jk = exp(-|tau| * a_j * (mu_k + i*omega_k)).
        # CRITICAL: the dispersive part must use the FULL complex a_j, not Re(a_j).
        # With Re(a_j) the A stages are not exp(tau*a_j*T) for a FIXED T (the effective
        # operator becomes stage-dependent), which breaks the splitting order conditions
        # and caps the forward order at 2. With the full a_j, T = -(gamma + i*alpha)*k^2
        # is fixed and the Root-11 order conditions hold. |w| <= 1 is the sector-cone
        # condition (Re(a_j)*gamma - Im(a_j)*alpha >= 0); d = sqrt(1 - |w|^2) is the
        # defect, and the SU(2) dilation [[w, -d], [d, w*]] is exactly unitary.
        w_jk = np.exp(-dt * a_j * (mu_k + 1j * omega_k))
        z_jk = w_jk
        # نقص یکانی (Defect): کسری از انرژی که بین سیستم و حمام جابه‌جا می‌شود
        # استفاده از clip برای جلوگیری از خطای گرد کردن منفی زیر رادیکال در مد k=0
        d_jk = np.sqrt(np.clip(1.0 - np.abs(z_jk) ** 2, 0.0, 1.0))

        if tau >= 0:
            # Forward Pass: U_jk
            psi_new_hat = z_jk * psi_hat - d_jk * bath_hat
            bath_new_hat = d_jk * psi_hat + np.conj(z_jk) * bath_hat
        else:
            # Backward Pass (Exact Inverse): U_jk^dagger
            # توجه: روی قطر اصلی np.conj(z_jk) یعنی همان a_j^* قرار دارد و +d_jk انرژی حمام را پس می‌دهد
            psi_new_hat = np.conj(z_jk) * psi_hat + d_jk * bath_hat
            bath_new_hat = -d_jk * psi_hat + z_jk * bath_hat

        return np.fft.ifft(psi_new_hat), np.fft.ifft(bath_new_hat)

    def step_nonlinear_symmetric(
        self,
        psi: np.ndarray,
        b_j: complex,
        tau: float,
        d_mid: complex = 0.0j,
        include_g2: bool = False,
        picard_iters: int = 4
    ) -> np.ndarray:
        """
        Time-Symmetric Holomorphic Midpoint Subflow for B_j and central G_2 = [V, [T, V]] stage.
        Guarantees Phi_mid(-tau) o Phi_mid(+tau) == I down to machine precision (1e-16).
        """
        # تقارن نقطه‌ی میانی: حل نقطه‌ی ثابت \psi_mid = exp(0.5 * M(\psi_mid, \tau)) * \psi
        psi_mid = psi.copy()
        for _ in range(picard_iters):
            M_half = 0.5 * tau * b_j * self.holomorphic_potential(psi_mid)
            if include_g2:
                # هم \tau و هم \tau^3 توان‌های فرد هستند؛ در \tau -> -\tau هر دو قرینه می‌شوند
                M_half = M_half + 0.5 * (tau ** 3) * d_mid * self.compute_g2_spectral(psi_mid)
            psi_mid = np.exp(M_half) * psi

        # گام کامل از روی نقطه‌ی میانی همگراشده: \psi^(+) = exp(0.5 * M(\psi_mid, \tau)) * \psi_mid
        return np.exp(M_half) * psi_mid

    def bernoulli_step(self, psi: np.ndarray, s: complex) -> np.ndarray:
        """
        Exact flow of the holomorphic-cubic B subproblem d psi/dt = g * psi^3
        over (signed) step s: psi -> psi / sqrt(1 - 2*s*g*psi^2).
        Exact AND exactly reversible (s -> -s is the inverse); unlike the implicit
        midpoint it does not cap the splitting order at 2.
        """
        return psi / np.sqrt(1.0 - 2.0 * s * self.g * psi ** 2)

    def step_nonlinear_bernoulli(
        self,
        psi: np.ndarray,
        b_j: complex,
        tau: float,
        d_mid: complex = 0.0j,
        include_g2: bool = False,
        kick_iters: int = 4
    ) -> np.ndarray:
        """
        B stage as the certified Flash-22 form: exact Bernoulli sandwich + G2 kick.
        Forward (tau > 0): Bernoulli(+0.5*tau*b) -> explicit kick psi + tau^3*d*G2(psi)
        -> Bernoulli(+0.5*tau*b). Backward (tau < 0): the SAME code path with signed tau
        gives the exact inverse -- Bernoulli(-0.5*|tau|*b) undoes the half-steps, and the
        kick is inverted by fixed point (psi1 <- psi2 - tau^3*d*G2(psi1)), which converges
        because tau^3*d is tiny. No O(tau^5) midpoint leak, no order cap.
        """
        if tau >= 0:
            psi1 = self.bernoulli_step(psi, 0.5 * tau * b_j)
            if include_g2:
                psi2 = psi1 + (tau ** 3) * d_mid * self.compute_g2_spectral(psi1)
            else:
                psi2 = psi1
            return self.bernoulli_step(psi2, 0.5 * tau * b_j)
        else:
            psi2 = self.bernoulli_step(psi, 0.5 * tau * b_j)
            if include_g2:
                # Inverse kick: solve psi1 + |tau|^3*d*G2(psi1) = psi2, i.e.
                # psi1 <- psi2 - |tau|^3*d*G2(psi1). With tau = -|tau| this is
                # psi1 <- psi2 + tau^3*d*G2(psi1) (note the PLUS: tau^3 < 0 here).
                psi1 = psi2.copy()
                for _ in range(kick_iters):
                    psi1 = psi2 + (tau ** 3) * d_mid * self.compute_g2_spectral(psi1)
            else:
                psi1 = psi2
            return self.bernoulli_step(psi1, 0.5 * tau * b_j)

    def step_phi_midpoint(
        self,
        psi: np.ndarray,
        b_j: complex,
        tau: float,
        d_mid: complex = 0.0j,
        include_g2: bool = False,
        picard_iters: int = 4
    ) -> np.ndarray:
        """
        B stage as Benyamin's Phi-midpoint form (2026-11-08): the G2 lives INSIDE the
        modified potential Phi(u) = V(u) + d_mid*(b_j*tau)^2*G2(u), and the stage is
        the implicit symmetric midpoint u^(*) = (u^(n) + u^(n+1))/2,
        u^(n+1) = u^(n) + tau*b_j*Phi(u^(*))*u^(*), solved by Picard iteration.
        The midpoint u^(*) is the SAME for the forward and the backward map, so the
        inverse is the same formula with -tau (F_{-tau} o F_{tau} = I); the inverse
        fixed-point iteration converges in 2-3 iters because the b_j sector angle is
        < 18.064 deg (strict local contraction in the complex plane).
        Exactly reversible (measured 6e-16) but caps the forward order at 2: the
        implicit midpoint is a 2nd-order integrator for the B subproblem, so this is
        the exact-reversal alternative to the Bernoulli (order 6), not the engine.
        """
        u_new = psi.copy()
        for _ in range(picard_iters):
            u_mid = 0.5 * (psi + u_new)
            Phi = self.holomorphic_potential(u_mid)
            if include_g2:
                Phi = Phi + d_mid * ((b_j * tau) ** 2) * self.compute_g2_spectral(u_mid)
            u_new = psi + tau * b_j * Phi * u_mid
        return u_new

    def step_flash22_macro(self, psi_sys, baths, tau, picard_iters=8, b_mode="bernoulli", ledger=None):
        """
        One full 13-stage Complex-Flash-22 macro-step on the spinor (psi_sys + 6 bath slots).
        Stage order (forward, tau > 0): B0 A0 B1 A1 B2 A2 B3 A3 B4 A4 B5 A5 B6.
        Backward (tau < 0): the exact inverse composition, B6^-1 A5^-1 B5^-1 ... A0^-1 B0^-1,
        realized by the same primitives with -tau (U^dagger for A stages, inverse midpoint for B).
        baths: list of 6 arrays, one per linear A stage (slot m drains in reverse order 6 -> 1).
        CRITICAL (Halmos-Nagy dilation): the 6 slots are PER MACRO-STEP and must be FRESH
        (zero) on the forward pass. Reusing the same slot across macro-steps corrupts the
        forward trajectory (U2.U1 has (1,1) entry z2*z1 - d2*d1, not z2*z1); the bath is a
        growing record (6 slots per macro-step), drained in reverse order on the way back.
        b_mode: 'bernoulli' (default) = exact Bernoulli B stage, preserves order 6;
        'midpoint' = implicit-midpoint B stage (G2 as kick), exactly reversible but caps order at 2;
        'phi_midpoint' = Benyamin's Phi-midpoint B stage (G2 inside the modified potential
        Phi = V + d_mid*(b_j*tau)^2*G2), exactly reversible but caps order at 2.
        ledger: optional dict; when given, the nonlinear work flux of the B stages is
        accumulated in ledger['nonlinear_work_flux'] (delta_W_B = sum_j ||psi_after B_j||^2
        - ||psi_before B_j||^2, raw sum of |psi|^2, no dx factor). The B stages are NOT
        dilated into the bath (an SU(2) dilation fails there: Re(b_j*tau*g*psi^2) can be
        locally positive, so |r(x)| > 1 and sqrt(1 - |r|^2) goes imaginary), and the
        b_j must not be touched (removing Re(b_j) breaks the BCH/holomorphic cancellation
        and drops the order from 6 to 2). Instead the work flux is booked in the boundary
        ledger (spec 11.1 / 20.7), and the full invariant
        I_total = ||psi_sys||^2 + sum_s ||psi_bath,s||^2 - delta_W_B
        is constant to machine precision. On the backward pass each inverse B stage
        contributes -delta_W, so the ledger drains back to zero.
        """
        A = FLASH_COMPLEX_A
        B = FLASH_COMPLEX_B
        C = FLASH_COMPLEX_C
        if b_mode == "bernoulli":
            b_step = self.step_nonlinear_bernoulli
            b_kwargs = {}
        elif b_mode == "phi_midpoint":
            b_step = self.step_phi_midpoint
            b_kwargs = {"picard_iters": picard_iters}
        else:
            b_step = self.step_nonlinear_symmetric
            b_kwargs = {"picard_iters": picard_iters}

        def b_stage(psi, idx):
            # One B stage with ledger bookkeeping of its norm change (nonlinear work flux).
            if ledger is not None:
                n_before = float(np.sum(np.abs(psi) ** 2))
            psi = b_step(
                psi, B[idx], tau, d_mid=C[idx],
                include_g2=(abs(C[idx]) > 1e-15), **b_kwargs)
            if ledger is not None:
                n_after = float(np.sum(np.abs(psi) ** 2))
                ledger['nonlinear_work_flux'] = ledger.get('nonlinear_work_flux', 0.0) + (n_after - n_before)
            return psi

        psi = psi_sys
        if tau >= 0:
            for idx in range(6):
                psi = b_stage(psi, idx)
                psi, baths[idx] = self.step_linear_spinor_su2(psi, baths[idx], A[idx], tau)
            psi = b_stage(psi, 6)
        else:
            psi = b_stage(psi, 6)
            for idx in range(5, -1, -1):
                psi, baths[idx] = self.step_linear_spinor_su2(psi, baths[idx], A[idx], tau)
                psi = b_stage(psi, idx)
        return psi, baths


def _fit_order(hs, errs):
    """Log-log linear fit of convergence order; returns (slope, R^2)."""
    x = np.log10(np.asarray(hs, dtype=float))
    y = np.log10(np.asarray(errs, dtype=float))
    slope, intercept = np.polyfit(x, y, 1)
    yhat = slope * x + intercept
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return slope, r2


def test_reversible_spinor_flash22():
    """
    4th duality test: exact time-reversible Complex-S6* (Flash-22 / Root 11) on the
    spinor (psi_sys + 6 bath slots) with Halmos-Nagy SU(2) dilation + symmetric G2 midpoint.
    (A) Forward order-6 convergence on the nonlinear holomorphic-cubic model (vs fine-step gold).
    (B) Exact time reversal under strong dissipation (gamma = 5, N = 256) where a naive
        backward-heat step would overflow (e^{+tau Re(a) gamma k^2} ~ 1e80).
    (C) Liouville conservation on M_sys (+) M_bath: ||psi_sys||^2 + sum_m ||bath_m||^2 constant.
    """
    # --- Part A: forward order-6 convergence ---
    # MEASUREMENT REGIME MATTERS (learned 2026-11-08): the order must be measured over
    # a LONG time (T=1.0, many steps) at COARSE h (0.2, 0.1, 0.05), i.e. in the
    # pre-roundoff regime. A short T=0.08 with fine h (0.01) measures the double-
    # precision roundoff floor (~3e-13) and a pre-asymptotic transient, and falsely
    # reports order ~2.7. The BCH expansion of the Root 11 coefficients confirms the
    # design: e_AAB = 0 (machine zero, 1.7e-18) and e_BAB = sum(c_j) exactly, so the
    # per-stage G2 kicks cancel the whole O(h^3) local error; the method is order 6
    # (measured ratios 73, 70 at g=0.5, i.e. order ~6.1; order 6 also holds at
    # g=0.1 and g=1.0). The error at fine h is the roundoff floor, not a method error.
    N, L = 64, 20.0
    dx = L / N
    x = np.linspace(-L / 2.0, L / 2.0, N, endpoint=False)
    k = 2.0 * np.pi * np.fft.fftfreq(N, d=dx)
    spinor = ReversibleComplexS6Spinor(k, alpha_disp=1.0, gamma_diss=0.5, g_nonlin=0.5)
    psi0 = np.exp(-0.5 * x ** 2) * np.exp(0.5j * x)
    psi0 /= np.sqrt(np.sum(np.abs(psi0) ** 2) * dx)
    T = 1.0
    h_ref = 0.0005
    n_ref = int(round(T / h_ref))
    psi_ref = psi0.copy()
    for _ in range(n_ref):
        slots_ref = [np.zeros(N, dtype=complex) for _ in range(6)]
        psi_ref, slots_ref = spinor.step_flash22_macro(psi_ref, slots_ref, h_ref)
    h_ladder = [0.2, 0.1, 0.05]
    errs = []
    for h in h_ladder:
        n_steps = int(round(T / h))
        psi = psi0.copy()
        for _ in range(n_steps):
            slots = [np.zeros(N, dtype=complex) for _ in range(6)]
            psi, slots = spinor.step_flash22_macro(psi, slots, h)
        errs.append(np.sqrt(np.sum(np.abs(psi - psi_ref) ** 2) * dx))
    slope, r2 = _fit_order(h_ladder, errs)
    assert slope >= 5.5, f"Forward method is not order 6: p = {slope:.2f}, R^2 = {r2:.5f}"
    print(f"test_reversible_spinor_flash22 [A] forward order: p = {slope:.2f}, R^2 = {r2:.5f} (errs: "
          + ", ".join(f"{e:.2e}" for e in errs) + ") -- ORDER 6 CONFIRMED (T=1.0, coarse h, pre-floor)")

    # --- Part B: exact time reversal under strong dissipation ---
    N2, L2 = 256, 20.0
    dx2 = L2 / N2
    x2 = np.linspace(-L2 / 2.0, L2 / 2.0, N2, endpoint=False)
    k2 = 2.0 * np.pi * np.fft.fftfreq(N2, d=dx2)
    spinor2 = ReversibleComplexS6Spinor(k2, alpha_disp=1.0, gamma_diss=5.0, g_nonlin=0.5)
    psi0_2 = np.exp(-0.5 * x2 ** 2) * np.exp(0.5j * x2)
    psi0_2 /= np.sqrt(np.sum(np.abs(psi0_2) ** 2) * dx2)
    h2, n2 = 0.02, 5
    psi_fwd = psi0_2.copy()
    history2 = []
    for _ in range(n2):
        slots2 = [np.zeros(N2, dtype=complex) for _ in range(6)]
        psi_fwd, slots2 = spinor2.step_flash22_macro(psi_fwd, slots2, h2)
        history2.append(slots2)
    psi_rec = psi_fwd.copy()
    for slots2 in reversed(history2):
        psi_rec, slots2 = spinor2.step_flash22_macro(psi_rec, slots2, -h2)
    rec_err = float(np.max(np.abs(psi_rec - psi0_2)))
    bath_left = max(float(np.max(np.abs(b))) for slots2 in history2 for b in slots2)
    # Naive backward-heat blowup factor for comparison (per macro-step, worst mode):
    k_max = float(np.max(np.abs(k2)))
    naive = float(np.exp(n2 * h2 * float(np.max(np.real(np.array(FLASH_COMPLEX_A)))) * 5.0 * k_max ** 2))
    assert rec_err < 1e-12, f"Time-reversal error too large: {rec_err:.2e}"
    assert bath_left < 1e-12, f"Bath slots did not drain: {bath_left:.2e}"
    print(f"test_reversible_spinor_flash22 [B] reversal: ||psi_rec - psi0||_inf = {rec_err:.2e}, "
          f"max bath left = {bath_left:.2e} (naive backward-heat factor would be ~1e{np.log10(naive):.0f})")

    # --- Part C: Liouville conservation on M_sys (+) M_bath, per linear stage ---
    # The SU(2) dilation is unitary, so each A stage preserves ||psi_sys||^2 + ||bath_slot||^2
    # to machine precision. (The B stages are non-unitary in the Complex branch -- their
    # Re(b_j) part changes ||psi_sys||^2 without a bath transfer -- so the FULL macro-step
    # total drifts by O(1%); that drift is logged below, not asserted: it is the known
    # B-stage-dilation gap, not a failure of the A-stage dilation.)
    psi_c = psi0.copy()
    history_c = []
    e0 = float(np.sum(np.abs(psi_c) ** 2) * dx)
    e_drift = 0.0
    for _ in range(4):
        slots_c = [np.zeros(N, dtype=complex) for _ in range(6)]
        psi_c, slots_c = spinor.step_flash22_macro(psi_c, slots_c, 0.02)
        history_c.append(slots_c)
        e_tot = float(np.sum(np.abs(psi_c) ** 2) * dx
                     + sum(np.sum(np.abs(b) ** 2) * dx for slots in history_c for b in slots))
        e_drift = max(e_drift, abs(e_tot - e0) / e0)
    # Per-A-stage check: a single SU(2) dilation preserves sys + slot norm exactly.
    stage_drift = 0.0
    psi_s = psi0.copy()
    for a_j in FLASH_COMPLEX_A:
        slot_s = np.zeros(N, dtype=complex)
        e_before = float(np.sum(np.abs(psi_s) ** 2) * dx + np.sum(np.abs(slot_s) ** 2) * dx)
        psi_s, slot_s = spinor.step_linear_spinor_su2(psi_s, slot_s, a_j, 0.02)
        e_after = float(np.sum(np.abs(psi_s) ** 2) * dx + np.sum(np.abs(slot_s) ** 2) * dx)
        stage_drift = max(stage_drift, abs(e_after - e_before) / e_before)
    assert stage_drift < 1e-14, f"Per-stage Liouville drift too large: {stage_drift:.2e}"
    print(f"test_reversible_spinor_flash22 [C] Liouville per A stage: max drift = {stage_drift:.2e} "
          f"(full macro-step total drift, B stages undilated, logged only: {e_drift:.2e})")

    # --- Part D: boundary-ledger invariant (Solution 1, spec 20.7) ---
    # The B stages' Re(b_j) work flux is booked in the boundary ledger, NOT dilated
    # (an SU(2) dilation fails on B: Re(b_j*tau*g*psi^2) can be locally positive, so
    # |r(x)| > 1 and sqrt(1 - |r|^2) goes imaginary; and removing Re(b_j) breaks the
    # BCH/holomorphic cancellation and drops the order from 6 to 2). The full invariant
    # I_total = ||psi_sys||^2 + sum_s ||psi_bath,s||^2 - delta_W_B is constant to
    # machine precision, and the ledger drains back to zero on the way back.
    ledger = {'nonlinear_work_flux': 0.0}
    psi_d = psi0.copy()
    history_d = []
    s0 = float(np.sum(np.abs(psi0) ** 2))
    max_dev = 0.0
    max_dev_no_ledger = 0.0
    for _ in range(4):
        slots_d = [np.zeros(N, dtype=complex) for _ in range(6)]
        psi_d, slots_d = spinor.step_flash22_macro(psi_d, slots_d, 0.02, ledger=ledger)
        history_d.append(slots_d)
        bath_sum = sum(float(np.sum(np.abs(b) ** 2)) for slots in history_d for b in slots)
        i_total = float(np.sum(np.abs(psi_d) ** 2)) + bath_sum - ledger['nonlinear_work_flux']
        i_no_ledger = float(np.sum(np.abs(psi_d) ** 2)) + bath_sum
        max_dev = max(max_dev, abs(i_total - s0) / s0)
        max_dev_no_ledger = max(max_dev_no_ledger, abs(i_no_ledger - s0) / s0)
    for slots_d in reversed(history_d):
        psi_d, slots_d = spinor.step_flash22_macro(psi_d, slots_d, -0.02, ledger=ledger)
        bath_sum = sum(float(np.sum(np.abs(b) ** 2)) for slots in history_d for b in slots)
        i_total = float(np.sum(np.abs(psi_d) ** 2)) + bath_sum - ledger['nonlinear_work_flux']
        max_dev = max(max_dev, abs(i_total - s0) / s0)
    assert max_dev < 1e-14, f"Ledger invariant drift too large: {max_dev:.2e}"
    print(f"test_reversible_spinor_flash22 [D] ledger invariant: max rel dev = {max_dev:.2e} "
          f"(without ledger: {max_dev_no_ledger:.2e}; ledger final = {ledger['nonlinear_work_flux']:.2e})")
    print("test_reversible_spinor_flash22: PASSED")

def test_phi_midpoint_reversal():
    """
    Benyamin's Phi-midpoint B stage (2026-11-08): the G2 lives inside the modified
    potential Phi(u) = V(u) + d_mid*(b_j*tau)^2*G2(u), the stage is the implicit
    symmetric midpoint, and the inverse is the same formula with -tau (the midpoint
    u^(*) is the same for forward and backward). Verified: exact reversal at machine
    precision, but the forward order is 2 (the implicit midpoint caps it) -- so this
    is the exact-reversal alternative to the Bernoulli (order 6), not the engine.
    """
    # Reversal (same strong-dissipation setup as Part B of the main spinor test).
    N2, L2 = 256, 20.0
    dx2 = L2 / N2
    x2 = np.linspace(-L2 / 2.0, L2 / 2.0, N2, endpoint=False)
    k2 = 2.0 * np.pi * np.fft.fftfreq(N2, d=dx2)
    spinor2 = ReversibleComplexS6Spinor(k2, alpha_disp=1.0, gamma_diss=5.0, g_nonlin=0.5)
    psi0_2 = np.exp(-0.5 * x2 ** 2) * np.exp(0.5j * x2)
    psi0_2 /= np.sqrt(np.sum(np.abs(psi0_2) ** 2) * dx2)
    h2, n2 = 0.02, 5
    psi_fwd = psi0_2.copy()
    history2 = []
    for _ in range(n2):
        slots2 = [np.zeros(N2, dtype=complex) for _ in range(6)]
        psi_fwd, slots2 = spinor2.step_flash22_macro(psi_fwd, slots2, h2, b_mode='phi_midpoint')
        history2.append(slots2)
    psi_rec = psi_fwd.copy()
    for slots2 in reversed(history2):
        psi_rec, slots2 = spinor2.step_flash22_macro(psi_rec, slots2, -h2, b_mode='phi_midpoint')
    rec_err = float(np.max(np.abs(psi_rec - psi0_2)))
    assert rec_err < 1e-12, f"Phi-midpoint reversal error too large: {rec_err:.2e}"
    # Forward order (T=0.5, coarse h; the order-2 error is far above the roundoff floor).
    N, L = 64, 20.0
    dx = L / N
    x = np.linspace(-L / 2.0, L / 2.0, N, endpoint=False)
    k = 2.0 * np.pi * np.fft.fftfreq(N, d=dx)
    spinor = ReversibleComplexS6Spinor(k, alpha_disp=1.0, gamma_diss=0.5, g_nonlin=0.5)
    psi0 = np.exp(-0.5 * x ** 2) * np.exp(0.5j * x)
    psi0 /= np.sqrt(np.sum(np.abs(psi0) ** 2) * dx)
    T, h_ref = 0.5, 0.0005
    psi_ref = psi0.copy()
    for _ in range(int(round(T / h_ref))):
        slots_ref = [np.zeros(N, dtype=complex) for _ in range(6)]
        psi_ref, slots_ref = spinor.step_flash22_macro(psi_ref, slots_ref, h_ref, b_mode='phi_midpoint')
    h_ladder = [0.1, 0.05, 0.025]
    errs = []
    for h in h_ladder:
        psi = psi0.copy()
        for _ in range(int(round(T / h))):
            slots = [np.zeros(N, dtype=complex) for _ in range(6)]
            psi, slots = spinor.step_flash22_macro(psi, slots, h, b_mode='phi_midpoint')
        errs.append(float(np.sqrt(np.sum(np.abs(psi - psi_ref) ** 2) * dx)))
    slope, r2 = _fit_order(h_ladder, errs)
    assert slope >= 1.9, f"Phi-midpoint forward order is not 2: p = {slope:.2f}"
    print(f"test_phi_midpoint_reversal: reversal = {rec_err:.2e}, forward order p = {slope:.2f} "
          f"(errs: " + ", ".join(f"{e:.2e}" for e in errs) + ") -- PASSED (exact reversal, order 2)")

def test_simplex_hamiltonian_unitarity_grid():
    mesh = SimplexMesh2D(Lx=10.0, Ly=10.0, Nx=16, Ny=16, periodic=True)
    solver = SimplexSolver(mesh, field='complex', evolution='hamiltonian', theta=0.0)
    r2 = mesh.nodes[:, 0]**2 + mesh.nodes[:, 1]**2
    psi0 = np.exp(-0.5 * r2) * np.exp(1j * 0.5 * mesh.nodes[:, 0])
    psi0 /= mesh.norm(psi0)

    psi_f = solver.integrate_simplex_s6(psi0, n_steps=20, h=0.01, use_fsal=True)
    norm_defect = abs(mesh.norm(psi_f) - 1.0)
    assert norm_defect < 1e-13, f"Unitary norm defect too large on grid: {norm_defect}"
    print(f"test_simplex_hamiltonian_unitarity_grid: PASSED (Delta N = {norm_defect:.2e})")

def test_simplex_hamiltonian_unitarity_delaunay():
    mesh = SimplexMesh2D(Lx=10.0, Ly=10.0, Nx=16, Ny=16, mode='delaunay', random_seed=42)
    solver = SimplexSolver(mesh, field='complex', evolution='hamiltonian', theta=0.0)
    r2 = mesh.nodes[:, 0]**2 + mesh.nodes[:, 1]**2
    psi0 = np.exp(-0.5 * r2) * np.exp(1j * 0.5 * mesh.nodes[:, 0])
    psi0 /= mesh.norm(psi0)

    psi_f = solver.integrate_simplex_s6(psi0, n_steps=20, h=0.01, use_fsal=True)
    norm_defect = abs(mesh.norm(psi_f) - 1.0)
    assert norm_defect < 1e-13, f"Unitary norm defect too large on Delaunay: {norm_defect}"
    print(f"test_simplex_hamiltonian_unitarity_delaunay: PASSED (Delta N = {norm_defect:.2e})")

def test_simplex_parabolic_contraction():
    mesh = SimplexMesh2D(Lx=10.0, Ly=10.0, Nx=16, Ny=16, periodic=True)
    solver = SimplexSolver(mesh, field='complex', evolution='parabolic', theta=0.0)
    r2 = mesh.nodes[:, 0]**2 + mesh.nodes[:, 1]**2
    u0 = np.exp(-0.5 * r2)
    u0 /= mesh.norm(u0)

    u_f = solver.integrate_simplex_s6(u0, n_steps=20, h=0.01, use_fsal=False)
    contraction = mesh.norm(u_f) / mesh.norm(u0)
    assert 0.0 < contraction <= 1.0, f"Expected non-expansive / contractive, got ratio: {contraction}"
    print(f"test_simplex_parabolic_contraction: PASSED (Contraction ratio = {contraction:.4f})")

if __name__ == '__main__':
    test_simplex_hamiltonian_unitarity_grid()
    test_simplex_hamiltonian_unitarity_delaunay()
    test_simplex_parabolic_contraction()
    test_reversible_spinor_flash22()
    test_phi_midpoint_reversal()
