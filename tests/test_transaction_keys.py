"""Transaction compatibility, input validation, and RSA key file safety."""

import hashlib
import json
import os
from unittest.mock import patch

import pytest
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding

from sentichain import Transaction, generate_transaction_hash, keys, verify_signature


@pytest.fixture(scope="module")
def key_pairs():
    return keys.generate_key_pair(), keys.generate_key_pair()


@pytest.fixture
def transaction(key_pairs):
    private_key, public_key = key_pairs[0]
    matrix = [[0.5, 0.3, 0.2], [0.1, 0.7, 0.2]]
    matrix_signature = private_key.sign(
        json.dumps(matrix, sort_keys=True).encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    ).hex()
    with patch("sentichain.transaction.time.time", return_value=1792454400.125):
        return Transaction(
            sender="market-observer",
            public_key=public_key,
            post_timestamp=1792454300.5,
            post_link="CoinDesk/status/2110000000000000000",
            post_matrix=matrix,
            matrix_signature=matrix_signature,
            source="Bitcoin exchange reserves fell during the session.",
            nonce=42,
        )


def sign_payload(payload, private_key):
    signature = private_key.sign(
        json.dumps(payload, sort_keys=True).encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return json.dumps({**payload, "signature": signature.hex()}, sort_keys=True)


def test_signed_serialization_matches_sorted_json_contract(transaction, key_pairs):
    private_key, public_key = key_pairs[0]
    signature = transaction.sign_transaction(private_key)
    serialized = transaction.serialize(signature)
    payload = transaction.to_dict()
    public_key.verify(
        signature,
        json.dumps(payload, sort_keys=True).encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    assert serialized == json.dumps({**payload, "signature": signature.hex()}, sort_keys=True)
    assert verify_signature(serialized)
    expected = hashlib.sha256(serialized.encode()).hexdigest()
    assert generate_transaction_hash(serialized) == expected
    reverse_order = dict(reversed(list(json.loads(serialized).items())))
    assert generate_transaction_hash(json.dumps(reverse_order)) == expected


def test_large_embedding_matrix_and_integer_values_are_supported(transaction, key_pairs):
    transaction.post_matrix = [[float(column) / 768 for column in range(768)] for _ in range(24)]
    transaction.post_matrix[0][0] = 0
    transaction.matrix_signature = (
        key_pairs[0][0]
        .sign(
            json.dumps(transaction.post_matrix, sort_keys=True).encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        .hex()
    )
    serialized = transaction.serialize(transaction.sign_transaction(key_pairs[0][0]))
    assert verify_signature(serialized)
    assert len(json.loads(serialized)["post_matrix"]) == 24


def test_tampered_source_signature_and_wrong_key_fail(transaction, key_pairs):
    signed = transaction.serialize(transaction.sign_transaction(key_pairs[0][0]))
    payload = json.loads(signed)
    payload["source"] += " Updated."
    assert not verify_signature(json.dumps(payload))
    payload = json.loads(signed)
    payload["signature"] = "00" * 256
    assert not verify_signature(json.dumps(payload))
    payload = json.loads(signed)
    payload["public_key"] = keys.public_key_to_str(key_pairs[1][1])
    assert not verify_signature(json.dumps(payload))
    with pytest.raises(ValueError, match="does not match"):
        transaction.sign_transaction(key_pairs[1][0])


@pytest.mark.parametrize("serialized", [None, b"{}", "not json", "[]", "null", "1", "true"])
def test_signature_verification_rejects_nonobjects(serialized):
    assert verify_signature(serialized) is False


@pytest.mark.parametrize("signature", [None, 7, [], {}, "", "invalid hex", "ff"])
def test_signature_verification_rejects_invalid_signature_values(signature, transaction, key_pairs):
    payload = transaction.to_dict()
    payload["signature"] = signature
    assert verify_signature(json.dumps(payload)) is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sender", None),
        ("post_link", ""),
        ("source", []),
        ("nonce", True),
        ("post_timestamp", "2026-10-20T00:00:00Z"),
        ("transaction_timestamp", float("inf")),
        ("post_matrix", []),
        ("post_matrix", [[]]),
        ("post_matrix", [[1], [2, 3]]),
        ("post_matrix", [[True]]),
        ("post_matrix", [[float("nan")]]),
        ("matrix_signature", 7),
        ("extra", {"value": float("inf")}),
    ],
)
def test_valid_rsa_signature_does_not_accept_invalid_fields(field, value, transaction, key_pairs):
    payload = transaction.to_dict()
    payload[field] = value
    assert verify_signature(sign_payload(payload, key_pairs[0][0])) is False


def test_signature_verification_rejects_non_rsa_public_key(transaction):
    private_key = ec.generate_private_key(ec.SECP256R1())
    payload = transaction.to_dict()
    payload["public_key"] = (
        private_key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    payload["signature"] = private_key.sign(
        json.dumps(payload, sort_keys=True).encode(), ec.ECDSA(hashes.SHA256())
    ).hex()
    assert verify_signature(json.dumps(payload)) is False


@pytest.mark.parametrize("public_key", [None, 7, [], {}, "invalid pem"])
def test_signature_verification_rejects_invalid_public_keys(public_key, transaction, key_pairs):
    payload = transaction.to_dict()
    payload["public_key"] = public_key
    assert verify_signature(sign_payload(payload, key_pairs[0][0])) is False


def test_signature_verification_does_not_hide_unexpected_backend_failure(transaction, key_pairs):
    signed = transaction.serialize(transaction.sign_transaction(key_pairs[0][0]))
    with patch("sentichain.transaction.public_key_from_str", side_effect=RuntimeError("backend")):
        with pytest.raises(RuntimeError, match="backend"):
            verify_signature(signed)


@pytest.mark.parametrize(
    "serialized", [None, b"{}", "not json", "[]", "null", "1", '{"x": NaN}', '{"x": 1e400}']
)
def test_hash_rejects_invalid_json_objects_and_nonfinite_values(serialized):
    with pytest.raises(ValueError):
        generate_transaction_hash(serialized)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sender", ""),
        ("public_key", None),
        ("post_timestamp", float("inf")),
        ("post_timestamp", True),
        ("post_matrix", "[[1.0]]"),
        ("post_matrix", []),
        ("post_matrix", [1, 2]),
        ("post_matrix", [[1], []]),
        ("post_matrix", [[1], [2, 3]]),
        ("post_matrix", [["1.0"]]),
        ("post_matrix", [[False]]),
        ("post_matrix", [[float("nan")]]),
        ("matrix_signature", None),
        ("source", None),
        ("nonce", 1.5),
        ("nonce", False),
    ],
)
def test_constructor_validates_field_types(field, value, transaction):
    payload = transaction.to_dict()
    del payload["transaction_timestamp"]
    payload["public_key"] = transaction.public_key
    payload[field] = value
    with pytest.raises(ValueError):
        Transaction(**payload)


