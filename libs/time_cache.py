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


#############################################
# Main - Demo and short test
#############################################

if __name__ == "__main__":
    import logging
    import random
    import sys

    # Configure the logger
    FORMAT = "%(asctime)s - %(message)s"
    logging.basicConfig(format=FORMAT, stream=sys.stdout)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    def write_data(cache: TimeCache, key: int) -> None:
        """Write a random data word in a cache location defined by the key."""
        value = random.random()
        cache[key] = value
        logger.info("  Cache[%s] <= %s", key, value)

    def fill_cache(cache: TimeCache, cache_size: int) -> None:
        """Fill a cache with random data."""
        logger.info("Fill the cache:")
        for key in range(cache_size):
            write_data(cache, key)

    def read_data(cache: TimeCache, key: int) -> None:
        """Read a cache location."""
        try:
            value = cache[key]
            logger.info("  Cache[%s] -> %s", key, value)
        except KeyError:
            logger.info("  Cache[%s] -> (empty)", key)

    def read_data_many_times(cache: TimeCache, cache_size: int,
                             nbr_iterations: int) -> None:
        """Loop through the cache and read the data repeatedly."""
        logger.info("Read the data:")
        for _ in range(nbr_iterations):
            for key in range(cache_size):
                read_data(cache, key)
                time.sleep(0.1)

    logger.info("**** Cache without constraints ****")

    my_cache = TimeCache()

    logger.info("Cache is empty:")
    read_data_many_times(my_cache, cache_size=3, nbr_iterations=1)
    fill_cache(my_cache, cache_size=3)
    read_data_many_times(my_cache, cache_size=3, nbr_iterations=3)

    logger.info("**** Cache with max_read=2 ****")
    my_cache = TimeCache(max_read=2)
    fill_cache(my_cache, 3)
    read_data_many_times(my_cache, cache_size=3, nbr_iterations=3)

    logger.info("**** Cache with ttl=0.5 ****")
    my_cache = TimeCache(ttl=0.5)
    fill_cache(my_cache, 3)
    read_data_many_times(my_cache, cache_size=3, nbr_iterations=3)

    logger.info("**** Cache with max_read=1 and ttl=0.5, random access ****")
    my_cache = TimeCache(ttl=0.5, max_read=1)
    fill_cache(my_cache, 3)

    logger.info("Write/read access:")
    for _ in range(5):
        for item in range(3):
            if random.random() > 0.75:
                write_data(my_cache, item)
            else:
                read_data(my_cache, item)
            time.sleep(0.1)
