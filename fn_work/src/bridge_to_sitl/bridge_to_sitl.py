"""PER 台阶→SITL 丢包/时延注入（不在位跳过不阻塞）——重写规约与签名意图详见 fn_docs/responsibility.md（R53 顶层；调用方 run_demo 可选拓展步/CLI 独立入口）。

落地口径：

- 取台阶：读 ``result['steps_executed']``（``[{'per','level_db'}, ...]`` 台阶表）
  → ``map_per_to_injection`` 生成注入参数表（映射参数取
  ``sitl_config['mapping_params']``，缺省内置）；``result`` 缺该键 → ValueError；
- pymavlink **延迟 import**：库缺（ImportError）→ SitlWarn 警告+返回
  ``{'bridged': False, 'reason': 'pymavlink_missing', 'hint': 'pip install
  pymavlink'}``——不抛出、不阻塞主流程；
- ``sitl_config['connection']`` 为 None → 跳过+标注
  ``{'bridged': False, 'reason': 'connection_not_configured'}``（SitlWarn 同步警告）；
- 连接失败/心跳超时/参数下发异常 → SitlWarn+安全断开（尽力 close）+返回
  ``{'bridged': False, 'reason': 'connection_failed'|'param_send_failed', ...}``；
- ``dry_run=True``（不真连）：只产参数表返回
  ``{'bridged': True, 'dry_run': True, 'injections': 表}``
  ——验证映射口径的 mock 层，不 import pymavlink、不建任何连接；
- ``sitl_config['heartbeat_timeout_s']`` 域校验前置（与路径无关）：
  负/0/bool/NaN/±inf → ValueError（缺省 2.0；可转 float 的正有限秒数）；
- 真连路径（简化 MAVLink mock 层口径，不依赖完整 ArduPilot 参数协议）：
  ``mavutil.mavlink_connection(connection)`` → ``wait_heartbeat`` → 逐注入档
  ``conn.mav.param_set_send`` 两条参数（SIM_PACKET_LOSS=丢包率、
  SIM_LATENCY_MS=时延 ms）→ 安全 close；
- 所有返回 dict 均携带 ``injections``（含空表）供调用方溯源。
"""
from __future__ import annotations

import math
import warnings

from .map_per_to_injection import map_per_to_injection

__all__ = ["SitlWarn", "bridge_to_sitl"]

#: 库缺安装提示（reason='pymavlink_missing' 附带）。
_PIP_HINT = "pip install pymavlink"

#: 简化参数通道：丢包率（0..1 分数）与时延（ms）。
_PARAM_LOSS = "SIM_PACKET_LOSS"
_PARAM_LATENCY = "SIM_LATENCY_MS"

#: 心跳等待超时缺省（秒）。
_DEFAULT_HEARTBEAT_TIMEOUT_S = 2.0


class SitlWarn(UserWarning):
    """SITL 桥不在位/失联警告（跳过注入不阻塞主流程，返回 dict 附 reason 标注）。"""


def _send_injections(conn, injections: list) -> list:
    """逐注入档下发两条简化参数（SIM_PACKET_LOSS/SIM_LATENCY_MS），返回 (名, 值) 清单。"""
    sent: list = []
    for inj in injections:
        conn.mav.param_set_send(_PARAM_LOSS, float(inj["packet_loss"]))
        sent.append((_PARAM_LOSS, float(inj["packet_loss"])))
        conn.mav.param_set_send(_PARAM_LATENCY, float(inj["latency_ms"]))
        sent.append((_PARAM_LATENCY, float(inj["latency_ms"])))
    return sent


def _safe_close(conn) -> None:
    """安全断开：close 失败静默（断开尽力而为，绝不反向抛出掩盖主结果）。"""
    try:
        conn.close()
    except Exception:  # noqa: BLE001 - 断开失败不阻塞、不再告警刷屏
        pass


