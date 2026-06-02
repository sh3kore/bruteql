# Bruteql

A GraphQL batch query generator for security testing. Generates aliased or batched queries to bypass rate limiting on GraphQL endpoints — output is ready to copy into Burp Suite, curl, or any HTTP client.

---

## How it works

Many GraphQL rate limiters count HTTP requests rather than individual operations. This tool exploits that by stuffing multiple login attempts into a single request using three batching techniques:

| Method | Description |
|--------|-------------|
| `alias` | Multiple aliased operations inside one block |
| `json` | JSON array of query objects in one HTTP request |
| `hybrid` | Aliased operations inside a JSON array (combines both) |

The tool generates the query and prints it — no requests are sent.

---

## Installation

No dependencies beyond Python 3.10+.

```bash
git clone https://github.com/sh3kore/bruteql.git
cd bruteql
python3 main.py --help
```

---

## Usage

```
python3 main.py -q <query> -w <wordlist> [options]
```
