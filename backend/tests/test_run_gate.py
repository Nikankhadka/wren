"""T-029: unit tests for the eval-gate decision helpers. The subprocess/DB
orchestration is exercised by CI itself; here we pin the pure logic that
decides pass/fail."""

from __future__ import annotations

from evals.run_gate import GateReport, absolute_pass, regression_pass


def test_absolute_pass_only_on_zero_exit() -> None:
    assert absolute_pass(0)
    assert not absolute_pass(1)
    assert not absolute_pass(2)


def test_regression_first_run_has_no_baseline_and_passes() -> None:
    passed, detail = regression_pass(0.91, None)
    assert passed
    assert "no baseline" in detail


def test_regression_missing_current_fails_closed() -> None:
    passed, detail = regression_pass(None, 0.90)
    assert not passed
    assert "no current" in detail


def test_regression_improvement_passes() -> None:
    passed, _ = regression_pass(0.95, 0.90)
    assert passed


def test_regression_small_drop_within_tolerance_passes() -> None:
    # 2-point drop, tolerance 3 points.
    passed, _ = regression_pass(0.88, 0.90, tolerance=0.03)
    assert passed


def test_regression_large_drop_beyond_tolerance_fails() -> None:
    # 5-point drop, tolerance 3 points.
    passed, detail = regression_pass(0.85, 0.90, tolerance=0.03)
    assert not passed
    assert "drop" in detail


def test_regression_drop_exactly_at_tolerance_passes() -> None:
    # Exactly the tolerance is not "beyond" it.
    passed, _ = regression_pass(0.87, 0.90, tolerance=0.03)
    assert passed


def test_gate_report_passes_only_when_all_pass() -> None:
    report = GateReport()
    report.add("a", True, "ok")
    report.add("b", True, "ok")
    assert report.passed
    report.add("c", False, "boom")
    assert not report.passed


def test_gate_report_empty_is_vacuously_passing() -> None:
    assert GateReport().passed
