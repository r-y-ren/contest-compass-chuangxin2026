"""B210 真硬件后端：传输适配层注入 + UHD 双通道初始化——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import logging
import math
import subprocess

# BackendError 单一事实源在注册表包（与 configure/write/read 叶子同源同类）；
# register_backend 供本模块 import 期自注册（与 open_sim_backend / open_replay_backend 同模式）。
from src.manage_backend_registry.register_backend import BackendError, register_backend

from .configure_b210_channels import configure_b210_channels
from .read_b210_rx_stream import read_b210_rx_stream
from .write_b210_tx_stream import write_b210_tx_stream

__all__ = [
    "B210Backend",
    "UhdPyTransport",
    "open_b210_backend",
    "probe_b210_available",
]

_LOGGER = logging.getLogger(__name__)

# 注册名与能力域（与 lookup_backend 别名表 b210 -> b210 同源；freq 70MHz-6GHz、增益 0-89.75dB）。
_BACKEND_NAME = "b210"
_FREQ_RANGE_MHZ: tuple[float, float] = (70.0, 6000.0)
_FREQ_MIN_HZ, _FREQ_MAX_HZ = 70e6, 6e9
_GAIN_MIN_DB, _GAIN_MAX_DB = 0.0, 89.75
_CLOCK_REFS = frozenset({"internal", "external", "gpsdo"})
_ANTENNA_WHITELIST = frozenset({"TX/RX", "RX2", "RX1", "TX"})

# 传输名白名单：str 须落此二名；非 str 一律按注入传输对象（鸭子接口 make_device/
# make_tx_stream/make_rx_stream，测试/模拟用）。
_TRANSPORT_NAMES = frozenset({"uhd_py", "uhd_cli"})
_TRANSPORT_DEFAULT = "uhd_py"
_TRANSPORT_DUCK_METHODS = ("make_device", "make_tx_stream", "make_rx_stream")
_TRANSPORT_NAMES_DESC = "/".join(sorted(_TRANSPORT_NAMES))

# 参数缺省（标量参数投影为双通道结构，见 open_b210_backend 文档）。
_DEFAULT_DEVICE_ARGS = "type=b200"
_DEFAULT_FREQ_HZ = 2.4e9
_DEFAULT_SAMPLE_RATE = 1e6
_DEFAULT_TX_GAIN_DB = 0.0
_DEFAULT_TX_ANTENNA = "TX/RX"
_DEFAULT_RX_ANTENNA = "RX2"

# CLI 探测：命令 / 超时 / 在位标记（uhd_find_devices 输出的设备段头）/ 摘要长度上限。
_FIND_DEVICES_CMD = ("uhd_find_devices",)
_PROBE_TIMEOUT_S = 30.0
_PROBE_DEVICE_MARKER = "-- UHD Device"
_PROBE_SUMMARY_MAX = 300

# probe_b210_available 模块级缓存：None=未探测（测试可 monkeypatch 本变量重置）。
_PROBE_CACHE: bool | None = None


def _as_real(key: str, raw: object) -> float:
    """数值参数统一校验：bool 拒收（布尔频率/增益几乎必为配置笔误），非数/非有限→ValueError。"""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(
            f"{key} 须为有限实数（int/float，bool 拒收），"
            f"得到 {type(raw).__name__}: {raw!r}"
        )
    val = float(raw)
    if not math.isfinite(val):
        raise ValueError(f"{key} 须为有限数，得到 {val!r}")
    return val


def _run_find_devices() -> str:
    """跑 uhd_find_devices CLI，返回 stdout+stderr 合并原文（探测失败的口径见各分支）。"""
    try:
        proc = subprocess.run(  # noqa: S603 - 固定命令名、无 shell 拼接
            _FIND_DEVICES_CMD,
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_S,
        )
    except FileNotFoundError:
        _LOGGER.warning("uhd_find_devices 不在 PATH：按无设备处理")
        return ""
    except subprocess.TimeoutExpired:
        _LOGGER.warning("uhd_find_devices 探测超时（>%ss）：按无设备处理", _PROBE_TIMEOUT_S)
        return ""
    output = proc.stdout or ""
    if proc.stderr:
        output = output + "\n" + proc.stderr if output else proc.stderr
    return output


def _probe_has_device(output: str) -> bool:
    """探测输出在位判定：出现设备段头 '-- UHD Device' 即在位（空探测输出 'No UHD Devices Found'）。"""
    return _PROBE_DEVICE_MARKER in output


def _probe_summary(output: str) -> str:
    """探测输出摘要：非空行以 ' | ' 连接，超长截断——供 BackendError 消息与降级日志引用。"""
    compact = " | ".join(line.strip() for line in output.splitlines() if line.strip())
    if not compact:
        return "(CLI 缺失/超时/空输出)"
    if len(compact) > _PROBE_SUMMARY_MAX:
        return compact[:_PROBE_SUMMARY_MAX] + "...(截断)"
    return compact


def probe_b210_available(refresh: bool = False) -> bool:
    """B210 在位探测（公开：autodetect_backend 与测试 skipif 用）。

    内部调 uhd_find_devices CLI（subprocess），结果模块级缓存——真机上固件加载
    探测一次秒级，重复探测无谓；refresh=True 强制重探并刷新缓存。
    CLI 缺失/超时按不在位处理（返回 False，不抛——探测失败不是调用方错误）。
    """
    global _PROBE_CACHE
    if _PROBE_CACHE is None or refresh:
        _PROBE_CACHE = _probe_has_device(_run_find_devices())
    return _PROBE_CACHE


class UhdPyTransport:
    """uhd Python 绑定传输：make_device→uhd.usrp.MultiUSRP，流句柄适配鸭子协议。

    uhd 模块延迟导入（构造时 import）：无 UHD 环境下本模块仍可导入注册，
    仅在真选 uhd_py 传输时才要求绑定在位（缺→BackendError 含 ImportError 原文）。
    """

    def __init__(self, uhd_module: object | None = None) -> None:
        if uhd_module is None:
            try:
                import uhd as uhd_module  # noqa: PLC0415 - 延迟导入是本类存在意义
            except ImportError as exc:
                raise BackendError(
                    f"uhd_py 传输不可用：Python uhd 绑定导入失败（{exc}）——"
                    "可改 transport='uhd_cli' 只读探测，或注入 transport 对象"
                ) from exc
        self._uhd = uhd_module

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<UhdPyTransport uhd={getattr(self._uhd, '__name__', 'uhd')}>"

    def make_device(self, args: str):
        """按 UHD 设备参数串打开设备（'type=b200' 等），异常原样上抛由 open 层包装。"""
        return self._uhd.usrp.MultiUSRP(args)

    def make_tx_stream(self, device):
        """CH1 发射流句柄：UHD tx_streamer 适配 send(chunk)->{'sent': n} 鸭子协议。"""
        return _UhdPyTxStream(device, self._uhd)

    def make_rx_stream(self, device):
        """CH2 监测流句柄：UHD rx_streamer 适配 recv(n)->{'samples','overflow','ts'} 鸭子协议。"""
        return _UhdPyRxStream(device, self._uhd)


class _UhdPyTxStream:
    """UHD 发射流适配器：write_b210_tx_stream 的鸭子句柄。

    start() 标记下一 send 为 start_of_burst；end() 尽力发 end_of_burst 空包
    （UHD 对 0 长数组可能 RuntimeError——吞掉记 warning，突发终止失败不视为发送失败）。
    """

    def __init__(self, device, uhd_module, timeout_s: float = 1.0) -> None:
        import numpy as np  # noqa: PLC0415 - uhd 绑定本身依赖 numpy，延迟到真用流时

        self._np = np
        self._timeout = timeout_s
        self._streamer = device.get_tx_stream(uhd_module.usrp.StreamArgs("fc32", ""))
        self._uhd = uhd_module
        self._pending_sob = True

    def start(self) -> None:
        self._pending_sob = True

    def send(self, iq_chunk) -> dict:
        md = self._uhd.types.TXMetadata()
        md.has_time_spec = False
        md.start_of_burst = self._pending_sob
        md.end_of_burst = False
        arr = self._np.asarray(iq_chunk, dtype=self._np.complex64)
        sent = self._streamer.send(arr, md, timeout=self._timeout)
        self._pending_sob = False
        return {"sent": int(sent)}

    def end(self) -> None:
        try:
            md = self._uhd.types.TXMetadata()
            md.has_time_spec = False
            md.end_of_burst = True
            self._streamer.send(
                self._np.zeros(0, dtype=self._np.complex64), md, timeout=self._timeout
            )
        except Exception as exc:  # EOB 空包在部分 UHD 版本拒收：尽力而为，不炸发送主流程
            _LOGGER.warning("TX end_of_burst 空包发送失败（吞掉）: %s: %s", type(exc).__name__, exc)
        finally:
            self._pending_sob = True


class _UhdPyRxStream:
    """UHD 监测流适配器：read_b210_rx_stream 的鸭子句柄。

    recv 惰性启动连续流（首次 recv 才 issue start_cont——open 时不抢占流）；
    stop() 发 stop_cont。ts 为设备时间戳按当前 RX 采样率换算的 tick 数。
    """

    def __init__(self, device, uhd_module, timeout_s: float = 1.0) -> None:
        import numpy as np  # noqa: PLC0415 - 同上，延迟导入

        self._np = np
        self._uhd = uhd_module
        self._device = device
        self._timeout = timeout_s
        self._streamer = device.get_rx_stream(uhd_module.usrp.StreamArgs("fc32", ""))
        self._streaming = False

    def _ensure_streaming(self) -> None:
        if not self._streaming:
            cmd = self._uhd.types.StreamCMD(self._uhd.types.StreamMode.start_cont)
            cmd.stream_now = True
            self._streamer.issue_stream_cmd(cmd)
            self._streaming = True

    def recv(self, num_samps: int) -> dict:
        self._ensure_streaming()
        count = max(1, int(num_samps))
        arr = self._np.zeros(count, dtype=self._np.complex64)
        md = self._uhd.types.RXMetadata()
        got = self._streamer.recv(arr, md, timeout=self._timeout)
        overflow = "overflow" in str(md.error_code).lower()
        ts = int(md.time_spec.to_ticks(float(self._device.get_rx_rate())))
        return {
            "samples": [complex(sample) for sample in arr[:got]],
            "overflow": overflow,
            "ts": ts,
        }

    def stop(self) -> None:
        if self._streaming:
            self._streamer.issue_stream_cmd(
                self._uhd.types.StreamCMD(self._uhd.types.StreamMode.stop_cont)
            )
            self._streaming = False


class B210Backend:
    """B210 真硬件后端实例（鸭子接口同 SimBackend：start_tx/stop_tx/set_tx_gain/read_samples/capabilities）。

    TX 块经 write_b210_tx_stream 送入传输层发射流句柄（同步发送，返回统计）；
    RX 块经 read_b210_rx_stream 从监测流句柄拉取。真硬件无环回信道——start_tx 的
    effects 参数被忽略并记 warning（不静默：调用方应知晓效应未作用于物理链路）。
    """

    def __init__(
        self,
        device,
        tx_stream,
        rx_stream,
        *,
        freq_hz: float,
        sample_rate: float,
        tx_gain_db: float,
        clock_ref: str | None,
        transport_name: str,
        configure_report: dict,
    ) -> None:
        self.device = device
        self.freq_hz = freq_hz
        self.sample_rate = sample_rate
        self.tx_gain_db = tx_gain_db
        self.clock_ref = clock_ref
        self.transport_name = transport_name
        self.configure_report = configure_report
        self.last_tx_stats: dict | None = None
        self.last_effects_ignored: object = None
        self._tx_stream = tx_stream
        self._rx_stream = rx_stream
        self._closed = False

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<B210Backend transport={self.transport_name!r} freq_hz={self.freq_hz!r} "
            f"sample_rate={self.sample_rate!r} closed={self._closed!r}>"
        )

    @property
    def closed(self) -> bool:
        """是否已 close（停止接收流并释放引用；MultiUSRP 无显式 close，句柄交 GC）。"""
        return self._closed

    def __enter__(self) -> "B210Backend":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def start_tx(self, iq_blocks, effects: dict | None = None) -> dict:
        """CH1 发射 IQ 块（经 write_b210_tx_stream，返回发送统计 dict）。

        effects 忽略——真硬件无环回，信道效应不作用于物理链路：记录 warning 并
        存 last_effects_ignored（不抛：同参调用 SimBackend 的代码无需分支）。
        """
        if effects is not None:
            self.last_effects_ignored = effects
            _LOGGER.warning(
                "B210 真硬件无环回信道：start_tx 的 effects 被忽略、未作用于物理链路（%r）",
                effects,
            )
        stats = write_b210_tx_stream(self._tx_stream, iq_blocks)
        self.last_tx_stats = stats
        return stats

    def stop_tx(self) -> None:
        """停止发射：透传到发射流句柄与设备钩子（缺方法跳过，不炸）。"""
        stream_stop = getattr(self._tx_stream, "stop", None)
        if callable(stream_stop):
            stream_stop()
        device_stop = getattr(self.device, "stop_tx", None)
        if callable(device_stop):
            device_stop()
        return None

    def set_tx_gain(self, db) -> float:
        """设置发射增益：透传 device.set_tx_gain 并回读 get_tx_gain 返回实际生效值。"""
        val = _as_real("tx_gain_db", db)
        setter = getattr(self.device, "set_tx_gain", None)
        if not callable(setter):
            raise BackendError(f"B210 设备句柄缺 set_tx_gain: {self.device!r}")
        try:
            setter(val)
        except Exception as exc:
            raise BackendError(
                f"B210 set_tx_gain 失败（gain={val!r}）: {type(exc).__name__}: {exc}"
            ) from exc
        getter = getattr(self.device, "get_tx_gain", None)
        if callable(getter):
            applied = getter()
            if isinstance(applied, (int, float)) and not isinstance(applied, bool):
                self.tx_gain_db = float(applied)
            return applied
        self.tx_gain_db = val
        return val

    def read_samples(self, max_blocks: int = 1) -> list[dict]:
        """CH2 监测读取（经 read_b210_rx_stream）：返回 [{'samples','ts','overflow','device_ts'}, ...]。

        块 dict 形状即 read_b210_rx_stream 产出（ts 为产出块单调序号、device_ts 为
        设备时间戳）；max_blocks 非法由 read_b210_rx_stream 调用即抛 ValueError。
        """
        return list(read_b210_rx_stream(self._rx_stream, max_blocks))

    def capabilities(self) -> dict:
        """能力元数据（每次返回新 dict，调用方篡改不回写实例与注册表）。"""
        return {
            "kind": _BACKEND_NAME,
            "tx": True,
            "rx": True,
            "freq_range_mhz": tuple(_FREQ_RANGE_MHZ),
            "freq_hz": self.freq_hz,
            "sample_rate_hz": self.sample_rate,
            "tx_gain_range_db": (_GAIN_MIN_DB, _GAIN_MAX_DB),
            "clock_ref": self.clock_ref,
            "transport": self.transport_name,
        }

    def close(self) -> None:
        """停止接收流并标记关闭（幂等）：MultiUSRP 无显式 close，停流+释放引用即可。"""
        if self._closed:
            return None
        self._closed = True
        stream_stop = getattr(self._rx_stream, "stop", None)
        if callable(stream_stop):
            try:
                stream_stop()
            except Exception as exc:
                _LOGGER.warning(
                    "RX 流停止异常（吞掉，不影响 close）: %s: %s", type(exc).__name__, exc
                )
        return None


def _validate_antenna(key: str, raw: object) -> str:
    """天线参数域校验：str 且在白名单 {'TX/RX','RX2','RX1','TX'}。"""
    if not isinstance(raw, str) or raw not in _ANTENNA_WHITELIST:
        raise ValueError(
            f"{key} 非法: {raw!r}（白名单: {sorted(_ANTENNA_WHITELIST)}）"
        )
    return raw


def open_b210_backend(params: dict) -> B210Backend:
    """B210 真硬件后端：CLI 探测→设备打开→双通道参数下发→包装为 B210Backend（注册名 b210）。

    输入: params: dict，键均可缺省——
      - transport: 'uhd_py'（缺省；try import uhd，用 uhd.usrp.MultiUSRP 打开）|
        'uhd_cli'（subprocess 调 uhd_find_devices/uhd_usrp_probe，仅探测不支持收发——
        BackendError 说明 CLI 传输只读探测）| 直接注入 transport 对象（测试/模拟用，
        鸭子接口 make_device(args)→device + make_tx_stream(device) + make_rx_stream(device)）；
      - device_args: str（缺省 'type=b200'，MultiUSRP 打开参数串）；
      - freq_hz: 中心频率 Hz（缺省 2.4e9，域 70e6–6e9，域外 ValueError）；
      - sample_rate: 采样率 Hz（缺省 1e6，须为正）；tx_gain_db: 发射增益 dB（缺省 0，
        域 0–89.75，域外 ValueError）；rx_gain_db: 监测增益 dB（可缺，给出时域同上）；
      - tx_bandwidth_hz / rx_bandwidth_hz: 带宽 Hz（缺省取 sample_rate，须为正）；
      - tx_antenna（缺省 'TX/RX'）/ rx_antenna（缺省 'RX2'）: 白名单 {'TX/RX','RX2','RX1','TX'}；
      - clock_ref: 'internal'|'external'|'gpsdo'|缺省不设。
    输出: B210Backend 实例（start_tx 经 write_b210_tx_stream、read_samples 经
      read_b210_rx_stream、参数下发经 configure_b210_channels——报告存
      configure_report['applied'/'skipped'/'clock_ref']）。
    错误: params 域错/transport 名非法/注入对象缺鸭子方法 → ValueError（校验先于
      任何探测与设备调用，失败路径零副作用）；BackendError——无设备（uhd_find_devices
      探测空，消息含探测输出摘要，供 autodetect_backend 降级）、uhd_py 绑定缺失、
      设备打开/流句柄创建失败（含 UHD 错误原文，初始化失败上抛由 R7 决定降级，
      绝不静默 sim）、参数回读不符（configure_b210_channels 透传）。
    """
    if not isinstance(params, dict):
        raise ValueError(
            f"params 须为 dict（transport/device_args/freq_hz/sample_rate/tx_gain_db/"
            f"clock_ref 等），得到 {type(params).__name__}: {params!r}"
        )

    # 1) 传输解析：str 名（uhd_py|uhd_cli）或注入对象（非 str 一律注入口径）。
    transport_raw = params.get("transport", _TRANSPORT_DEFAULT)
    injected_transport = None
    if isinstance(transport_raw, str):
        if transport_raw not in _TRANSPORT_NAMES:
            raise ValueError(
                f"transport 须为 {_TRANSPORT_NAMES_DESC} 或注入传输对象"
                f"（make_device/make_tx_stream/make_rx_stream），得到 {transport_raw!r}"
            )
        transport_name = transport_raw
    else:
        for method in _TRANSPORT_DUCK_METHODS:
            if not callable(getattr(transport_raw, method, None)):
                raise ValueError(
                    f"注入 transport 缺可调用方法 {method}()（鸭子接口: "
                    f"{'/'.join(_TRANSPORT_DUCK_METHODS)}）: {transport_raw!r}"
                )
        injected_transport = transport_raw
        transport_name = type(transport_raw).__name__

    # 2) 标量参数域校验（全部先于探测/设备调用：ValueError 路径零硬件副作用）。
    device_args = params.get("device_args", _DEFAULT_DEVICE_ARGS)
    if not isinstance(device_args, str) or not device_args.strip():
        raise ValueError(
            f"device_args 须为非空 str（UHD 打开参数串，如 'type=b200'），得到 {device_args!r}"
        )
    freq_hz = _as_real("freq_hz", params.get("freq_hz", _DEFAULT_FREQ_HZ))
    if not _FREQ_MIN_HZ <= freq_hz <= _FREQ_MAX_HZ:
        raise ValueError(
            f"freq_hz 超出 B210 频率域 [{_FREQ_MIN_HZ:g}, {_FREQ_MAX_HZ:g}] Hz: {freq_hz!r}"
        )
    sample_rate = _as_real("sample_rate", params.get("sample_rate", _DEFAULT_SAMPLE_RATE))
    if sample_rate <= 0:
        raise ValueError(f"sample_rate 须为正数，得到 {sample_rate!r}")
    tx_gain_db = _as_real("tx_gain_db", params.get("tx_gain_db", _DEFAULT_TX_GAIN_DB))
    if not _GAIN_MIN_DB <= tx_gain_db <= _GAIN_MAX_DB:
        raise ValueError(
            f"tx_gain_db 超出增益域 [{_GAIN_MIN_DB:g}, {_GAIN_MAX_DB:g}] dB: {tx_gain_db!r}"
        )
    rx_gain_raw = params.get("rx_gain_db")
    if rx_gain_raw is not None:
        rx_gain = _as_real("rx_gain_db", rx_gain_raw)
        if not _GAIN_MIN_DB <= rx_gain <= _GAIN_MAX_DB:
            raise ValueError(
                f"rx_gain_db 超出增益域 [{_GAIN_MIN_DB:g}, {_GAIN_MAX_DB:g}] dB: {rx_gain!r}"
            )
    tx_bandwidth = _as_real(
        "tx_bandwidth_hz", params.get("tx_bandwidth_hz", sample_rate)
    )
    if tx_bandwidth <= 0:
        raise ValueError(f"tx_bandwidth_hz 须为正数，得到 {tx_bandwidth!r}")
    rx_bandwidth = _as_real(
        "rx_bandwidth_hz", params.get("rx_bandwidth_hz", sample_rate)
    )
    if rx_bandwidth <= 0:
        raise ValueError(f"rx_bandwidth_hz 须为正数，得到 {rx_bandwidth!r}")
    tx_antenna = _validate_antenna("tx_antenna", params.get("tx_antenna", _DEFAULT_TX_ANTENNA))
    rx_antenna = _validate_antenna("rx_antenna", params.get("rx_antenna", _DEFAULT_RX_ANTENNA))
    clock_ref = params.get("clock_ref")
    if clock_ref is not None and (
        not isinstance(clock_ref, str) or clock_ref not in _CLOCK_REFS
    ):
        raise ValueError(
            f"clock_ref 非法: {clock_ref!r}（合法值: {sorted(_CLOCK_REFS)}）"
        )

    # 3) uhd_cli：只读探测传输——不支持收发/下发，无论在位与否 BackendError 说明。
    if transport_name == "uhd_cli":
        summary = _probe_summary(_run_find_devices())
        raise BackendError(
            "uhd_cli 传输只读探测（uhd_find_devices/uhd_usrp_probe），不支持收发与通道配置："
            "请改 transport='uhd_py' 或注入 transport 对象。探测输出摘要: " + summary
        )

    # 4) uhd_py：CLI 探测先行（注入传输跳过——在位性由注入方自负其责）。
    #    无设备 → BackendError 含探测输出摘要：供 autodetect_backend 据此降级 sim。
    if injected_transport is None:
        probe_output = _run_find_devices()
        if not _probe_has_device(probe_output):
            raise BackendError(
                "B210 无设备：uhd_find_devices 探测为空（供 autodetect_backend 降级 sim）。"
                "探测输出摘要: " + _probe_summary(probe_output)
            )
        transport: object = UhdPyTransport()
    else:
        transport = injected_transport

    # 5) 设备打开（失败含 UHD 错误原文，__cause__ 保留——上抛由 R7 决定降级，不静默 sim）。
    try:
        device = transport.make_device(device_args)
    except Exception as exc:
        raise BackendError(
            f"B210 设备打开失败（device_args={device_args!r}）: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    # 6) 双通道参数下发 + 回读校验（回读不符 BackendError 透传）。
    ch2: dict = {
        "freq_hz": freq_hz,
        "sample_rate": sample_rate,
        "bandwidth_hz": rx_bandwidth,
        "antenna": rx_antenna,
    }
    if rx_gain_raw is not None:
        ch2["gain_db"] = rx_gain
    channel_params: dict = {
        "ch1_tx": {
            "freq_hz": freq_hz,
            "gain_db": tx_gain_db,
            "sample_rate": sample_rate,
            "bandwidth_hz": tx_bandwidth,
            "antenna": tx_antenna,
        },
        "ch2_rx": ch2,
    }
    if clock_ref is not None:
        channel_params["clock_ref"] = clock_ref
    report = configure_b210_channels(device, channel_params)

    # 7) 流句柄创建（发射/监测各一，失败同口径包装）。
    try:
        tx_stream = transport.make_tx_stream(device)
        rx_stream = transport.make_rx_stream(device)
    except Exception as exc:
        raise BackendError(
            f"B210 流句柄创建失败: {type(exc).__name__}: {exc}"
        ) from exc

    resolved_clock = report.get("clock_ref")
    return B210Backend(
        device,
        tx_stream,
        rx_stream,
        freq_hz=freq_hz,
        sample_rate=sample_rate,
        tx_gain_db=tx_gain_db,
        clock_ref=resolved_clock,
        transport_name=transport_name,
        configure_report=report,
    )


# 注册名与实例方法清单（caps 声明 tx/rx 为真 → 契约要求四方法齐备，import 期即受形式检查；
# override=True：重复 import / importlib.reload 幂等不炸）。
_METHOD_NAMES = ["start_tx", "stop_tx", "set_tx_gain", "read_samples"]

register_backend(
    _BACKEND_NAME,
    open_b210_backend,
    {
        "kind": _BACKEND_NAME,
        "caps": {"tx": True, "rx": True, "freq_range_mhz": tuple(_FREQ_RANGE_MHZ)},
    },
    override=True,
    method_names=list(_METHOD_NAMES),
)
