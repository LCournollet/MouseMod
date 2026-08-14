"""Pull targeted windows of context out of the (minified, 15 MB) ATK HUB bundle."""

import re
import sys

SRC = r"h:\MouseMod\recon\index-O22l5tpG.js"


def windows(text, pattern, before=300, after=900, limit=20):
    out = []
    for m in re.finditer(pattern, text):
        s = max(0, m.start() - before)
        e = min(len(text), m.end() + after)
        out.append((m.start(), text[s:e]))
        if len(out) >= limit:
            break
    return out


def main():
    text = open(SRC, encoding="utf-8", errors="replace").read()
    pattern = sys.argv[1]
    before = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    after = int(sys.argv[3]) if len(sys.argv) > 3 else 900
    limit = int(sys.argv[4]) if len(sys.argv) > 4 else 20

    hits = windows(text, pattern, before, after, limit)
    print(f"### {len(hits)} hit(s) for /{pattern}/\n")
    for off, snip in hits:
        print(f"--- offset {off} ---")
        print(snip)
        print()


if __name__ == "__main__":
    main()
