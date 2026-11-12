"""Read snapshots must include already committed registry system boundaries."""
from datetime import datetime

from sqlalchemy import text


def current_system_time(engine, wall_time: str) -> str:
    # Successor writes may advance past a repeated or backward wall-clock tick.
    tables = ("assertions", "relationships", "lineage", "resolution_policies",
              "policy_activations", "resolution_overrides", "conflicts")
    query = " UNION ALL ".join(
        f"SELECT MAX(system_from) AS boundary FROM entity_registry_{table}" for table in tables
    )
    with engine.connect() as conn:
        boundaries = conn.execute(text(query)).scalars().all()
    return max(datetime.fromisoformat(value) for value in [wall_time, *boundaries] if value).isoformat()
