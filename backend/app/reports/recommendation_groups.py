"""Group location-specific actions for display without changing saved reports."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.contracts.report import Metric, Recommendation
from app.recommendations.texts_pl import RETENTION_OUTSIDE_PARCEL


@dataclass(frozen=True, slots=True)
class Site:
    number: int
    geometry: dict
    note_pl: str
    evidence: list[Metric]


@dataclass(frozen=True, slots=True)
class Action:
    recommendation: Recommendation
    action_pl: str
    evidence: list[Metric]
    sites: list[Site]


def group_actions(recommendations: list[Recommendation]) -> list[Action]:
    groups = defaultdict(list)
    actions = []
    for item in recommendations:
        if item.geometry is None:
            actions.append(Action(item, item.action_pl, item.evidence, []))
            continue
        # landscape.evaluate appends this caution only to the affected sites.
        base = item.action_pl.removesuffix(f" {RETENTION_OUTSIDE_PARCEL}")
        groups[item.category, item.title_pl, base, item.why_pl, tuple(sorted(item.reference_ids))].append(item)

    for (_, _, base, _, _), items in groups.items():
        common = [
            metric for metric in items[0].evidence if all(metric in item.evidence for item in items[1:])
        ] if len(items) > 1 else []
        sites = [
            Site(number, item.geometry, item.action_pl.removeprefix(base).strip(),
                 [metric for metric in item.evidence if metric not in common])
            for number, item in enumerate(items, start=1)
        ]
        actions.append(Action(items[0], base, common, sites))

    # Keep the engine's order of action types, including recommendations without locations.
    order = {item.id: i for i, item in enumerate(recommendations)}
    return sorted(actions, key=lambda action: order[action.recommendation.id])
