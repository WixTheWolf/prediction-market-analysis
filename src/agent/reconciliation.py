"""Exchange-state reconciliation primitives for safe execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class LocalOrder:
    client_order_id: str
    ticker: str
    side: str
    contracts: int
    status: str


@dataclass(frozen=True)
class RemoteOrder:
    client_order_id: str
    ticker: str
    side: str
    remaining_contracts: int
    status: str


@dataclass(frozen=True)
class ReconciliationReport:
    missing_remote: tuple[str, ...]
    unknown_remote: tuple[str, ...]
    mismatched: tuple[str, ...]

    @property
    def healthy(self) -> bool:
        return not (self.missing_remote or self.unknown_remote or self.mismatched)


def reconcile_orders(
    local_orders: Iterable[LocalOrder],
    remote_orders: Iterable[RemoteOrder],
) -> ReconciliationReport:
    local = {order.client_order_id: order for order in local_orders}
    remote = {order.client_order_id: order for order in remote_orders}

    missing_remote = tuple(sorted(set(local) - set(remote)))
    unknown_remote = tuple(sorted(set(remote) - set(local)))
    mismatched: list[str] = []

    for order_id in sorted(set(local) & set(remote)):
        left = local[order_id]
        right = remote[order_id]
        if left.ticker != right.ticker or left.side.lower() != right.side.lower():
            mismatched.append(order_id)

    return ReconciliationReport(
        missing_remote=missing_remote,
        unknown_remote=unknown_remote,
        mismatched=tuple(mismatched),
    )
