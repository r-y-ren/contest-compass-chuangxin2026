"""责任文档对账校验：断言 responsibility.md 已含演进期契约登记并与代码锚点交叉；
漏登列清单——重写规约与签名意图详见 fn_docs/responsibility.md（R75 功能块）。

对账口径（R75，登记侧=责任文档四旧块补注+域二十引言；锚点侧=代码实测）：

- 对账项七件（每项一组针文本，缺任一针即漏登）：
  1. run_scenario 公共入口（R44 块——入口名+dict 装载第二通道描述）；
  2. serve_console 双载荷合并契约+_KNOWN_KEYS 跨模块耦合（R47 块）；
  3. 场景白名单键域（R1 块——键数针取代码 _KNOWN_KEYS len 动态值，如
     「63 键」；代码键数漂移→旧文档的静态键数针失配→漏登）；
  4. R48 页面元素枚举更新（急停/轮询回显/清单内联/编辑器/三路图区五针）；
  5. 域二十新块在册（R56–R75 共 20 个块头齐备+域二十标记）；
  6. 快速通道变更说明（「改造点·快速通道：」块引言标记 ≥6 处——R56/R58/
     R59/R64/R68/R75）；
  7. 装配资产件清单注（14 页区资产件+build_realtime_charts 全名在册）。
- 代码锚点交叉（动态实测）：run_demo `__all__` 含 run_scenario 导出；
  _KNOWN_KEYS 实测键数入 code_anchors（文档键数针与之同源——见对账项 3）。
- 本函数**只读不写**：不修文档、不改代码；对账失败（文档/锚点文件缺失）
  上抛，漏登不抛——返回 missing 清单由调用方（pytest/维护命令）消费。
"""
import importlib.util
import os
import re

__all__ = ["audit_responsibility_alignment"]

#: 功能块头（`## 功能块 <名> ← R<号>`——对账项 1-4 的块作用域切分依据；
#: 行尾可带 [P1] 标注（需求覆盖矩阵口径：P1 在 R 号后标注））。
_BLOCK_HEADER_RE = re.compile(r"^## 功能块\s+\S.*?\s*←\s*(R\d+)\b.*$", re.MULTILINE)

#: 域二十新块号域（R56–R75，共 20 块——对账项 5 的完备性锚）。
_DOMAIN_TWENTY = [f"R{n}" for n in range(56, 76)]

#: 快速通道变更说明标记（块引言内「改造点·快速通道：」——全角冒号区分于
#: 文档头部对约定本身的描述行；演进轮登记 6 处：R56/R58/R59/R64/R68/R75）。
_FAST_TRACK_MARKER = "改造点·快速通道："
_FAST_TRACK_MIN = 6

#: 装配资产件清单（对账项 7——域二十引言资产件清单注的完备性锚；
#: 14 页区资产件+build_realtime_charts，B24–B30 各批申报在案）。
_ASSET_AREA_NAMES = (
    "report_view_area",
    "run_list_area",
    "comparison_area",
    "dataset_area",
    "train_area",
    "eval_area",
    "infer_area",
    "emc_area",
    "panels_area",
    "calibration_area",
    "audit_area",
    "sitl_area",
    "rl_area",
    "rff_area",
    "build_realtime_charts",
)

#: 代码锚点文件相对路径（code_root 起——缺失即对账失败上抛）。
_SCHEMA_ANCHOR_REL = os.path.join("src", "load_scenario", "validate_scenario_schema.py")
_RUN_DEMO_ANCHOR_REL = os.path.join("src", "run_demo", "run_demo.py")


def _read_text(path: str, what: str) -> str:
    """读文本文件；缺失/不可读→FileNotFoundError（对账失败上抛口径）。"""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{what} 缺失，对账无法进行: {path}")
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise FileNotFoundError(f"{what} 不可读，对账无法进行: {path}（{exc}）") from exc


