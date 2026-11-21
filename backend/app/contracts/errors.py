"""Exceptions that may cross the A<->B boundary. Frozen after T0."""


class InvalidParcelQuery(ValueError):
    """The query is not a valid parcel id / 'obreb + number' / coordinates."""


class ParcelNotFound(LookupError):
    """ULDK returned no parcel for a syntactically valid query."""


class UpstreamUnavailable(RuntimeError):
    """A required upstream service did not answer (after retries)."""
