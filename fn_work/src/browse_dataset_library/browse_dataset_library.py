"""录音库与数据集浏览：index_dataset list/query 上页（SigMF 卡片+样式/日期过滤）+索引重建入口——重写规约与签名意图详见 fn_docs/responsibility.md（R63 功能块）。

职责口径（R63 L0）：
- 经 index_dataset 的 list/query 出 SigMF 真值对卡片（样式/功率/时长/批次/运行
  来源），按样式/日期过滤；
- 卡片真值双源：索引条目（register 登记口径）+ 来源运行目录的场景副本
  scenario.yaml（manage_run 落盘的规范化场景——真跑运行的 result.json 常缺
  style/freq_mhz 等卡片字段，副本是这些字段的真值来源，与 R64
  build_replay_scenario 的来源场景同源）；副本缺失/损坏→该卡降级（索引字段
  兜底/未知标注），不虚构不剔除；
- 索引未建（索引文件不存在）→状态提示+重建入口（rebuild_available=True），
  不报错拦页；重建由调用方经 index_dataset('rebuild')（操控台侧 POST
  /api/dataset/rebuild）执行——本函数只浏览不重建；
- 样式过滤按卡片真值判定（副本补全后的 style；索引侧仅承载日期条件——rebuild
  重建的条目常缺 style，索引侧过滤会漏真值命中的卡，此口径保证过滤语义跟卡片
  真值一致）；日期过滤经索引 date_range（闭区间，字典序比较）。
"""
import math
import os

from src.index_dataset.index_dataset import (
    DEFAULT_INDEX_PATH,
    DEFAULT_RUNS_ROOT,
    QueryError,
    index_dataset,
)

__all__ = [
    "DATASET_INDEX_FILENAME",
    "UNKNOWN_LABEL",
    "browse_dataset_library",
    "dataset_index_path",
]

#: 操控台侧数据集索引落点名（置于 report_root 下——console 的运行目录根即
#: index_dataset 的 runs_root 口径，索引随之按服务域自包含；GET /api/runs 与
#: list_run_summaries 均按目录过滤，该文件不入运行列表）。
DATASET_INDEX_FILENAME = "dataset-index.json"

#: 卡片缺数据字段的占位标签（明示「不可考」，不虚构值）。
UNKNOWN_LABEL = "未知"

#: 来源运行目录内场景副本文件名（与 manage_run.create_run_workspace 约定一致）。
SCENARIO_FILENAME = "scenario.yaml"

#: 浏览查询支持的条件键（未知键→QueryError 附此清单）。
_SUPPORTED_QUERY_KEYS = ("style", "date_from", "date_to")

#: 日期开区间兜底边界（'YYYYMMDD' 字典序口径——单边界过滤时代替另一端）。
_DATE_LOW_BOUND = "00000000"
_DATE_HIGH_BOUND = "99999999"


def dataset_index_path(report_root: str) -> str:
    """report_root → 数据集索引落点路径（操控台侧唯一派生口径，R63/R64 端点共用）。"""
    return os.path.join(report_root, DATASET_INDEX_FILENAME)


