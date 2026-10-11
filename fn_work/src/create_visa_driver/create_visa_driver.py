"""PyVISA SCPI 仪表驱动槽位（远期真仪表接入层）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import logging

from .exchange_scpi import DriverError, exchange_scpi

__all__ = ["MODELS", "VisaDriver", "create_visa_driver"]

_LOGGER = logging.getLogger(__name__)

#: pyvisa 缺失且未注入会话时，随 DriverError 给出的安装/绕行提示。
_PYVISA_INSTALL_HINT = (
    "pyvisa 不可用：请安装 'pip install pyvisa pyvisa-py'，"
    "或在 create_visa_driver(..., session=...) 注入鸭子仪器会话（write/read）"
)

#: 内置型号→SCPI 命令映射注册表：命令键→命令模板（str.format(**args) 展开参数）。
#: registry visa 槽与 open_sim_* 远期后端按型号复用同一张表（真仪表/sim 仪表同槽可换）。
MODELS = {
    "1433d": {
        "set_freq": "FREQ {mhz} MHz",
        "set_power": "POW {dbm} dBm",
        "output_on": "OUTP ON",
        "output_off": "OUTP OFF",
        "query_id": "*IDN?",
    },
    "emi_receiver": {
        "set_freq": "FREQ {mhz} MHz",
        "query_level": "MEAS:LEV {mhz} MHz?",  # 查询模板须以 '?' 结尾（exchange_scpi 读回契约）
    },
    "generic": {
        "query_id": "*IDN?",
        "set_freq": "FREQ {mhz} MHz",
    },
}


class VisaDriver:
    """统一 SCPI 仪表驱动：命令键→模板格式化→exchange_scpi；raw_exchange 透传原句。

    真仪表（PyVISA 会话）与 sim/测试仪表（注入的鸭子会话）共用本接口，
    差异只在于底层会话来源——上层（registry visa 槽、open_sim_siggen 等）无感。
    """

    def __init__(self, session, model: str, resource: str):
        self._session = session
        self._model = model
        self._resource = resource
        self._commands = MODELS[model]
        self._closed = False

    @property
    def model(self) -> str:
        """仪表型号（MODELS 键；未知型号已回退为 'generic'）。"""
        return self._model

    @property
    def resource(self) -> str:
        """VISA 地址（或注入会话标签）。"""
        return self._resource

    def exchange(
        self,
        command_key: str,
        expect: str = "str",
        *,
        args: dict | None = None,
        timeout_s: float = 2.0,
        retry: int = 0,
    ) -> dict:
        """按命令映射模板格式化参数后经 exchange_scpi 发送。

        Args:
            command_key: MODELS[model] 中的命令键；未知键 → DriverError（列可用键）。
            expect: 应答类型，透传 exchange_scpi（'float'/'int'/'str'/'bool'）。
            args: 模板参数（如 {'mhz': 2450}）；模板缺参/格式化失败 → DriverError
                （指明缺哪个，或含模板原文与 args 键）。
            timeout_s / retry: 透传 exchange_scpi 的超时预算与 Timeout 重试次数。

        Returns:
            exchange_scpi 原样结果 ``{'raw', 'value', 'elapsed_ms'}``。
        """
        if command_key not in self._commands:
            raise DriverError(
                f"未知命令键 {command_key!r}（型号 {self._model!r} 可用命令键: "
                f"{'/'.join(sorted(self._commands))}）"
            )
        template = self._commands[command_key]
        try:
            command = template.format(**(args or {}))
        except KeyError as exc:
            raise DriverError(
                f"命令键 {command_key!r} 模板 {template!r} 缺少参数（缺 {exc}，"
                f"收到 args={args!r}）"
            ) from exc
        except (IndexError, ValueError, TypeError) as exc:
            # str.format 全类失败兜底：位置占位缺参（IndexError）/非法格式说明符
            # （ValueError）/值不支持说明符（TypeError）——统一 DriverError 含模板与 args 键。
            raise DriverError(
                f"命令键 {command_key!r} 模板 {template!r} 格式化失败"
                f"（args 键: {sorted((args or {}).keys())}）: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        return exchange_scpi(self._session, command, expect, timeout_s=timeout_s, retry=retry)

    def raw_exchange(
        self,
        cmd: str,
        expect: str = "str",
        *,
        timeout_s: float = 2.0,
        retry: int = 0,
    ) -> dict:
        """透传原句到 exchange_scpi：绕过命令映射，供调机/罕见命令使用。"""
        return exchange_scpi(self._session, cmd, expect, timeout_s=timeout_s, retry=retry)

    def close(self) -> None:
        """关闭底层会话（幂等，_closed 守卫）：会话鸭子提供 close 才调用（FakeSession/
        sim 会话可不带）。

        共享会话提示：close 作用于底层会话本身——若该会话被多个持有者共享（sim 注册表
        复用同一会话等场景），关闭可能影响其他共享者，实际关闭前记一条 warning 提示。
        """
        if self._closed:
            return None
        self._closed = True
        closer = getattr(self._session, "close", None)
        if callable(closer):
            _LOGGER.warning(
                "VisaDriver.close 关闭会话（resource=%s）：会话可能被其他持有者共享，"
                "关闭将同时影响它们",
                self._resource,
            )
            closer()
        return None


def _open_pyvisa_session(resource: str):
    """真仪表路径：延迟 import pyvisa → ResourceManager（原生后端不可用则走 PyVISA-Py）→ open_resource。

    pyvisa 不可用 → DriverError（含安装提示）；资源管理器/资源打开失败 →
    DriverError（消息含仪器原文，底层异常经 ``__cause__`` 保留）。
    """
    try:
        import pyvisa  # 延迟到调用时导入：注入会话路径完全不依赖 pyvisa 安装
    except ImportError as exc:
        raise DriverError(
            f"pyvisa 不可用（resource={resource!r}）：{_PYVISA_INSTALL_HINT}"
        ) from exc
    try:
        try:
            rm = pyvisa.ResourceManager()
        except Exception:  # 本机无 NI-VISA 等原生后端 → 显式回退 PyVISA-Py 纯 Python 后端
            rm = pyvisa.ResourceManager("@py")
        return rm.open_resource(resource)
    except Exception as exc:
        raise DriverError(f"VISA 资源打开失败 (resource={resource!r}): {exc}") from exc


def create_visa_driver(resource: str, model: str, session=None) -> VisaDriver:
    """PyVISA SCPI 仪表驱动槽位（远期真仪表接入层）。

    会话获取优先级:
      1. ``session`` 注入（鸭子 ``write(cmd)`` / ``read() -> str``，测试与 sim 仪表用）；
      2. 否则延迟 ``import pyvisa``，ResourceManager（原生后端不可用回退 PyVISA-Py）→
         ``rm.open_resource(resource)``；
      3. pyvisa 不可用 → DriverError（含 ``pip install pyvisa pyvisa-py`` 安装提示）。

    Args:
        resource: VISA 地址（真仪表路径）或注入会话标签（注入路径），非 str → ValueError。
        model: 仪表型号（MODELS 键）；未知型号 → 回退 'generic' 并 warning；
            非 str → ValueError。
        session: 可选注入仪器会话（None=走 pyvisa 路径）。

    Returns:
        VisaDriver 实例（exchange/raw_exchange/model/resource/close 统一接口）。

    Raises:
        ValueError: model 或 resource 非 str。
        DriverError: pyvisa 缺失且未注入会话（含安装提示）/ 资源打开失败（含仪器原文）。
    """
    if not isinstance(model, str):
        raise ValueError(
            f"model 必须为 str（MODELS 键），收到 {type(model).__name__}: {model!r}"
        )
    if not isinstance(resource, str):
        raise ValueError(
            f"resource 必须为 str（VISA 地址或注入会话标签），收到 "
            f"{type(resource).__name__}: {resource!r}"
        )

    resolved = model if model in MODELS else "generic"
    if resolved != model:
        _LOGGER.warning(
            "未知仪表型号 %r，回退 generic 命令映射（内置型号: %s）",
            model,
            "/".join(sorted(MODELS)),
        )

    if session is None:
        session = _open_pyvisa_session(resource)
    return VisaDriver(session, resolved, resource)
