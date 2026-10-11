"""单次 SCPI 交互：发送/应答/超时重试/类型化解析——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import time

__all__ = ["DriverError", "exchange_scpi"]

#: 重试指数退避基数（秒）：第 n 次重试（n 从 0 起）先睡 0.05 * 2**n 再重发。
_BACKOFF_BASE_S = 0.05
#: 支持的应答类型 expect 取值。
_EXPECT_KINDS = ("float", "int", "str", "bool")


class DriverError(RuntimeError):
    """SCPI 交互失败：会话读写失败 / 应答解析失败 / Timeout 类重试耗尽。

    底层异常（若有）经 ``__cause__`` 保留；消息中携带命令原文与 timeout_s 上下文。
    """


def _is_timeout_like(exc: BaseException) -> bool:
    """鸭子判定会话异常是否 Timeout 类：带 timeout 属性，或异常类名含 Timeout。"""
    return hasattr(exc, "timeout") or "Timeout" in type(exc).__name__


def _parse_answer(raw: object, expect: str) -> object:
    """把原始应答 strip 后解析为期望类型；解析失败抛 DriverError（不参与重试）。"""
    token = str(raw).strip()
    if expect == "float":
        try:
            return float(token)
        except ValueError:
            raise DriverError(f"SCPI 应答无法解析为 float: {raw!r}") from None
    if expect == "int":
        try:
            return int(token)
        except ValueError:
            raise DriverError(f"SCPI 应答无法解析为 int: {raw!r}") from None
    if expect == "bool":
        upper = token.upper()
        if upper in ("1", "ON"):
            return True
        if upper in ("0", "OFF"):
            return False
        raise DriverError(f"SCPI 应答无法解析为 bool（'1'/'ON'/'0'/'OFF'）: {raw!r}")
    return token  # expect == 'str'（缺省）：strip 后原文


def exchange_scpi(
    session,
    command: str,
    expect: str = "str",
    *,
    timeout_s: float = 2.0,
    retry: int = 0,
) -> dict:
    """单次 SCPI 交互：类型化应答 + Timeout 类指数退避重试。

    对鸭子仪器会话（``write(cmd)`` / ``read() -> str``）发送命令；仅当命令为查询
    （rstrip 后以 ``?`` 结尾）才 ``read()`` 读回应答（"可选读回应答"），设置类命令只写不读。

    超时语义：``timeout_s`` 参数化（默认 2.0s），计时用 ``time.monotonic``，由会话自身
    阻塞语义模拟——本函数不做真实超时打断，只把会话抛出的异常分类：
    - Timeout 类（鸭子判定：异常带 ``timeout`` 属性，或类名含 ``Timeout``）→ 重试整个
      write+read，指数退避 ``0.05 * 2**n`` 秒，至多 retry 次；耗尽抛 DriverError
      （``__cause__``=最后一次异常）。
    - 非 Timeout 异常 → 立即抛 DriverError（``__cause__``=底层异常），不重试。

    Args:
        session: 鸭子仪器会话，需提供 ``write(cmd)`` 与 ``read()``。
        command: SCPI 命令（查询以 ``?`` 结尾）；非 str 或空白 → ValueError。
        expect: 应答类型 ``'float'``/``'int'``/``'str'``（缺省）/``'bool'``；
            未知取值 → ValueError。bool 映射：``'1'/'ON'``→True，``'0'/'OFF'``→False。
        timeout_s: 预算超时秒数（参数化记录，不做真实打断）。
        retry: Timeout 类失败后的额外重试次数（0=不重试）；非负 int（bool 拒收），
            否则 → ValueError。

    Returns:
        ``{'raw': read 原文（未 strip）, 'value': 类型化值, 'elapsed_ms': int 毫秒}``；
        非查询命令 raw/value 为 ``''``。查询命令空应答（read 回空串/纯空白）且
        expect='str' 时附 ``'empty_response': True`` 标注（value 仍为 ``''``）。

    Raises:
        ValueError: command 非 str/为空，expect 未知，或 retry 非非负 int。
        DriverError: 会话读写失败、read() 返回 None（仪器无应答）、应答解析失败、
            Timeout 重试耗尽（含 __cause__）。
    """
    if not isinstance(command, str) or not command.strip():
        raise ValueError(
            f"command 必须为非空 str，收到 {type(command).__name__}: {command!r}"
        )
    if expect not in _EXPECT_KINDS:
        raise ValueError(f"expect 须为 {'/'.join(_EXPECT_KINDS)} 之一，收到 {expect!r}")
    if isinstance(retry, bool) or not isinstance(retry, int) or retry < 0:
        raise ValueError(f"retry 须为非负 int（bool 拒收），收到 {retry!r}")

    needs_read = command.rstrip().endswith("?")
    started = time.monotonic()
    last_exc: Exception | None = None
    for attempt in range(retry + 1):
        if attempt:
            time.sleep(_BACKOFF_BASE_S * 2 ** (attempt - 1))
        try:
            session.write(command)
            raw = session.read() if needs_read else ""
        except Exception as exc:  # 会话鸭子异常统一分类：仅 Timeout 类进入重试
            if not _is_timeout_like(exc):
                raise DriverError(
                    f"SCPI 会话交互失败 (command={command!r}, timeout_s={timeout_s}): {exc!r}"
                ) from exc
            last_exc = exc
            continue
        if needs_read and raw is None:
            # read() 无应答（部分会话超时/断链以 None 而非异常表达）——定性失败，不参与重试。
            raise DriverError(f"仪器无应答 (command={command!r})：read() 返回 None")
        elapsed_ms = int((time.monotonic() - started) * 1000)
        # 解析失败即 DriverError 直接上抛，不占用重试名额（重试仅针对 Timeout 类会话异常）。
        result = {"raw": raw, "value": _parse_answer(raw, expect), "elapsed_ms": elapsed_ms}
        if needs_read and expect == "str" and result["value"] == "":
            # 空应答标注：'str' 缺省口径回 ''，调用方可据 empty_response 区分"仪表确认但无内容"
            result["empty_response"] = True
        return result
    raise DriverError(
        f"SCPI 交互 Timeout 重试耗尽 (command={command!r}, retry={retry}, "
        f"timeout_s={timeout_s}): {last_exc!r}"
    ) from last_exc
