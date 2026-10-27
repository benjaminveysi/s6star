#!/usr/bin/env bash
set -e
export PYTHONPATH=.
echo "Running S6* Scientific Verification Suite (Release v16 unified Simplex)..."
python3 tests/test_all_7_members.py
python3 tests/test_coefficients.py
python3 tests/test_simplex_duality.py
python3 tests/test_adjoint_g.py
python3 tests/test_krylov_estimator.py
python3 tests/test_simplex_unified_architecture.py
echo "All tests passed successfully!"
