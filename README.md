# SentiChain Python Client

Read full SentiChain token matrices, block time, and free network metadata from Python. Local RSA key and canonical transaction signing helpers remain available for ingestion.

[API documentation](https://sentichain.com/docs) | [Package](https://pypi.org/project/sentichain/) | [Support](mailto:info@sentichain.com)

## Installation and credentials

```bash
python -m pip install sentichain
```

Connect your Ethereum-compatible wallet at [Yototec Credits](https://credits.yototec.com) to initialize its permanent API key and one-time 1,000-credit grant. Reconnecting reuses the same key and balance. Additional credits are arranged through [info@yototec.com](mailto:info@yototec.com). Store your key in `YOTOTEC_API_KEY`; the SDK sends it only in `Authorization: Bearer`, never a URL. The former SentiChain keys and account-points system are retired.

## Purchase a block

A block purchase costs one credit, including complete matrices for every transaction in that block. Metadata and unsuccessful requests are free. Insufficient credit rejects the whole purchase without data or a debit. These rules also apply to administrators.

```python
import os

from sentichain import Client

with Client(api_key=os.environ["YOTOTEC_API_KEY"]) as client:
    print("Block count:", client.get_chain_length("mainnet"))
    block = client.get_last_block("mainnet")
    if block is not None:
        print("Block:", block["block_number"], "Time:", block["block_timestamp"])
        for transaction in block["transactions"]:
            matrix = transaction["post_matrix"]
            print("Matrix dimensions:", len(matrix), len(matrix[0]))
    print("Credits charged:", client.credits_charged)
    print("Credits remaining:", client.credits_remaining)
```

Responses are ordinary dictionaries. A public block has `block_number`, `block_timestamp` (Unix seconds), `hash` and an ordered `transactions` list. Each transaction contains the full rectangular numeric `post_matrix` and, when available, its `matrix_signature`. Empty transaction lists are valid. Block time is the observation time available to readers.

Original text, URLs, source identifiers, publication time, transaction time, sender and nonce are unavailable through public reads for every role. Canonical stored records and ingestion signatures are unchanged. The SDK rejects unexpected public block/transaction fields and malformed matrices rather than returning an old raw-source representation.

Both block methods retain the keyword `full_embedding=True` for callers that specify it. `False` raises `ValueError`: reduced or pooled matrices do not satisfy the public reader contract.

## Retries and purchase identity

Each intentional block-method call creates a fresh UUID in `Idempotency-Key`. Automatic connection and temporary HTTP retries reuse it. The server freezes that operation's block identity, including for a latest-block request. A second intentional purchase gets a new UUID and costs one credit again. Reusing a UUID with different requested resources is a conflict.

Supply `idempotency_key=` when resuming the same purchase after an uncertain transport result. Save the UUID before calling when a process restart must preserve purchase identity. `last_operation_id` records the most recent purchase UUID; transport and HTTP errors also expose `operation_id`. Never create a new purchase ID merely because an earlier commit may have succeeded.

```python
import os
from uuid import uuid4

from sentichain import Client, TransportError

purchase_id = str(uuid4())
with Client(api_key=os.environ["YOTOTEC_API_KEY"], timeout=(5, 30)) as client:
    try:
        block = client.get_block_by_number("mainnet", 130191, idempotency_key=purchase_id)
    except TransportError:
        # Persist purchase_id and resume the same operation after transport recovers.
        raise
```

`credits_charged` and `credits_remaining` contain safe integer receipt headers from the last successful purchase, when supplied by the service. They reset before a new purchase; a failed request does not retain an old receipt. An idempotent response can repeat the original one-credit receipt without another debit. Account balances are viewed through Yototec Credits.

## Configure requests and discover available blocks

`Client` uses `https://api.sentichain.com`. Set `base_url` for another deployment. Redirects are disabled. `timeout` is a positive finite number of seconds or a `(connect, read)` pair, defaulting to thirty seconds. `max_retries` is an integer from zero through five, defaulting to two. `backoff_factor` and `max_backoff` bound retry delays. A server `Retry-After` above `max_backoff` raises the HTTP error without retrying early.

Use a context manager or call `close()` to release connections. The client is intended for sequential use; use a separate client per concurrent worker so purchase receipt attributes remain unambiguous.

```python
from datetime import datetime, timezone

from sentichain import Client

with Client(timeout=15, max_retries=0) as client:
    timestamp = datetime.now(timezone.utc).isoformat()
    number = client.get_block_number_from_timestamp("mainnet", timestamp)
    if number is not None:
        print(number, client.get_timestamp_from_block_number("mainnet", number))
```

Metadata requests contain no credentials or purchase IDs. Check metadata before a paid refresh. A chain length is a count, so derive a requested identifier from metadata rather than treating the count itself as a block identifier.

| Method | Return value | Price |
| --- | --- | --- |
| `get_chain_length(network)` | Block count or `None` | Free |
| `get_last_block_time(network)` | Latest block Unix time or `None` | Free |
| `get_total_number_of_transactions(network)` | Confirmed transaction count or `None` | Free |
| `get_last_block(network, *, full_embedding=True, idempotency_key=None)` | Latest public block or `None` | One credit for a delivered block |
| `get_block_by_number(network, block_number, *, full_embedding=True, idempotency_key=None)` | Requested public block or `None` | One credit for a delivered block |
| `get_block_number_from_timestamp(network, timestamp)` | Block identifier at or before the timestamp, or `None` | Free |
| `get_timestamp_from_block_number(network, block_number)` | ISO timestamp string or `None` | Free |
| `get_max_block_number()` | Latest mapper block identifier or `None` | Free |
| `get_vectorizer_public_key()` | Vectorizer public PEM or `None` | Free |

Use `mainnet` or `testnet`, nonnegative integer block identifiers, and timezone-aware ISO timestamps (`Z` or an explicit offset). Query parameters preserve timezone offsets. A legitimate API JSON `null` returns `None`; errors raise exceptions.

## Verify public matrix proofs

`verify_matrix_signature(matrix, signature, trusted_public_key)` checks the hex proof using RSA-PSS/SHA-256 and the vectorizer's exact JSON matrix format. Pin the trusted vectorizer public key separately. Fetching a key alongside the matrix is useful for discovery but does not establish independent trust.

```python
import os
from pathlib import Path

from sentichain import Client, verify_matrix_signature
from sentichain.keys import public_key_from_str

trusted_key = public_key_from_str(
    Path(os.environ["TRUSTED_VECTORIZER_PUBLIC_KEY_PATH"]).read_text()
)
with Client(api_key=os.environ["YOTOTEC_API_KEY"]) as client:
    block = client.get_block_by_number("mainnet", 130191)
    if block is not None:
        for transaction in block["transactions"]:
            proof = transaction.get("matrix_signature")
            if proof is not None:
                print("Matrix proof valid:", verify_matrix_signature(
                    transaction["post_matrix"], proof, trusted_key
                ))
```

A valid proof authenticates the supplied matrix values against that trusted vectorizer key. It does not verify the omitted transaction fields, a canonical transaction signature/hash, the block hash, block inclusion, or original text. The public view is insufficient for `verify_signature()` or `generate_transaction_hash()` to verify the original signed transaction. Those helpers remain for locally held complete canonical transactions used in ingestion.

## Handle errors and migrate callers

All errors derive from `SentiChainError` and are importable from `sentichain`.

| Exception | Meaning |
| --- | --- |
| `APIError` | Unsuccessful HTTP response, including redirects; exposes `status_code` and `operation_id`. |
| `AuthenticationError` | Missing or rejected credentials/permissions. |
| `InsufficientCreditsError` | HTTP 402; safe `required_credits`, `available_credits`, and `operation_id` attributes. |
| `RateLimitError` | HTTP 429 outside the retry policy; `retry_after` is seconds when available. |
| `TransportError` | Connection/timeout failure after bounded retries; preserves `operation_id`. |
| `ResponseError` | Invalid JSON or an unexpected public response shape. |

```python
import os

from sentichain import Client, InsufficientCreditsError, SentiChainError

try:
    with Client(api_key=os.environ["YOTOTEC_API_KEY"]) as client:
        block = client.get_last_block("mainnet")
except InsufficientCreditsError as error:
    print("Required:", error.required_credits, "Available:", error.available_credits)
except SentiChainError:
    print("The request could not be completed")
```

Migration requires a permanent Yototec key, ordered-list iteration for `transactions`, and full matrix reads. `get_user_info`, both mapper content methods, `get_reasoning_match_chunk_end`, and `analytics_base_url` have been removed. Use Yototec Credits for account access and the SentiMove client combined report interface for intelligence purchases. Retired mapper/source/component routes do not provide an alternate raw or unpaid read. The lightweight SDK contains no network writer; operational ingestion clients must send the new Bearer key while retaining their existing blockchain signing keys and canonical transaction payloads.

## Key and transaction helpers

Key helpers run locally. `generate_key_pair()` returns an RSA private key and its matching public key. `public_key_to_str(public_key)` and `public_key_from_str(pem_string)` convert RSA public keys to and from PEM text.

```python
from sentichain.keys import (
    generate_key_pair,
    public_key_from_str,
    public_key_to_str,
)

private_key, public_key = generate_key_pair()
public_pem = public_key_to_str(public_key)
restored_public_key = public_key_from_str(public_pem)
assert restored_public_key.public_numbers() == public_key.public_numbers()
```

`save_key_pair(private_key, public_key, directory, *, overwrite=False)` saves `private_key.pem` and `public_key.pem` in an existing directory. Files use owner-only permissions on POSIX systems; on Windows they inherit the directory's access controls, so use a restricted directory. The helper rejects a mismatched or non-RSA pair and refuses to replace existing files unless `overwrite=True`. Symbolic links are rejected. `load_key_pair(directory)` reads and validates the matching RSA pair. The private key file is unencrypted; keep the directory private, protect backups, and never log or publish the private key. Keep other readers out of the directory during an overwrite, because replacing the pair's two files is not a single filesystem operation.

`Transaction(sender, public_key, post_timestamp, post_link, post_matrix, matrix_signature, source, nonce=1)` prepares a transaction for local signing. Supply a matching RSA key pair, a finite Unix post timestamp, a nonempty rectangular matrix of finite numeric values, the matrix's authentic vectorizer signature, source text, and the original post link. `sender`, `post_link`, and `matrix_signature` must be nonempty strings; `source` must be a string and `nonce` an integer. The transaction creation timestamp is assigned locally. The `source` field carries the original post text and is included in the signed payload. A transaction signature authenticates the supplied payload; it does not independently verify the matrix signature, the source's factual accuracy, or acceptance by the network. The nonce alone does not prevent replay. Invalid or non-finite payload values raise `ValueError`.

| Helper | Result |
| --- | --- |
| `transaction.to_dict()` | Transaction dictionary without the transaction signature. |
| `transaction.sign_transaction(private_key)` | RSA-PSS signature bytes using SHA-256. |
| `transaction.serialize(signature)` | JSON string with a hex-encoded transaction signature. |
| `verify_signature(transaction_json)` | `True` for a valid transaction signature; `False` for malformed data or a failed check. |
| `generate_transaction_hash(transaction_json)` | Hexadecimal transaction hash from the canonical sorted JSON payload. Raises `ValueError` for malformed, non-object, or non-finite JSON. |

The following function signs an already prepared transaction locally and returns its hash and serialized payload. It does not submit it to the network.

```python
from sentichain import Transaction, generate_transaction_hash, verify_signature


def serialize_signed_transaction(transaction: Transaction, private_key):
    signature = transaction.sign_transaction(private_key)
    payload = transaction.serialize(signature)
    if not verify_signature(payload):
        raise ValueError("Transaction signature verification failed")
    return generate_transaction_hash(payload), payload
```

## Support

Report bugs and request features through [GitHub issues](https://github.com/SentiChain/client_lightweight/issues), or email [info@sentichain.com](mailto:info@sentichain.com).
