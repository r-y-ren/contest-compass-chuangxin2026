"""NRF24 链路驱动：计数帧流（丢包/重传，无 RSSI 口径）——重写规约与签名意图详见 fn_docs/responsibility.md。

编排口径（单帧解析归 parse_nrf24_frame、安全停发射归 stop_transmit_safely，本函数
只做流驱动）：串口行流 → 逐帧解析 → 增量 KPI 样本生成器。与 drive_esp32_link 同构
（serial_config 同形：source='serial'|'lines'/port/baud/lines/bad_frame_limit——
Ruling⑰①③ config 统一，旧「source 直收迭代器」形态不再兼容），差异仅在样本口径——
link='nrf24'、无 rssi 字段（NRF24 无 RSSI 读数，指标口径固定丢包/重传）、多 rpd
1bit 门限位：
- 增量口径：帧内 sent/lost/retries 为固件累计计数寄存器读数（PLOS_CNT/ARC_CNT），
  驱动逐帧求窗增量——per_raw = lost 增量 / sent 增量、retries 为窗重传增量、
  rpd 为当帧门限位（bool 透传）；流首基线取 0（首帧增量即其绝对读数）。
- 不可比窗 per_raw=None 并附 'per_note'：'no_delta'（sent 增量为 0——0/0 不可比）、
  'counter_reset'（计数回退——设备复位/寄存器回绕，重定基线不硬算负增量，该窗
  重传按 0 计）、'delta_overflow'（lost 增量>sent 增量——物理不可能，不杀流、
  如实标注，重传增量照实透出）。
- 损坏处置：坏帧（FrameError，含空行/前缀错/字段错/非文本行）只跳过不产出；
  **连续**坏帧计数达 bad_frame_limit（缺省 5，与 drive_esp32_link 同键名同缺省）
  视为损坏超阈——先 stop_transmit_safely 再抛 LinkError；好帧将连续计数清零，
  零星坏帧永不触发。
- 断开处置：行流迭代自身抛异常（串口断开等 Exception 族）——先停发射再抛
  LinkError（链上原始异常）；行流耗尽与消费方提前弃流（GeneratorExit 透传）均
  自然结束：不产错、不停发射（收尾停发射归编排方 record_run_streams）。
- 校验时点：serial_config/ctx 全部校验在调用时即刻抛 ValueError、不消费行流
  （同 capture_monitor_spectrum 口径，错误不推迟到首 next）。
"""
from __future__ import annotations

import time
from typing import Iterator
from uuid import uuid4

from .parse_nrf24_frame import FrameError, parse_nrf24_frame
from src.shared.stop_transmit_safely import stop_transmit_safely

#: 错误契约随本函数透传不捕获，FrameError 重导出供调用方就地导入。
__all__ = ["FrameError", "LinkError", "drive_nrf24_link"]

_LINK_NAME = "nrf24"
_DEFAULT_BAUD = 115200
_DEFAULT_BAD_FRAME_LIMIT = 5
_VALID_SOURCES = ("serial", "lines")
# source='serial' 且 pyserial 缺失时随 LinkError 给出的安装提示
_INSTALL_HINT = "pip install pyserial"

#: 自生成 run_token 前缀（同 run_power_ladder）：ctx 未提供 token 时自生成并写回
#: ctx——同 backend 跨调用各配独立 token，停发射按 (backend, token) 运行级幂等，
#: 每次错误路径均实停（缺省 None 退化为进程级幂等会漏停）；ctx 跨调用复用时
#: '_auto:' 前缀旧 token 一律换新防误继承，外部 token（无前缀）不覆盖。
_AUTO_TOKEN_PREFIX = "_auto:"


