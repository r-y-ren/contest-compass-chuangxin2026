"""主动推理入口：选历史运行/录音→predict_style→样式+置信度+对照标准答案；模型缺失提示不阻塞——重写规约与签名意图详见 fn_docs/responsibility.md（R67 infer_style_entry L0；调用方 mount_console_extensions）。

落地口径（R67）：

- IQ 源选择（``source`` 三选一 + 可选键）：
  - ``run_id``（历史运行/录音条目标识）→ index_dataset('list') 定位条目 →
    其 recordings 目录内最早 .sigmf-meta；
  - ``sigmf_path``（录音条目 .sigmf-meta 直给）；
  - ``query``（数据集检索条件 dict）→ index_dataset('query') 首条匹配条目 →
    recordings 内最早 .sigmf-meta；
  - 可选：``model``（str 模型文件路径|dict 内联|None——缺省 None 走 R32
    no_model 提示态不阻塞）、``nfft``（缺省 256）、``index_path``/``runs_root``
    （索引落点传输键——run_id/query 定位用，缺省 index_dataset 缺省）；
- 推理：predict_style(sigmf_meta 路径, model, nfft)——结果行（label/
  confidence/features/model_version/短段跳段 short_iq 等口径）原样透传；
- 标准答案对照：真值双源——① SigMF 标注（meta annotations 的 'jam:style'
  首个非空 str）② 场景副本（recordings 父目录 scenario.yaml 的 'style'）；
  两源皆缺 → truth.style=None 如实标注（不虚构）；``hit``=识别标签与真值
  相等性（任一侧缺失 → None 不判定）；
- 错误：源形状错（source 非 dict/三选一全缺/nfft 非法）→ ValueError；模型
  缺失/条目不在库/录音无样本→**status 行不抛**（R32 提示态口径——no_model/
  no_iq 行原样返回，模型缺失附「先训练」提示）。
"""
import json
import os

from src.index_dataset.index_dataset import index_dataset
from src.predict_style.predict_style import predict_style

__all__ = ["infer_style_entry"]

#: 谱图窗长缺省（source['nfft'] 可覆盖——与 predict_style 同域）。
_DEFAULT_NFFT = 256

#: source 的索引落点传输键（run_id/query 定位用，不进检索条件）。
_INDEX_PLUMB_KEYS = ("index_path", "runs_root")

#: 来源运行目录内场景副本文件名（与 manage_run.create_run_workspace 约定一致）。
SCENARIO_FILENAME = "scenario.yaml"

#: SigMF 真值标注的样式键（与 annotate_truth_labels 产出契约一致）。
_TRUTH_STYLE_KEY = "jam:style"


def _first_sigmf_meta(recordings_dir: object) -> "str | None":
    """recordings 目录 → 字典序最早 .sigmf-meta 路径（无/不可读→None）。"""
    if not isinstance(recordings_dir, str) or not recordings_dir.strip():
        return None
    try:
        names = os.listdir(recordings_dir)
    except OSError:
        return None
    metas = sorted(name for name in names if name.endswith(".sigmf-meta"))
    return os.path.join(recordings_dir, metas[0]) if metas else None


def _resolve_entry_sigmf(source: dict):
    """run_id/query 两路 → (sigmf_meta 路径 | None, 状态注 str | None)。

    run_id：index_dataset('list') 全量→run_id 精确匹配；query：'query' 首条
    匹配条目（entries[0]）；定位不到/recordings 无 .sigmf-meta → (None, 原因注)。
    """
    index_kwargs = {
        key: source[key] for key in _INDEX_PLUMB_KEYS if key in source
    }
    if "run_id" in source:
        run_id = source.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError(
                f"source['run_id'] 必须为非空 str（历史运行/录音条目标识），"
                f"实际 {run_id!r}"
            )
        run_id = run_id.strip()
        entries = index_dataset("list", **index_kwargs)["entries"]
        entry = next(
            (item for item in entries if isinstance(item, dict) and item.get("run_id") == run_id),
            None,
        )
        if entry is None:
            return None, f"运行/录音条目不在库: run_id={run_id!r}——先重建索引（POST /api/dataset/rebuild）"
        meta_path = _first_sigmf_meta(entry.get("path"))
        if meta_path is None:
            return None, f"条目无可用录音（recordings 缺 .sigmf-meta）: run_id={run_id!r}"
        return meta_path, None
    # 'query' 路：首条匹配条目
    query = source.get("query")
    if not isinstance(query, dict):
        raise ValueError(
            f"source['query'] 必须为 dict（数据集检索条件），实际 {type(query).__name__}"
        )
    found = index_dataset("query", query=query or None, **index_kwargs)
    entries = found.get("entries", [])
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        meta_path = _first_sigmf_meta(entry.get("path"))
        if meta_path is not None:
            return meta_path, None
    return None, "数据集查询无可用录制（无匹配条目或 recordings 缺 .sigmf-meta）"


