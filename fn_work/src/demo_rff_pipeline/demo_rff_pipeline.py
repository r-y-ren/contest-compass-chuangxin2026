"""RFF 管道演示入口：run_rff_pipeline smoke 各阶段进度+产物清单；数据不足拒跑
提示——重写规约与签名意图详见 fn_docs/responsibility.md（R74 demo_rff_pipeline
L0；调用方 mount_console_extensions）。

落地口径（R74，沿用 R55 run_rff_pipeline 口径）：

- smoke 小样本固定参数：nfft=128、min_samples=4、k=3（演示缺省——秒级完成；
  params['hyperparams'] 同键覆盖——显式给出则尊重）；query 缺省 {}（全量条目）；
- params 可选键：``'query'``（检索条件 dict|None）、``'hyperparams'``
  （dict|None）、``'index_path'``/``'runs_root'``（索引落点——缺省由端点层
  注入操控台 report_root 口径，本函数不注入缺省、只透传显式值）；params 非
  dict → ValueError；
- 阶段进度：取数（fetch：匹配条目数）→谱特征（features：有效样本/跳段）→
  分组 CV（grouped_cv：k 折+macro_f1）→部署模拟（deploy：本地推理端点+
  参数量）——四阶段 done 明细+``stage_progress`` 计数（阶段产物全出自
  run_rff_pipeline 单次返回，不重复跑管道）；
- 产物清单：model（最近质心分类器——labels/参数量/train_meta 蒸馏）、
  evaluation（混淆矩阵/macro_f1/per_fold）、deployment（endpoint+
  model_meta+latency_note='simulated' 缺位申报）；
- 数据不足拒跑（TrainError 原样上抛——R55 口径：查询零匹配/有效样本不足/
  类别覆盖 <2/分组不可行，消息附数与阈值；端点层转 400 拒跑提示上屏不静默）。
"""
from src.run_rff_pipeline.run_rff_pipeline import TrainError, run_rff_pipeline

__all__ = [
    "DEMO_NFFT",
    "DEMO_MIN_SAMPLES",
    "DEMO_K",
    "RFF_STAGES",
    "demo_rff_pipeline",
]

#: smoke 缺省窗长（与 make_spectrogram 缺省同族的小窗——秒级口径）。
DEMO_NFFT = 128

#: smoke 缺省有效样本下限（小样本演示阈值；正式口径 20 由 R55 缺省承载）。
DEMO_MIN_SAMPLES = 4

#: smoke 缺省分组折数（≥2——小样本可分组）。
DEMO_K = 3

#: 演示阶段序（进度条目顺序契约——页区渲染锚点）。
RFF_STAGES = ("fetch", "features", "grouped_cv", "deploy")

#: 演示视图的诚实基注（smoke 小样本+时延缺位申报口径）。
_SIM_NOTE = (
    "RFF 管道演示为 smoke 小样本固定参数口径（nfft/min_samples/k 取演示缺省，"
    "非正式训练参数）；部署模拟为本地推理端点（local-inference），时延缺位申报 "
    "latency_note='simulated'（非实测——R55 口径）"
)


