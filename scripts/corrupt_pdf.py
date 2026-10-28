"""Create an intentionally modified PDF for PaySeal demo scenario B."""

import sys
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit("Usage: python scripts/corrupt_pdf.py original.pdf modified.pdf")
source, destination = map(Path, sys.argv[1:])
data = source.read_bytes()
if not data.startswith(b"%PDF-"):
    raise SystemExit("Input is not a PDF")
destination.write_bytes(data + b"\n% PaySeal demo modification\n")
print(f"Wrote modified document: {destination}")
