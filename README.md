# SentiChain Python Client

Read SentiChain blocks, transactions, network statistics, event maps, and account information from Python. The package also provides local RSA key and transaction signing helpers, plus access to public SentiMove analytics.

[API documentation](https://sentichain.com/docs) | [Package](https://pypi.org/project/sentichain/) | [Support](mailto:info@sentichain.com)

## Installation

Use a supported Python installation. Python and dependency requirements are declared in the package metadata.

```bash
python -m pip install sentichain
```

## Read the latest block

Public network statistics do not require an API key. Block transaction details and mapper content depend on your API access and available account points. Store your SentiChain API key in the `SENTICHAIN_API_KEY` environment variable before running this example.

```python
import os

from sentichain import Client

with Client(api_key=os.environ["SENTICHAIN_API_KEY"]) as client:
    print("Block count:", client.get_chain_length(network="mainnet"))
    block = client.get_last_block(network="mainnet")
    if block is not None:
        print("Latest block:", block["block_number"])
        for transaction_hash, transaction in block["transactions"].items():
            print("Transaction:", transaction_hash)
            print("Source:", transaction["source"])
            print("Matrix rows:", len(transaction["post_matrix"]))
```

Responses are ordinary Python values, not block or transaction objects. A block is a dictionary; its `transactions` field maps transaction hashes to transaction dictionaries. Each transaction's `post_matrix` is a nested numeric list, not a `vector` attribute. Transaction details may be hidden when access is unavailable. Requesting a block does not guarantee that it contains transactions.

Block methods accept the keyword-only `full_embedding` option, which defaults to `True`. Pass `full_embedding=False` to request reduced embedding detail. The API determines the returned representation and applies the same access checks.

```python
from sentichain import Client

with Client() as client:
    block = client.get_last_block(network="mainnet", full_embedding=False)
    if block is not None:
        print("Latest block:", block["block_number"])
```

## Configure requests

`Client` uses `https://api.sentichain.com` for blockchain, mapper, and account reads. Public analytics use the separate `https://api.sentimove.com` service. Set `base_url` and `analytics_base_url` independently when connecting to other deployments. The SentiChain API key is never attached to analytics requests, and HTTP redirects are not followed.

```python
import os

from sentichain import Client

with Client(
    api_key=os.environ["SENTICHAIN_API_KEY"],
    timeout=(5, 30),
    max_retries=2,
    backoff_factor=0.5,
    max_backoff=5,
) as client:
    user = client.get_user_info(user_id=os.environ["SENTICHAIN_USER_ID"])
    if user is not None:
        print("Account information retrieved")
```

`timeout` is a positive finite number of seconds or a `(connect, read)` pair. It defaults to thirty seconds. `max_retries` accepts an integer from zero through five and defaults to two. It bounds retries of connection failures and temporary HTTP responses; set it to zero to disable retries. `backoff_factor` and `max_backoff` control the retry delay. If the service's `Retry-After` delay exceeds `max_backoff`, the client raises the corresponding HTTP error instead of retrying early. Invalid configuration raises `ValueError`.

Use `Client` as a context manager to close its HTTP session automatically. If you create a client directly, call `client.close()` when finished. `get_user_info(user_id)` uses the client's API key; pass `api_key=` to override it for that call.

## API reference

Successful methods return the named value from the API response. A legitimate JSON `null` is returned as `None`. Request failures raise an exception instead of being returned as `None`.

| Method | Return value | Access and behavior |
| --- | --- | --- |
| `get_user_info(user_id, api_key=None)` | Account dictionary or `None` | Requires the user's API key; defaults to the client key. |
| `get_chain_length(network)` | Integer block count or `None` | Public network statistic. The count is not a block identifier. |
| `get_last_block_time(network)` | Numeric Unix timestamp or `None` | Time of the latest block. |
| `get_total_number_of_transactions(network)` | Integer transaction count or `None` | Confirmed transactions on the selected network. |
| `get_last_block(network, *, full_embedding=True)` | Block dictionary or `None` | Latest block; transaction details depend on access. |
| `get_block_by_number(network, block_number, *, full_embedding=True)` | Block dictionary or `None` | Block with the requested identifier; transaction details depend on access. |
| `get_block_number_from_timestamp(network, timestamp)` | Integer block identifier or `None` | Latest available block at or before the supplied time. |
| `get_timestamp_from_block_number(network, block_number)` | Timestamp string or `None` | Timestamp for the requested block. |
| `get_max_block_number()` | Integer block identifier or `None` | Latest mainnet block processed by the mapper. Mapper progress can trail the chain. |
| `get_points_by_block_no_embedding(block_number)` | List of point rows or `None` | Mapper snapshots for one block; post content depends on access. |
| `get_points_by_block_range_no_embedding(start_block, end_block)` | List of point rows or `None` | Mapper snapshots for an inclusive block range; post content depends on access. |
| `get_reasoning_match_chunk_end(ticker, summary_type, user_chunk_end)` | Reasoning string or `None` | Public SentiMove analytics for the latest available chunk at or before the cutoff. |

Use `mainnet` or `testnet` for `network`; block identifiers and range endpoints must be nonnegative integers. Pass a timezone-aware ISO timestamp string to `get_block_number_from_timestamp`, using `Z` or an explicit UTC offset. Query parameters are encoded, so offsets retain their meaning. Derive block identifiers from an actual block or mapper response rather than assuming the block count is the latest identifier.

```python
from datetime import datetime, timezone

from sentichain import Client

with Client() as client:
    timestamp = datetime.now(timezone.utc).isoformat()
    block_number = client.get_block_number_from_timestamp(network="mainnet", timestamp=timestamp)
    if block_number is not None:
        print(client.get_timestamp_from_block_number("mainnet", block_number))

    mapped_block = client.get_max_block_number()
    if mapped_block is not None:
        points = client.get_points_by_block_no_embedding(mapped_block)
        print("Mapper snapshots:", len(points) if points is not None else 0)
```

Mapper point rows contain coordinates, cluster information, and permitted post content. The SDK preserves each row as returned by the API, whether a dictionary or a list. Empty lists and hidden content are valid results. The methods named `no_embedding` do not return embedding matrices.

## Public SentiMove analytics

Use `sm_events` for event analysis or `sm_signal` for signal analysis. Availability depends on the ticker, summary type, and completed analytics chunks. These methods read published analysis; the SDK does not generate trading decisions.

```python
from sentichain import Client

with Client(analytics_base_url="https://api.sentimove.com") as client:
    block = client.get_last_block(network="mainnet", full_embedding=False)
    if block is not None:
        reasoning = client.get_reasoning_match_chunk_end(
            ticker="BTC",
            summary_type="sm_events",
            user_chunk_end=block["block_number"],
        )
        if reasoning is not None:
            print(reasoning)
```

## Handle errors

All request errors derive from `SentiChainError` and can be imported from `sentichain`.

| Exception | Meaning |
| --- | --- |
| `APIError` | An unsuccessful HTTP response, including redirects. Its `status_code` identifies the response. |
| `AuthenticationError` | An authentication or permission response. Subclass of `APIError`. |
| `RateLimitError` | A rate limit response that cannot be retried within the configured policy. Subclass of `APIError`; `retry_after` contains a delay in seconds when available. |
| `TransportError` | A connection, timeout, or other HTTP transport failure after allowed retries. |
| `ResponseError` | Invalid JSON or an unexpected successful response shape. |

```python
from sentichain import AuthenticationError, Client, RateLimitError, SentiChainError

try:
    with Client() as client:
        print(client.get_chain_length(network="mainnet"))
except AuthenticationError:
    print("Check API access before retrying")
except RateLimitError as error:
    print("Rate limited; retry delay:", error.retry_after)
except SentiChainError:
    print("The request could not be completed")
```

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
