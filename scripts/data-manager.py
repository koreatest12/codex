#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = Path("/opt/app") if Path("/opt/app/data_manager.py").exists() else ROOT / "app"
sys.path.insert(0, str(APP_DIR))

from data_manager import DataManager, DataManagerError  # noqa: E402


def load_json(text: str | None, file_path: str | None):
    if (text is None) == (file_path is None):
        raise SystemExit("exactly one of --json or --file is required")
    raw = text if text is not None else Path(file_path).read_text(encoding="utf-8")
    return json.loads(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="Versioned public-data manager.")
    parser.add_argument(
        "--db",
        default=os.environ.get("MANAGED_DATA_DB_PATH", "/data/managed-data.db"),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init")
    sub.add_parser("datasets")

    create = sub.add_parser("create-dataset")
    create.add_argument("dataset_id")
    create.add_argument("--description", default="")

    listing = sub.add_parser("list")
    listing.add_argument("dataset_id")

    get = sub.add_parser("get")
    get.add_argument("dataset_id")
    get.add_argument("record_id")

    put = sub.add_parser("put")
    put.add_argument("dataset_id")
    put.add_argument("record_id")
    put.add_argument("--json")
    put.add_argument("--file")
    put.add_argument("--expected-revision", type=int)

    delete = sub.add_parser("delete")
    delete.add_argument("dataset_id")
    delete.add_argument("record_id")
    delete.add_argument("--expected-revision", type=int)

    history = sub.add_parser("history")
    history.add_argument("dataset_id")
    history.add_argument("record_id")

    export = sub.add_parser("export")
    export.add_argument("--dataset")
    export.add_argument("--output")

    imp = sub.add_parser("import")
    imp.add_argument("file")

    verify = sub.add_parser("verify")
    verify.add_argument("--dataset")

    args = parser.parse_args()
    manager = DataManager(args.db)
    manager.init_schema()

    try:
        if args.command == "init":
            result = {"ok": True, "db": str(args.db)}
        elif args.command == "datasets":
            result = manager.list_datasets()
        elif args.command == "create-dataset":
            result = manager.create_dataset(args.dataset_id, args.description)
        elif args.command == "list":
            result = manager.list_records(args.dataset_id)
        elif args.command == "get":
            result = manager.get_record(args.dataset_id, args.record_id)
        elif args.command == "put":
            result = manager.put_record(
                args.dataset_id,
                args.record_id,
                load_json(args.json, args.file),
                args.expected_revision,
            )
        elif args.command == "delete":
            result = manager.delete_record(
                args.dataset_id,
                args.record_id,
                args.expected_revision,
            )
        elif args.command == "history":
            result = manager.history(args.dataset_id, args.record_id)
        elif args.command == "export":
            result = manager.export_bundle(args.dataset)
            if args.output:
                Path(args.output).write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                result = {"ok": True, "output": args.output}
        elif args.command == "import":
            bundle = json.loads(Path(args.file).read_text(encoding="utf-8"))
            result = manager.import_bundle(bundle)
        elif args.command == "verify":
            result = manager.verify(args.dataset)
            if not result["ok"]:
                print(json.dumps(result, ensure_ascii=False, indent=2))
                raise SystemExit(1)
        else:
            raise SystemExit("unknown command")
    except DataManagerError as exc:
        raise SystemExit(str(exc)) from exc

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
