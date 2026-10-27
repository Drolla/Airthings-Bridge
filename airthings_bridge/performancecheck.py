"""Performance Check.

This file implements a performance check context manager that allows measuring
the execution time of code blocks.

Copyright (C) 2022 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of
this file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import logging
import time
from types import TracebackType

logger = logging.getLogger(__name__)


class PerformanceCheck:
    """Tasks performance checking.

    Context manager to check the performance of tasks. It reports the
    execution time of the code placed in the with block.

    Args:
        task_short_name: Text that will be used in the performance logs
        log_level: Logging level, provided by the logging module.
                   Default=logging.INFO

    Example:
        from airthings_bridge.performancecheck import PerformanceCheck

        with PerformanceCheck("Test loop"):
            value = 1.0
            for _ in range(1000000):
                value = value*1.1
                if value > 1000:
                    value /= 1000
    """

    def __init__(self, task_short_name: str,
                 log_level: int = logging.INFO):
        self.task_short_name = task_short_name
        self.log_level = log_level

    def __enter__(self) -> "PerformanceCheck":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type: type[BaseException] | None,
                 exc_value: BaseException | None,
                 traceback: TracebackType | None) -> None:
        execution_time_ms = 1000*(time.perf_counter()-self.start_time)
        logger.log(self.log_level, "%s: %.3fms",
                   self.task_short_name, execution_time_ms)

