"""Data-source adapters for the EV Charge India refresh pipeline.

Each adapter exposes the same contract:

    fetch(**opts)  -> list[dict]   raw records from the source (live)
    normalise(raw) -> dict         one record mapped to the canonical station shape

`refresh.py` calls fetch(), then normalise() per record, then diffs and upserts.
Add a new source by dropping a module here and registering it in refresh.SOURCES.
"""