def bridge_to_sitl(result: dict, sitl_config: dict, dry_run: bool = False) -> dict:
    """PER 台阶 → SITL 丢包/时延注入桥（不在位/失联跳过+标注，不抛 Sitl 族错误）。

    Args:
        result: 运行结果，须含 ``'steps_executed'``：
            ``[{'per': float∈[0,1], 'level_db': float}, ...]``（缺键 ValueError）。
        sitl_config: SITL 连接配置——``'connection'``（MAVLink 连接串如
            ``'udp:127.0.0.1:14540'`` 或 None=未配置跳过）、``'mapping_params'``
            （可选 dict，透传 map_per_to_injection 覆盖缺省映射参数）、
            ``'heartbeat_timeout_s'``（缺省 2.0，可转 float 的正有限秒数——
            负/0/bool/NaN/±inf 一律 ValueError，校验前置与路径无关）。
        dry_run: True=只产参数表不真连（不 import pymavlink、不建连接），
            返回 ``{'bridged': True, 'dry_run': True, 'injections': 表}``。

    Returns:
        成功：``{'bridged': True, 'dry_run': bool, 'injections': [...],
        'connection': str, 'params_sent': [(名, 值), ...]}``；
        跳过：``{'bridged': False, 'dry_run': False, 'reason':
        'pymavlink_missing'|'connection_not_configured'|'connection_failed'|
        'param_send_failed', 'injections': [...], ...附 hint/error 细节}``。

    Raises:
        ValueError: result/sitl_config 形状错（非 dict、缺 'steps_executed'、
            steps_executed 非 list、heartbeat_timeout_s 域错——负/0/bool/
            NaN/±inf、映射参数非法由 map_per_to_injection 上抛）。
    """
    if not isinstance(result, dict):
        raise ValueError(f"result 必须为 dict（运行结果），实际: {type(result).__name__}")
    if not isinstance(sitl_config, dict):
        raise ValueError(
            f"sitl_config 必须为 dict（SITL 连接配置），实际: {type(sitl_config).__name__}"
        )
    if not isinstance(dry_run, bool):
        raise ValueError(f"dry_run 必须为 bool，实际: {type(dry_run).__name__}")
    if "steps_executed" not in result:
        raise ValueError(
            "result 缺 'steps_executed' 台阶表（[{'per','level_db'}, ...]）——无可桥接数据"
        )
    steps = result["steps_executed"]
    if not isinstance(steps, list):
        raise ValueError(
            f"result['steps_executed'] 必须为 list[台阶 dict]，实际: {type(steps).__name__}"
        )

    mapping_params = sitl_config.get("mapping_params")
    if mapping_params is None:
        mapping_params = {}
    if not isinstance(mapping_params, dict):
        raise ValueError(
            f"sitl_config['mapping_params'] 必须为 dict | None，实际: "
            f"{type(mapping_params).__name__}"
        )
    injections = map_per_to_injection(steps, mapping_params)

    # 心跳超时域校验前置（路径无关：dry_run/跳过/真连一律先拒域错——
    # 负/0/bool/NaN/±inf 不是合法等待时长，早拒胜过真连路径上才暴露）。
    timeout_raw = sitl_config.get("heartbeat_timeout_s", _DEFAULT_HEARTBEAT_TIMEOUT_S)
    if isinstance(timeout_raw, bool):
        raise ValueError(
            f"sitl_config['heartbeat_timeout_s'] 必须为正有限秒数（bool 拒），"
            f"得到 {timeout_raw!r}"
        )
    try:
        timeout = float(timeout_raw)
    except (TypeError, ValueError):
        raise ValueError(
            f"sitl_config['heartbeat_timeout_s'] 必须为可转 float 的正有限秒数，"
            f"得到 {timeout_raw!r}"
        ) from None
    if not math.isfinite(timeout) or timeout <= 0.0:
        raise ValueError(
            f"sitl_config['heartbeat_timeout_s'] 必须为正有限秒数（>0，拒 "
            f"NaN/±inf/负/0），得到 {timeout_raw!r}"
        )

    # ① dry_run：只产参数表（不 import pymavlink、不建连接——映射口径 mock 层）。
    if dry_run:
        return {
            "bridged": True,
            "dry_run": True,
            "injections": injections,
            "connection": sitl_config.get("connection"),
            "n_injections": len(injections),
        }

    connection = sitl_config.get("connection")

    # ② 未配置连接：跳过+标注（SitlWarn 警告，不阻塞）。
    if connection is None:
        warnings.warn(
            "SITL 连接未配置（sitl_config['connection'] 为 None）——跳过注入不阻塞主流程",
            SitlWarn,
            stacklevel=2,
        )
        return {
            "bridged": False,
            "dry_run": False,
            "reason": "connection_not_configured",
            "injections": injections,
            "n_injections": len(injections),
        }

    # ③ pymavlink 延迟 import：库缺 → 跳过+标注（不抛，附 pip 提示）。
    try:
        from pymavlink import mavutil  # 延迟 import：主流程无 SITL 时不强依赖
    except Exception:  # noqa: BLE001 - ImportError 及任何构建期异常一律按库缺处理
        warnings.warn(
            f"pymavlink 未安装——SITL 注入跳过（不阻塞主流程）；安装: {_PIP_HINT}",
            SitlWarn,
            stacklevel=2,
        )
        return {
            "bridged": False,
            "dry_run": False,
            "reason": "pymavlink_missing",
            "hint": _PIP_HINT,
            "injections": injections,
            "n_injections": len(injections),
        }

    # ④ 真连路径：连接+心跳 → 逐档下发简化参数 → 安全断开；失败均跳过+标注。
    conn = None
    try:
        conn = mavutil.mavlink_connection(connection)
        conn.wait_heartbeat(timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - 连接/心跳失败：跳过+标注，不抛
        if conn is not None:  # 连接半建即失败：尽力安全断开
            _safe_close(conn)
        warnings.warn(
            f"SITL 连接失败: {connection!r}: {type(exc).__name__}: {exc}"
            "——安全断开跳过注入，不阻塞主流程",
            SitlWarn,
            stacklevel=2,
        )
        return {
            "bridged": False,
            "dry_run": False,
            "reason": "connection_failed",
            "error": f"{type(exc).__name__}: {exc}",
            "connection": connection,
            "injections": injections,
            "n_injections": len(injections),
        }

    try:
        params_sent = _send_injections(conn, injections)
    except Exception as exc:  # noqa: BLE001 - 下发异常：先安全断开再跳过+标注
        _safe_close(conn)
        warnings.warn(
            f"SITL 参数下发失败: {connection!r}: {type(exc).__name__}: {exc}"
            "——安全断开跳过注入，不阻塞主流程",
            SitlWarn,
            stacklevel=2,
        )
        return {
            "bridged": False,
            "dry_run": False,
            "reason": "param_send_failed",
            "error": f"{type(exc).__name__}: {exc}",
            "connection": connection,
            "injections": injections,
            "n_injections": len(injections),
        }
    _safe_close(conn)

    return {
        "bridged": True,
        "dry_run": False,
        "injections": injections,
        "connection": connection,
        "params_sent": params_sent,
        "n_injections": len(injections),
    }
