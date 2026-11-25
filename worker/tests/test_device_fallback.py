import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from device_fallback import CpuFallback


class Adapter:
    calls = 0

    def __init__(self, device="mps", error=None):
        self.device, self.error = device, error

    def run(self, x):
        Adapter.calls += 1
        if self.device != "cpu" and self.error:
            raise self.error
        return (self.device, x)


def make(error):
    owner = SimpleNamespace(device="mps", device_fallbacks=[])
    Adapter.calls = 0
    first = Adapter("mps", error)
    wrapped = CpuFallback(owner, "net", lambda device: Adapter(device), (), first)
    return owner, wrapped


def test_mps_runtime_error_falls_back_to_cpu():
    owner, w = make(RuntimeError("[srcBuf length] > 0 INTERNAL ASSERT FAILED: Placeholder tensor is empty!"))
    assert w.run(1) == ("cpu", 1)
    assert owner.device_fallbacks == ["net"]
    assert w.run(2) == ("cpu", 2)       # stays on cpu, no further swap
    assert owner.device_fallbacks == ["net"]


def test_other_errors_are_reraised_without_fallback():
    owner, w = make(ValueError("bad input shape"))
    with pytest.raises(ValueError):
        w.run(1)
    assert owner.device_fallbacks == [] and Adapter.calls == 1
    owner, w = make(RuntimeError("out of memory"))
    with pytest.raises(RuntimeError):
        w.run(1)
    assert owner.device_fallbacks == []
