"""Keep the app's CLI contract while using MinerU 4's stateless Python API."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", type=Path, required=True)
    parser.add_argument("-o", type=Path, required=True)
    parser.add_argument("-b", choices=("basic", "standard", "advanced", "flash"), default="basic")
    args = parser.parse_args()
    from mineru.parser import ParseResult, parse
    from mineru.parser.writer import FileBasedDataWriter
    from mineru.render import RenderFormat, render

    args.o.mkdir(parents=True, exist_ok=True)
    result = parse(args.p, tier=args.b)
    result.save(FileBasedDataWriter(str(args.o)))
    # Read the saved copy so content-list references use materialized image paths.
    saved = ParseResult.from_json((args.o / "middle_json.json").read_text())
    content = render(saved.middle_json, RenderFormat.CONTENT_LIST)
    (args.o / "content_list.json").write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