def _truth_from_sigmf(meta_path: str) -> "dict | None":
    """SigMF meta → 真值标注（首个非空 'jam:style' 注解）；不可读/无标注→None。"""
    try:
        with open(meta_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    annotations = payload.get("annotations")
    if isinstance(annotations, list):
        for annotation in annotations:
            if not isinstance(annotation, dict):
                continue
            style = annotation.get(_TRUTH_STYLE_KEY)
            if isinstance(style, str) and style.strip():
                return {"source": "sigmf_annotation", "style": style.strip()}
    return None


def _truth_from_scenario_copy(meta_path: str) -> "dict | None":
    """场景副本（recordings 父目录 scenario.yaml）→ 真值 style；缺/损坏→None。"""
    run_dir = os.path.dirname(os.path.dirname(os.path.abspath(meta_path)))
    copy_path = os.path.join(run_dir, SCENARIO_FILENAME)
    if not os.path.isfile(copy_path):
        return None
    try:
        import yaml

        with open(copy_path, encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    except Exception:  # noqa: BLE001 - 副本损坏→真值来源失效（不虚构不反杀）
        return None
    if not isinstance(payload, dict):
        return None
    style = payload.get("style")
    if isinstance(style, str) and style.strip():
        return {"source": "scenario_copy", "style": style.strip()}
    return None


def infer_style_entry(source: dict) -> dict:
    """主动推理入口：选历史运行/录音→predict_style→样式+置信度+对照标准答案；模型缺失提示不阻塞（详见 fn_docs/responsibility.md 功能块）。

    输入:
        source: IQ 源选择 dict——三选一：'run_id'（历史运行/录音条目标识，
            index list 定位）| 'sigmf_path'（.sigmf-meta 路径直给）| 'query'
            （数据集检索条件 dict，首条匹配条目）；可选：'model'（str 模型
            文件路径 | dict 内联模型 | 缺省 None——R32 no_model 提示态）、
            'nfft'（缺省 256）、'index_path'/'runs_root'（索引落点传输键）。

    输出:
        识别结果行 dict：predict_style 结果行字段（status/recognized/label/
        confidence/note/features/model_version/iq_source——no_model/no_iq/
        short_iq 等提示态行原样）+ 'truth': {'source': 'sigmf_annotation'|
        'scenario_copy'|None, 'style': str|None}（真值双源，皆缺如实 None）+
        'hit': bool|None（识别标签与真值相等性——任一侧缺失 None 不判定）。
        模型缺失行另附 note「先训练」提示（不阻塞，R32 口径）。

    错误:
        ValueError: source 非 dict / 三选一源全缺 / run_id、query 形状错 /
            nfft 非法（make_spectrogram 透传——predict_style 唯一上抛例外）。
        条目不在库/录音无样本/模型缺失→**不抛**（status 行提示态返回）。
    """
    if not isinstance(source, dict):
        raise ValueError(
            f"source 必须为 dict（IQ 源选择），实际 {type(source).__name__}: {source!r}"
        )
    model = source.get("model")
    nfft = source.get("nfft", _DEFAULT_NFFT)
    if nfft is None:
        nfft = _DEFAULT_NFFT
    if isinstance(nfft, bool) or not isinstance(nfft, int):
        raise ValueError(f"source['nfft'] 必须为 int（谱图窗长），实际 {nfft!r}")

    # ---- IQ 源解析：三选一 → sigmf_meta 路径（定位不到→提示态行不抛） ----
    if "sigmf_path" in source:
        sigmf_path = source.get("sigmf_path")
        if not isinstance(sigmf_path, str) or not sigmf_path.strip():
            raise ValueError(
                f"source['sigmf_path'] 必须为非空 str（.sigmf-meta 路径），"
                f"实际 {sigmf_path!r}"
            )
        meta_path = sigmf_path.strip()
        missing_note = None
    elif "run_id" in source or "query" in source:
        meta_path, missing_note = _resolve_entry_sigmf(source)
    else:
        raise ValueError(
            "source 须三选一携带 IQ 源：'run_id'（历史运行/录音条目）| "
            f"'sigmf_path'（录音 meta 路径）| 'query'（数据集检索），实际键: "
            f"{sorted(source)}"
        )
    if meta_path is None:
        row = {
            "status": "no_iq",
            "recognized": False,
            "note": missing_note or "IQ 源不可用",
            "iq_source": json.dumps(
                {k: source[k] for k in ("run_id", "sigmf_path", "query") if k in source},
                ensure_ascii=False,
                default=str,
            ),
        }
        row["truth"] = {"source": None, "style": None}
        row["hit"] = None
        return row

    # ---- 推理：predict_style 结果行原样透传（no_model/short_iq 提示态不抛） ----
    row = predict_style(meta_path, model=model, nfft=nfft)
    if not isinstance(row, dict):  # 防御：单源路径恒为 dict
        row = {"status": "bad_iq", "recognized": False, "note": "推理结果行缺失"}
    if row.get("status") == "no_model":
        # R67：模型缺失→提示态非报错——附「先训练」指引（不阻塞主流程）。
        row["note"] = (
            f"{row.get('note', '')}——请先在训练面板发起训练（POST /api/ai/train）"
        )

    # ---- 标准答案对照：SigMF 标注 → 场景副本（皆缺如实 None 不虚构） ----
    truth = _truth_from_sigmf(meta_path)
    if truth is None:
        truth = _truth_from_scenario_copy(meta_path)
    if truth is None:
        truth = {"source": None, "style": None}
    row["truth"] = truth
    if row.get("recognized") and isinstance(truth.get("style"), str):
        row["hit"] = bool(row.get("label") == truth["style"])
    else:
        row["hit"] = None
    return row
