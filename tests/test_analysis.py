from analysis.baseline import BaselineAnalyzer

def test_baseline_empty_cohort_is_deterministic():
    result=BaselineAnalyzer().analyze([])
    assert result["counts"]["executions"]==0
    assert result["response_length"]["mean"] is None
