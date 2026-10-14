"""仪表模拟演示面板：五台远期仪表 sim（open_sim_* 工厂）打开/读数演示/关闭状态机
+VISA 槽位状态；超模型域如实标注——重写规约与签名意图详见 fn_docs/responsibility.md
（R69 demo_instrument_panels L0；调用方 mount_console_extensions）。

落地口径（R69）：

- 五台仪表（canonical 键 → open_sim_* 工厂）：siggen_1433d（1433D 信号源）/
  analyzer_rsa513a（RSA513A 频谱仪）/ mixer_13g（13GHz 混频扩展）/
  emi_receiver（EMI 接收机）/ attenuator（程控衰减器）；别名表收编短名
  （1433d/rsa513a/mixer/emi 等，strip().lower() 归一）；
- 面板状态机：open（工厂 params 建实例入会话表）→ read/read-demo（仿真读数：
  可选 params 先配置再读——读数超模型域按 R39–R43 口径裁剪到最近域边界并
  warnings 标注，不拒）→ close（出会话表）；未打开先读/未打开先关 →
  IllegalStateError（ValueError 子类）；重复 open 替换会话（reopened=True）；
- 会话表：模块级 ``_SESSIONS`` dict（进程内——演示态单进程口径，重启即清）；
- VISA 槽位状态（list_instrument_panels）：manage_backend_registry('lookup')
  查注册名在位性+meta、create_visa_driver.MODELS 查命令映射（builtin/generic）、
  pyvisa import 探测真仪表接入层可用性——全部如实回显，不虚构连接；
- 超模型域如实标注：读数恒带 simulated=True 与诚实基注（模拟后端读数非实测；
  mixer 的 RF 越过 20GHz 仿真域按其自带 rf_domain_note='beyond_model' 透传）。
"""
from datetime import datetime, timezone

from src.create_visa_driver.create_visa_driver import MODELS as _VISA_MODELS
from src.manage_backend_registry.manage_backend_registry import (
    BackendError as _BackendError,
)
from src.manage_backend_registry.manage_backend_registry import (
    manage_backend_registry as _registry,
)
from src.open_sim_analyzer.open_sim_analyzer import open_sim_analyzer
from src.open_sim_attenuator.open_sim_attenuator import open_sim_attenuator
from src.open_sim_emi_receiver.open_sim_emi_receiver import open_sim_emi_receiver
from src.open_sim_mixer.open_sim_mixer import open_sim_mixer
from src.open_sim_siggen.open_sim_siggen import open_sim_siggen

__all__ = [
    "INSTRUMENTS",
    "IllegalStateError",
    "demo_instrument_panels",
    "list_instrument_panels",
]


class IllegalStateError(ValueError):
    """面板状态机非法状态：未打开先读 / 未打开先关（演示态状态错）。"""


#: 五台仪表在册清单（canonical 键序即面板渲染序）。
INSTRUMENTS = (
    "siggen_1433d",
    "analyzer_rsa513a",
    "mixer_13g",
    "emi_receiver",
    "attenuator",
)

#: 短名/别名 → canonical（strip().lower() 归一后查）。
_ALIASES = {
    "1433d": "siggen_1433d",
    "siggen": "siggen_1433d",
    "rsa513a": "analyzer_rsa513a",
    "analyzer": "analyzer_rsa513a",
    "mixer": "mixer_13g",
    "13g": "mixer_13g",
    "emi": "emi_receiver",
    "att": "attenuator",
}

