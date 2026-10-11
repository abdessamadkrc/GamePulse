"""Tiny in-process memoisation. The dataset is immutable between re-seeds, so results can be cached
by (function, arguments). Cache is cleared on process restart (which happens after every re-seed)."""
from __future__ import annotations

import functools
from collections import OrderedDict
from typing import Any, Callable

_MAX = 600
_STORES: list[OrderedDict] = []   # every cached function registers its store here


def clear_all() -> None:
    """Forget every cached result (called after the data changes, e.g. an import)."""
    for st in _STORES:
        st.clear()


def cached(fn: Callable[..., Any]) -> Callable[..., Any]:
    store: OrderedDict[tuple, Any] = OrderedDict()
    _STORES.append(store)

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        key = (args, tuple(sorted(kwargs.items())))
        if key in store:
            store.move_to_end(key)
            return store[key]
        result = fn(*args, **kwargs)
        store[key] = result
        if len(store) > _MAX:
            store.popitem(last=False)
        return result

    wrapper.cache_clear = store.clear  # type: ignore[attr-defined]
    return wrapper
