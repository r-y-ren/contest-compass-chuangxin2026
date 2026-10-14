"""AI 训练任务：train_classifier 触发（remote/local/dry_run）后台任务+状态轮询+模型列表；拒训信息原样上屏——重写规约与签名意图详见 fn_docs/responsibility.md（R65 launch_classifier_training L0；调用方 mount_console_extensions）。

落地口径（R65）：

- 任务表自建键空间（模块级 ``_TASKS`` dict+锁——复用 /api/run 的 app.state.runs
  运行表模式，但不与操控台运行表混键）：``launch_classifier_training(params)``
  注册任务→后台线程调 train_classifier→终态 done（附 result）/failed（附 error
  原文——TrainError 拒训信息原样上屏，不吞不改写）；``get_training_task``
  供 GET /api/ai/train/{task_id} 轮询；
- params 契约：``{'query': 数据集检索条件 dict（必填，原样透传 train_classifier→
  index_dataset('query')——数据筛选）, 'where': 'remote'|'local'（缺省 'remote'）,
  'dry_run': bool（缺省 False——remote 不真派发，dispatched=False）,
  'hyperparams': dict|None（nfft/min_samples/out_path/index_path/runs_root/
  code_root/entrypoint 等，原样透传 train_classifier）}``；
- 模型文件列表：``list_model_files(models_root)`` 扫描 run 目录根下 models/
  的 *.json 模型条目（name/path/size_bytes/modified_at/labels——labels 读
  JSON 根对象 'labels' 键，损坏文件 labels=None 如实标注不剔除）；
- 形状错（params 非 dict/query 非 dict/where 非法/hyperparams 非 dict）在
  注册前 ValueError 先拒；训练期一切异常（TrainError/RemoteError 包装/
  ValueError 族）只落任务表 failed——绝不炸调用方（端点 202 后异步观测）。
"""
import json
import os
import threading
import uuid
from datetime import datetime, timezone

from src.train_classifier.train_classifier import train_classifier

__all__ = [
    "DEFAULT_WHERE",
    "MODELS_DIRNAME",
    "get_training_task",
    "launch_classifier_training",
    "list_model_files",
]

#: 执行地缺省（remote——派发 remote-compute；网页表单可显式 where='local' 降级）。
DEFAULT_WHERE = "remote"

#: run 目录根（report_root）下模型目录名（train_classifier out_path 约定落点）。
MODELS_DIRNAME = "models"

#: 训练任务表（自建键空间——task_id → 任务条目；读写全程持锁）。
_TASKS: dict = {}

_TASKS_LOCK = threading.Lock()


def _task_snapshot(task_id: str) -> dict:
    """任务条目浅拷贝快照（读侧不暴露可变内部——轮询响应形状稳定）。"""
    with _TASKS_LOCK:
        entry = _TASKS.get(task_id)
        return dict(entry) if isinstance(entry, dict) else None


def get_training_task(task_id: object) -> "dict | None":
    """训练任务状态查询（GET /api/ai/train/{task_id} 轮询口径）。

    输入: task_id（str）；输出: 任务条目浅拷贝 dict | None（未知 id→None）。
    条目形状：{'task_id', 'status': 'running'|'done'|'failed', 'created_at',
    'query', 'where', 'dry_run', 'result'?（done 附 train_classifier 返回）,
    'error'?（failed 附 f'{类型名}: {原文}'——拒训信息原样）}。
    """
    if not isinstance(task_id, str) or not task_id:
        return None
    return _task_snapshot(task_id)


def list_model_files(models_root: object) -> list:
    """run 目录根下 models/ 的模型文件列表（GET /api/ai/models 口径）。

    输入: models_root（str 路径——约定 report_root/models）；目录缺失/不可读
    → 空列表（未训练提示态，不报错）。输出: 条目 list（mtime 新在前）：
    [{'name': 文件名, 'path': 绝对路径, 'size_bytes': int, 'modified_at':
    ISO 时间戳, 'labels': list[str]|None（JSON 根对象 'labels' 键——损坏/
    非 JSON/无键→None 如实标注）}]——仅 *.json（train_classifier 落盘形状）。
    """
    if not isinstance(models_root, str) or not models_root.strip():
        return []
    if not os.path.isdir(models_root):
        return []
    rows: list = []
    try:
        names = os.listdir(models_root)
    except OSError:
        return []
    for name in sorted(names):
        if not name.endswith(".json"):
            continue
        path = os.path.join(models_root, name)
        try:
            stat = os.stat(path)
        except OSError:
            continue  # 竞态消失条目：跳过不炸
        labels = None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            raw_labels = payload.get("labels") if isinstance(payload, dict) else None
            if isinstance(raw_labels, list) and all(
                isinstance(item, str) and item for item in raw_labels
            ):
                labels = list(raw_labels)
        except (OSError, ValueError):
            labels = None  # 损坏模型文件：labels=None 如实标注不剔除
        rows.append(
            {
                "name": name,
                "path": os.path.abspath(path),
                "size_bytes": int(stat.st_size),
                "modified_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
                "labels": labels,
            }
        )
    rows.sort(key=lambda row: row["modified_at"], reverse=True)  # 新训练在前
    return rows


