"""场景装载总入口：读 YAML→schema 校验→红线校验（guard_compliance，不可跳）→规范化
——重写规约与签名意图详见 fn_docs/responsibility.md。

申报简化（无 yaml 库回退手写解析）：仅支持平铺「key: value」+单层嵌套子块
（含简单列表项 '- 标量' 与 '- [a, b]' 二元组）；更复杂结构（深层嵌套/内联
字典/components 分量清单等）→ScenarioError 提示安装 PyYAML。

数值口径对齐（B17 中#4）：PyYAML 1.1 不认 '1e6' 这类无点科学计数为 float
（解析为 str）——validate_scenario_schema 宽数字 str、normalize_scenario
数值化；手写回退 _fallback_scalar 则 float() 直转——两路径装载结果一致。
"""
from __future__ import annotations

import os

from src.guard_compliance.guard_compliance import guard_compliance

from .normalize_scenario import DEFAULT_POWER_DBM, normalize_scenario
from .validate_scenario_schema import ScenarioError, validate_scenario_schema

__all__ = ["load_scenario"]

try:
    import yaml as _yaml
except ImportError:  # 缺库回退手写解析（能力边界见模块 docstring）
    _yaml = None

#: 手写回退解析的能力边界提示（复杂结构须装 PyYAML）。
_YAML_INSTALL_HINT = "复杂结构须安装 PyYAML（pip install pyyaml）后重试"

#: 信封键：场景字段之外由本入口消费——bands/shielded_box/dut_scope 平铺直取，
#: declarations 为单层嵌套声明块的替代形态（两种形态取先者）。信封键不进
#: validate_scenario_schema（不在册），经 guard_compliance 红线把关后原样落位
#: 到规范化输出的顶层（下游唯一依赖的形状）。
_ENVELOPE_KEYS = frozenset({"bands", "shielded_box", "dut_scope", "declarations"})


def _fallback_scalar(text: str, lineno: int, *, allow_pair: bool = False) -> object:
    """手写标量解析：引号串/布尔/null/int/float；allow_pair 时支持 '[a, b]' 二元组。"""
    s = text.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in {"null", "~", "none", ""}:
        return None
    if allow_pair and s.startswith("[") and s.endswith("]"):
        return [_fallback_scalar(part, lineno) for part in s[1:-1].split(",")]
    if "[" in s or "{" in s:  # 内联结构超出回退能力
        raise ScenarioError(
            f"第 {lineno} 行: 值含内联结构 {s!r}——手写解析仅支持平铺+单层嵌套，{_YAML_INSTALL_HINT}"
        )
    for cast in (int, float):
        try:
            return cast(s)
        except ValueError:
            continue
    return s


def _fallback_parse(text: str, path: str) -> dict:
    """无 yaml 库时的手写解析：平铺 + 单层嵌套（缩进宽容——块内子行缩进一致即可）。

    支持：顶层「key: value」；「key:」开块后接统一缩进的子键或 '- ' 列表项
    （标量或 '[a, b]' 二元组）。不支持（→ScenarioError 提示装 PyYAML）：
    Tab 缩进、顶层裸列表/无冒号行、内联 '{'/'[' 结构、超过单层的嵌套、
    块内子键与列表项混用。
    """
    root: dict = {}
    block_key: str | None = None  # 当前单层嵌套宿主键（None=顶层）
    block_indent: int | None = None  # 块内子行的统一缩进（首行定标）

    def _complex(lineno: int, why: str) -> None:
        raise ScenarioError(
            f"{path} 第 {lineno} 行: {why}——手写解析仅支持平铺+单层嵌套"
            f"（key: value 与单层缩进子键/简单列表项），{_YAML_INSTALL_HINT}"
        )

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            _complex(lineno, "含 Tab 缩进")
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()

        if block_key is not None and indent == 0:  # 块结束，回到顶层
            block_key, block_indent = None, None

        if stripped.startswith("- "):
            if block_key is None:
                _complex(lineno, "顶层出现列表项（无宿主键）")
            if block_indent is None:
                block_indent = indent
            elif indent != block_indent:
                _complex(lineno, "列表项缩进与块内约定不一致")
            if root[block_key] is None:
                root[block_key] = []
            elif not isinstance(root[block_key], list):
                _complex(lineno, "块内混用列表项与子键")
            root[block_key].append(_fallback_scalar(stripped[2:], lineno, allow_pair=True))
            continue

        if ":" not in stripped:
            _complex(lineno, f"无法按「key: value」解析: {stripped!r}")
        key, _, rest = stripped.partition(":")
        key = key.strip().strip("'\"")
        rest = rest.strip()

        if indent == 0:
            if rest == "":
                block_key, block_indent = key, None
                root[key] = None  # 占位：见到子行再定 list/dict，块空则保持 None
            else:
                root[key] = _fallback_scalar(rest, lineno)
        else:
            if block_key is None:
                _complex(lineno, "缩进行缺少宿主键（顶层无「key:」开块）")
            if block_indent is None:
                block_indent = indent
            elif indent != block_indent:
                _complex(lineno, "缩进层级超过单层嵌套")
            if root[block_key] is None:
                root[block_key] = {}
            elif isinstance(root[block_key], list):
                _complex(lineno, "块内混用子键与列表项")
            root[block_key][key] = (
                None if rest == "" else _fallback_scalar(rest, lineno)
            )
    return root


