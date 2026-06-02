#!/usr/bin/env python3
import argparse
import json
import re
import sys

class WordlistLoader:
    @staticmethod
    def load(path: str) -> list[str]:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return [line.strip() for line in f if line.strip()]

class OperationDetector:
    @staticmethod
    def detect(template: str) -> str:
        stripped = template.strip().lower()
        if stripped.startswith("mutation"):
            return "mutation"
        if stripped.startswith("query"):
            return "query"
        return "mutation"

    @staticmethod
    def strip_keyword(template: str) -> str:
        stripped = template.strip()
        match = re.match(r'^(mutation|query)\s*\{(.*)\}\s*$', stripped, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(2).strip()
        return stripped

class AliasBatcher:
    def __init__(self, prefix: str = "brute"):
        self.prefix = prefix

    def build(self, candidates: list[tuple], query_template: str, operation: str) -> str:
        inner = OperationDetector.strip_keyword(query_template)
        aliases = []
        for i, (label, subs) in enumerate(candidates):
            q = inner
            for placeholder, value in subs.items():
                q = q.replace(placeholder, value)
            aliases.append(f"  {self.prefix}{i}:{q}")
        return f"{operation} {{\n" + "\n".join(aliases) + "\n}"

class JsonArrayBatcher:
    def build(self, candidates: list[tuple], query_template: str, operation: str) -> str:
        inner = OperationDetector.strip_keyword(query_template)
        items = []
        for _, subs in candidates:
            q = inner
            for placeholder, value in subs.items():
                q = q.replace(placeholder, value)
            items.append({"query": f"{operation} {{ {q} }}"})
        return json.dumps(items, indent=2)

class HybridBatcher:
    def __init__(self, prefix: str = "brute", sub_batch_size: int = 10):
        self.prefix = prefix
        self.sub_batch_size = sub_batch_size

    def build(self, candidates: list[tuple], query_template: str, operation: str) -> str:
        inner = OperationDetector.strip_keyword(query_template)
        array_items = []
        for chunk_start in range(0, len(candidates), self.sub_batch_size):
            chunk = candidates[chunk_start:chunk_start + self.sub_batch_size]
            aliases = []
            for i, (label, subs) in enumerate(chunk):
                idx = chunk_start + i
                q = inner
                for placeholder, value in subs.items():
                    q = q.replace(placeholder, value)
                aliases.append(f"  {self.prefix}{idx}:{q}")
            body = f"{operation} {{\n" + "\n".join(aliases) + "\n}"
            array_items.append({"query": body})
        return json.dumps(array_items, indent=2)

class CandidateGenerator:
    @staticmethod
    def password_mode(passwords: list[str]) -> list[tuple]:
        return [(pw, {"FUZZ": pw}) for pw in passwords]

    @staticmethod
    def userpass_mode(usernames: list[str], passwords: list[str]) -> list[tuple]:
        candidates = []
        for user in usernames:
            for pw in passwords:
                candidates.append((f"{user}:{pw}", {"FUZZUSER": user, "FUZZPASS": pw}))
        return candidates

class GraphQLQueryGenerator:
    BATCH_TYPES = {
        "alias": AliasBatcher,
        "json": JsonArrayBatcher,
        "hybrid": HybridBatcher,
    }

    def __init__(self, args):
        self.args = args
        self.operation = OperationDetector.detect(args.query)

    def _get_batcher(self):
        cls = self.BATCH_TYPES[self.args.batch_type]
        if self.args.batch_type in ("alias", "hybrid"):
            return cls(prefix=self.args.prefix)
        return cls()

    def _get_candidates(self) -> list[tuple]:
        if self.args.mode == "password":
            passwords = WordlistLoader.load(self.args.wordlist)
            print(f"[*] Mode: password | {len(passwords)} passwords loaded")
            return CandidateGenerator.password_mode(passwords)

        elif self.args.mode == "userpass":
            usernames = WordlistLoader.load(self.args.userlist)
            passwords = WordlistLoader.load(self.args.wordlist)
            total = len(usernames) * len(passwords)
            print(f"[*] Mode: userpass | {len(usernames)} users x {len(passwords)} passwords = {total} combos")
            return CandidateGenerator.userpass_mode(usernames, passwords)

        else:
            print(f"[-] Unknown mode: {self.args.mode}")
            sys.exit(1)

    def _chunk(self, lst: list, size: int):
        for i in range(0, len(lst), size):
            yield lst[i:i + size]

    def run(self):
        candidates = self._get_candidates()
        batcher = self._get_batcher()
        batch_size = self.args.batch_size
        total_batches = (len(candidates) + batch_size - 1) // batch_size

        print(f"[*] Operation : {self.operation} (auto-detected)")
        print(f"[*] Batch type: {self.args.batch_type}")
        print(f"[*] Batch size: {batch_size} | Total batches: {total_batches}\n")

        for batch_num, chunk in enumerate(self._chunk(candidates, batch_size), 1):
            output = batcher.build(chunk, self.args.query, self.operation)

            print(f"{'='*60}")
            print(f"  Batch {batch_num}/{total_batches} — {len(chunk)} candidates")
            print(f"{'='*60}")
            print(output)
            print()

            if self.args.output:
                suffix = f".batch{batch_num}" if total_batches > 1 else ""
                fname = f"{self.args.output}{suffix}.txt"
                with open(fname, "w") as f:
                    f.write(output)
                print(f"[*] Saved to {fname}\n")

def parse_args():
    parser = argparse.ArgumentParser(
        description="GraphQL Batch Query Generator",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument("-q", "--query", required=True,
        help=(
            "GraphQL operation with placeholders:\n"
            "  FUZZ       — password\n"
            "  FUZZUSER   — username (userpass mode)\n"
            "  FUZZPASS   — password (userpass mode)\n"
            "Operation type auto-detected from keyword (defaults to mutation).\n"
            'Example: login(input:{username:"test",password:"FUZZ"}){token success}'
        ))

    parser.add_argument("--mode", choices=["password", "userpass"], default="password",
        help="Brute force mode (default: password)")

    parser.add_argument("-w", "--wordlist", help="Password wordlist")
    parser.add_argument("--userlist", help="Username wordlist (userpass mode)")

    parser.add_argument("--batch-type", choices=["alias", "json", "hybrid"], default="alias",
        help="Batching method (default: alias)")
    parser.add_argument("-b", "--batch-size", type=int, default=100,
        help="Candidates per batch (default: 100)")
    parser.add_argument("-p", "--prefix", default="brute",
        help="Alias prefix for alias/hybrid mode (default: brute)")

    parser.add_argument("-o", "--output", help="Save output to file(s) with this base name")

    args = parser.parse_args()

    if args.mode == "password" and not args.wordlist:
        parser.error("--wordlist is required for password mode")
    if args.mode == "userpass" and (not args.wordlist or not args.userlist):
        parser.error("--wordlist and --userlist are required for userpass mode")

    return args

def main():
    args = parse_args()
    generator = GraphQLQueryGenerator(args)
    generator.run()

if __name__ == "__main__":
    main()
