"""
S6* Real Geometric Splitting Family (Optimized Hamiltonian Portfolio)
Exports certified high-precision coefficients for:
- S6* Real-Standard-33 (33 FFTs/step) - Full spectral baseline
- S6* Real-Stencil-12 (12 FFTs/step)  - 8th-order compact spatial difference stencils
- Yoshida-6 baseline (14 FFTs/step)  - 7-stage symmetric T-V-T pure splitting with FSAL (NOT a family member)
"""
from src.coefficients import (
    REAL_STANDARD_33_A, REAL_STANDARD_33_B, REAL_STANDARD_33_C, REAL_STANDARD_33_FFTS,
    REAL_STENCIL_12_A, REAL_STENCIL_12_B, REAL_STENCIL_12_C, REAL_STENCIL_12_FFTS,
    STENCIL_D, STENCIL_D2, STENCIL_D2_CENTER,
    YOSHIDA_6_A, YOSHIDA_6_B, YOSHIDA_6_W, YOSHIDA_6_FFTS,
    S6_REAL_A, S6_REAL_B, S6_REAL_C, YOSHIDA6_W
)
