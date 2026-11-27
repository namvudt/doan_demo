"""Export blind draft cases and import human review without fabricating gold labels."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from core.evaluation import digest, validate_manifest
from scripts.evaluate import ROOT, prepare, read

INPUT_FIELDS = ("case_id", "image_path", "image_family", "question", "degradation")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def image_hash(case):
    path = Path(case["image_path"])
    path = path if path.is_absolute() else ROOT / path
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_pack(output, *, pilot=None):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Review pack destination must be empty; preserve existing human edits")
    pilot = pilot or read(ROOT / "config/evaluation/hanoi-pilot.json")
    source_cases = prepare(pilot)
    cases, mapping, copied = [], [], {}
    for index, raw in enumerate(source_cases, 1):
        original = ROOT / raw["image_path"]
        original_digest = hashlib.sha256(original.read_bytes()).hexdigest()
        if original_digest not in copied:
            number = len(copied) + 1
            target = output / "blind" / "images" / f"image-{number:02d}{original.suffix.lower()}"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
            copied[original_digest] = target
        target = copied[original_digest]
        try:
            path = target.relative_to(ROOT).as_posix()
        except ValueError:
            path = str(target)
        family = target.stem
        case = {
            **raw,
            "case_id": f"case-{index:03d}",
            "image_path": path,
            "image_family": family,
            "entity_group": family,
            "split": "draft",
            "annotation_status": "draft",
        }
        cases.append(case)
        mapping.append(
            {
                "case_id": case["case_id"],
                "original_case_id": raw["case_id"],
                "repository_image": raw["image_path"],
                "image_sha256": image_hash(case),
            }
        )
    cases = [item.model_dump(mode="json") for item in validate_manifest(cases, allow_draft=True)]
    write_json(output / "blind" / "manifest.json", cases)
    write_json(output / "operator" / "original-cases.json", cases)
    write_json(output / "operator" / "provenance.json", mapping)
    write_json(
        output / "operator" / "pack.json",
        {
            "schema_version": 1,
            "cases_sha256": digest(cases),
            "cases": len(cases),
            "images": len(copied),
            "gold_status": "awaiting_human_review",
        },
    )
    (output / "REVIEW.md").write_text(
        "# Bộ ca chờ người duyệt\n\n"
        "Bắt đầu từ blind/manifest.json và blind/images; chưa xem dự đoán model khi ghi đáp án chuẩn.\n"
        "Tên ảnh và ca đã được đổi để tránh gợi ý từ tên sample; nguồn gốc byte ảnh ở operator/provenance.json.\n\n"
        "Người duyệt điền reviewer, reviewed_at, image_source, image_rights, answerable và accepted_answers. "
        "Các slot lịch sử/mixed trả lời được phải có source_ids trỏ nguồn có URL/content_hash đã được kiểm tra. "
        "Chia dev/test theo cả image_family và entity_group; một nhóm chỉ thuộc một split. "
        "Đặt annotation_status=reviewed sau khi hoàn tất và lưu bản riêng. Không tự coi dự đoán AI là đáp án đúng.\n\n"
        "Sau đó chạy scripts.export_review_pack finalize để kiểm tra nhãn và tạo manifest đã duyệt. "
        "Dự đoán cũ chỉ được gắn lại hash sau khi xác nhận ảnh/câu hỏi/slot không đổi. "
        "Bước này giữ original_case_hash để truy vết, không thực hiện gọi model. "
        "Cuối cùng người duyệt điền judgments-template.json cho từng prediction, rồi dùng scripts.evaluate score.\n",
        encoding="utf-8",
    )
    return {"cases": len(cases), "images": len(copied), "gold_status": "awaiting_human_review"}


def finalize_pack(pack, reviewed, *, predictions=None):
    pack = Path(pack)
    originals = read(pack / "operator" / "original-cases.json")
    metadata = read(pack / "operator" / "pack.json")
    if digest(originals) != metadata["cases_sha256"]:
        raise ValueError("Original draft manifest changed; export a new pack")
    wanted = {item["case_id"]: item for item in originals}
    cases = [item.model_dump(mode="json") for item in validate_manifest(reviewed)]
    if {case["case_id"] for case in cases} != set(wanted):
        raise ValueError("Human review must cover the original cases exactly")
    provenance = {item["case_id"]: item for item in read(pack / "operator" / "provenance.json")}
    for case in cases:
        original = wanted[case["case_id"]]
        if any(case[field] != original[field] for field in INPUT_FIELDS):
            raise ValueError("Model input changed; export a new pack and rerun predictions")
        if [(s["slot_id"], s["question"], s["kind"]) for s in case["slots"]] != [
            (s["slot_id"], s["question"], s["kind"]) for s in original["slots"]
        ]:
            raise ValueError("Requested slots changed; rerun predictions")
        if image_hash(case) != provenance[case["case_id"]]["image_sha256"]:
            raise ValueError("Image bytes changed; rerun predictions")
    result = {"cases": len(cases), "gold_status": "human_reviewed", "predictions_rebound": 0}
    if predictions is not None:
        actual = {prediction["case_id"]: prediction for prediction in predictions}
        if len(actual) != len(predictions) or not set(actual) <= set(wanted):
            raise ValueError("Predictions must reference unique original cases")
        by_id = {case["case_id"]: case for case in cases}
        rebound, templates = [], []
        for identifier, prediction in actual.items():
            if prediction.get("model_mode") != "live":
                raise ValueError("Demo predictions cannot become quality measurements")
            if prediction.get("case_hash") != digest(wanted[identifier]):
                raise ValueError("Prediction case snapshot is stale or unrelated")
            if prediction.get("image_hash") != provenance[identifier]["image_sha256"]:
                raise ValueError("Prediction image hash does not match the reviewed image")
            item = {
                **prediction,
                "original_case_hash": prediction["case_hash"],
                "case_hash": digest(by_id[identifier]),
            }
            rebound.append(item)
            output = item["result"]
            templates.append(
                {
                    "case_id": identifier,
                    "reviewer": "",
                    "reviewed_at": "",
                    "prediction_hash": digest(item),
                    "recognition_correct": None,
                    "claims": {
                        claim["claim_id"]: None
                        for claim in output.get("claims", [])
                        if claim["verdict"] == "supported"
                    },
                    "slots": {slot["slot_id"]: "" for slot in by_id[identifier]["slots"]},
                }
            )
        write_json(pack / "reviewed" / "predictions.json", rebound)
        write_json(pack / "reviewed" / "judgments-template.json", templates)
        write_json(
            pack / "reviewed" / "prediction-manifest.json",
            [by_id[identifier] for identifier in actual],
        )
        result["predictions_rebound"] = len(rebound)
    write_json(pack / "reviewed" / "manifest.json", cases)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("--output", type=Path, default=ROOT / "data/evaluation/review-pack")
    final = commands.add_parser("finalize")
    final.add_argument("--pack", type=Path, required=True)
    final.add_argument("--reviewed", type=Path, required=True)
    final.add_argument("--predictions", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            result = export_pack(args.output)
        else:
            result = finalize_pack(
                args.pack,
                read(args.reviewed),
                predictions=read(args.predictions) if args.predictions else None,
            )
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Review pack rejected: {error}\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
