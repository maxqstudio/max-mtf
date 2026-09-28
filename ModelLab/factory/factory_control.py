from __future__ import annotations

class FactoryControlSignal(RuntimeError):
    """Base class for operator lifecycle control; never convert into research failure."""

class FactoryStopRequested(FactoryControlSignal):
    pass

class FactoryPauseRequested(FactoryControlSignal):
    pass
