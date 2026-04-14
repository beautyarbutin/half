from datetime import datetime, timezone

from pydantic import BaseModel, field_serializer


def utc_isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class UtcDatetimeModel(BaseModel):
    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_datetime(self, value):
        if isinstance(value, datetime):
            return utc_isoformat(value)
        return value
