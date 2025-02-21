# SentiChain Python Client

A lightweight Python client to interact with the SentiChain [REST API](https://api.sentichain.com).

This library provides convenience methods for:

- [API Balance](https://sentichain.com/app?tab=APIBalance): Retrieve user information (e.g., remaining points).
- [Block Explorer](https://sentichain.com/app?tab=BlockExplorer): Get chain length, last block time, total transactions, etc.
- [Event Map](https://sentichain.com/app?tab=EventMap): Retrieve event map data for specified block ranges.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
  - [Initializing the Client](#initializing-the-client)
  - [Examples](#examples)
- [Supports](#supports)

## Features

- API Balance
  - Fetch detailed user information, including points usage.
- Block Explorer
  - Get chain length and last block time.
  - Retrieve total number of transactions.
  - Fetch the latest block or a specific block by number.
- Event Map
  - Fetch maximum block number processed in the event map.
  - Retrieve “points” snapshots for a specific block or for a range of blocks.

## Requirements

- Python 3.8+ (recommend)
- [requests](https://pypi.org/project/requests/) library

## Installation

Since this is a standalone Python file, you can simply:
1. Clone or download this repository.
2. Ensure you have `requests` installed:
   ```bash
   pip install requests
   ```
3. Place `client.py` in your project, or install it as a local module.

## Usage

### Initializing the Client

```python
from client import Client

# If you have an API key:
api_key = "YOUR_SENTICHAIN_API_KEY"

# Initialize the client with the default SentiChain API URL
client = Client(api_key=api_key)

# Or override the base URL if needed:
# client = Client(base_url="https://some-other-domain.com", api_key=api_key)
```

### Examples

This is an example of how you might use this client:

```python
from client import Client

def main():
    api_key = "YOUR_API_KEY"  # Replace with your real key
    client = Client(api_key=api_key)

    # Get user info
    user_info = client.get_user_info(user_id="12345", api_key=api_key)
    print("User info:", user_info)

    # Check chain length on testnet
    length = client.get_chain_length("testnet")
    print("Chain length:", length)

    # Fetch data for a specific block
    block_data = client.get_block_by_number(network="testnet", block_number=50)
    print("Block #50 data:", block_data)

if __name__ == "__main__":
    main()
```

## Supports

Contributions, bug reports, and feature requests are welcome! Feel free to email us at info@sentichain.com