def _is_number(value) -> bool:
    """数值口径：int/float 且非 bool（与 query_dataset 的频段判定一致）。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _lenient_number(value):
    """宽容数值化（B17 中#4 同口径）：int/float（拒 bool）或可解析有限数字 str
    （PyYAML 1.1 把 '2.4e9' 这类无点科学计数解析为 str）→ float；其余 None。

    场景副本直读（yaml.safe_load）不走 load_scenario 的 normalize_scenario
    数值化——卡片补缺字段在此就地宽容，保持与装载路径同结果。
    """
    if _is_number(value):
        return float(value)
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def _normalize_query(query: object) -> dict:
    """浏览查询规范化：{'style','date_from','date_to'} 可选键 → 内部条件 dict。

    - 非 dict / 未知键 → QueryError（附支持清单）；
    - style: 非空 str（空白剥离）；
    - date_from/date_to: 非空 str（'YYYYMMDD' 字典序口径，值域校验归索引侧
      date_range 比较）；单边界→另一端以开区间兜底边界补全。
    """
    if query is None:
        query = {}
    if not isinstance(query, dict):
        raise QueryError(
            f"query 必须为 dict（浏览条件），得到 {type(query).__name__}: {query!r}"
        )
    unknown = [key for key in query if key not in _SUPPORTED_QUERY_KEYS]
    if unknown:
        raise QueryError(
            f"未知浏览条件字段 {unknown!r}；支持字段清单: {list(_SUPPORTED_QUERY_KEYS)}"
        )
    conditions: dict = {"style": None, "date_from": None, "date_to": None}
    for key in ("style", "date_from", "date_to"):
        value = query.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise QueryError(
                f"query[{key!r}] 必须为非空 str，得到 {value!r}"
            )
        conditions[key] = value.strip()
    return conditions


def _date_range(conditions: dict):
    """日期条件 → 索引 date_range 二元组（无任何边界→None 不过滤）。"""
    if conditions["date_from"] is None and conditions["date_to"] is None:
        return None
    low = conditions["date_from"] or _DATE_LOW_BOUND
    high = conditions["date_to"] or _DATE_HIGH_BOUND
    return [low, high]


def _read_scenario_copy(run_dir: object) -> dict:
    """读来源运行目录的场景副本 scenario.yaml → dict（补缺真值来源）。

    缺失/损坏/非 dict/路径不可考→{}（降级口径——副本只是卡片补缺来源，
    绝不反杀浏览；红线消费归 R64 build_replay_scenario 的显式拒绝）。
    """
    if not isinstance(run_dir, str) or not run_dir.strip():
        return {}
    path = os.path.join(run_dir, SCENARIO_FILENAME)
    if not os.path.isfile(path):
        return {}
    try:
        import yaml

        with open(path, encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    except Exception:  # noqa: BLE001 - 副本损坏→补缺来源失效，卡片降级不反杀
        return {}
    return payload if isinstance(payload, dict) else {}


def _first_sigmf_meta(recordings_dir: object) -> "str | None":
    """recordings 目录 → 字典序最早 .sigmf-meta 路径（无→None）。

    与 run_rff_pipeline/train_classifier 的「目录→最早 .sigmf-meta 配对 data」
    口径一致；目录不可读/非 str → None。
    """
    if not isinstance(recordings_dir, str) or not recordings_dir.strip():
        return None
    try:
        names = os.listdir(recordings_dir)
    except OSError:
        return None
    metas = sorted(name for name in names if name.endswith(".sigmf-meta"))
    if not metas:
        return None
    return os.path.join(recordings_dir, metas[0])


def _run_dir_of(entry: dict) -> "str | None":
    """条目 → 来源运行目录（recordings 父目录）：'run_dir' 显式 > dirname('path')。"""
    explicit = entry.get("run_dir")
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    path = entry.get("path")
    if isinstance(path, str) and path.strip():
        return os.path.dirname(path.rstrip(os.sep))
    return None


def _card(entry: dict) -> dict:
    """索引条目+场景副本 → 卡片（样式/功率/时长/批次/运行来源真值双源合并）。

    卡片契约（键序即页区展示序；缺数据的键为 None/'未知'——降级不虚构）：
    - run_id/source_run: 运行标识（运行来源——回放端点按 run_id 定位）；
    - path: recordings 目录（索引条目原值）；sigmf_path: 最早 .sigmf-meta
      （显式 'sigmf_path' 键优先）；replayable: sigmf_path 在位且同名
      .sigmf-data 成对（「回放此条」可点性真值）；
    - style: 场景副本 style → 索引 style → '未知'（副本为真跑运行的真值来源）；
    - freq_mhz/power_dbm/duration_s: 副本数值（freq_hz 换算 MHz），缺→索引
      freq_mhz（freq）/None；
    - batch_key/backend/date/failed: 索引条目原值（failed 缺省 False 口径）。
    """
    scenario = _read_scenario_copy(_run_dir_of(entry))
    sigmf_path = None
    explicit_meta = entry.get("sigmf_path")
    if isinstance(explicit_meta, str) and explicit_meta.strip():
        sigmf_path = explicit_meta
    else:
        sigmf_path = _first_sigmf_meta(entry.get("path"))
    replayable = False
    if isinstance(sigmf_path, str) and os.path.isfile(sigmf_path):
        data = sigmf_path[: -len(".sigmf-meta")] + ".sigmf-data"
        replayable = os.path.isfile(data)

    style = scenario.get("style")
    if not (isinstance(style, str) and style.strip()):
        style = entry.get("style")
    style_text = (
        style.strip()
        if isinstance(style, str) and style.strip()
        else UNKNOWN_LABEL
    )
    freq_hz = _lenient_number(scenario.get("freq_hz"))
    freq_mhz = (
        freq_hz / 1.0e6
        if freq_hz is not None
        else (entry.get("freq_mhz") if _is_number(entry.get("freq_mhz")) else None)
    )
    power_dbm = _lenient_number(scenario.get("power_dbm"))
    duration_s = _lenient_number(scenario.get("duration_s"))
    backend = scenario.get("backend")
    if not (isinstance(backend, str) and backend.strip()):
        backend = entry.get("backend")
    backend_text = (
        backend.strip()
        if isinstance(backend, str) and backend.strip()
        else UNKNOWN_LABEL
    )
    batch_key = entry.get("batch_key")
    run_id = entry.get("run_id")
    return {
        "run_id": run_id if isinstance(run_id, str) else None,
        "source_run": run_id if isinstance(run_id, str) else UNKNOWN_LABEL,
        "path": entry.get("path") if isinstance(entry.get("path"), str) else None,
        "sigmf_path": sigmf_path,
        "replayable": replayable,
        "style": style_text,
        "freq_mhz": freq_mhz,
        "power_dbm": power_dbm,
        "duration_s": duration_s,
        "batch_key": batch_key if isinstance(batch_key, str) else None,
        "backend": backend_text,
        "date": entry.get("date") if isinstance(entry.get("date"), str) else None,
        "failed": bool(entry.get("failed", False)),
    }


def browse_dataset_library(
    query: "dict | None" = None,
    index_path: "str | None" = None,
    runs_root: "str | None" = None,
) -> dict:
    """录音库与数据集浏览：index_dataset query 出 SigMF 真值对卡片+过滤+索引状态。

    输入:
        query: 浏览条件 dict（均可选）——'style'（非空 str，按卡片真值判定）、
            'date_from'/'date_to'（'YYYYMMDD'，经索引 date_range 闭区间过滤；
            单边界时另一端开放）；None=不过滤全量。未知键→QueryError。
        index_path: 索引 JSON 落点（None=DEFAULT_INDEX_PATH）。
        runs_root: 运行目录根（None=DEFAULT_RUNS_ROOT——索引损坏读路径自愈与
            场景副本定位的数据源口径）。

    输出:
        {'index_status': 'ready'|'missing', 'cards': [卡片…], 'count': 匹配卡数,
        'matched': 索引侧条件命中数, 'total': 索引条目总数, 'filters': 规范化后
        的条件回显, 'hint': str|None（missing 态的重建提示）, 'rebuild_available':
        bool（missing 态 True——重建入口可用性标志）}；卡片契约见 _card。

    错误:
        索引缺失→**不报错**（状态提示+重建入口的 missing 返回）；QueryError:
            query 形状错（未知键/值非 str）或索引侧 date_range 反序等条件非法
            （index_dataset 透传）；IndexFormatError/IndexWriteError: 索引损坏
            且无法自愈/读 IO 失败（index_dataset 透传）。
    """
    conditions = _normalize_query(query)
    if index_path is None:
        index_path = DEFAULT_INDEX_PATH
    if runs_root is None:
        runs_root = DEFAULT_RUNS_ROOT

    if not os.path.exists(index_path):
        return {
            "index_status": "missing",
            "cards": [],
            "count": 0,
            "matched": 0,
            "total": 0,
            "filters": conditions,
            "hint": (
                "数据集索引未建——先触发重建（POST /api/dataset/rebuild，或"
                " index_dataset(action='rebuild', runs_root=运行目录根)），"
                "再回到本页浏览 SigMF 真值对卡片"
            ),
            "rebuild_available": True,
        }

    index_query: dict = {}
    date_range = _date_range(conditions)
    if date_range is not None:
        index_query["date_range"] = date_range
    outcome = index_dataset(
        "query",
        query=index_query or None,
        index_path=index_path,
        runs_root=runs_root,
    )
    cards = [_card(entry) for entry in outcome["entries"]]
    wanted_style = conditions["style"]
    if wanted_style is not None:
        cards = [card for card in cards if card["style"] == wanted_style]
    return {
        "index_status": "ready",
        "cards": cards,
        "count": len(cards),
        "matched": outcome["matched"],
        "total": outcome["total"],
        "filters": conditions,
        "hint": None,
        "rebuild_available": False,
    }
