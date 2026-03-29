from aviation_supply_console.services.http import maybe_decompress


def test_maybe_decompress_returns_plain_payload_unchanged() -> None:
    payload = b'{"ok": true}'
    assert maybe_decompress(payload) == payload