def test_mutated_transaction_and_invalid_signature_bytes_are_rejected(transaction, key_pairs):
    transaction.post_matrix[0][0] = float("inf")
    with pytest.raises(ValueError):
        transaction.sign_transaction(key_pairs[0][0])
    with pytest.raises(ValueError):
        transaction.serialize(b"signature")
    for value in (None, "aa", b""):
        with pytest.raises(ValueError):
            transaction.serialize(value)


def test_public_key_conversion_round_trip_and_rsa_validation(key_pairs):
    public_key = key_pairs[0][1]
    pem = keys.public_key_to_str(public_key)
    assert keys.public_key_from_str(pem).public_numbers() == public_key.public_numbers()
    ec_public = ec.generate_private_key(ec.SECP256R1()).public_key()
    ec_pem = ec_public.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    for value in (None, "invalid pem", ec_pem):
        with pytest.raises(ValueError):
            keys.public_key_from_str(value)
    for value in (None, ec_public):
        with pytest.raises(ValueError):
            keys.public_key_to_str(value)


def test_unsupported_public_key_algorithm_is_reported_as_invalid(key_pairs, transaction):
    pem = keys.public_key_to_str(key_pairs[0][1])
    signed = transaction.serialize(transaction.sign_transaction(key_pairs[0][0]))
    with patch(
        "sentichain.keys.serialization.load_pem_public_key",
        side_effect=UnsupportedAlgorithm("unsupported public key algorithm"),
    ):
        with pytest.raises(ValueError, match="RSA PEM"):
            keys.public_key_from_str(pem)
        assert verify_signature(signed) is False


