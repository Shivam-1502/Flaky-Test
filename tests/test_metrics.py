from app.metrics import _duration_cv

def test_duration_cv_zero_for_identical_values():
    assert _duration_cv([1.0, 1.0, 1.0]) == 0.0

def test_duration_cv_positive_for_variable_values():
    assert _duration_cv([1.0, 2.0, 3.0]) > 0
