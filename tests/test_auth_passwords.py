import hashlib

from backend.auth_service import hash_password, is_legacy_password_hash, validate_password_strength, verify_password


def test_new_password_hash_is_salted_and_verifiable():
    first = hash_password("Correct Horse Battery Staple")
    second = hash_password("Correct Horse Battery Staple")

    assert first != second
    assert not is_legacy_password_hash(first)
    assert verify_password("Correct Horse Battery Staple", first)
    assert not verify_password("wrong password", first)


def test_legacy_sha256_hash_can_be_identified_and_verified_for_migration():
    legacy = hashlib.sha256("Legacy Password".encode()).hexdigest()

    assert is_legacy_password_hash(legacy)
    assert verify_password("Legacy Password", legacy)
    assert not verify_password("wrong password", legacy)


def test_password_strength_policy():
    assert validate_password_strength("short")
    assert validate_password_strength("alllowercase123")
    assert validate_password_strength("NoNumbersHere")
    assert validate_password_strength("StrongPassword9") is None
