"""标定演示与看板：三类标定表当前状态（【待实测】占位如实）+合成数据演示流程；只读不改真实表——重写规约与签名意图详见 fn_docs/responsibility.md（R70 view_calibration_status L0；调用方 mount_console_extensions）。

落地口径（R70）：

- 标定三件只读看板：gain 增益标定表与 compensation 全链路补偿两件（link_loss/
  antenna 两张表）经 load_calibration_table(placeholder=True) 口径出状态——在位
  （status='ok'，附 source/entry_count）/缺失（status='placeholder'，【待实测】
  占位如实显示，entries 为空禁止预写数字）/损坏或目录不存在（status='error'，
  CalibrationError 原文如实上屏不虚构）；leakage 自漏标定一件为 calibrate_leakage
  自有表格式（kind/status/points 的 JSON），看板按约定路径 calibration_dir/
  leakage.json 探在位性+轻解析（status='ok'|'insufficient'——样本不足照实标注），
  缺失同为【待实测】占位；
- 合成数据演示流程一键走（demo=True）：临时目录内以 build_gain_calibration
  合成建表（单调测点→成功分支，经 load_calibration_table 回读核验 entry_count）
  →非单调测点→CalibrationError 拒用分支（拒用发生在写表之前，如实验证未落盘）
  →单测点→样本不足拒用分支；三分支结果如实上屏（ok/rejected/message），演示
  失败亦如实记录不抛出；**只读红线**：一切演示 out_path 均在临时目录（用后即
  清），绝不触碰真实标定表；
- section 看板查询过滤：None=三件全量；'gain'/'leakage'/'compensation' 单件
  （strip().lower() 归一，未知值 ValueError——端点层转 400 上屏）；demo 触发独立
  于 section；
- 只读：本函数无任何写真实表路径（演示仅写临时目录），输出恒带 read_only=True
  与诚实基注。
"""
import json
import os
import tempfile
from pathlib import Path

from src.build_gain_calibration.build_gain_calibration import (
    CalibrationError as _GainCalibrationError,
)
from src.build_gain_calibration.build_gain_calibration import (
    build_gain_calibration,
)
from src.shared.load_calibration_table import (
    CalibrationError,
    load_calibration_table,
)

__all__ = ["CALIBRATION_SECTIONS", "view_calibration_status"]

#: 看板三件 section 取值域（gain 增益标定/leakage 自漏标定/compensation 全链路补偿）。
CALIBRATION_SECTIONS = ("gain", "leakage", "compensation")

#: 标定目录锚定：本文件 fn_work/src/view_calibration_status/*.py 的 parents[2]
#: 即 fn_work——与 build_gain_calibration 缺省 'fn_work/calibrations' 同落点，
#: 但仓库根锚定（cwd 无关：网页运行 cwd 任意时看板仍指仓内同一目录）。运行时
#: 以本模块全局名为解析来源，测试可 monkeypatch 指向 tmp 目录。
_CALIBRATION_DIR = str(Path(__file__).resolve().parents[2] / "calibrations")

#: 三件看板条目的中文标签（页区渲染锚点）。
_SECTION_LABELS = {
    "gain": "增益标定表",
    "leakage": "自漏标定表",
    "link_loss": "链路损耗表（L_link）",
    "antenna": "天线补偿表（C_ant）",
}

#: 演示视图的诚实基注（只读红线+模拟口径）。
_READ_ONLY_NOTE = (
    "标定看板为只读——不改任何真实标定表；合成数据演示仅写临时目录（用后即清），"
    "演示读数为合成测点非实测"
)


def _loader_table_view(table_name: str, config: dict) -> dict:
    """load_calibration_table 口径的单表状态（在位/【待实测】占位/损坏如实）。

    标定目录不存在＝尚未标定：按缺失→【待实测】占位如实显示（loader 对缺目录
    抛 CalibrationError 是防误用口径，看板语义是「还没有任何标定」——不误报
    error；表文件损坏仍 error 原文如实）。"""
    calibration_dir = config["calibration_dir"]
    path = os.path.join(calibration_dir, f"{table_name}.json")
    if not os.path.isdir(calibration_dir):
        return {
            "label": _SECTION_LABELS[table_name],
            "status": "placeholder",
            "present": False,
            "placeholder": True,
            "source": None,
            "entry_count": 0,
            "note": (
                f"【待实测】标定目录不存在（尚未标定），约定目录 {calibration_dir}"
            ),
        }
    try:
        view = load_calibration_table(table_name, config, placeholder=True)
    except CalibrationError as exc:  # 损坏/目录不存在→error 如实上屏不虚构
        return {
            "label": _SECTION_LABELS[table_name],
            "status": "error",
            "present": os.path.isfile(path),
            "placeholder": False,
            "source": path if os.path.isfile(path) else None,
            "entry_count": None,
            "note": f"标定表加载失败（load_calibration_table）: {exc}",
        }
    if view["placeholder"]:
        meta = dict(view["meta"])
        return {
            "label": _SECTION_LABELS[table_name],
            "status": "placeholder",
            "present": False,
            "placeholder": True,
            "source": None,
            "entry_count": 0,
            "note": str(meta.get("note", "【待实测】标定表缺失")) + (
                f"（约定路径 {meta.get('expected_path', path)}）"
            ),
        }
    return {
        "label": _SECTION_LABELS[table_name],
        "status": "ok",
        "present": True,
        "placeholder": False,
        "source": view["source"],
        "entry_count": int(dict(view["meta"]).get("entry_count", 0)),
        "note": f"在位（{int(dict(view['meta']).get('entry_count', 0))} 条目）",
    }


