from collections.abc import Callable


def skip_signature_verify(wrapped: Callable = None):
    if wrapped is None:
        return skip_signature_verify
    wrapped._skip_signature_verify = True
    return wrapped
