from app.core.logging import redact_processor, redact_text


def test_secrets_and_personal_data_are_masked():
    text = "Bearer eyJhbGciOi.abc.def from jane.doe@amicorp.com for GB82WEST12345698765432 card 4111111111111111"
    redacted = redact_text(text)
    assert "eyJhbGciOi" not in redacted
    assert "jane.doe@amicorp.com" not in redacted
    assert "GB82WEST12345698765432" not in redacted
    assert "4111111111111111" not in redacted


def test_uuids_and_short_numbers_are_kept():
    text = "card 550e8400-e29b-41d4-a716-446655440000 execution 1001"
    assert redact_text(text) == text


def test_sensitive_keys_are_masked_at_any_depth():
    event = {"event": "x", "request": {"headers": {"Authorization": "Bearer abc"}, "token": "t"}}
    redacted = redact_processor(None, "info", event)
    assert redacted["request"]["headers"]["Authorization"] == "[REDACTED]"
    assert redacted["request"]["token"] == "[REDACTED]"