def _parse_yaml(text: str, path: str) -> object:
    """解析场景文本：yaml 库优先（附行号尽力）；缺库回退手写解析。"""
    if _yaml is not None:
        try:
            return _yaml.safe_load(text)
        except _yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            line = getattr(mark, "line", None)
            loc = f"（第 {line + 1} 行起）" if line is not None else ""
            raise ScenarioError(f"YAML 解析失败{loc}: {path}: {exc}") from exc
    return _fallback_parse(text, path)


def load_scenario(path: str) -> dict:
    """场景装载总入口：读文件→schema 校验→红线校验→规范化，产出场景对象。

    流程（场景进入系统的唯一入口）：
      ① 读文件（path 不存在/不可读→ScenarioError）；解析——yaml 库在则
      safe_load（解析失败→ScenarioError 附行号尽力），缺库回退手写解析
      （平铺+单层嵌套；复杂结构→ScenarioError 提示装 PyYAML）；
      ② 信封键摘出（bands/shielded_box/dut_scope 平铺或 declarations 单层
      嵌套块）；validate_scenario_schema 校验场景字段（错误清单非空→
      ScenarioError 附编号清单透传）；
      ③ guard_compliance 红线三查（不可跳）：power（power_dbm 缺省 -10 填充，
      超 0dBm→拒）、bands（缺省/越白名单→拒）、declarations（场景须含
      shielded_box/dut_scope 声明键，缺→ScenarioError 提示补声明）——
      status='rejected' 即 ScenarioError 携带条款清单；
      ④ normalize_scenario 规范化（默认值填充+归一）+信封键落位→返回。

    Args:
        path: 场景 YAML 文件路径。

    Returns:
        规范化场景 dict（normalize_scenario 全部键+bands/shielded_box/dut_scope）。

    Raises:
        ScenarioError: 路径不存在/不可读；YAML 解析失败（含回退局限）；
        schema 错误清单（透传）；红线拒绝（[power]/[band]/[declaration] 条款）；
        规范化冲突（透传自 normalize_scenario）。
    """
    if not isinstance(path, str):
        raise ScenarioError(
            f"场景路径必须为 str，实际收到 {type(path).__name__}: {path!r}"
        )
    if not os.path.isfile(path):
        raise ScenarioError(f"场景文件不存在: {path}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise ScenarioError(f"场景文件不可读: {path}（{exc}）") from exc

    raw = _parse_yaml(text, path)

    # ---- 信封键摘出：场景字段进 validate，信封键进红线 ----
    if isinstance(raw, dict):
        nested = raw.get("declarations")
        declarations = nested if isinstance(nested, dict) else {}
        shielded_box = declarations.get("shielded_box", raw.get("shielded_box"))
        dut_scope = declarations.get("dut_scope", raw.get("dut_scope"))
        bands = raw.get("bands")
        scenario_fields = {k: v for k, v in raw.items() if k not in _ENVELOPE_KEYS}
    else:
        shielded_box = dut_scope = bands = None
        scenario_fields = raw

    # ---- schema 校验（形状与取值域；错误清单透传） ----
    errors = validate_scenario_schema(scenario_fields)
    if errors:
        numbered = "\n".join(f"  {i}. {e}" for i, e in enumerate(errors, start=1))
        raise ScenarioError(
            f"场景字段校验未通过（{len(errors)} 处）: {path}\n{numbered}"
        )

    # ---- 红线总闸（不可跳：缺节即该节违例，bands/声明须显式携带） ----
    guard_config = {
        "power": {"power_dbm": scenario_fields.get("power_dbm", DEFAULT_POWER_DBM)},
        "bands": bands,
        "declarations": {"shielded_box": shielded_box, "dut_scope": dut_scope},
    }
    verdict = guard_compliance(guard_config)
    if verdict["status"] == "rejected":
        violation_lines = "\n".join(f"  - {v}" for v in verdict["violations"])
        hint = ""
        if any("[declaration]" in v for v in verdict["violations"]):
            hint = (
                "\n红线不可跳——请在场景文件补齐声明键: "
                "shielded_box: true 与 dut_scope: self_built"
            )
        raise ScenarioError(
            f"红线校验拒绝（guard_compliance）: {path}\n{violation_lines}{hint}"
        )

    # ---- 规范化 + 信封键落位（下游唯一场景形状） ----
    scenario = normalize_scenario(scenario_fields)
    scenario["bands"] = bands
    scenario["shielded_box"] = shielded_box
    scenario["dut_scope"] = dut_scope
    return scenario
