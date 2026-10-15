"""数据集索引：登记/条件检索/重建/清单入口（索引损坏时自动重建）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import json
import logging
import math
import os
import re

from .query_dataset import QueryError, query_dataset

__all__ = [
    "IndexConflictError",
    "IndexEntryError",
    "IndexFormatError",
    "IndexWriteError",
    "index_dataset",
    "QueryError",
    "query_dataset",
]

_LOGGER = logging.getLogger(__name__)

#: 索引文件 schema 版本（结构不符即视为损坏，触发自动重建）
_INDEX_VERSION = 1

#: 默认落点（相对 fn_work；测试一律显式传 tmp_path 覆盖，不触碰真实目录）
DEFAULT_INDEX_PATH = os.path.join("fn_work", "dataset", "index.json")
DEFAULT_RUNS_ROOT = os.path.join("fn_work", "dataset", "runs")

#: register 必填字段（缺任一→IndexEntryError）
_REQUIRED_FIELDS = ("run_id", "path", "style", "freq_mhz", "date", "backend")

#: 支持的 action 清单（未知 action→IndexEntryError 附此清单）
_ACTIONS = ("register", "query", "rebuild", "list")

#: 运行目录名前缀日期：runs/<YYYYMMDD-HHMMSS>/ → date='YYYYMMDD'
_DIR_DATE_RE = re.compile(r"^(\d{8})")

#: 运行目录内场景副本文件名（manage_run.create_run_workspace 落盘名；finalize 的
#: 八件套检查兼容 scenario.yml 拼写——读取同款兼容）。真跑运行的 result.json 常缺
#: style/freq_mhz（finalize 固定键集不含），副本是这两个字段的真值来源——与
#: browse_dataset_library 的卡片真值双源同源（走查 C1 修复）。
_SCENARIO_FILENAMES = ("scenario.yaml", "scenario.yml")


class IndexEntryError(ValueError):
    """登记条目非法：record 非 dict/必填缺失/类型错；或 action 未知（消息附支持清单）。"""


class IndexConflictError(RuntimeError):
    """run_id 已登记且未传 update=True 覆盖。"""


class IndexFormatError(RuntimeError):
    """索引文件损坏（非法 JSON/结构错）且 runs_root 不可用、无法自动重建。"""


class IndexWriteError(OSError):
    """索引文件 IO 失败（读/写，OSError 透传包装，消息含 index_path）。"""


def _is_number(value) -> bool:
    """数值口径：int/float 且非 bool（与 query_dataset 的频段判定一致）。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _lenient_number(value):
    """宽容数值化（browse_dataset_library 同口径）：int/float（拒 bool）或可解析
    有限数字 str（PyYAML 1.1 把 '2.4e9' 这类无点科学计数解析为 str）→ float；
    其余 None。

    场景副本直读（yaml.safe_load）不走 load_scenario 的 normalize_scenario
    数值化——rebuild 补缺字段在此就地宽容，保持与装载/浏览路径同结果。
    """
    if _is_number(value):
        return float(value)
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def _read_scenario_copy(run_dir: str) -> dict:
    """读运行目录的场景副本（scenario.yaml，兼容 scenario.yml）→ dict。

    缺失/损坏/非 dict/yaml 库不可用 → {}（降级口径——副本只是 rebuild 补缺的
    真值来源，绝不反杀重建；与 browse_dataset_library._read_scenario_copy 同款）。
    """
    for name in _SCENARIO_FILENAMES:
        path = os.path.join(run_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            import yaml

            with open(path, encoding="utf-8") as handle:
                payload = yaml.safe_load(handle)
        except Exception:  # noqa: BLE001 - 副本不可读→补缺来源失效，保持缺省
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _validate_record(record: object) -> dict:
    """登记条目校验+规范化：必填齐全、类型正确；可选字段类型对则透传，failed 缺省补 False。"""
    if record is None:
        raise IndexEntryError("action='register' 需要 record（dict），得到 None")
    if not isinstance(record, dict):
        raise IndexEntryError(f"record 必须为 dict，得到 {type(record).__name__}")
    missing = [field for field in _REQUIRED_FIELDS if field not in record]
    if missing:
        raise IndexEntryError(f"record 必填字段缺失 {missing}；必填清单: {list(_REQUIRED_FIELDS)}")
    for field in ("run_id", "path", "style", "date", "backend"):
        value = record[field]
        if not isinstance(value, str) or not value:
            raise IndexEntryError(f"record['{field}'] 必须为非空 str，得到 {value!r}")
    freq = record["freq_mhz"]
    if not _is_number(freq) or not math.isfinite(freq):
        raise IndexEntryError(f"record['freq_mhz'] 必须为有限数值（int/float 非 bool），得到 {freq!r}")
    if "failed" in record and not isinstance(record["failed"], bool):
        raise IndexEntryError(f"record['failed'] 可选但必须为 bool，得到 {record['failed']!r}")
    for field in ("jsr_db", "batch_key"):
        if field in record and record[field] is not None and not isinstance(record[field], str):
            raise IndexEntryError(f"record['{field}'] 可选但必须为 str 或 None，得到 {record[field]!r}")
    entry = dict(record)  # 额外键原样透传（不参与校验）；failed 统一落盘口径缺省 False
    entry.setdefault("failed", False)
    return entry


def _entry_from_run(run_id: str, run_dir: str, result: dict) -> dict:
    """从 runs/<id>/result.json 提取可得字段；date 缺失补运行目录名前缀日期（YYYYMMDD）；
    style/freq_mhz 缺失时从该 run 的场景副本（scenario.yaml/yml，manage_run 落盘的
    规范化场景）补全——副本缺失/不可读/字段无效则保持缺省（不虚构，走查 C1 修复）。

    字段校验与 _validate_record 同口径（B6 中#4）：freq_mhz 在且非 None 须为有限
    数值（int/float 非 bool）；backend/style/jsr_db/batch_key/date 在且非 None 须为
    非空 str。脏 run 抛 IndexEntryError，由 _scan_runs 记 skipped（不短路 rebuild，
    读路径自愈重建同样逐条校验）；None 视同未提供（rebuild 的可得字段缺省口径）。
    副本补全只填缺失（result.json 已有的有效值不覆盖）且只经副本的有效值入口
    （style 非空白 str、freq_hz 宽容数值化后换算 MHz）。
    """
    entry: dict = {
        "run_id": run_id,
        "path": os.path.join(run_dir, "recordings"),
        "failed": result.get("status") != "done",
    }
    for field in ("backend", "style", "jsr_db", "batch_key", "date"):
        if field not in result:
            continue
        value = result[field]
        if value is None:
            continue
        if not isinstance(value, str) or not value:
            raise IndexEntryError(
                f"run {run_id!r} 的 result.json 字段 {field!r} "
                f"须为非空 str 或缺省，得到 {value!r}"
            )
        entry[field] = value
    if "status" in result:
        entry["status"] = result["status"]
    freq = result.get("freq_mhz")
    if freq is not None:
        if not _is_number(freq) or not math.isfinite(freq):
            raise IndexEntryError(
                f"run {run_id!r} 的 result.json 字段 'freq_mhz' "
                f"须为有限数值（int/float 非 bool），得到 {freq!r}"
            )
        entry["freq_mhz"] = freq
    # 场景副本补缺（真值来源与 browse_dataset_library 同款）：finalize 的固定
    # 键集不含 style/freq_mhz，真跑运行全靠副本补——副本不可得则保持缺省。
    scenario = _read_scenario_copy(run_dir)
    if "style" not in entry:
        style = scenario.get("style")
        if isinstance(style, str) and style.strip():
            entry["style"] = style.strip()
    if "freq_mhz" not in entry:
        freq_hz = _lenient_number(scenario.get("freq_hz"))
        if freq_hz is not None:
            entry["freq_mhz"] = freq_hz / 1.0e6
    if "date" not in entry:  # result 无有效 date → 补运行目录名前缀日期
        matched = _DIR_DATE_RE.match(run_id)
        if matched:
            entry["date"] = matched.group(1)  # runs/<YYYYMMDD-HHMMSS>/ → 'YYYYMMDD'
    return entry


def _scan_runs(runs_root: str) -> tuple[list, int]:
    """扫描 runs_root 下各 run 目录重建索引条目，返回 (entries, skipped)。

    有效 run：recordings 目录存在 + result.json 可读且为 dict；
    result.json 缺失/损坏/非 dict、recordings 目录缺、或字段脏
    （_entry_from_run 校验不过，如 freq_mhz=NaN/backend 非 str）→ skipped
    计数后跳过（B6 中#4：逐条跳过，不短路整个 rebuild）。
    条目 style/freq_mhz 缺失时自该 run 的场景副本补全（见 _entry_from_run）。
    runs_root 不存在/不是目录 → 空索引 (0, 0)；runs 根下的杂项文件不算 run 也不计 skipped。
    """
    if not os.path.isdir(runs_root):
        return [], 0
    entries: list = []
    skipped = 0
    for name in sorted(os.listdir(runs_root)):
        run_dir = os.path.join(runs_root, name)
        if not os.path.isdir(run_dir):
            continue
        if not os.path.isdir(os.path.join(run_dir, "recordings")):
            skipped += 1
            continue
        result_path = os.path.join(run_dir, "result.json")
        try:
            with open(result_path, encoding="utf-8") as fh:
                result = json.load(fh)
        except (OSError, ValueError):
            skipped += 1
            continue
        if not isinstance(result, dict):
            skipped += 1
            continue
        try:
            entries.append(_entry_from_run(name, run_dir, result))
        except IndexEntryError:
            skipped += 1  # 脏 run：计数后跳过，不短路 rebuild
    return entries, skipped


def _persist(index_path: str, entries: list) -> None:
    """索引落盘 {'version': 1, 'entries': [...]}；任何写失败→IndexWriteError（消息含路径）。"""
    payload = {"version": _INDEX_VERSION, "entries": entries}
    try:
        os.makedirs(os.path.dirname(os.path.abspath(index_path)), exist_ok=True)
        with open(index_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, allow_nan=False)
    except (OSError, ValueError, TypeError) as exc:
        raise IndexWriteError(f"索引写入失败: {index_path}: {type(exc).__name__}: {exc}") from exc


def _recover_or_fail(index_path: str, runs_root: str, reason: str) -> list:
    """索引损坏后的读路径自愈（B6 低#7）：runs_root 可用则现场重建——重建事实记
    warning（含 index_path 与重建计数）并落盘重建结果（修复磁盘损坏态，下次读
    直接命中落盘索引）；落盘失败仅再记 warning、读路径继续用内存重建（不阻塞）。
    runs_root 不可用则 IndexFormatError。
    """
    if os.path.isdir(runs_root):
        entries, skipped = _scan_runs(runs_root)
        try:
            _persist(index_path, entries)
        except IndexWriteError as exc:
            _LOGGER.warning("索引自愈结果落盘失败（读路径继续用内存重建）: %s", exc)
        _LOGGER.warning(
            "索引损坏自动重建并落盘: %s（原因: %s；重建 %d 条，跳过 %d 个 run）",
            index_path,
            reason,
            len(entries),
            skipped,
        )
        return entries
    raise IndexFormatError(f"索引文件损坏且无法自动重建（runs_root 不可用: {runs_root!r}）: {reason}")


def _load_entries(index_path: str, runs_root: str) -> list:
    """读索引条目：文件不存在→空；非法 JSON/结构错→自动重建或 IndexFormatError；读 IO 失败→IndexWriteError。"""
    if not os.path.exists(index_path):
        return []
    try:
        with open(index_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except ValueError as exc:  # JSONDecodeError 为 ValueError 子类：非法 JSON 属损坏
        return _recover_or_fail(index_path, runs_root, f"非法 JSON: {type(exc).__name__}: {exc}")
    except OSError as exc:  # 读 IO 失败（如 index_path 指向目录/无权限）：非损坏，与写失败同口径包装
        raise IndexWriteError(f"索引读取失败: {index_path}: {type(exc).__name__}: {exc}") from exc
    version = data.get("version") if isinstance(data, dict) else None
    entries = data.get("entries") if isinstance(data, dict) else None
    if (
        not _is_number(version)  # 排除 bool（True == 1）冒充 version=1
        or version != _INDEX_VERSION
        or not isinstance(entries, list)
        or any(not isinstance(entry, dict) for entry in entries)
    ):
        return _recover_or_fail(
            index_path,
            runs_root,
            f"结构错（须为 {{'version': {_INDEX_VERSION}, 'entries': [dict, ...]}}）",
        )
    return entries


def index_dataset(
    action: str,
    record: dict | None = None,
    query: dict | None = None,
    *,
    index_path: str = DEFAULT_INDEX_PATH,
    runs_root: str = DEFAULT_RUNS_ROOT,
    update: bool = False,
) -> dict:
    """数据集索引管理：action 分派的登记/条件检索/重建/清单入口（索引损坏自动重建）。

    Args:
        action: 'register' | 'query' | 'rebuild' | 'list'。
        record: register 用；必填 run_id/path/style/freq_mhz/date/backend，
            可选 jsr_db/failed/batch_key（其余额外键原样透传），failed 缺省记 False。
        query: query 用；条件原样透传 query_dataset（未知字段→QueryError 原样抛出）。
        index_path: 索引 JSON 落点（{'version': 1, 'entries': [...]}），默认 fn_work/dataset/index.json。
        runs_root: 运行目录根（runs/<id>/result.json + recordings/），默认 fn_work/dataset/runs；
            索引损坏读路径的自愈数据源，也是 rebuild 动作的扫描对象。
        update: register 遇 run_id 已存在时 True=原位覆盖，False=IndexConflictError。

    Returns:
        register → {'registered': 规范化条目, 'total': 登记后总数}；
        query → query_dataset 返回值透传（{'entries','batch_groups','total','matched'}）；
        rebuild → {'rebuilt': 有效条数, 'skipped': 跳过数}；
        list → {'entries': 全量条目, 'total': 总数}。

    Raises:
        IndexEntryError: action 未知（消息附支持清单）/record 缺必填或类型错。
        IndexConflictError: run_id 已存在且 update=False。
        IndexFormatError: 索引文件损坏且 runs_root 不可用（无法自动重建）。
        IndexWriteError: register/rebuild 落盘失败或索引读取 IO 失败（消息含 index_path）。
        QueryError: query 条件非法（由 query_dataset 抛出，原样透传）。
    """
    if not isinstance(action, str) or action not in _ACTIONS:
        raise IndexEntryError(f"未知 action {action!r}；支持清单: {list(_ACTIONS)}")

    if action == "register":
        entry = _validate_record(record)
        entries = _load_entries(index_path, runs_root)
        run_id = entry["run_id"]
        for position, existing in enumerate(entries):
            if existing.get("run_id") == run_id:
                if not update:
                    raise IndexConflictError(
                        f"run_id {run_id!r} 已登记（现有 {len(entries)} 条）；update=True 可原位覆盖"
                    )
                entries[position] = entry  # 原位覆盖，保持其余条目次序
                break
        else:
            entries.append(entry)
        _persist(index_path, entries)
        return {"registered": entry, "total": len(entries)}

    if action == "query":
        return query_dataset(_load_entries(index_path, runs_root), query)

    if action == "rebuild":
        entries, skipped = _scan_runs(runs_root)
        _persist(index_path, entries)
        return {"rebuilt": len(entries), "skipped": skipped}

    entries = _load_entries(index_path, runs_root)  # action == "list"
    return {"entries": entries, "total": len(entries)}
