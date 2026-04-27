__all__ = ["BitzApp"]


def __getattr__(name):
    if name == "BitzApp":
        from .app import BitzApp
        return BitzApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