def test_saved_pair_has_owner_only_permissions_and_loads(tmp_path, key_pairs):
    previous = os.umask(0o022)
    try:
        keys.save_key_pair(*key_pairs[0], tmp_path)
    finally:
        os.umask(previous)
    if os.name == "posix":
        for path in tmp_path.iterdir():
            assert path.stat().st_mode & 0o777 == 0o600
    private_key, public_key = keys.load_key_pair(tmp_path)
    assert private_key.private_numbers() == key_pairs[0][0].private_numbers()
    assert public_key.public_numbers() == key_pairs[0][1].public_numbers()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["private_key.pem", "public_key.pem"]


def test_existing_pair_requires_explicit_overwrite_and_is_restricted(tmp_path, key_pairs):
    keys.save_key_pair(*key_pairs[0], tmp_path)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    with pytest.raises(FileExistsError):
        keys.save_key_pair(*key_pairs[1], tmp_path)
    assert before == {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    for path in tmp_path.iterdir():
        path.chmod(0o644)
    keys.save_key_pair(*key_pairs[1], tmp_path, overwrite=True)
    assert keys.load_key_pair(tmp_path)[1].public_numbers() == key_pairs[1][1].public_numbers()
    if os.name == "posix":
        assert all(path.stat().st_mode & 0o777 == 0o600 for path in tmp_path.iterdir())


def test_save_validates_directory_and_matching_keys_before_writing(tmp_path, key_pairs):
    with pytest.raises(FileNotFoundError):
        keys.save_key_pair(*key_pairs[0], tmp_path / "missing")
    with pytest.raises(ValueError, match="do not match"):
        keys.save_key_pair(key_pairs[0][0], key_pairs[1][1], tmp_path)
    with pytest.raises(ValueError, match="boolean"):
        keys.save_key_pair(*key_pairs[0], tmp_path, overwrite="False")
    with pytest.raises(ValueError, match="RSA private key"):
        keys.save_key_pair(None, key_pairs[0][1], tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(os.name == "nt", reason="Creating links requires Windows privileges.")
def test_symlink_destination_is_rejected_without_touching_target(tmp_path, key_pairs):
    other = tmp_path / "retained.pem"
    other.write_bytes(b"retained content")
    private_path = tmp_path / "private_key.pem"
    private_path.symlink_to(other)
    with pytest.raises(ValueError, match="regular files"):
        keys.save_key_pair(*key_pairs[0], tmp_path, overwrite=True)
    assert other.read_bytes() == b"retained content"
    assert private_path.is_symlink()
    with pytest.raises(ValueError, match="regular files"):
        keys.load_key_pair(tmp_path)


def test_staging_failure_preserves_existing_pair_and_cleans_temporary_files(tmp_path, key_pairs):
    keys.save_key_pair(*key_pairs[0], tmp_path)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    stage = keys._stage_file
    calls = 0

    def fail_second_stage(directory, content):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("write interrupted")
        return stage(directory, content)

    with patch("sentichain.keys._stage_file", side_effect=fail_second_stage):
        with pytest.raises(OSError, match="write interrupted"):
            keys.save_key_pair(*key_pairs[1], tmp_path, overwrite=True)
    assert before == {path.name: path.read_bytes() for path in tmp_path.iterdir()}


def test_overwrite_publication_failure_restores_existing_pair(tmp_path, key_pairs):
    keys.save_key_pair(*key_pairs[0], tmp_path)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    replace = os.replace
    calls = 0

    def fail_second_replace(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("replace interrupted")
        return replace(source, target)

    with patch("sentichain.keys.os.replace", side_effect=fail_second_replace):
        with pytest.raises(OSError, match="replace interrupted"):
            keys.save_key_pair(*key_pairs[1], tmp_path, overwrite=True)
    assert before == {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    assert keys.load_key_pair(tmp_path)[1].public_numbers() == key_pairs[0][1].public_numbers()


def test_failed_rollback_retains_original_private_key_backup(tmp_path, key_pairs):
    keys.save_key_pair(*key_pairs[0], tmp_path)
    original_private = (tmp_path / "private_key.pem").read_bytes()
    original_public = (tmp_path / "public_key.pem").read_bytes()
    replace = os.replace
    calls = 0

    def fail_after_first_replace(source, target):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise OSError("replacement unavailable")
        return replace(source, target)

    with patch("sentichain.keys.os.replace", side_effect=fail_after_first_replace):
        with pytest.raises(OSError, match="recovery was incomplete") as error:
            keys.save_key_pair(*key_pairs[1], tmp_path, overwrite=True)
    backups = list(tmp_path.glob(".sentichain-key-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original_private
    assert str(backups[0]) in str(error.value)
    assert (tmp_path / "public_key.pem").read_bytes() == original_public
    if os.name == "posix":
        assert backups[0].stat().st_mode & 0o777 == 0o600


def test_new_pair_publication_failure_removes_partial_pair(tmp_path, key_pairs):
    link = os.link
    calls = 0

    def fail_second_link(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("link interrupted")
        return link(source, target)

    with patch("sentichain.keys.os.link", side_effect=fail_second_link):
        with pytest.raises(OSError, match="link interrupted"):
            keys.save_key_pair(*key_pairs[0], tmp_path)
    assert not list(tmp_path.iterdir())


def test_load_rejects_missing_mismatched_invalid_and_non_rsa_files(tmp_path, key_pairs):
    with pytest.raises(FileNotFoundError):
        keys.load_key_pair(tmp_path)
    keys.save_key_pair(*key_pairs[0], tmp_path)
    (tmp_path / "public_key.pem").write_text(keys.public_key_to_str(key_pairs[1][1]))
    with pytest.raises(ValueError, match="do not match"):
        keys.load_key_pair(tmp_path)
    (tmp_path / "private_key.pem").write_bytes(b"invalid pem")
    with pytest.raises(ValueError, match="unencrypted RSA"):
        keys.load_key_pair(tmp_path)
    ec_private = ec.generate_private_key(ec.SECP256R1())
    (tmp_path / "private_key.pem").write_bytes(
        ec_private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    with pytest.raises(ValueError, match="RSA private key"):
        keys.load_key_pair(tmp_path)


def test_load_rejects_encrypted_private_key_and_unsupported_algorithm(tmp_path, key_pairs):
    keys.save_key_pair(*key_pairs[0], tmp_path)
    (tmp_path / "private_key.pem").write_bytes(
        key_pairs[0][0].private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(b"temporary test password"),
        )
    )
    with pytest.raises(ValueError, match="unencrypted RSA"):
        keys.load_key_pair(tmp_path)
    with patch(
        "sentichain.keys.serialization.load_pem_private_key",
        side_effect=UnsupportedAlgorithm("unsupported private key algorithm"),
    ):
        with pytest.raises(ValueError, match="unencrypted RSA"):
            keys.load_key_pair(tmp_path)
