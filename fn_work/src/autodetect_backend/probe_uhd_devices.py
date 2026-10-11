"""枚举在位 USRP（uhd_find_devices），失败不抛出——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import re
import subprocess

__all__ = ["probe_uhd_devices"]

# 设备段头：形如 "-- UHD Device 0"；分隔线 "--...--" 与 [INFO] 横幅均不匹配。
_DEVICE_HEADER_RE = re.compile(r"^--\s*UHD Device\s+(\d+)\s*$")
_FIELD_KEYS = ("serial", "product", "type")
# 失败时 raw 只保留 stderr 尾部摘要，避免异常工具刷屏撑爆结果。
_STDERR_TAIL = 4000


def probe_uhd_devices(timeout_s: float = 10.0) -> dict:
    """枚举在位 USRP 设备清单与原始输出，工具缺失/超时/非零退出一律不抛出。

    返回 {'devices': [{'index': int, 'serial': str|None, 'product': str|None,
    'type': str|None}], 'raw': str, 'available': bool, 'error': None|
    'binary_missing'|'timeout'|'exit_N'}。注意：设备被其他进程占用时
    uhd_find_devices 可能丢设备段（devices 为空）——属正常探测结果。
    """
    try:
        proc = subprocess.run(
            ["uhd_find_devices"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except FileNotFoundError:
        return {"devices": [], "raw": "", "available": False, "error": "binary_missing"}
    except subprocess.TimeoutExpired as exc:
        # TimeoutExpired 携带的输出可能是 bytes（text=True 下亦有可能），尽力保留摘要。
        raw = _combine(_to_text(exc.stdout), _to_text(exc.stderr))
        return {"devices": [], "raw": raw, "available": False, "error": "timeout"}

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    raw = _combine(stdout, stderr)
    devices = _parse_devices(raw)
    error = None if proc.returncode == 0 else f"exit_{proc.returncode}"
    return {"devices": devices, "raw": raw, "available": bool(devices), "error": error}


def _parse_devices(text: str) -> list:
    """从 uhd_find_devices 输出解析设备段：以 "-- UHD Device N" 行起，收集随后
    缩进字段 serial:/product:/type:（name: 等其他字段忽略）。缺字段记 None，
    空值（"serial:" 后无内容）同样记 None。"""
    devices: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        stripped = line.strip()
        header = _DEVICE_HEADER_RE.match(stripped)
        if header:
            if current is not None:
                devices.append(current)
            current = {
                "index": int(header.group(1)),
                "serial": None,
                "product": None,
                "type": None,
            }
            continue
        if current is None:
            continue
        for key in _FIELD_KEYS:
            if stripped.startswith(key + ":"):
                value = stripped.split(":", 1)[1].strip()
                current[key] = value or None
                break
    if current is not None:
        devices.append(current)
    return devices


def _combine(stdout: str, stderr: str) -> str:
    """拼原始输出：stdout 为主，stderr 非空时附加尾部摘要（带 [stderr] 标记）。"""
    if not stderr:
        return stdout
    if len(stderr) > _STDERR_TAIL:
        stderr = "..." + stderr[-_STDERR_TAIL:]
    if not stdout:
        return "[stderr]\n" + stderr
    return stdout.rstrip("\n") + "\n[stderr]\n" + stderr


def _to_text(data) -> str:
    """TimeoutExpired 携带的输出归一为 str：None→''，bytes→utf-8 容错解码。"""
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)
