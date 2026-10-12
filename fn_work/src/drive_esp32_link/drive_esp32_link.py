"""ESP32 链路驱动：串口连接+KPI 帧流（断开先停发射）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import time
from typing import Iterator
from uuid import uuid4

from src.shared.stop_transmit_safely import stop_transmit_safely

from .parse_esp32_frame import FrameError, parse_esp32_frame

# serial_config 默认值与合法域
_DEFAULT_BAUD = 115200
_DEFAULT_BAD_FRAME_LIMIT = 5
_VALID_SOURCES = ("serial", "lines")
# source='serial' 且 pyserial 缺失时随 LinkError 给出的安装提示
_INSTALL_HINT = "pip install pyserial"

#: 自生成 run_token 前缀（同 drive_nrf24_link/run_power_ladder）：ctx 未提供 token
#: 时自生成并写回 ctx——同 backend 跨调用各配独立 token，停发射按 (backend, token)
#: 运行级幂等，每次错误路径均实停（缺省 None 退化为进程级幂等会漏停）；ctx 跨调用
#: 复用时 '_auto:' 前缀旧 token 一律换新防误继承，外部 token（无前缀）不覆盖。
_AUTO_TOKEN_PREFIX = "_auto:"


class LinkError(RuntimeError):
    """ESP32 链路级错误：pyserial 缺失/port 缺失/串口打开或读取失败/连续坏帧超阈。

    除前两种（链路从未建立）外，抛出前发射均已通过 stop_transmit_safely 先行停止。
    """


def _validate_config(serial_config: dict) -> dict:
    """校验并归一 serial_config；形状错抛 ValueError（调用即执行，不等首次迭代）。"""
    if not isinstance(serial_config, dict):
        raise ValueError(
            f"serial_config 必须为 dict，收到 {type(serial_config).__name__}"
        )
    source = serial_config.get("source", "serial")
    if source not in _VALID_SOURCES:
        raise ValueError(
            f"serial_config['source'] 必须为 {_VALID_SOURCES} 之一，收到 {source!r}"
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
    """打开真实串口；pyserial 缺失/port 缺失→LinkError（含提示），打开失败→原异常上抛。"""
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


def _sample_from_frame(frame: dict, prev: dict) -> dict:
    """已解析帧+上一好帧计数→KPI 样本（per 双口径：增量 per_raw + 累计 per_cum）。

    帧给的是累计 sent/err：增量口径用本帧−上帧（首帧以 0 为基线，天然等于帧内累计）。
    不可比窗 per_raw=None 并附注（不得以 0.0 成为零丢包判据证据）：
    sent 增量<=0（含计数器重置回退）附 'per_note': 'no_delta'；err 增量>sent 增量
    （物理不可能）附 'per_note': 'delta_overflow'（不杀流、如实标注）。per_cum>1
    同窗附 'cum_overflow': True（累计口径溢出标注，值照实透出）。
    """
    sent_delta = frame["sent"] - prev["sent"]
    err_delta = frame["err"] - prev["err"]
    sample: dict = {
        "timestamp_ms": time.monotonic() * 1000,
        "link": "esp32",
        "seq": frame["seq"],
        "per_raw": None,
        "per_cum": (frame["err"] / frame["sent"]) if frame["sent"] > 0 else 0.0,
        "retries": frame["retries"],
        "rssi_dbm": frame["rssi_dbm"],
        "source": "esp32",
    }
    if sent_delta > 0:
        if err_delta > sent_delta:
            # err 增量>sent 增量：物理不可能（丢包不可能多于发包），如实标注不硬算
            sample["per_note"] = "delta_overflow"
        else:
            # err 回退（计数器重置但 sent 仍在涨的畸形流）按 0 截断，防负 PER
            sample["per_raw"] = max(err_delta, 0) / sent_delta
    else:
        # 不可比窗（无新增发包，含 sent 回退）：per_raw=None，不得记 0.0 冒充零丢包
        sample["per_note"] = "no_delta"
    if sample["per_cum"] > 1.0:
        sample["cum_overflow"] = True
    if prev["seq"] is not None and frame["seq"] < prev["seq"]:
        # 帧序回退：计数器重置场景，只标注不抛
        sample["seq_rollback"] = True
    return sample


def _sample_stream(
    config: dict, backend: object, run_token: object
) -> Iterator[dict]:
    """真实生成器体：驱动行流→逐帧解析→逐样本产出（错误路径先停发射）。"""
    serial_port = None
    # 上一好帧累计计数（首帧基线 seq 未知/sent=err=0）
    prev: dict = {"seq": None, "sent": 0, "err": 0}
    consecutive_bad = 0
    try:
        if config["source"] == "serial":
            serial_port = _open_serial(config)  # 缺库/缺 port→LinkError；打开失败→走下方统一停发射
            line_stream = serial_port
        else:
            line_stream = iter(config["lines"])
        for raw in line_stream:
            # lines 源耗尽→StopIteration 由 for 消化→自然结束（不算错误）
            try:
                frame = parse_esp32_frame(raw)
            except FrameError:
                consecutive_bad += 1
                if consecutive_bad >= config["bad_frame_limit"]:
                    # 先停发射，再抛链路错误
                    stop_transmit_safely(backend, run_token=run_token)
                    raise LinkError(
                        f"连续坏帧 {consecutive_bad} 达阈值 "
                        f"{config['bad_frame_limit']}：链路数据不可用"
                    ) from None
                continue
            consecutive_bad = 0  # 好帧清零：阈值只统计连续坏帧
            yield _sample_from_frame(frame, prev)
            prev = {"seq": frame["seq"], "sent": frame["sent"], "err": frame["err"]}
    except LinkError:
        raise  # 已按各自语义处理（含先停发射），不重复停
    except Exception as exc:
        # 串口打开/读取失败（SerialException 族等疑似断开）：先停发射再抛 LinkError
        stop_transmit_safely(backend, run_token=run_token)
        raise LinkError(
            f"ESP32 串口打开或读取失败（疑似断开）：{type(exc).__name__}: {exc}"
        ) from exc
    finally:
        if serial_port is not None:
            close = getattr(serial_port, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:  # noqa: BLE001 - 关闭失败不得掩盖主结果/主错误
                    pass


def drive_esp32_link(serial_config: dict, ctx: dict | None = None) -> Iterator[dict]:
    """ESP32 链路驱动（生成器）：打开串口/注入行流，逐帧产出 KPI 样本（断开先停发射）。

    输入: serial_config——
          'source': 'serial'（默认，真实串口 serial.Serial(port, baud)）| 'lines'
                    （注入 Iterable[bytes|str] 帧行，测试/sim 数据用；耗尽=正常结束）；
          'port': str|None（serial 源用）；
          'baud': 正整数，默认 115200；
          'lines': source='lines' 时必填；
          'bad_frame_limit': 连续坏帧阈值，默认 5（与 drive_nrf24_link 同键名同缺省）。
          ctx——可选 dict，可含 'backend'（鸭子类型发射后端；断开/坏帧超阈经
          stop_transmit_safely 先停发射再抛错）与 'run_token'（运行级幂等 token；
          未提供时自生成 '_auto:' 前缀写回 ctx，ctx 复用时旧 '_auto:' token 换新，
          外部 token 不覆盖——同 backend 两轮错误路径均实停）。
    输出: 生成器，逐帧产出样本
          {'timestamp_ms': time.monotonic()*1000, 'link': 'esp32', 'seq',
           'per_raw': 增量 PER（本帧 err−上帧 err / 本帧 sent−上帧 sent；首帧以 0 为
                      基线；不可比窗为 None 并附 'per_note'——sent 增量<=0（含回退）
                      →'no_delta'，err 增量>sent 增量（物理不可能）→'delta_overflow'），
           'per_cum': 累计 PER（本帧 err/sent；sent=0→0.0；>1 同窗附
                      'cum_overflow': True），
           'retries': int, 'rssi_dbm': float|None（'NA'→None 透传）, 'source': 'esp32'}；
           帧序回退（seq<上帧，计数器重置场景）附 'seq_rollback': True（不抛）。
    错误: config 形状错（非 dict / source 非法 / baud 或 bad_frame_limit 非正整数 /
          lines 源缺 lines 等）→ValueError（调用即抛，生成器未建）；
          pyserial 未装 / port 缺失（serial 源）→LinkError（消息含安装/配置提示）；
          串口打开或读取失败（SerialException 族）/ 连续坏帧达 bad_frame_limit→
          先 stop_transmit_safely(ctx['backend'], run_token=运行级 token) 再抛 LinkError；
          lines 源耗尽→生成器自然结束（StopIteration 语义，不算错误）。
    """
    config = _validate_config(serial_config)
    # 停发射凭据（仅错误路径使用）：backend/run_token 取自 ctx；未提供 token 时自生成
    # '_auto:' 前缀 token 写回 ctx（口径见 _AUTO_TOKEN_PREFIX 注释；ctx 非 dict 时
    # 只生成不写回——此时 backend 亦为 None，token 不参与任何停发射）。
    ctx_fields = ctx if isinstance(ctx, dict) else {}
    backend = ctx_fields.get("backend")
    run_token = ctx_fields.get("run_token")
    if run_token is None or (
        isinstance(run_token, str) and run_token.startswith(_AUTO_TOKEN_PREFIX)
    ):
        run_token = f"{_AUTO_TOKEN_PREFIX}{uuid4().hex}"
        ctx_fields["run_token"] = run_token
    return _sample_stream(config, backend, run_token)