#: canonical → {label, registry(注册名), factory(open_sim_* 工厂), visa_model(
#: create_visa_driver.MODELS 键；None=generic 回落)}。
_SPECS = {
    "siggen_1433d": {
        "label": "1433D 信号源（1MHz–20GHz）",
        "registry": "sim_siggen_1433d",
        "factory": open_sim_siggen,
        "visa_model": "1433d",
    },
    "analyzer_rsa513a": {
        "label": "RSA513A 频谱仪（实时谱 DPX）",
        "registry": "sim_rsa513a",
        "factory": open_sim_analyzer,
        "visa_model": None,
    },
    "mixer_13g": {
        "label": "13GHz 混频扩展（LO+IF→RF）",
        "registry": "sim_mixer_13g",
        "factory": open_sim_mixer,
        "visa_model": None,
    },
    "emi_receiver": {
        "label": "EMI 接收机（CISPR 口径读数）",
        "registry": "sim_emi_receiver",
        "factory": open_sim_emi_receiver,
        "visa_model": "emi_receiver",
    },
    "attenuator": {
        "label": "程控衰减器（0–75dB，0.25dB 步进）",
        "registry": "sim_attenuator",
        "factory": open_sim_attenuator,
        "visa_model": None,
    },
}

#: 在册动作（read-demo 为网页口径，read 为 API 短名，read_demo 容错下划线）。
_ACTIONS = ("open", "read", "read-demo", "read_demo", "close")

#: 面板诚实基注（超模型域/模拟口径——R39–R43 家族口径）。
_SIM_NOTE = (
    "仪表面板为模拟后端（open_sim_* 工厂）仿真读数，simulated=True——非真仪表"
    "实测；读数请求超模型域时按 R39–R43 口径裁剪到最近域边界并标注，不拒"
)

#: pyvisa 缺失时的真仪表接入层提示（create_visa_driver 同源口径）。
_PYVISA_HINT = (
    "pyvisa 不可用：真仪表接入层（create_visa_driver）需 'pip install pyvisa"
    " pyvisa-py'，或注入鸭子仪器会话（session=…）"
)

#: 面板会话表（模块级，进程内——canonical 键 → {'instance','opened_at'}）。
_SESSIONS: dict = {}


def _now_iso() -> str:
    """UTC ISO 时间戳（会话表 opened_at 口径）。"""
    return datetime.now(timezone.utc).isoformat()


def _canonical(instrument: object) -> str:
    """仪表名归一：strip().lower() → 别名表 → canonical 键；未知 → ValueError。"""
    if not isinstance(instrument, str):
        raise ValueError(
            f"instrument 必须为 str（仪表名，别名收编短名），实际 "
            f"{type(instrument).__name__}: {instrument!r}"
        )
    key = instrument.strip().lower()
    canonical = key if key in _SPECS else _ALIASES.get(key)
    if canonical is None:
        raise ValueError(
            f"未在册仪表 {instrument!r}（五台远期仪表: {list(INSTRUMENTS)}，"
            f"短名别名: {sorted(_ALIASES)}）"
        )
    return canonical


def _normalize_action(action: object) -> str:
    """动作归一：read-demo/read_demo → 'read'；未知/非 str → ValueError。"""
    if not isinstance(action, str):
        raise ValueError(
            f"action 必须为 str（open/read-demo/close），实际 "
            f"{type(action).__name__}: {action!r}"
        )
    key = action.strip().lower()
    if key not in _ACTIONS:
        raise ValueError(
            f"未知面板动作 {action!r}（在册: ['open', 'read-demo', 'close']）"
        )
    return "read" if key in ("read-demo", "read_demo", "read") else key


def _registry_meta(registry_name: str):
    """注册表查询（manage_backend_registry lookup）→ meta dict | None（不在位如实）。"""
    try:
        return _registry("lookup", registry_name).get("meta")
    except _BackendError:
        return None