def launch_classifier_training(params: dict) -> dict:
    """AI 训练任务：train_classifier 触发（remote/local/dry_run）后台任务+状态轮询+模型列表；拒训信息原样上屏（详见 fn_docs/responsibility.md 功能块）。

    输入:
        params: 训练参数 dict——{'query': 数据集检索条件 dict（必填，
            train_classifier→index_dataset('query') 数据筛选，支持 style/
            freq_range/date_range/backend/failed/batch_key）, 'where':
            'remote'|'local'（缺省 'remote'——远程派发；'local' 显式本地降级）,
            'dry_run': bool（缺省 False；True 透传 dispatch_remote_training
            ——不真派发，dispatched=False）, 'hyperparams': dict|None（nfft/
            min_samples/out_path/index_path/runs_root/code_root/entrypoint
            等训练超参与落点选项，原样透传 train_classifier）}。

    输出:
        任务句柄 dict：{'task_id': str（uuid hex——任务表键）, 'status':
        'running', 'created_at': ISO 时间戳, 'query': 原样回显, 'where': str,
        'dry_run': bool}——终态经 get_training_task(task_id) 轮询（done 附
        train_classifier 完整返回 / failed 附错误原文）。

    错误:
        ValueError: params 非 dict / 缺 'query' 或 query 非 dict / where 非
            'remote'|'local' / dry_run 非 bool / hyperparams 非 dict|None
            （形状错注册前先拒——与 train_classifier 同口径）。
        训练期异常（TrainError 拒训/RemoteError 远程不可达/IO 等）**不抛**：
            任务表 status='failed'+error=f'{类型名}: {原文}'（异步观测）。
    """
    if not isinstance(params, dict):
        raise ValueError(
            f"params 必须为 dict（训练参数），实际 {type(params).__name__}: {params!r}"
        )
    query = params.get("query")
    if not isinstance(query, dict):
        raise ValueError(
            f"params['query'] 必须为 dict（数据集检索条件——train_classifier 数据筛选），"
            f"实际 {type(query).__name__}: {query!r}"
        )
    where = params.get("where", DEFAULT_WHERE)
    if where is None:
        where = DEFAULT_WHERE
    if not isinstance(where, str) or where not in ("remote", "local"):
        raise ValueError(f"params['where'] 必须为 'remote' 或 'local'，实际 {where!r}")
    dry_run = params.get("dry_run", False)
    if not isinstance(dry_run, bool):
        raise ValueError(f"params['dry_run'] 必须为 bool，实际 {dry_run!r}")
    hyperparams = params.get("hyperparams")
    if hyperparams is None:
        hyperparams = {}
    if not isinstance(hyperparams, dict):
        raise ValueError(
            f"params['hyperparams'] 必须为 dict | None（训练超参），"
            f"实际 {type(hyperparams).__name__}"
        )

    task_id = uuid.uuid4().hex[:12]
    entry = {
        "task_id": task_id,
        "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "query": dict(query),
        "where": where,
        "dry_run": dry_run,
    }
    with _TASKS_LOCK:
        _TASKS[task_id] = entry

    def _train_in_background() -> None:
        # 训练一切异常只落任务表——绝不炸线程（端点 202 后异步观测，拒训信息原样）。
        try:
            result = train_classifier(
                query, hyperparams=dict(hyperparams), where=where, dry_run=dry_run
            )
        except BaseException as exc:  # noqa: BLE001 - 后台线程隔离边界
            with _TASKS_LOCK:
                entry["status"] = "failed"
                entry["error"] = f"{type(exc).__name__}: {exc}"
            return
        with _TASKS_LOCK:
            entry["status"] = "done"
            entry["result"] = result

    threading.Thread(
        target=_train_in_background, daemon=True, name=f"ai-train-{task_id}"
    ).start()
    return dict(entry)
