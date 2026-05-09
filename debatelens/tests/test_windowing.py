from debatelens.analysis.windowing import to_windows
from debatelens.models import Segment, Transcript


def _seg(speaker, text, start, end):
    return Segment(speaker=speaker, text=text, start_time=start, end_time=end)


def test_to_windows_single_window_under_target():
    t = Transcript(segments=[
        _seg("1", "a", 0.0, 10.0),
        _seg("2", "b", 10.0, 20.0),
    ])
    windows = to_windows(t, target_seconds=60.0)
    assert len(windows) == 1
    assert windows[0].index == 0
    assert len(windows[0].segments) == 2


def test_to_windows_splits_on_target_seconds():
    t = Transcript(segments=[
        _seg("1", "a", 0.0, 30.0),
        _seg("2", "b", 30.0, 65.0),
        _seg("1", "c", 65.0, 90.0),
    ])
    windows = to_windows(t, target_seconds=60.0)
    assert len(windows) == 2
    assert windows[0].segments[0].text == "a"
    assert windows[0].segments[-1].text == "b"
    assert windows[1].segments[0].text == "c"


def test_to_windows_empty():
    t = Transcript(segments=[])
    assert to_windows(t, target_seconds=60.0) == []


def test_window_indices_sequential():
    t = Transcript(segments=[
        _seg("1", str(i), float(i * 30), float((i + 1) * 30)) for i in range(5)
    ])
    windows = to_windows(t, target_seconds=60.0)
    indices = [w.index for w in windows]
    assert indices == sorted(indices)
    assert indices[0] == 0


def test_window_times_match_segments():
    t = Transcript(segments=[
        _seg("1", "a", 5.0, 15.0),
        _seg("2", "b", 15.0, 70.0),
    ])
    windows = to_windows(t, target_seconds=60.0)
    assert windows[0].start_time == 5.0
    assert windows[0].end_time == 70.0
