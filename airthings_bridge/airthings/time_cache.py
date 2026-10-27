"""Cache with a time to live (TTL).

This file implements a cache where the stored data words have optionally a time
to live. Also, the number of read access to each data word can be limited
before the word becomes obsolete.

Copyright (C) 2023 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of
this file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import time
from collections.abc import Hashable
from typing import Any


class TimeCache:
    """Caches values with optional TTL and reload interval.

    The class implements a dict like object with indexed access to dictionary.
    The stored data can have a time to live (TTL), and the number data read
    accesses can be limited until a data word becomes invalid. Reading a
    data word that does not exist (wrong key) or that has an obsolete live will
    raise a KeyError.

    Args:
        ttl: Time to live in seconds
        max_read: Maximum number of times a data word can be read

    Example:
        cache = time_cache.TimeCache(ttl=5.0)
        cache["a"]=123
        cache["a"]
        -> 123
        ... wait more than 5 seconds ...
        cache["a"]
        -> Error: KeyError
    """

    def __init__(self, ttl: float | None = None,
                 max_read: int | None = None):
        self._ttl = ttl
        self._max_read = max_read
        self._data_dict: dict[Hashable, list] = {}

    def __contains__(self, key: Hashable) -> bool:
        if key not in self._data_dict:
            return False
        value = self._data_dict[key]
        if self._ttl is not None and value[1]+self._ttl < time.monotonic():
            return False
        return self._max_read is None or value[2] < self._max_read

    def __getitem__(self, key: Hashable) -> Any:
        if key not in self:
            raise KeyError(key)
        value = self._data_dict[key]
        value[2] += 1
        return value[0]

    def __setitem__(self, key: Hashable, value: Any) -> None:
        self._data_dict[key] = [value, time.monotonic(), 0]

