"""创建 runs/<YYYYMMDD-HHMMSS>/ 运行目录与八件套骨架——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
import os
import shutil
from datetime import datetime
from pathlib import Path

try:  # PyYAML 已装则用其转义；否则回退本文件手写最小 YAML 序列化器（零第三方依赖）
    import yaml as _yaml_mod
except ImportError:  # pragma: no cover - 取决于运行环境
    _yaml_mod = None

KPI_CSV_HEADER = "timestamp_ms,link,per,retries,rssi,source"
MONITOR_CSV_HEADER = "timestamp_ms,freq_mhz,power_db,confidence"
REPORT_TITLE = "# Run Report"

#: 磁盘空间预检阈值：剩余 < 100MB 拒绝建目录
_MIN_FREE_BYTES = 100 * 1024 * 1024

#: 八件套固定清单（相对 run_dir 的路径，亦为返回 files 的顺序）
WORKSPACE_FILES = (
    "scenario.yaml",
    "kpi.csv",
    "events.jsonl",
    "monitor.csv",
    "recordings",
    "report.md",
    "plots",
    "run.log",
)


class RunDirError(RuntimeError):
    """运行目录创建失败：磁盘空间不足 / 父目录不可创建不可写。"""


def _now() -> datetime:
    """本地时间（测试经 monkeypatch 本函数固定时间戳）。"""
    return datetime.now()


# ---------------------------------------------------------------------------
# 手写最小 YAML 序列化器（PyYAML 缺失时的回退路径）
# 支持 dict/list/str/int/float/bool/None 的嵌套组合，输出可被标准 YAML 解析器读回。
# ---------------------------------------------------------------------------


def _yaml_quote(text: str) -> str:
    """双引号标量：转义反斜杠/引号/控制字符，非 ASCII 原样保留（UTF-8 落盘）。"""
    out = ['"']
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append("\\x%02x" % ord(ch))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _render_scalar(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _yaml_quote(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return ".nan"
        if math.isinf(value):
            return "-.inf" if value < 0 else ".inf"
        return repr(value)
    raise TypeError(f"场景包含不支持的标量类型: {type(value).__name__}")


def _render_key(key: object) -> str:
    return _yaml_quote(key) if isinstance(key, str) else _render_scalar(key)


def _emit_mapping(mapping: dict, indent: int, lines: list) -> None:
    pad = "  " * indent
    for key, value in mapping.items():
        key_s = _render_key(key)
        if isinstance(value, dict):
            if value:
                lines.append(f"{pad}{key_s}:")
                _emit_mapping(value, indent + 1, lines)
            else:
                lines.append(f"{pad}{key_s}: {{}}")
        elif isinstance(value, list):
            if value:
                lines.append(f"{pad}{key_s}:")
                _emit_sequence(value, indent + 1, lines)
            else:
                lines.append(f"{pad}{key_s}: []")
        else:
            lines.append(f"{pad}{key_s}: {_render_scalar(value)}")


def _emit_sequence(sequence: list, indent: int, lines: list) -> None:
    pad = "  " * indent
    for item in sequence:
        if isinstance(item, (dict, list)) and item:
            sub: list = []
            if isinstance(item, dict):
                _emit_mapping(item, indent + 1, sub)
            else:
                _emit_sequence(item, indent + 1, sub)
            # "- " 占两格，与 indent+1 级缩进对齐，保证块内键同列
            lines.append(f"{pad}- {sub[0].lstrip()}")
            lines.extend(sub[1:])
        elif isinstance(item, dict):
            lines.append(f"{pad}- {{}}")
        elif isinstance(item, list):
            lines.append(f"{pad}- []")
        else:
            lines.append(f"{pad}- {_render_scalar(item)}")


def _fallback_dump_yaml(data: object) -> str:
    lines: list = []
    if isinstance(data, dict):
        _emit_mapping(data, 0, lines)
    elif isinstance(data, list):
        _emit_sequence(data, 0, lines)
    else:
        lines.append(_render_scalar(data))
    return "\n".join(lines) + "\n"


def _dump_scenario_yaml(scenario: dict) -> str:
    """场景副本序列化：优先 PyYAML，缺失时回退手写序列化器。"""
    if _yaml_mod is not None:
        return _yaml_mod.safe_dump(
            scenario, allow_unicode=True, sort_keys=False, default_flow_style=False
        )
    return _fallback_dump_yaml(scenario)


# ---------------------------------------------------------------------------
# 目录创建
# ---------------------------------------------------------------------------


def _existing_ancestor(path: Path) -> Path:
    """自 path 起向上找第一个已存在祖先（磁盘预检锚点；/ 总存在，必然终止）。"""
    current = path
    while not current.exists():
        if current.parent == current:
            return current
        current = current.parent
    return current


def _check_disk_space(anchor: Path) -> None:
    try:
        free = shutil.disk_usage(str(anchor)).free
    except OSError as exc:
        raise RunDirError(f"磁盘空间预检失败: {anchor}: {exc}") from exc
    if free < _MIN_FREE_BYTES:
        raise RunDirError(
            f"磁盘剩余空间不足: free={free} 字节 < 阈值 {_MIN_FREE_BYTES} 字节"
        )


def _populate_workspace(run_dir: Path, scenario: dict) -> None:
    (run_dir / "recordings").mkdir()  # SigMF 录制目录
    (run_dir / "plots").mkdir()  # 图目录
    (run_dir / "scenario.yaml").write_text(_dump_scenario_yaml(scenario), encoding="utf-8")
    (run_dir / "kpi.csv").write_text(KPI_CSV_HEADER + "\n", encoding="utf-8")
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    (run_dir / "monitor.csv").write_text(MONITOR_CSV_HEADER + "\n", encoding="utf-8")
    (run_dir / "report.md").write_text(
        REPORT_TITLE + "\n\n> 占位：正文由 build_report 在收尾阶段生成。\n", encoding="utf-8"
    )
    (run_dir / "run.log").write_text("", encoding="utf-8")


def create_run_workspace(runs_root: str, scenario: dict) -> dict:
    """创建 runs/<YYYYMMDD-HHMMSS>/ 运行目录与八件套骨架。

    输入: runs_root 基础目录（不存在则自动创建）、scenario 场景 dict（落盘为 scenario.yaml 副本）。
    输出: {'run_dir': 绝对路径, 'files': [八件套相对路径清单]}。
    错误: 磁盘剩余 <100MB / 父目录不可创建不可写 / runs_root 为文件 → RunDirError。
    同秒冲突时以 -2、-3 后缀去重；时间戳取本地时间。
    """
    root = Path(runs_root)
    if root.exists() and not root.is_dir():
        raise RunDirError(f"runs_root 已存在且不是目录: {root}")

    _check_disk_space(_existing_ancestor(root))

    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RunDirError(f"runs_root 不可创建: {root}: {exc}") from exc

    stamp = _now().strftime("%Y%m%d-%H%M%S")
    name = stamp
    suffix = 1
    while True:
        run_dir = root / name
        try:
            run_dir.mkdir()  # 原子占位，规避同秒竞态
        except FileExistsError:
            suffix += 1
            name = f"{stamp}-{suffix}"
            continue
        except OSError as exc:
            raise RunDirError(f"运行目录不可创建: {run_dir}: {exc}") from exc
        break

    try:
        _populate_workspace(run_dir, scenario)
    except OSError as exc:
        raise RunDirError(f"八件套骨架写入失败: {run_dir}: {exc}") from exc

    return {"run_dir": os.path.abspath(str(run_dir)), "files": list(WORKSPACE_FILES)}
