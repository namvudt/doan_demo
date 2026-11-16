"""Fetch an allowlisted source into a draft JSON snapshot, without calling a model."""

import argparse
import hashlib
import json
from pathlib import Path

from core.config import load_config
from core.ingestion import fetch_source
from core.schemas import SourceRecord


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?")
    parser.add_argument(
        "--publish",
        type=Path,
        help="Publish a human-reviewed JSON snapshot to the configured corpus",
    )
    parser.add_argument("--config", type=Path, default=Path("config/hanoi-evidence.yaml"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/heritage/drafts"))
    args = parser.parse_args()
    policy = load_config(args.config).accuracy.retrieval
    if bool(args.url) == bool(args.publish):
        parser.error("Provide a URL or --publish, exactly one")
    if args.publish:
        source = SourceRecord.model_validate(json.loads(args.publish.read_text(encoding="utf-8")))
        from urllib.parse import urlsplit

        parsed = urlsplit(str(source.url))
        host = parsed.hostname or ""
        if (
            source.annotation_status != "reviewed"
            or not source.reviewer
            or not source.reviewed_at
            or source.type == "maps"
            or parsed.scheme != "https"
            or parsed.port not in {None, 443}
            or parsed.username
            or parsed.password
            or not any(host == d or host.endswith("." + d) for d in policy.allowed_domains)
            or source.content_hash != hashlib.sha256(source.snippet.encode()).hexdigest()
        ):
            parser.error(
                "Publication requires reviewed provenance, allowed host and unchanged content hash"
            )
        path = Path(policy.corpus_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[1] / path
        records = (
            [
                SourceRecord.model_validate(json.loads(line)).model_dump(mode="json")
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if path.is_file()
            else []
        )
        records = [r for r in records if r["source_id"] != source.source_id] + [
            source.model_dump(mode="json")
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8"
        )
        temporary.replace(path)
        print(f"Published reviewed source to {path}; {len(records)} documents.")
        return
    source = fetch_source(args.url, policy)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / (source["source_id"] + ".json")
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Saved draft: {path}. Review content and provenance before adding to the reviewed corpus."
    )


if __name__ == "__main__":
    main()
