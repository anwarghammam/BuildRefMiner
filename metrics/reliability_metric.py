from __future__ import annotations


def compute_overall_reliability(issue_reliability: float, dss: float, edr: float) -> float:
    issue_reliability = max(0.0, min(1.0, float(issue_reliability)))
    dss = max(0.0, min(1.0, float(dss)))
    edr = max(0.0, min(1.0, float(edr)))
    return round((issue_reliability + dss + (1.0 - edr)) / 3.0, 4)
