"""Consumers of the readings of each polling cycle."""

from typing import Protocol

from airthings_bridge.readings import Cycle


class Consumer(Protocol):
    """Consumer of the polling cycles, started and stopped by the bridge."""

    async def start(self) -> None:
        """Start the consumer."""

    async def handle(self, cycle: Cycle) -> None:
        """Process the readings of a cycle."""

    async def stop(self) -> None:
        """Stop the consumer and release its resources."""