def _leakage_table_view(calibration_dir: str) -> dict:
    """自漏标定表状态：calibrate_leakage 自有格式轻解析（缺表【待实测】占位）。"""
    path = os.path.join(calibration_dir, "leakage.json")
    if not os.path.isfile(path):
        return {
            "label": _SECTION_LABELS["leakage"],
            "status": "placeholder",
            "present": False,
            "placeholder": True,
            "source": None,
            "entry_count": 0,
            "note": (
                "【待实测】自漏标定表缺失（calibrate_leakage 未建表），"
                f"约定路径 {path}"
            ),
        }
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict) or not isinstance(payload.get("table"), list):
            raise ValueError("缺少 table 列表（calibrate_leakage 表格式不符）")
    except (ValueError, OSError) as exc:  # 坏 JSON/坏格式/不可读→error 如实
        return {
            "label": _SECTION_LABELS["leakage"],
            "status": "error",
            "present": True,
            "placeholder": False,
            "source": path,
            "entry_count": None,
            "note": f"自漏标定表加载失败: {exc}",
        }
    status = "insufficient" if payload.get("status") == "insufficient" else "ok"
    count = payload.get("points")
    count = count if isinstance(count, int) else len(payload["table"])
    note = (
        f"在位（{count} 测点，status={payload.get('status', 'ok')}）"
        if status == "ok"
        else f"在位但样本不足（{count} < 3，status=insufficient——calibrate_leakage 标注）"
    )
    return {
        "label": _SECTION_LABELS["leakage"],
        "status": status,
        "present": True,
        "placeholder": False,
        "source": path,
        "entry_count": count,
        "note": note,
    }


def _demo_branch(name: str, measurements, expect_reject: bool) -> dict:
    """单条演示分支：build_gain_calibration 合成建表/拒用结果如实记录（不抛出）。

    expect_reject=True 的分支以 CalibrationError 拒用为预期终态（ok=True +
    rejected=True）；意外成功/意外异常均如实记录（ok=False + 原因）。"""
    try:
        built = build_gain_calibration(measurements)
    except _GainCalibrationError as exc:
        return {
            "branch": name,
            "ok": True,
            "rejected": True,
            "error": "CalibrationError",
            "message": str(exc),
        }
    except Exception as exc:  # noqa: BLE001 - 演示分支隔离边界（失败如实上屏）
        return {
            "branch": name,
            "ok": False,
            "rejected": None,
            "error": type(exc).__name__,
            "message": str(exc),
        }
    if expect_reject:  # 应拒未拒——分支契约失守，如实上报不掩饰
        return {
            "branch": name,
            "ok": False,
            "rejected": False,
            "error": None,
            "message": "预期 CalibrationError 拒用，实际建表成功（分支契约失守）",
        }
    return {
        "branch": name,
        "ok": True,
        "rejected": False,
        "error": None,
        "result": built,
    }


