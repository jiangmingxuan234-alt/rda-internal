import pytest
from rda.quality.window_contract import TrainingWindow, compare_window_indices, load_training_windows

def w(i=0, ep=1):
    return TrainingWindow(i, ep, (0,1), (1,), (False, True), (0.0, 0.1), 0.02)

def test_window_contract_rejects_bad_padding_and_preserves_episode_boundary():
    with pytest.raises(ValueError): TrainingWindow(0, 1, (0,1), (1,), (False,), (), None)
    assert w().episode_index == 1

def test_provider_and_parity_are_explicit():
    class P:
        def iter_training_windows(self, profile): return [w()]
    assert list(load_training_windows(P(), {}))[0].index == 0
    report = compare_window_indices([w()], [w(1)])
    assert report.alignment == "MISMATCH" and report.missing_indices == (0,)
