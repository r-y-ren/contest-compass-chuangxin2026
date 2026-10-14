"""预跑演示历史运行（R76 L1）：按配置逐轮走 run_demo 既有入口落 runs/（含带标注 SigMF 录音供录音库/AI 页翻阅）；--demo 口径 exit 1=测到失效属预期产出；单轮意外失败即中止不吞错——重写规约与签名意图详见 fn_docs/responsibility.md。

入口选择（落点口径，相对签名意图的申报项）：run_demo CLI 的 runs_root 硬编码
'runs'（相对 cwd）且逐轮打 stdout 摘要、台账缺省启用——与本级 runs_root 参数
直接冲突；改走同文件无头等价入口 run_scenario（R44 双入口共享同一
_execute_pipeline：场景装载后经 backend='sim' 与 out_root=runs_root 进同一
执行/采集/报告/溯源管线，退出码 0/1/2 三态同口径，台账缺省不动）。落点机制
本身（manage_run runs_root 自动创建+同秒 -2/-3 去重）即 run_demo 现状，仅把
runs_root 经无头入口传到位。

场景装载走 load_scenario（与 CLI 文件路线同一装载器）：LoadScenarioError 即
CLI 的 exit 2（场景写错）口径——按单轮意外失败中止。

预期退出码（简化口径，R76 签名意图）：exit∈{0,1} 均算成功——0=跑完未失效；
1=国标测法测到失效=核心产出，如实登记不算失败；2 或单轮异常崩溃=意外失败，
抛 PrewarmDemoRunError 即时中止并附已跑清单（不吞错：装载/崩溃异常经
__cause__ 链保留原异常）。
"""
from __future__ import annotations

from pathlib import Path

from src.load_scenario.load_scenario import ScenarioError as LoadScenarioError
from src.load_scenario.load_scenario import load_scenario
from src.run_demo.run_demo import (
    EXIT_OK,
    EXIT_RUN_FAILED,
    EXIT_VALIDATION_FAILED,
    run_scenario,
)

__all__ = ["PrewarmDemoRunError", "prewarm_demo_runs"]

#: 预期退出码集合（--demo 口径：1=测到失效属预期产出，不算失败；2=场景写错）。
_EXPECTED_EXIT_CODES = frozenset({EXIT_OK, EXIT_RUN_FAILED})


class PrewarmDemoRunError(RuntimeError):
    """预跑单轮意外失败（exit 2 或崩溃）的中止信号（R76：不吞错，如实上报）。

    属性:
        runs: 中止前已跑清单 [(运行目录, 退出码), ...]（场景主序逐轮追加；
            意外失败轮本身不入清单，归 scenario/round_index/exit_code/detail）。
        scenario: 意外失败的场景名（调用方传入的原名）。
        round_index: 该场景内第几轮（0 起）。
        exit_code: 意外退出码（装载失败按 CLI 口径记 2；单轮异常记 None）。
        detail: 失败原因文本。
    """

    def __init__(
        self,
        message: str,
        *,
        runs: "list[tuple[str | None, int]]",
        scenario: str,
        round_index: int,
        exit_code: "int | None",
        detail: str,
    ) -> None:
        super().__init__(message)
        self.runs = runs
        self.scenario = scenario
        self.round_index = round_index
        self.exit_code = exit_code
        self.detail = detail


