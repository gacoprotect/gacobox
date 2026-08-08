"""Export harvested accounts to txt / json / csv."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def export_keys_txt(output_dir: str, results: list[dict[str, Any]]) -> Path:
    """Write email:password:api_key lines, one per account."""
    out = Path(output_dir) / "keys.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"{r.get('email', '')}:{r.get('password', '')}:{r.get('api_key', '')}"
        for r in results
        if r.get("api_key")
    ]
    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return out


def export_keys_json(output_dir: str, results: list[dict[str, Any]]) -> Path:
    """Write the full results array as JSON."""
    out = Path(output_dir) / "keys.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def export_keys_csv(output_dir: str, results: list[dict[str, Any]]) -> Path:
    """Write email,password,api_key as a CSV."""
    out = Path(output_dir) / "keys.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["email", "password", "api_key"])
        for r in results:
            if r.get("api_key"):
                writer.writerow([r.get("email", ""), r.get("password", ""), r.get("api_key", "")])
    return out


def export_keys_9router(output_dir: str, results: list[dict[str, Any]]) -> Path:
    """Write email|api_key lines for 9Router bulk import."""
    out = Path(output_dir) / "keys_9router.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"{r.get('email', '')}|{r.get('api_key', '')}"
        for r in results
        if r.get("api_key")
    ]
    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return out


def export_all(output_dir: str, results: list[dict[str, Any]]) -> dict[str, Path]:
    """Run every exporter and return {format: path}."""
    return {
        "txt": export_keys_txt(output_dir, results),
        "json": export_keys_json(output_dir, results),
        "csv": export_keys_csv(output_dir, results),
        "9router": export_keys_9router(output_dir, results),
    }
