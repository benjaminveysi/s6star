# Release v15 patch notes — S6* Simplex-Commutator

## Core numerical fix

The canonical S6* B stage is now realized as a single Krylov exponential

\[ B_j(h) = \exp(-i h b_j V - i h^3 c_j C), \qquad C=[V,[M^{-1}K,V]]. \]

The former symmetric splitting of the B stage into separate V and C actions was removed. On a general simplicial discretization [V,C] != 0, so splitting those operators would introduce an O(h^5) local defect and reduce the global temporal order.

## Multi-step fix

The canonical 13-stage sequence is executed exactly. The previous multi-step commutator loop skipped B6 and therefore did not reproduce the 13-stage palindrome. That loop has been replaced.

Because the canonical map starts and ends with B, there is no kinetic FSAL. Identical B boundary stages can be fused exactly across macro-steps when the linear external-potential commutator scheme is used.

## Instrumentation

Kinetic Laplacian SpMVs and discrete-commutator SpMVs are counted separately. Total sparse matvec work is their sum.

## Validation added

`tests/test_simplex_commutator_order.py` validates sixth-order convergence against an independent dense matrix exponential and checks exact boundary-B fusion against an unfused two-step reference.