def prewarm_demo_runs(
    scenarios: list[str],
    runs_root: str | Path,
    *,
    rounds: int = 3,
    scenario_dir: str | Path | None = None,
) -> dict:
    """按配置预跑若干轮 sim 运行（场景取预置集，逐轮走 run_demo 既有管线）。

    输入: 场景名清单（不带路径，与 seed_preset_scenarios 写入的文件名对应；
        scenario_dir 在位且名非绝对路径时按其拼接，否则按原名作路径）+
        runs_root（运行目录基础路径，manage_run 自动创建）+ rounds 每场景
        轮数（缺省 3）。
    输出: {"runs": [(运行目录, 退出码), ...]}——场景主序（逐场景逐轮追加），
        条目数=len(scenarios)×rounds；exit 0/1 均如实登记（1=测到失效=
        核心产出，不算失败）。
    错误: rounds<1 或非 int→ValueError（编程错早暴露）；单轮意外（场景装载
        失败=exit 2 口径 / run_scenario 退出码 2 / 单轮异常崩溃）→抛
        PrewarmDemoRunError 即时中止并附已跑清单（不吞错——装载/崩溃异常经
        __cause__ 链保留）。
    """
    if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1:
        raise ValueError(
            f"rounds 须为 ≥1 的整数（每场景预跑轮数配置），实际收到 {rounds!r}"
        )

    root = str(runs_root)
    runs: list[tuple[str | None, int]] = []
    #: 消息用逐轮留痕（场景名+轮次+目录+退出码）——与 runs 同步追加，中止时
    #: 「列已跑清单」可读（runs 契约形状不变，仅 (目录, 码) 二元组）。
    trace: list[str] = []
    for name in scenarios:
        # 场景路径解析：scenario_dir 在位且名非绝对 → 拼接；否则按原名作路径
        # （绝对路径名或 scenario_dir=None——兼容直传路径的调用方）。
        path = (
            Path(scenario_dir) / name
            if scenario_dir is not None and not Path(name).is_absolute()
            else Path(name)
        )
        for round_index in range(rounds):
            # ---- 装载（CLI 文件路线同一装载器；失败=exit 2 场景写错口径） ----
            try:
                scenario = load_scenario(str(path))
            except LoadScenarioError as exc:
                raise PrewarmDemoRunError(
                    f"预跑意外失败即中止: 场景={name} 第{round_index + 1}/{rounds}轮"
                    f" 场景装载失败（exit 2 口径）；已跑 {len(runs)} 轮: {trace}",
                    runs=runs,
                    scenario=name,
                    round_index=round_index,
                    exit_code=EXIT_VALIDATION_FAILED,
                    detail=f"{type(exc).__name__}: {exc}",
                ) from exc
            # ---- 单轮运行（无头等价入口：同一执行管线，backend=sim，台账不动） ----
            try:
                outcome = run_scenario(scenario, backend="sim", out_root=root)
            except Exception as exc:  # noqa: BLE001 - 单轮任何崩溃=意外失败中止（不吞错）
                raise PrewarmDemoRunError(
                    f"预跑意外失败即中止: 场景={name} 第{round_index + 1}/{rounds}轮"
                    f" 运行崩溃；已跑 {len(runs)} 轮: {trace}",
                    runs=runs,
                    scenario=name,
                    round_index=round_index,
                    exit_code=None,
                    detail=f"{type(exc).__name__}: {exc}",
                ) from exc
            code = outcome.get("exit_code")
            if code in _EXPECTED_EXIT_CODES:
                # 0=跑完未失效 / 1=测到失效（核心产出）——如实登记不算失败。
                run_dir = outcome.get("run_dir")
                runs.append((run_dir, code))
                trace.append(
                    f"{name}#{round_index + 1} run={run_dir} exit={code}"
                )
                continue
            # ---- 意外退出码（2=场景写错；未知码同口径防御）→ 即时中止不吞错 ----
            raise PrewarmDemoRunError(
                f"预跑意外失败即中止: 场景={name} 第{round_index + 1}/{rounds}轮"
                f" exit={code!r}（预期 0/1——1=测到失效属预期产出；2=场景写错）；"
                f"已跑 {len(runs)} 轮: {trace}",
                runs=runs,
                scenario=name,
                round_index=round_index,
                exit_code=code if isinstance(code, int) else None,
                detail=str(outcome.get("error") or outcome.get("summary") or code),
            )
    return {"runs": runs}
