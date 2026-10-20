"""Generate, validate, and store RSA key pairs."""

import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_key_pair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """Generate an RSA key pair with a 2048-bit modulus."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def public_key_to_str(public_key: rsa.RSAPublicKey) -> str:
    """Encode an RSA public key as PEM; reject other key types."""
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise ValueError("public_key must be an RSA public key.")
    return public_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("utf-8")


def public_key_from_str(pem_str: str) -> rsa.RSAPublicKey:
    """Decode an RSA public key from PEM, raising ``ValueError`` on invalid input."""
    if not isinstance(pem_str, str):
        raise ValueError("The public key must be a PEM string.")
    try:
        public_key = serialization.load_pem_public_key(pem_str.encode("utf-8"))
    except (ValueError, TypeError, UnicodeError, UnsupportedAlgorithm) as exc:
        raise ValueError("The public key must be valid RSA PEM.") from exc
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise ValueError("The public key must be an RSA public key.")
    return public_key


def _validate_pair(private_key: Any, public_key: Any) -> None:
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise ValueError("private_key must be an RSA private key.")
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise ValueError("public_key must be an RSA public key.")
    if private_key.public_key().public_numbers() != public_key.public_numbers():
        raise ValueError("The private and public keys do not match.")


def _regular_file(path: Path) -> os.stat_result | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Key paths must be regular files, not symbolic links.")
    return info


def _read_regular_file(path: Path) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            raise ValueError("Key paths must be regular files, not symbolic links.")
        return stream.read(), info


def _stage_file(directory: Path, content: bytes) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".sentichain-key-", dir=directory)
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.chmod(staged, 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        return staged
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def save_key_pair(
    private_key: rsa.RSAPrivateKey,
    public_key: rsa.RSAPublicKey,
    directory: str | os.PathLike[str],
    *,
    overwrite: bool = False,
) -> None:
    """Save a matching pair as ``private_key.pem`` and ``public_key.pem``.

    The directory must exist. Both files receive mode ``0600`` on POSIX. On Windows,
    files inherit directory access controls; use a directory restricted to the key
    owner. Existing files require ``overwrite=True``; symbolic links are rejected.
    Both files are staged before each destination is published atomically. Replacing
    two separate files is not one filesystem transaction, so concurrent readers
    should not read the directory during an overwrite. If replacement and rollback
    both fail, the exception identifies retained backups of the original files.
    """
    _validate_pair(private_key, public_key)
    if not isinstance(overwrite, bool):
        raise ValueError("overwrite must be a boolean.")
    folder = Path(directory)
    if not folder.is_dir():
        raise FileNotFoundError("The key directory must already exist.")
    targets = [folder / "private_key.pem", folder / "public_key.pem"]
    original = [_regular_file(target) for target in targets]
    if not overwrite and any(info is not None for info in original):
        raise FileExistsError("Key files already exist; use overwrite=True to replace them.")
    contents = [
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ),
        public_key_to_str(public_key).encode("utf-8"),
    ]
    staged: list[Path] = []
    backups: dict[int, Path] = {}
    published: list[int] = []
    retained: set[Path] = set()
    try:
        for content in contents:
            staged.append(_stage_file(folder, content))
        for index, info in enumerate(original):
            if info is not None:
                content, observed = _read_regular_file(targets[index])
                if not os.path.samestat(info, observed):
                    raise FileExistsError("Key files changed while preparing the save.")
                backups[index] = _stage_file(folder, content)
        for index, target in enumerate(targets):
            current = _regular_file(target)
            expected = original[index]
            if expected is None:
                os.link(staged[index], target)
            else:
                if current is None or not os.path.samestat(expected, current):
                    raise FileExistsError("Key files changed while preparing the save.")
                os.replace(staged[index], target)
            published.append(index)
    except BaseException as exc:
        restore_errors = []
        for index in reversed(published):
            try:
                if index in backups:
                    os.replace(backups[index], targets[index])
                elif targets[index].exists() and os.path.samestat(
                    targets[index].stat(), staged[index].stat()
                ):
                    targets[index].unlink()
            except OSError:
                if index in backups:
                    retained.add(backups[index])
                    restore_errors.append(f"{targets[index].name}: {backups[index]}")
                else:
                    restore_errors.append(f"could not remove {targets[index]}")
        if restore_errors:
            raise OSError(
                "Key replacement failed and recovery was incomplete. Retained files: "
                + "; ".join(restore_errors)
            ) from exc
        raise
    finally:
        for path in [*staged, *backups.values()]:
            if path not in retained:
                path.unlink(missing_ok=True)


def load_key_pair(
    directory: str | os.PathLike[str],
) -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """Load a matching unencrypted RSA pair, rejecting links and unsupported keys."""
    folder = Path(directory)
    private_path = folder / "private_key.pem"
    public_path = folder / "public_key.pem"
    _regular_file(private_path)
    _regular_file(public_path)
    private_pem, _ = _read_regular_file(private_path)
    public_pem, _ = _read_regular_file(public_path)
    try:
        private_key = serialization.load_pem_private_key(private_pem, password=None)
        public_key = serialization.load_pem_public_key(public_pem)
    except (ValueError, TypeError, UnsupportedAlgorithm) as exc:
        raise ValueError("Key files must contain unencrypted RSA PEM keys.") from exc
    _validate_pair(private_key, public_key)
    return private_key, public_key
