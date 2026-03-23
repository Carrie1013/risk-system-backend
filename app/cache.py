from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from functools import wraps
from threading import RLock
from time import time


def _freeze(value):
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
    if isinstance(value, set):
        return tuple(sorted(_freeze(v) for v in value))
    return repr(value)


def ttl_cache(ttl_seconds: int = 300, maxsize: int = 128):
    def decorator(func):
        store = OrderedDict()
        lock = RLock()

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (_freeze(args), _freeze(kwargs))
            now = time()
            with lock:
                hit = store.get(key)
                if hit is not None:
                    expires_at, value = hit
                    if expires_at > now:
                        store.move_to_end(key)
                        return deepcopy(value)
                    del store[key]

            result = func(*args, **kwargs)

            with lock:
                store[key] = (now + ttl_seconds, result)
                store.move_to_end(key)
                while len(store) > maxsize:
                    store.popitem(last=False)

            return deepcopy(result)

        return wrapper

    return decorator
