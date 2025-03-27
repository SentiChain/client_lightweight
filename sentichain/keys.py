"""
Utils functions for managing keys.
"""

from typing import Tuple
import os
from cryptography.hazmat.primitives import serialization  # type: ignore
from cryptography.hazmat.primitives.asymmetric import rsa  # type: ignore
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey  # type: ignore
from cryptography.hazmat.primitives.serialization import load_pem_public_key  # type: ignore


def generate_key_pair() -> Tuple[RSAPrivateKey, RSAPublicKey]:
    """
    Generates a private key and a public key.
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


def public_key_to_str(public_key: RSAPublicKey) -> str:
    """
    Converts a public key to a pem str.
    """
    # Serialize the public key to PEM format
    pem = public_key.public_bytes(  # type: ignore
        encoding=serialization.Encoding.PEM,  # type: ignore
        format=serialization.PublicFormat.SubjectPublicKeyInfo,  # type: ignore
    )  # type: ignore
    return pem.decode("utf-8")


def public_key_from_str(pem_str: str) -> RSAPublicKey:
    """
    Recovers a public key from a pem str.
    """
    return load_pem_public_key(pem_str.encode("utf-8"))  # type: ignore


def save_key_pair(
    private_key: RSAPrivateKey, public_key: RSAPublicKey, directory: str
) -> None:
    """
    Saves a key pair to a local directory.
    """
    with open(f"{directory}/private_key.pem", "wb") as private_file:
        private_file.write(  # type: ignore
            private_key.private_bytes(  # type: ignore
                encoding=serialization.Encoding.PEM,  # type: ignore
                format=serialization.PrivateFormat.TraditionalOpenSSL,  # type: ignore
                encryption_algorithm=serialization.NoEncryption(),  # type: ignore
            )  # type: ignore
        )  # type: ignore
    with open(f"{directory}/public_key.pem", "wb") as public_file:
        public_file.write(  # type: ignore
            public_key.public_bytes(  # type: ignore
                encoding=serialization.Encoding.PEM,  # type: ignore
                format=serialization.PublicFormat.SubjectPublicKeyInfo,  # type: ignore
            )  # type: ignore
        )  # type: ignore


def load_key_pair(directory: str) -> Tuple[RSAPrivateKey, RSAPublicKey]:
    """
    Loads a key pair from a local directory.
    """
    private_key_path = f"{directory}/private_key.pem"
    public_key_path = f"{directory}/public_key.pem"
    if os.path.exists(private_key_path) and os.path.exists(public_key_path):
        with open(private_key_path, "rb") as private_file:
            private_key = serialization.load_pem_private_key(  # type: ignore
                private_file.read(),  # type: ignore
                password=None,  # type: ignore
            )  # type: ignore
        with open(public_key_path, "rb") as public_file:
            public_key = serialization.load_pem_public_key(public_file.read())  # type: ignore
    else:
        raise ValueError(f"{directory} does not contain key pair.")

    return private_key, public_key  # type: ignore
