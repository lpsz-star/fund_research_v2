from __future__ import annotations

import csv
import json
import pickle
from pathlib import Path
from typing import Iterable


def ensure_directories(paths: Iterable[Path]) -> None:
    """确保一组目录存在，供数据层和输出层安全写入。"""
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: object) -> None:
    """以 UTF-8 和缩进格式写入 JSON 文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> object:
    """读取 JSON 文件并返回 Python 对象。"""
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """把字典列表按字段顺序写入 CSV。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, object]]:
    """读取 CSV 并返回字典列表。"""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_pickle(path: Path, payload: object) -> None:
    """以二进制格式写入本地缓存，用于加速大表加载。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)


def read_pickle(path: Path) -> object:
    """读取本地二进制缓存。"""
    with path.open("rb") as handle:
        return pickle.load(handle)


def append_jsonl(path: Path, payload: object) -> None:
    """向 JSONL 文件追加一条实验或运行记录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