class LinkError(RuntimeError):
    """NRF24 链路错误（帧损坏超阈/串口源中断）——抛出前已先走 stop_transmit_safely。

    属性: reason=原因文案; stop_result=停发射结果 dict（status/steps/ts/context）；
    链路从未建立（pyserial 缺失/port 缺失）时 stop_result 为 None。
    """

    def __init__(self, reason: str, stop_result: dict | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.stop_result = stop_result


def _validate_config(serial_config: dict) -> dict:
    """校验并归一 serial_config（与 drive_esp32_link 同形）；形状错抛 ValueError。"""
    if not isinstance(serial_config, dict):
        raise ValueError(
            f"serial_config 必须为 dict，收到 {type(serial_config).__name__}"
        )
    source = serial_config.get("source", "serial")
    if source not in _VALID_SOURCES:
        raise ValueError(
            f"serial_config['source'] 必须为 {_VALID_SOURCES} 之一，收到 {source!r}"
            f"（旧「source 直收迭代器」形态不再兼容——请改用 source='lines' + "
            f"serial_config['lines']=行流迭代器）"
        )
    baud = serial_config.get("baud", _DEFAULT_BAUD)
    if isinstance(baud, bool) or not isinstance(baud, int) or baud <= 0:
        raise ValueError(f"serial_config['baud'] 必须为正整数，收到 {baud!r}")
    bad_frame_limit = serial_config.get("bad_frame_limit", _DEFAULT_BAD_FRAME_LIMIT)
    if (
        isinstance(bad_frame_limit, bool)
        or not isinstance(bad_frame_limit, int)
        or bad_frame_limit < 1
    ):
        raise ValueError(
            f"serial_config['bad_frame_limit'] 必须为 >=1 的整数，收到 {bad_frame_limit!r}"
        )
    port = serial_config.get("port")
    if port is not None and not isinstance(port, str):
        raise ValueError(
            f"serial_config['port'] 必须为 str 或 None，收到 {type(port).__name__}"
        )
    lines = serial_config.get("lines")
    if source == "lines":
        if lines is None:
            raise ValueError(
                "source='lines' 需同时提供 serial_config['lines']（Iterable[bytes|str] 帧行）"
            )
        try:
            iter(lines)
        except TypeError:
            raise ValueError(
                f"serial_config['lines'] 必须可迭代，收到 {type(lines).__name__}"
            ) from None
    return {
        "source": source,
        "port": port,
        "baud": baud,
        "lines": lines,
        "bad_frame_limit": bad_frame_limit,
    }


def _open_serial(config: dict):
    """打开真实串口（与 drive_esp32_link 同款）；pyserial 缺失/port 缺失→LinkError
    （含提示，链路从未建立故不停发射），打开失败→原异常上抛（由驱动统一先停发射再包）。"""
    try:
        import serial  # 延迟导入：无 pyserial 的环境走到 serial 源才报 LinkError
    except ImportError as exc:
        raise LinkError(
            f"pyserial 未安装或不可用（{exc}）：source='serial' 需先安装（{_INSTALL_HINT}）"
        ) from exc
    port = config["port"]
    if not port:
        raise LinkError(
            f"serial 源缺少可用 port（serial_config['port']={port!r}）："
            "请提供如 '/dev/ttyUSB0' 的串口名，或改用 source='lines' 注入帧行"
        )
    return serial.Serial(port, config["baud"])


def drive_nrf24_link(serial_config: dict, ctx: dict | None = None) -> Iterator[dict]:
    """NRF24 被测链路驱动：串口计数帧流 → 增量 KPI 样本生成器（无 RSSI 口径）。

    输入: serial_config（与 drive_esp32_link 同形，Ruling⑰①③ 统一）:
          'source'='serial'（缺省，真实串口 serial.Serial(port, baud)）| 'lines'
          （注入 Iterable[bytes|str] 帧行，测试经此注入行序列；耗尽=正常结束；
          lines 模式 port 可缺）、'port'=串口名（str|None，serial 源缺 port 在
          迭代时 LinkError）、'baud'=波特率（正 int，缺省 115200）、
          'bad_frame_limit'=连续坏帧阈（正 int，缺省 5，与 drive_esp32_link 同键名）；
          ctx=运行上下文 dict|None（'backend'=停发射后端、'run_token'=运行级幂等
          token，未提供时自生成 '_auto:' 前缀写回 ctx）。
    输出: 生成器逐好帧产出 KPI 样本（键集恰为 5 项，永不携带 rssi 字段）:
          {'timestamp_ms': float（主机单调钟 ms，非降）、'link': 'nrf24'、
          'per_raw': float|None（=lost 增量/sent 增量；不可比窗为 None）、
          'retries': int（窗重传增量）、'rpd': bool（当帧 1bit 门限位透传）}；
          不可比窗另附 'per_note': 'no_delta'（sent 增量为 0——0/0 不可比，交下游
          按不可用样本处理）、'counter_reset'（计数回退——设备复位/寄存器回绕，
          重定基线不硬算负增量，该窗重传按 0 计）或 'delta_overflow'（lost 增量>
          sent 增量——物理不可能，不杀流、如实标注，重传增量照实透出）。流首基线
          取 0（首帧增量即其绝对读数）；行流耗尽自然结束。
    错误: serial_config/ctx 非法（非 dict、source 非 'serial'/'lines'——含旧
          「source 直收迭代器」形态、baud/bad_frame_limit 非正 int（bool 拒）、
          port 非 str|None、lines 源缺 lines/不可迭代）→ ValueError，调用时即刻
          抛出（不推迟到首 next，不消费行流）；pyserial 未装 / port 缺失（serial
          源）→ LinkError（消息含安装/配置提示，不停发射——链路从未建立）；串口
          打开或读取失败 / 连续坏帧达 bad_frame_limit 或行流迭代自身抛异常
          （串口断开）→ 先 stop_transmit_safely（ctx['backend']+运行级 run_token）
          再抛 LinkError（附 .stop_result；源中断链上原始异常）。
    口径: NRF24 无 RSSI 读数——样本永不携带 rssi/rssi_dbm 键（指标口径固定
          丢包/重传+RPD 门限位，此为与 drive_esp32_link 样本的口径差异点）。
    """
    if not isinstance(serial_config, dict):
        raise ValueError(
            f"serial_config 必须为 dict（source/port/baud/lines/bad_frame_limit），"
            f"实际类型: {type(serial_config).__name__}"
        )
    if ctx is not None and not isinstance(ctx, dict):
        raise ValueError(f"ctx 必须为 dict 或 None，实际类型: {type(ctx).__name__}")

    config = _validate_config(serial_config)

    # 停发射凭据（仅错误路径使用）：backend/run_token 取自 ctx；未提供 token 时
    # 自生成 '_auto:' 前缀 token 写回 ctx（口径见 _AUTO_TOKEN_PREFIX 注释）。
    ctx_fields = ctx if isinstance(ctx, dict) else {}
    backend = ctx_fields.get("backend")
    run_token = ctx_fields.get("run_token")
    if run_token is None or (
        isinstance(run_token, str) and run_token.startswith(_AUTO_TOKEN_PREFIX)
    ):
        run_token = f"{_AUTO_TOKEN_PREFIX}{uuid4().hex}"
        ctx_fields["run_token"] = run_token

    return _iter_nrf24_samples(config, backend, run_token)


def _iter_nrf24_samples(
    config: dict,
    backend: object,
    run_token: object,
) -> Iterator[dict]:
    """实际驱动循环：入口校验已就绪，此处纯流式解析+增量产出+错误处置。"""
    port = config["port"]
    serial_port = None
    prev_sent = prev_lost = prev_retries = 0  # 流首基线取 0：首帧增量即绝对读数
    bad_streak = 0
    bad_total = 0
    good_total = 0

    def _stop(reason: str, error_text: str | None = None) -> dict:
        """错误路径停发射（安全路径不抛出，结果供 LinkError 附带）。"""
        context: dict = {"origin": "drive_nrf24_link", "reason": reason, "port": port}
        if error_text is not None:
            context["error"] = error_text
        return stop_transmit_safely(backend, context=context, run_token=run_token)

    try:
        if config["source"] == "serial":
            serial_port = _open_serial(config)  # 缺库/缺 port→LinkError（未建链不停发射）
            line_stream = serial_port
        else:
            line_stream = iter(config["lines"])
        for line in line_stream:
            try:
                frame = parse_nrf24_frame(line)
            except FrameError:
                bad_streak += 1
                bad_total += 1
                if bad_streak >= config["bad_frame_limit"]:
                    # 损坏超阈：先停发射再抛（异常能传出即证明停发射已完成）。
                    stop_result = _stop("bad_frame_streak")
                    raise LinkError(
                        f"NRF24 链路帧损坏超阈: 连续坏帧 {bad_streak} >= "
                        f"{config['bad_frame_limit']}（port={port}，好帧 {good_total}，"
                        f"累计坏帧 {bad_total}）——已先停发射",
                        stop_result=stop_result,
                    )
                continue  # 阈下坏帧：跳过不产出（好帧将连续计数清零）
            bad_streak = 0
            good_total += 1

            sent_d = frame["sent"] - prev_sent
            lost_d = frame["lost"] - prev_lost
            retries_d = frame["retries"] - prev_retries

            per_note: str | None = None
            if sent_d < 0 or lost_d < 0 or retries_d < 0:
                # 计数回退（设备复位/寄存器回绕）：重定基线，本窗不硬算负增量。
                per_note = "counter_reset"
                per_raw = None
                retries_out = 0
            elif sent_d == 0:
                # 本窗无新包：0/0 不可比，交下游按不可用样本处理（retries 增量照实透出）。
                per_note = "no_delta"
                per_raw = None
                retries_out = retries_d
            elif lost_d > sent_d:
                # lost 增量>sent 增量：物理不可能（丢包不可能多于发包），不杀流、
                # 如实标注（retries 增量照实透出）。
                per_note = "delta_overflow"
                per_raw = None
                retries_out = retries_d
            else:
                per_raw = lost_d / sent_d
                retries_out = retries_d
            prev_sent, prev_lost, prev_retries = frame["sent"], frame["lost"], frame["retries"]

            sample: dict = {
                "timestamp_ms": time.monotonic_ns() / 1e6,
                "link": _LINK_NAME,
                "per_raw": per_raw,
                "retries": retries_out,
                "rpd": frame["rpd"],
            }
            if per_note is not None:
                sample["per_note"] = per_note
            yield sample
        # 行流耗尽：自然结束（不产错、不停发射——收尾停发射归编排方）。
    except LinkError:
        raise  # 已按"先停发射再抛"语义处置过（或链路从未建立），不再包装
    except Exception as exc:  # noqa: BLE001 - 串口断开等源异常：先停发射再转 LinkError
        stop_result = _stop("source_error", f"{type(exc).__name__}: {exc}")
        raise LinkError(
            f"NRF24 串口打开或读取失败（疑似断开；port={port}，好帧 {good_total}，"
            f"累计坏帧 {bad_total}）: {type(exc).__name__}: {exc}——已先停发射",
            stop_result=stop_result,
        ) from exc
    finally:
        if serial_port is not None:
            close = getattr(serial_port, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:  # noqa: BLE001 - 关闭失败不得掩盖主结果/主错误
                    pass