def _split_blocks(text: str) -> "dict[str, str]":
    """按功能块头切分 → {块号: 块全文（含头与引言）}；非块文本不入册。"""
    blocks: "dict[str, str]" = {}
    matches = list(_BLOCK_HEADER_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks[match.group(1)] = text[match.start() : end]
    return blocks


def _count_known_keys(code_root: str) -> int:
    """代码锚点：_KNOWN_KEYS 实测键数（独立装载校验模块——不占 sys.modules
    缓存位，code_root 指向任意目录均取该目录真值）。"""
    path = os.path.join(code_root, _SCHEMA_ANCHOR_REL)
    _read_text(path, "锚点文件 validate_scenario_schema")
    spec = importlib.util.spec_from_file_location(
        "_audit_anchor_validate_scenario_schema", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr] - 标准文件装载
    known = getattr(module, "_KNOWN_KEYS", None)
    if known is None or not hasattr(known, "__len__"):
        raise FileNotFoundError(
            f"锚点失真：{path} 无 _KNOWN_KEYS 白名单容器——代码结构与对账口径不符"
        )
    return len(known)


def _run_demo_all(code_root: str) -> "list[str]":
    """代码锚点：run_demo `__all__` 导出清单（正则解析——不整体 import 编排链）。"""
    source = _read_text(
        os.path.join(code_root, _RUN_DEMO_ANCHOR_REL), "锚点文件 run_demo"
    )
    match = re.search(r"^__all__\s*=\s*\[(.*?)\]", source, re.MULTILINE | re.DOTALL)
    if match is None:
        return []
    return re.findall(r"[\"']([^\"']+)[\"']", match.group(1))


def audit_responsibility_alignment(doc_path: str, code_root: str) -> dict:
    """责任文档对账校验：断言 responsibility.md 已含演进期契约登记并与代码
    锚点交叉；漏登列清单（详见 fn_docs/responsibility.md R75 功能块）。

    Args:
        doc_path: 责任文档路径（fn_docs/responsibility.md；缺失→上抛）。
        code_root: 代码根（fn_work——锚点文件 src/run_demo/run_demo.py 与
            src/load_scenario/validate_scenario_schema.py 由此解析；缺失→上抛）。

    Returns:
        {'registered': [对账项 id, ...]（通过项）, 'missing': [漏登描述 str, ...],
        'code_anchors': {'run_scenario_exported': bool, 'run_demo___all__': [...],
        'known_keys_len': int, 'whitelist_keys_needle': '63 键' 形动态针,
        'domain_blocks_present': int, 'fast_track_notes': int, 'doc_path': 绝对路径,
        'code_root': 绝对路径}, 'ok': missing 为空}——ok=False 即有漏登（不抛）。

    Raises:
        FileNotFoundError: 责任文档或锚点文件缺失/不可读/锚点失真（对账失败
            上抛——区别于漏登：漏登是文档内容问题，返回 missing 清单）。
    """
    doc = _read_text(doc_path, "责任文档")
    blocks = _split_blocks(doc)
    known_keys_len = _count_known_keys(code_root)
    run_all = _run_demo_all(code_root)
    keys_needle = f"{known_keys_len} 键"

    # ---- 对账项 1-4：旧块回登记（块作用域针文本——防他块同名顶替） ----
    block_items: "list[tuple[str, str, str, list[str]]]" = [
        (
            "run_scenario_public_entry",
            "R44 块 run_scenario 公共入口与 dict 装载第二通道登记",
            "R44",
            ["run_scenario", "第二通道"],
        ),
        (
            "serve_console_dual_payload",
            "R47 块 serve_console 双载荷合并契约与 _KNOWN_KEYS 跨模块耦合登记",
            "R47",
            ["双载荷", "_KNOWN_KEYS"],
        ),
        (
            "scenario_whitelist_keys",
            f"R1 块场景白名单 {keys_needle}域登记（键数=代码 _KNOWN_KEYS 实测锚）",
            "R1",
            ["白名单", keys_needle],
        ),
        (
            "r48_page_elements_enum",
            "R48 块页面元素枚举更新（急停/轮询回显/清单内联/编辑器/三路图区）",
            "R48",
            ["急停", "轮询", "清单", "编辑器", "三路图"],
        ),
    ]
    registered: "list[str]" = []
    missing: "list[str]" = []
    for item_id, label, block_id, needles in block_items:
        block = blocks.get(block_id)
        absent = [needle for needle in needles if block is None or needle not in block]
        if absent:
            missing.append(
                f"{item_id}: {label}——{block_id} 块"
                + ("缺整块，" if block is None else "")
                + f"缺针 {absent}"
            )
        else:
            registered.append(item_id)

    # ---- 对账项 5：域二十新块在册（标记+R56–R75 块头完备） ----
    domain_present = sum(1 for rno in _DOMAIN_TWENTY if rno in blocks)
    if "域二十" in doc and domain_present == len(_DOMAIN_TWENTY):
        registered.append("domain_twenty_new_blocks")
    else:
        missing.append(
            "domain_twenty_new_blocks: 域二十新块在册（R56–R75 共 "
            f"{len(_DOMAIN_TWENTY)} 块）——实测 {domain_present} 块在册"
            + ("、缺「域二十」标记" if "域二十" not in doc else "")
        )

    # ---- 对账项 6：快速通道变更说明 ≥6 处（grep 改造点标记） ----
    fast_track_notes = doc.count(_FAST_TRACK_MARKER)
    if fast_track_notes >= _FAST_TRACK_MIN:
        registered.append("fast_track_change_notes")
    else:
        missing.append(
            f"fast_track_change_notes: 快速通道变更说明应 ≥{_FAST_TRACK_MIN} 处"
            f"（{_FAST_TRACK_MARKER}标记）——实测 {fast_track_notes} 处"
        )

    # ---- 对账项 7：装配资产件清单注（14 页区+build_realtime_charts 全名） ----
    absent_assets = [name for name in _ASSET_AREA_NAMES if name not in doc]
    if not absent_assets:
        registered.append("asset_area_inventory")
    else:
        missing.append(
            f"asset_area_inventory: 装配资产件清单注缺名 {absent_assets}"
            "（域二十引言资产件清单注——B24–B30 申报件）"
        )

    # ---- 代码锚点交叉：run_scenario 公共入口导出（动态实测） ----
    run_scenario_exported = "run_scenario" in run_all
    if run_scenario_exported:
        registered.append("code_anchor_run_scenario_export")
    else:
        missing.append(
            "code_anchor_run_scenario_export: run_demo `__all__` 未导出 "
            f"run_scenario——实测导出 {run_all}（文档登记与代码现状漂移）"
        )

    return {
        "registered": registered,
        "missing": missing,
        "code_anchors": {
            "run_scenario_exported": run_scenario_exported,
            "run_demo___all__": run_all,
            "known_keys_len": known_keys_len,
            "whitelist_keys_needle": keys_needle,
            "domain_blocks_present": domain_present,
            "fast_track_notes": fast_track_notes,
            "doc_path": os.path.abspath(doc_path),
            "code_root": os.path.abspath(code_root),
        },
        "ok": not missing,
    }
