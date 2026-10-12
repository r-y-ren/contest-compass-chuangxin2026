"""13GHz 混频扩展模拟后端（LO+IF→RF 全链演示）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import math
import numbers

import numpy as np

# register_backend 供本模块 import 期自注册、BackendError 为发射请求报错单源
# （同 open_sim_analyzer 先例：start_tx 即抛）；上变频纯计算叶子来自同包——公式(2)/
# 镜像残留/二次杂散口径的单一事实源，本模块只做 LO 自持组装与 RF 域标注，绝不复算公式。
from src.manage_backend_registry.register_backend import BackendError, register_backend

from .upconvert_with_image_rejection import upconvert_with_image_rejection

__all__ = ["SimMixer13G", "open_sim_mixer"]

# ---- 13GHz 混频仿真口径常量（capabilities()/域标注/工厂缺省/演示链共用同一事实源）----
_RF_MAX_HZ = 20e9  # RF 仿真域上限（越过不拒收——标注 'beyond_model'，见重写规约）
_LO_DEFAULT_HZ = 12.85e9  # 缺省 LO：IF 150MHz → RF 恰 13GHz（配 2.4G 链→13G RF 演示口径）
_LO_POWER_DEFAULT_DBM = 7.0  # 缺省 LO 驱动功率 dBm
_PHASE_NOISE_DBC_HZ = -100.0  # LO 相噪口径 dBc/Hz（R40 C8 指标；模型固定，不经工厂参数化）
_REJECTION_DEFAULT_DB = 60.0  # 缺省镜像抑制比 dB（腔体滤波等效模型口径）
_FS_DEFAULT_HZ = 10e6  # shift_iq 缺省采样率 Hz（基带搬移演示域）

# chain_demo 全链演示的 IF 设置（缺省 LO 下 RF 恰 13GHz）
_DEMO_IF_HZ = 150e6
_DEMO_IF_POWER_DBM = -10.0

# RF 域标注口径：恰在 20GHz 端点仍 in_model（含端点），越过才 beyond_model
_NOTE_IN_MODEL = "in_model"
_NOTE_BEYOND_MODEL = "beyond_model"

# 无发射能力事件文案（stop_tx/set_tx_gain 记录）与 start_tx 报错文案
_NO_TX_EVENT = "sim_mixer_13g 无发射能力（混频组件）"
_NO_TX_MESSAGE = "sim_mixer_13g 后端无发射能力（混频组件，无 TX 通道）"

# 注册名：caps tx/rx 均假（组件级插件——混频器不是收发信机）；method_names=None
# 延迟（注册期跳过契约形式检查；caps 假声明本就无任何契约方法要求）。
_BACKEND_NAME = "sim_mixer_13g"


def _as_real(key: str, raw: object) -> float:
    """数值参数统一校验：bool 拒收（布尔频率/功率几乎必为配置笔误），非实数/非有限→ValueError。"""
    if isinstance(raw, bool) or not isinstance(raw, numbers.Real):
        raise ValueError(f"{key} 必须为实数，实际为 {type(raw).__name__}: {raw!r}")
    val = float(raw)
    if not math.isfinite(val):
        raise ValueError(f"{key} 必须为有限数，实际为 {val!r}")
    return val


def _check_positive(key: str, val: float) -> float:
    """正值域校验：频率/采样率须为正有限实数（≤0 → ValueError）。"""
    if val <= 0.0:
        raise ValueError(f"{key} 必须为正数（Hz），实际为 {val!r}")
    return val


def _check_non_negative(key: str, val: float) -> float:
    """非负域校验：镜像抑制比（dB）须 ≥0（负值 → ValueError；0 合法——镜像全残留）。"""
    if val < 0.0:
        raise ValueError(f"{key} 必须为非负数（dB），实际为 {val!r}")
    return val


def _iq_1d_finite(key: str, iq: object) -> np.ndarray:
    """IQ 域校验：一维复数化样本序列（None/非数值/2D+/空序列/含 NaN 或 ±inf → ValueError）。"""
    try:
        arr = np.asarray(iq, dtype=complex)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} 必须为一维复数/实数样本序列，无法解析: {iq!r}") from exc
    if arr.ndim != 1:
        raise ValueError(f"{key} 必须为一维样本序列，实际维度为 {arr.ndim}")
    if arr.size == 0:
        raise ValueError(f"{key} 不允许空序列（空 IQ 无频谱可言）")
    if not bool(np.isfinite(arr).all()):
        raise ValueError(f"{key} 含 NaN/±inf 样本（域拒绝）")
    return arr


class SimMixer13G:
    """13GHz 混频扩展仿真后端实例（注册名 sim_mixer_13g）：LO 自持 + 频谱搬移链演示。

    仿真口径（与 capabilities() 键一一对应，文档即规约）:
      - LO 自持: ``lo_freq_hz`` 缺省 12.85 GHz（配 IF 150MHz → RF 恰 13GHz，2.4G 链
        →13G RF 演示口径）、``lo_power_dbm`` 缺省 +7 dBm、镜像抑制比缺省 60 dB
        （腔体滤波等效模型）；三者经工厂/构造器参数化，LO 相噪 −100 dBc/Hz
        （R40 C8 指标）为模型固定口径，不经参数化——upconvert/chain_demo 逐次透传；
      - 频谱搬移链: ``upconvert`` 组装 IF+LO 调叶子 ``upconvert_with_image_rejection``
        （公式(2) f_RF=f_LO+f_IF、镜像按抑制比残留、二次杂散口径均在叶子——本模块
        不复算），并在叶子结果上附 RF 域标注 ``rf_domain_note``: RF 越过 20 GHz
        仿真域不拒收，标注 ``'beyond_model'``（恰在端点仍 ``'in_model'``）；
      - IQ 搬移演示: ``shift_iq`` 基带 IQ × exp(j·2π·f_IF·t)（fs 参数化，缺省 10 MHz）
        ——频谱整体上移的可视化演示；f_IF/fs 超过 1 按数字混频自然折叠（mod 1），
        不做拒收（环绕即演示语义）；
      - 串接演示: ``chain_demo`` 一步给出 IF 设置→LO 混频→RF 结果摘要三步
        （R41「串接 sim 信号源/分析仪演示 13GHz 全链」的组件侧口径）；
      - 无发射能力: ``stop_tx``/``set_tx_gain`` 记录事件返回 ``{'status': 'no_tx'}``
        （鸭子兼容，不抛——同 analyzer 先例）；``start_tx`` 调用即 BackendError。
    """

    def __init__(
        self,
        lo_freq_hz: float = _LO_DEFAULT_HZ,
        lo_power_dbm: float = _LO_POWER_DEFAULT_DBM,
        rejection_db: float = _REJECTION_DEFAULT_DB,
    ) -> None:
        self._lo_freq_hz = _check_positive("lo_freq_hz", _as_real("lo_freq_hz", lo_freq_hz))
        self._lo_power_dbm = _as_real("lo_power_dbm", lo_power_dbm)
        self._rejection_db = _check_non_negative(
            "rejection_db", _as_real("rejection_db", rejection_db)
        )
        self._phase_noise_dbc_hz = _PHASE_NOISE_DBC_HZ
        self.events: list[str] = []  # no_tx 调用记录（同 analyzer 先例）

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<SimMixer13G lo_freq_hz={self._lo_freq_hz!r} "
            f"lo_power_dbm={self._lo_power_dbm!r} rejection_db={self._rejection_db!r}>"
        )

    # ---- 只读配置面 ----

    @property
    def lo_freq_hz(self) -> float:
        """LO 频率 Hz（构造时定值；本后端无运行中调谐面）。"""
        return self._lo_freq_hz

    @property
    def lo_power_dbm(self) -> float:
        """LO 驱动功率 dBm（口径记录）。"""
        return self._lo_power_dbm

    @property
    def rejection_db(self) -> float:
        """镜像抑制比 dB。"""
        return self._rejection_db

    @property
    def phase_noise_dbc_hz(self) -> float:
        """LO 相噪口径 dBc/Hz（模型固定 −100，R40 C8 指标）。"""
        return self._phase_noise_dbc_hz

    # ---- ① 频谱搬移链 ----

    def upconvert(self, if_freq_hz: float, if_power_dbm: float) -> dict:
        """执行一次上变频频谱搬移（LO 自持）：IF+LO→叶子纯计算 + RF 域标注。

        输入: if_freq_hz IF 频率 Hz（正有限实数）；if_power_dbm IF 功率 dBm（任意
          有限实数）——域校验全部由叶子 ``upconvert_with_image_rejection`` 单源执行
          （bool/非数值/NaN/±inf/频率 ≤0 → ValueError），本方法不做前置复检。
        输出: 叶子结果 7 键（rf_freq_hz/rf_power_dbm/image_freq_hz/image_power_dbm/
          image_rejection_db/phase_noise_note/spurious——公式(2) f_RF=f_LO+f_IF、
          镜像 f_LO−f_IF 按抑制比残留等口径详见叶子 docstring）+ 2 个本层标注键:
          ``rf_domain_note``（'in_model' | 'beyond_model'：RF 越过 20 GHz 仿真域
          不拒收、标注 'beyond_model'，恰在端点仍 'in_model'）与 ``simulated``: True。
        错误: IF 参数域错 → ValueError（叶子抛出，原样透传）。
        """
        result = upconvert_with_image_rejection(
            {"if_freq_hz": if_freq_hz, "if_power_dbm": if_power_dbm},
            {
                "lo_freq_hz": self._lo_freq_hz,
                "lo_power_dbm": self._lo_power_dbm,
                "phase_noise_dbc_hz": self._phase_noise_dbc_hz,
            },
            rejection_db=self._rejection_db,
        )
        note = _NOTE_BEYOND_MODEL if result["rf_freq_hz"] > _RF_MAX_HZ else _NOTE_IN_MODEL
        return {**result, "rf_domain_note": note, "simulated": True}

    # ---- ② IQ 搬移演示 ----

    def shift_iq(self, iq, if_freq_hz: float, fs_hz: float = _FS_DEFAULT_HZ) -> dict:
        """IQ 频谱整体上移演示：基带 IQ × exp(j·2π·f_IF·t)（数字上变频可视化）。

        输入: iq 一维复/实样本序列（list/tuple/ndarray；None/非数值/2 维及以上/
          空序列/含 NaN 或 ±inf → ValueError，bool 标量同被 complex 化前拒于非序列/
          非数值路径）；if_freq_hz 搬移频率 Hz（正有限实数，≤0/bool/NaN → ValueError；
          f_IF/fs 超过 1 按数字混频自然折叠 mod 1——环绕不拒收，即演示语义）；
          fs_hz 采样率 Hz（正有限实数，缺省 10e6）。
        输出: {'iq': 上移后复样本 ndarray（新数组，不改入参；幅度不变、相位按
          2π·(f_IF/fs)·n 旋转）, 'fs_hz', 'if_freq_hz', 'n_samples', 'simulated': True}。
        错误: 上述任一域错 → ValueError。
        """
        samples = _iq_1d_finite("iq", iq)
        f_if = _check_positive("if_freq_hz", _as_real("if_freq_hz", if_freq_hz))
        fs = _check_positive("fs_hz", _as_real("fs_hz", fs_hz))
        # t = n/fs：数字混频只依赖归一频率 f_IF/fs，n 取样本序号即可（与连续时间等价）
        n = np.arange(samples.size, dtype=float)
        shifted = samples * np.exp(2j * math.pi * (f_if / fs) * n)
        return {
            "iq": shifted,
            "fs_hz": fs,
            "if_freq_hz": f_if,
            "n_samples": int(samples.size),
            "simulated": True,
        }

    # ---- ③ 串接演示 ----

    def chain_demo(self) -> dict:
        """13GHz 全链一步演示（R41「串接 sim 信号源/分析仪演示 13GHz 全链」）。

        用缺省演示 IF（150 MHz @ −10 dBm——2.4G 链中频口径）+ 实例 LO（缺省 12.85 GHz
        时 RF 恰 13.0 GHz）走完整 upconvert 链，汇总为三步。

        输出（键集固定 4 键）: {'steps': [IF 设置 → LO 混频 → RF 结果摘要] 三步 dict
          （step 依次 'if_setup'/'lo_mix'/'rf_summary'，末步含 rf_freq_hz/rf_power_dbm/
          image_freq_hz/rf_domain_note）, 'rf_freq_hz', 'image_freq_hz',
          'phase_noise_dbc_hz': −100.0（LO 相噪口径透传）}。
        """
        if_freq_hz, if_power_dbm = _DEMO_IF_HZ, _DEMO_IF_POWER_DBM
        result = self.upconvert(if_freq_hz, if_power_dbm)
        steps = [
            {
                "step": "if_setup",
                "if_freq_hz": if_freq_hz,
                "if_power_dbm": if_power_dbm,
            },
            {
                "step": "lo_mix",
                "lo_freq_hz": self._lo_freq_hz,
                "lo_power_dbm": self._lo_power_dbm,
                "phase_noise_dbc_hz": self._phase_noise_dbc_hz,
                "image_rejection_db": self._rejection_db,
            },
            {
                "step": "rf_summary",
                "rf_freq_hz": result["rf_freq_hz"],
                "rf_power_dbm": result["rf_power_dbm"],
                "image_freq_hz": result["image_freq_hz"],
                "rf_domain_note": result["rf_domain_note"],
            },
        ]
        return {
            "steps": steps,
            "rf_freq_hz": result["rf_freq_hz"],
            "image_freq_hz": result["image_freq_hz"],
            "phase_noise_dbc_hz": self._phase_noise_dbc_hz,
        }

    # ---- ④ 能力口径 ----

    def capabilities(self) -> dict:
        """能力元数据（每次返回新 dict，调用方篡改不回写实例与注册表）。"""
        return {
            "rf_max_hz": _RF_MAX_HZ,
            "lo_default_hz": _LO_DEFAULT_HZ,
            "phase_noise_dbc_hz": _PHASE_NOISE_DBC_HZ,
            "image_rejection_db_default": _REJECTION_DEFAULT_DB,
            "simulated": True,
        }

    # ---- ⑤ 统一后端鸭子接口（组件级：无 TX/RX 通道）----

    def stop_tx(self, *args, **kwargs) -> dict:
        """无发射能力：记录事件并返回 {'status': 'no_tx'}（鸭子兼容，不抛——同 analyzer 先例）。"""
        self.events.append(_NO_TX_EVENT)
        return {"status": "no_tx"}

    def set_tx_gain(self, *args, **kwargs) -> dict:
        """无发射能力：记录事件并返回 {'status': 'no_tx'}（鸭子兼容，不抛——同 analyzer 先例）。"""
        self.events.append(_NO_TX_EVENT)
        return {"status": "no_tx"}

    def start_tx(self, *args, **kwargs) -> dict:
        """sim_mixer_13g 无 TX 通道：任何发射请求调用即明确报错，绝不静默假装成功。"""
        raise BackendError(_NO_TX_MESSAGE)


def open_sim_mixer(params: dict | None = None) -> SimMixer13G:
    """创建 13GHz 混频扩展仿真后端实例（注册名 sim_mixer_13g）。

    输入: params: dict | None，键均可缺省——
      - lo_freq_hz: LO 频率 Hz（默认 12.85e9——配 IF 150MHz → RF 恰 13GHz 演示链；
        正有限实数，≤0/bool/NaN → ValueError）；
      - lo_power_dbm: LO 驱动功率 dBm（默认 +7.0；有限实数，bool/NaN → ValueError）；
      - rejection_db: 镜像抑制比 dB（默认 60.0；非负有限实数，负值/bool/NaN →
        ValueError；0 合法——镜像全残留）。
      LO 相噪 −100 dBc/Hz（R40 C8 指标）为模型固定口径，不经本工厂参数化。
    输出: SimMixer13G 实例（LO 自持配置定值，事件记录空）。
    错误: params 非 dict 且非 None / 数值键非实数/为布尔/非有限 / lo_freq_hz ≤ 0 /
      rejection_db < 0 → ValueError（校验先于实例构造，失败不产生半初始化对象）。
    """
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError(
            f"params 必须为 dict | None，实际为 {type(params).__name__}: {params!r}"
        )
    lo_freq_hz = _check_positive(
        "lo_freq_hz", _as_real("lo_freq_hz", params.get("lo_freq_hz", _LO_DEFAULT_HZ))
    )
    lo_power_dbm = _as_real(
        "lo_power_dbm", params.get("lo_power_dbm", _LO_POWER_DEFAULT_DBM)
    )
    rejection_db = _check_non_negative(
        "rejection_db", _as_real("rejection_db", params.get("rejection_db", _REJECTION_DEFAULT_DB))
    )
    return SimMixer13G(
        lo_freq_hz=lo_freq_hz, lo_power_dbm=lo_power_dbm, rejection_db=rejection_db
    )


# import 时自注册（override=True：重复 import / importlib.reload 幂等不炸；组件级
# 插件 caps tx/rx 均假 → 无契约方法要求；method_names=None 延迟——注册期跳过检查）。
register_backend(
    _BACKEND_NAME,
    open_sim_mixer,
    {
        "kind": _BACKEND_NAME,
        "caps": {"tx": False, "rx": False, "freq_range_mhz": (1, 20000)},
    },
    override=True,
    method_names=None,
)
