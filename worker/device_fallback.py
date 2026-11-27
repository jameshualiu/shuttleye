"""CPU fallback for torch adapters built on an accelerator (MPS). No heavy imports."""

DEVICE_ERROR_MARKERS = ("mps", "placeholder tensor", "not implemented for", "not currently implemented")


def is_device_error(exc: BaseException) -> bool:
    """True for the errors an accelerator raises for ops it lacks (RuntimeError /
    NotImplementedError naming MPS, an empty placeholder tensor or an unimplemented op).
    Anything else (bad input, OOM, logic bugs) is not a device problem."""
    if not isinstance(exc, (RuntimeError, NotImplementedError)):
        return False
    msg = str(exc).lower()
    return any(m in msg for m in DEVICE_ERROR_MARKERS)


class CpuFallback:
    """Forwards to an adapter built on an accelerator; the first call that fails
    with a device error swaps in a CPU copy and retries. Other exceptions re-raise."""

    def __init__(self, owner, name, cls, args, target):
        self.__dict__.update(_owner=owner, _name=name, _cls=cls, _args=args, _target=target)

    def __getattr__(self, attr):
        value = getattr(self._target, attr)
        if not callable(value):
            return value

        def call(*a, **kw):
            try:
                return value(*a, **kw)
            except Exception as e:
                if getattr(self._target, "device", None) == "cpu" or not is_device_error(e):
                    raise
                print(f"[device] {self._name} failed on {self._owner.device} ({e}); falling back to cpu")
                self._owner.device_fallbacks.append(self._name)
                self.__dict__["_target"] = self._cls(*self._args, device="cpu")
                return getattr(self._target, attr)(*a, **kw)
        return call
