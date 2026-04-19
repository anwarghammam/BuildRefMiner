from __future__ import annotations


def empty_external_dependency_risk_result() -> dict:
    return {
        "external_risk_factors": 0,
        "edr": 0.0,
    }


def compute_external_dependency_risk(coupling_result: dict) -> dict:
    if not coupling_result:
        return empty_external_dependency_risk_result()

    components = coupling_result.get("components", {}) or {}
    cp_total = int(coupling_result.get("cp_total", 0) or 0)

    # Local module links are excluded because EDR is meant to capture
    # reliance on external systems rather than project-internal structure.
    external_risk_factors = int(
        (components.get("d", 0) or 0)
        + (components.get("p", 0) or 0)
        + (components.get("r", 0) or 0)
        + (components.get("e", 0) or 0)
        + (components.get("u", 0) or 0)
    )

    if cp_total <= 0:
        return {
            "external_risk_factors": external_risk_factors,
            "edr": 0.0,
        }

    return {
        "external_risk_factors": external_risk_factors,
        "edr": round(external_risk_factors / cp_total, 4),
    }