def _clip(warnings: list, key: str, value: object, lo: float, hi: float) -> float:
    """数值参数裁剪：非有限/bool → ValueError（形状错）；越域 → 最近边界+标注不拒。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"params[{key!r}] 必须为实数（bool/非数值拒），实际 {value!r}"
        )
    val = float(value)
    if val != val or val in (float("inf"), float("-inf")):
        raise ValueError(f"params[{key!r}] 必须为有限数，实际 {value!r}")
    if lo <= val <= hi:
        return val
    clipped = min(max(val, lo), hi)
    warnings.append(
        f"params[{key!r}] {val!r} 超出仿真域 [{lo!r}, {hi!r}]，已裁剪至 {clipped!r}"
        "（R69 超模型域口径：读数带标注不拒）"
    )
    return clipped


def _require_session(canonical: str) -> object:
    """会话表取实例：未打开 → IllegalStateError（未打开先读/先关，非法状态拒）。"""
    session = _SESSIONS.get(canonical)
    if session is None:
        raise IllegalStateError(
            f"面板未打开，先 POST open 再执行本动作（instrument={canonical!r}，"
            f"会话表在册: {sorted(_SESSIONS)}）"
        )
    return session["instance"]


def _read_siggen(instance, params: dict) -> dict:
    """1433D 读数演示：可选 freq_hz/power_dbm 配置（超域裁剪标注）→ 回读口径。"""
    warnings: list = []
    caps = instance.capabilities()
    freq_lo, freq_hi = caps["freq_range_hz"]
    power_lo, power_hi = caps["power_range_dbm"]
    if params.get("freq_hz") is not None:
        instance.set_freq(
            _clip(warnings, "freq_hz", params["freq_hz"], freq_lo, freq_hi)
        )
    if params.get("power_dbm") is not None:
        instance.set_power(
            _clip(warnings, "power_dbm", params["power_dbm"], power_lo, power_hi)
        )
    return {
        "readings": {
            "freq_hz_set": instance.freq_hz,
            "freq_hz_readback": instance.get_freq(),
            "power": instance.get_power(),
            "output": instance.output,
            "phase_noise_dbc_hz_10k": instance.get_phase_noise(),
            "last_scpi": instance.last_scpi,
        },
        "warnings": warnings,
        "readback_note": "频率回读=1.000001×设定（+1ppm 仿真偏差）；功率回读=0.5dB 量化生效值",
    }


def _read_analyzer(instance, params: dict) -> dict:
    """RSA513A 读数演示：可选 center_hz/span_hz 配置（超域裁剪标注）→ measure 谱。"""
    warnings: list = []
    caps = instance.capabilities()
    if params.get("center_hz") is not None:
        instance.set_center(
            _clip(
                warnings,
                "center_hz",
                params["center_hz"],
                1e6,
                caps["max_freq_hz"],
            )
        )
    if params.get("span_hz") is not None:
        span_lo, span_hi = caps["span_range_hz"]
        instance.set_span(
            _clip(warnings, "span_hz", params["span_hz"], span_lo, span_hi)
        )
    spectrum = instance.measure(None)  # None=内置自校准测试音路径
    return {
        "readings": {
            "center_hz": instance.center_hz,
            "span_hz": instance.span_hz,
            "rbw_hz": instance.rbw_hz,
            "n_bins": len(spectrum["freqs"]),
            "peak_power_db": max(spectrum["power_db"]),
            "uncertainty_db": spectrum["uncertainty_db"],
            "trace_mode": spectrum["trace_mode"],
            "freqs": spectrum["freqs"],
            "power_db": spectrum["power_db"],
        },
        "warnings": warnings,
        "readback_note": "measure(None)=内置自校准测试音路径（单音 −30 dBm @ center，确定性仿真）",
    }


def _read_mixer(instance, params: dict) -> dict:
    """13GHz 混频读数演示：params 给 if_freq_hz → upconvert（RF 越域自带
    rf_domain_note='beyond_model' 标注——混频超模型域即此口径）；缺省 chain_demo
    全链三步演示；IF 参数域错（≤0/bool 等）由叶子 ValueError 透传。"""
    warnings: list = []
    if params.get("if_freq_hz") is not None or params.get("if_power_dbm") is not None:
        outcome = instance.upconvert(
            params.get("if_freq_hz", 150e6),
            params.get("if_power_dbm", -10.0),
        )
        if outcome.get("rf_domain_note") == "beyond_model":
            warnings.append(
                f"RF {outcome.get('rf_freq_hz')!r} Hz 越过混频仿真域 20GHz——"
                "后端自带 rf_domain_note='beyond_model'（超模型域如实标注，不拒）"
            )
        return {
            "readings": outcome,
            "warnings": warnings,
            "readback_note": "upconvert：IF+LO→RF 公式(2) 口径（镜像按抑制比残留）",
        }
    outcome = instance.chain_demo()
    rf_note = "in_model"
    for step in outcome.get("steps", []):
        if step.get("step") == "rf_summary":
            rf_note = step.get("rf_domain_note", rf_note)
    return {
        "readings": outcome,
        "warnings": warnings,
        "readback_note": (
            f"chain_demo 全链三步演示（缺省 IF 150MHz @ −10dBm）——RF 域标注 {rf_note!r}"
        ),
    }


def _read_emi(instance, params: dict) -> dict:
    """EMI 接收机读数演示：可选 freq_hz/detector/rbw_hz 配置（freq 超域裁剪标注）
    → measure(None) 底噪口径读数。"""
    warnings: list = []
    caps = instance.capabilities()
    freq_lo, freq_hi = caps["freq_range_hz"]
    if params.get("freq_hz") is not None:
        instance.freq_hz = _clip(
            warnings, "freq_hz", params["freq_hz"], freq_lo, freq_hi
        )
    if params.get("detector") is not None:
        instance.set_detector(params["detector"])  # 域错 ValueError 原样透传
    if params.get("rbw_hz") is not None:
        instance.set_rbw(params["rbw_hz"])
    reading = instance.measure(None)  # 底噪口径读数
    return {
        "readings": reading,
        "warnings": warnings,
        "readback_note": "measure(None)=底噪口径（−150 dBm/Hz + 10·log10(rbw)，CISPR 仿真）",
    }


def _read_attenuator(instance, params: dict) -> dict:
    """程控衰减器读数演示：可选 attenuation_db 配置（超域裁剪标注）→ 档位回读。"""
    warnings: list = []
    caps = instance.capabilities()
    att_lo, att_hi = caps["attenuation_range_db"]
    record = None
    if params.get("attenuation_db") is not None:
        record = instance.set_attenuation(
            _clip(warnings, "attenuation_db", params["attenuation_db"], att_lo, att_hi)
        )
    return {
        "readings": {
            "attenuation_db": instance.get_attenuation(),
            "switch": record,
            "switches_logged": len(instance.switch_log),
            "nominal_switch_ns": caps["nominal_switch_ns"],
        },
        "warnings": warnings,
        "readback_note": "档位=0.25dB 网格量化生效值（half-up）；switch 缺省 None=未下发只读",
    }


#: canonical → 读数演示器（params dict → 读数视图 dict）。
_READERS = {
    "siggen_1433d": _read_siggen,
    "analyzer_rsa513a": _read_analyzer,
    "mixer_13g": _read_mixer,
    "emi_receiver": _read_emi,
    "attenuator": _read_attenuator,
}


def demo_instrument_panels(instrument: str, action: str, params: dict | None = None) -> dict:
    """仪表模拟演示面板：五台远期仪表 sim 打开/读数演示/关闭状态机（详见
    fn_docs/responsibility.md 功能块）。

    输入:
        instrument: 仪表名（canonical 或短名别名——siggen_1433d/1433d、
            analyzer_rsa513a/rsa513a、mixer_13g/mixer、emi_receiver/emi、
            attenuator/att；大小写不敏感，未知 → ValueError）。
        action: 'open'（工厂 params 建实例入会话表——重复 open 替换）| 'read'
            /'read-demo'（仿真读数，可选 params 先配置——超模型域裁剪+标注不拒）
            | 'close'（出会话表）；未知 → ValueError。
        params: 动作参数 dict|None——open：透传 open_sim_* 工厂（如 freq_hz/
            attenuation_db/lo_freq_hz 等，域错 ValueError 透传）；read：各仪表
            可选配置键（siggen: freq_hz/power_dbm；analyzer: center_hz/span_hz；
            mixer: if_freq_hz/if_power_dbm；emi: freq_hz/detector/rbw_hz；
            attenuator: attenuation_db——越域裁剪标注，形状错 ValueError）。

    输出:
        面板视图 dict：{'instrument': canonical, 'label', 'action': 归一动作,
        'state': 'open'|'closed', 'simulated': True, 'note': 诚实基注}——open 另附
        {'capabilities', 'registry': {'name','registered'}, 'reopened', 'opened_at'}；
        read 另附 {'readings', 'warnings', 'readback_note'}；close 另附
        {'closed_at'}。

    错误:
        ValueError: 仪表名/动作/params 形状错，工厂或配置域错（透传）。
        IllegalStateError（ValueError 子类）: 未打开先读 / 未打开先关——
            面板状态机非法状态拒。
    """
    canonical = _canonical(instrument)
    act = _normalize_action(action)
    if params is not None and not isinstance(params, dict):
        raise ValueError(
            f"params 必须为 dict | None（面板动作参数），实际 "
            f"{type(params).__name__}: {params!r}"
        )
    spec = _SPECS[canonical]

    if act == "open":
        instance = spec["factory"](params)  # 域错 ValueError 原样透传
        reopened = canonical in _SESSIONS
        _SESSIONS[canonical] = {"instance": instance, "opened_at": _now_iso()}
        registry_name = spec["registry"]
        return {
            "instrument": canonical,
            "label": spec["label"],
            "action": "open",
            "state": "open",
            "reopened": reopened,
            "opened_at": _SESSIONS[canonical]["opened_at"],
            "capabilities": instance.capabilities(),
            "registry": {
                "name": registry_name,
                "registered": _registry_meta(registry_name) is not None,
            },
            "simulated": True,
            "note": _SIM_NOTE,
        }

    if act == "close":
        _require_session(canonical)  # 未打开先关 → IllegalStateError
        _SESSIONS.pop(canonical, None)
        return {
            "instrument": canonical,
            "label": spec["label"],
            "action": "close",
            "state": "closed",
            "closed_at": _now_iso(),
            "simulated": True,
            "note": _SIM_NOTE,
        }

    # read / read-demo：会话表实例 + 各仪表读数演示器
    instance = _require_session(canonical)
    view = _READERS[canonical](instance, params if params is not None else {})
    return {
        "instrument": canonical,
        "label": spec["label"],
        "action": "read",
        "state": "open",
        "simulated": True,
        "note": _SIM_NOTE,
        **view,
    }


def list_instrument_panels() -> dict:
    """五仪表面板状态+VISA 槽位状态总览（GET /api/instruments 口径，只读）。

    输出:
        {'instruments': [五台面板行（canonical/label/state（open|closed）/
        registry 在位性/caps（open 时附实例 capabilities，否则 None））],
        'visa': {'pyvisa_available': bool, 'install_hint': str, 'slots': [五台
        槽位行（model 命令映射 builtin/generic + 真仪表接入说明）]},
        'simulated': True, 'note': 诚实基注}——一切如实回显，不虚构连接。
    """
    try:
        import pyvisa  # noqa: F401 - 探测真仪表接入层可用性（不建会话）

        pyvisa_available = True
    except ImportError:
        pyvisa_available = False
    rows = []
    slots = []
    for canonical in INSTRUMENTS:
        spec = _SPECS[canonical]
        session = _SESSIONS.get(canonical)
        registry_name = spec["registry"]
        rows.append(
            {
                "instrument": canonical,
                "label": spec["label"],
                "state": "open" if session is not None else "closed",
                "opened_at": session["opened_at"] if session else None,
                "registry": {
                    "name": registry_name,
                    "registered": _registry_meta(registry_name) is not None,
                },
                "capabilities": (
                    session["instance"].capabilities() if session else None
                ),
                "simulated": True,
            }
        )
        model_key = spec["visa_model"]
        slots.append(
            {
                "instrument": canonical,
                "model": model_key if model_key is not None else "generic",
                "command_map": "builtin" if model_key in _VISA_MODELS else "generic",
                "visa_driver": (
                    f"create_visa_driver(resource, {model_key!r})"
                    if model_key is not None
                    else "create_visa_driver(resource, 'generic')（未知型号回退）"
                ),
            }
        )
    return {
        "instruments": rows,
        "visa": {
            "pyvisa_available": pyvisa_available,
            "install_hint": _PYVISA_HINT,
            "slots": slots,
        },
        "simulated": True,
        "note": _SIM_NOTE,
    }
