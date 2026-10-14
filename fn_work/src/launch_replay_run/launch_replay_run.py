"""replay 一键回放编排：录音条目→build_replay_scenario 组装→经操控台 runner 发起；
损坏录音装载期报错——重写规约与签名意图详见 fn_docs/responsibility.md（R64
launch_replay_run L0）。

编排链（一键回放）：
① build_replay_scenario(entry) 组装 replay 场景（声明缺失/文件不可读/
  来源场景不可得→ScenarioError 装载期即抛——错误消息进操控台响应上屏，不进
  后台线程后知后觉）；
② replay 后端注册表登记（import 副作用——run_demo 管线不主动 import
  open_replay_backend，本编排是 replay 后端的注册现场，缺此步 autodetect_backend
  查不到 'replay' 名）；
③ 经操控台 runner（/api/run 同一后台线程执行器注入的 scenario→result callable）
  发起：runner 内部经 run_scenario 的 validate→guard→normalize 三件套再过闸
  （红线二次把关）后真跑 replay 后端——回放过程在实时曲线与报告中心可见。

返回契约：{'run_id': 回放运行目录名（None=未建目录，如校验失败）, 'status':
'completed'|'failed'|…（runner 结果原值）, 'exit_code': 0|1|2（R44 三态口径）,
'run_dir': str|None, 'backend': 'replay', 'scenario': 组装场景（审计留痕）,
'result': runner 返回的完整结果 dict}——操控台 /api/run/replay 端点把它并入
运行表条目（轮询 GET /api/runs/{id} 可见 exit_code 终态）。
"""
import os

from .build_replay_scenario import build_replay_scenario
from .build_replay_scenario import ScenarioError  # noqa: F401 - 重导出（调用方错误契约）

__all__ = ["ScenarioError", "launch_replay_run"]


def launch_replay_run(entry: dict, runner) -> dict:
    """replay 一键回放编排：录音条目→组装场景→经操控台 runner 发起（详见
    fn_docs/responsibility.md 功能块）。

    输入:
        entry: 录音条目元数据 dict（契约见 build_replay_scenario docstring——
            sigmf_path/speed/source_scenario/run_id 等）。
        runner: 操控台运行执行器 callable（scenario dict→result dict——
            /api/run 的后台线程同款 deps['runner']；缺省装配为 serve_console
            的真实运行器，replay 场景经 run_scenario 真跑 replay 后端）。

    输出:
        回放运行句柄 dict（契约见模块 docstring——run_id/status/exit_code/
        run_dir/backend/scenario/result）。

    错误:
        ValueError: runner 不可调用（编程错误早暴露）。
        ScenarioError: 录音损坏/声明缺失等装载期拒绝（build_replay_scenario
            透传——调用方（操控台端点）转错误信息进响应上屏）。
        其余 runner 内部异常原样上抛（操控台运行表隔离边界归端点后台线程）。
    """
    if not callable(runner):
        raise ValueError(
            f"runner 必须可调用（scenario dict→result dict，操控台 /api/run 同款"
            f" 执行器），实际: {runner!r}"
        )
    scenario = build_replay_scenario(entry)  # 装载期组装（拒绝即抛，不进后台）

    # replay 后端注册现场（import 副作用登记注册表；幂等 override）——run_demo
    # 管线不主动 import 本模块族，缺此步 autodetect_backend 查不到 'replay'。
    import src.open_replay_backend.open_replay_backend  # noqa: F401 - 注册副作用

    result = runner(scenario)
    if not isinstance(result, dict):
        raise ValueError(
            f"runner 返回值必须为结果 dict（run_scenario 契约），实际 "
            f"{type(result).__name__}: {result!r}"
        )
    run_dir = result.get("run_dir")
    run_id = None
    if isinstance(run_dir, str) and run_dir.strip():
        run_id = os.path.basename(run_dir.rstrip(os.sep)) or None
    return {
        "run_id": run_id,
        "status": result.get("status"),
        "exit_code": result.get("exit_code"),
        "run_dir": run_dir if isinstance(run_dir, str) else None,
        "backend": "replay",
        "scenario": scenario,
        "result": result,
    }
