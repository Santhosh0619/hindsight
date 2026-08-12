import uuid
from datetime import UTC, datetime

from app.core.pagination import decode_cursor, encode_cursor


def test_cursor_roundtrip() -> None:
    created_at = datetime(2026, 1, 15, 12, 30, 0, tzinfo=UTC)
    item_id = uuid.uuid4()

    cursor = encode_cursor(created_at, item_id)
    decoded_created_at, decoded_item_id = decode_cursor(cursor)

    assert decoded_created_at == created_at
    assert decoded_item_id == item_id


def test_cursor_is_url_safe() -> None:
    cursor = encode_cursor(datetime.now(UTC), uuid.uuid4())

    assert "+" not in cursor
    assert "/" not in cursor