def demo_rff_pipeline(params: dict | None = None) -> dict:
    """RFF 管道演示入口：run_rff_pipeline smoke 各阶段进度+产物清单；数据不足
    拒跑提示（详见 fn_docs/responsibility.md 功能块）。

    输入:
        params: 演示参数 dict|None——``'query'``（检索条件 dict|None→{}）、
            ``'hyperparams'``（dict|None→与演示缺省合并，同键覆盖）、
            ``'index_path'``/``'runs_root'``（可选 str，透传 run_rff_pipeline；
            缺省落点由端点层注入操控台口径）。

    输出:
        演示视图 dict：{'ok': True, 'smoke': True, 'params_effective':
        {'query','nfft','min_samples','k'}, 'stages': [{'stage','status':
        'done','detail'}, ...]（fetch/features/grouped_cv/deploy 序）,
        'stage_progress': '4/4', 'artifacts': [model/evaluation/deployment
        产物行], 'evaluation': grouped_cv_evaluate 完整结果, 'deployment':
        部署模拟报告, 'model_meta': 蒸馏元数据, 'n_samples', 'skipped',
        'note': 诚实基注}。

    错误:
        ValueError: params/query/hyperparams 形状错（含 run_rff_pipeline 透传的
            超参域错）。
        TrainError: 数据不足拒跑（查询零匹配/有效样本 <min_samples/类别覆盖
            <2/评测分组不可行——原文附数与阈值上抛）。
    """
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError(
            f"params 必须为 dict | None（演示参数——query/hyperparams/索引落点），"
            f"实际: {params!r}"
        )
    query = params.get("query")
    if query is None:
        query = {}
    if not isinstance(query, dict):
        raise ValueError(
            f"params['query'] 必须为 dict | None（检索条件，透传 index_dataset），"
            f"实际: {query!r}"
        )
    hyperparams = params.get("hyperparams")
    if hyperparams is None:
        hyperparams = {}
    if not isinstance(hyperparams, dict):
        raise ValueError(
            f"params['hyperparams'] 必须为 dict | None（训练超参），"
            f"实际: {hyperparams!r}"
        )
    hp = {"nfft": DEMO_NFFT, "min_samples": DEMO_MIN_SAMPLES, "k": DEMO_K}
    hp.update(hyperparams)
    dataset_config: dict = {"query": query}
    for key in ("index_path", "runs_root"):
        if params.get(key) is not None:
            if not isinstance(params[key], str) or not params[key].strip():
                raise ValueError(
                    f"params[{key!r}] 必须为非空 str（索引落点）| None，"
                    f"实际: {params[key]!r}"
                )
            dataset_config[key] = params[key].strip()

    outcome = run_rff_pipeline(dataset_config, hp)
    n_samples = int(outcome["n_samples"])
    skipped = int(outcome["skipped"])
    evaluation = outcome["evaluation"]
    deployment = outcome["deployment"]
    model_meta = deployment["model_meta"]
    stages = [
        {
            "stage": "fetch",
            "status": "done",
            "detail": f"数据集检索命中 {n_samples + skipped} 条（query={query!r}）",
        },
        {
            "stage": "features",
            "status": "done",
            "detail": (
                f"谱特征化（nfft={hp['nfft']}）：有效样本 {n_samples}，"
                f"跳段 {skipped}"
            ),
        },
        {
            "stage": "grouped_cv",
            "status": "done",
            "detail": (
                f"分组 CV（k={hp['k']}，batch_key=run_id 防泄漏）：macro_f1="
                f"{evaluation['macro_f1']:.4f}"
            ),
        },
        {
            "stage": "deploy",
            "status": "done",
            "detail": (
                f"部署模拟：endpoint={outcome['endpoint']}，参数量 "
                f"{model_meta['n_params']}（质心 {model_meta['n_centroids']}×"
                f"维度 {model_meta['n_features']}，latency_note=simulated）"
            ),
        },
    ]
    artifacts = [
        {
            "name": "model",
            "kind": "centroid 最近质心分类器",
            "labels": model_meta["labels"],
            "n_params": model_meta["n_params"],
            "n_train_samples": model_meta["n_train_samples"],
        },
        {
            "name": "evaluation",
            "kind": "grouped_cv_evaluate 分组评测",
            "macro_f1": evaluation["macro_f1"],
            "n_folds": len(evaluation.get("per_fold", [])),
        },
        {
            "name": "deployment",
            "kind": "本地推理端点部署模拟",
            "endpoint": outcome["endpoint"],
            "latency_note": deployment["latency_note"],
        },
    ]
    return {
        "ok": True,
        "smoke": True,
        "params_effective": {
            "query": query,
            "nfft": hp["nfft"],
            "min_samples": hp["min_samples"],
            "k": hp["k"],
        },
        "stages": stages,
        "stage_progress": f"{len(stages)}/{len(RFF_STAGES)}",
        "artifacts": artifacts,
        "evaluation": evaluation,
        "deployment": deployment,
        "model_meta": model_meta,
        "n_samples": n_samples,
        "skipped": skipped,
        "note": _SIM_NOTE,
    }