def _run_synthetic_demo() -> dict:
    """合成数据演示流程：临时目录内建表→非单调拒用→样本不足拒用三分支。

    只读红线：一切 out_path 均在 tempfile.TemporaryDirectory 内（上下文退出即
    清），不触碰真实标定表；成功分支另经 load_calibration_table 回读核验
    entry_count（建表→loader 口径闭环）。"""
    branches: list = []
    with tempfile.TemporaryDirectory(prefix="calibration-demo-") as tmp:
        ok_path = os.path.join(tmp, "gain.json")
        ok_branch = _demo_branch(
            "synthetic_build",
            [
                {"gain_step": 10, "power_dbm": -12.0, "out_path": ok_path},
                {"gain_step": 20, "power_dbm": -6.0},
                {"gain_step": 30, "power_dbm": 0.0},
            ],
            expect_reject=False,
        )
        if ok_branch.get("result") is not None:
            try:
                reload_view = load_calibration_table(
                    "gain", {"calibration_dir": tmp}, placeholder=False
                )
                ok_branch["reload"] = {
                    "name": "gain",
                    "entry_count": int(dict(reload_view["meta"]).get("entry_count", 0)),
                    "placeholder": False,
                }
            except CalibrationError as exc:  # 回读失败如实记录（不推翻建表结果）
                ok_branch["reload"] = {"error": f"CalibrationError: {exc}"}
        branches.append(ok_branch)

        bad_path = os.path.join(tmp, "gain_non_monotonic.json")
        bad_branch = _demo_branch(
            "non_monotonic_reject",
            [
                {"gain_step": 10, "power_dbm": -6.0, "out_path": bad_path},
                {"gain_step": 20, "power_dbm": -11.0},
            ],
            expect_reject=True,
        )
        bad_branch["wrote_table"] = os.path.isfile(bad_path)
        branches.append(bad_branch)

        thin_branch = _demo_branch(
            "insufficient_reject",
            [{"gain_step": 10, "power_dbm": -6.0, "out_path": os.path.join(tmp, "t.json")}],
            expect_reject=True,
        )
        branches.append(thin_branch)

    return {
        "ok": all(branch.get("ok") for branch in branches),
        "kind": "synthetic",
        "wrote_real_table": False,
        "branches": branches,
        "note": (
            "合成数据演示：三分支（合成建表/非单调拒用/样本不足拒用）结果如实上屏；"
            "演示仅写临时目录（已清理），不改真实标定表"
        ),
    }


def view_calibration_status(section: str | None = None, demo: bool = False) -> dict:
    """标定演示与看板：三类标定表当前状态（【待实测】占位如实）+合成数据演示流程；只读不改真实表（详见 fn_docs/responsibility.md 功能块）。

    输入:
        section: 看板查询过滤——None=三件全量（gain 增益标定/leakage 自漏标定/
            compensation 全链路补偿）；'gain'/'leakage'/'compensation' 单件
            （strip().lower() 归一；未知值/非 str|None → ValueError，端点层转
            400 错误信息上屏）。
        demo: 合成数据演示触发（bool；True=一键走 build_gain_calibration 合成
            建表→非单调拒用→样本不足拒用三分支，仅写临时目录不改真实标定表；
            非 bool → ValueError）。

    输出:
        看板视图 dict：{'ok': True, 'section': 归一后 section|None,
        'calibration_dir': 看板锚定的标定目录（仓库根锚定，cwd 无关）,
        'calibrations': {件名: 表状态视图}——gain/leakage/link_loss/antenna
        条目为 {label, status('ok'|'placeholder'|'error'|'insufficient'),
        present, placeholder, source, entry_count, note}（【待实测】占位如实、
        损坏原文如实），compensation 件为 {'link_loss': …, 'antenna': …} 两表
        嵌套；demo=True 时另附 'demo': {ok, kind, wrote_real_table,
        branches[…], note}（演示分支结果如实上屏，失败不抛）, 'read_only':
        True, 'note': 诚实基注}。

    错误:
        ValueError: section 未知/非 str|None、demo 非 bool（形状错先拒——端点层
            转 400 错误信息上屏）；演示分支失败不抛（结果如实记录上屏）。
    """
    if section is not None:
        if not isinstance(section, str) or section.strip().lower() not in CALIBRATION_SECTIONS:
            raise ValueError(
                f"section 必须为 {'|'.join(CALIBRATION_SECTIONS)} 之一或 None"
                f"（标定看板三件），实际: {section!r}"
            )
        section = section.strip().lower()
    if not isinstance(demo, bool):
        raise ValueError(
            f"demo 必须为 bool（合成数据演示触发），实际: {demo!r}"
        )

    config = {"calibration_dir": _CALIBRATION_DIR}
    wanted = CALIBRATION_SECTIONS if section is None else (section,)
    calibrations: dict = {}
    for piece in wanted:
        if piece == "gain":
            calibrations["gain"] = _loader_table_view("gain", config)
        elif piece == "leakage":
            calibrations["leakage"] = _leakage_table_view(_CALIBRATION_DIR)
        else:
            calibrations["compensation"] = {
                "link_loss": _loader_table_view("link_loss", config),
                "antenna": _loader_table_view("antenna", config),
            }

    view = {
        "ok": True,
        "section": section,
        "calibration_dir": _CALIBRATION_DIR,
        "calibrations": calibrations,
        "read_only": True,
        "note": _READ_ONLY_NOTE,
    }
    if demo:
        view["demo"] = _run_synthetic_demo()
    return view

def _describe_empty_gain_status(read_result):
    """区分"文件不存在（待实测）"与"文件存在但 entries 为空（ok/0 条）"。

    输入: 表读取结果 / 输出: {'status','note','entry_count'} / 错误: 不抛。
    """
    raise NotImplementedError("unimplemented:fn:_describe_empty_gain_status")
