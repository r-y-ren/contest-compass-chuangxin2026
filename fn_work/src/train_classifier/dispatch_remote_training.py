"""训练包远程派发（remote-compute 子进程协议，dry_run 供 CI 验收）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

__all__ = ["RemoteError", "dispatch_remote_training"]

# 必填四键（runner 可选，缺省 'remote-compute'）：路径/入口 str、数据路径列表、超参 dict。
_REQUIRED_KEYS = ("code_root", "data_paths", "hyperparams", "entrypoint")
_KNOWN_RUNNERS = ("remote-compute", "local")
_DEFAULT_RUNNER = "remote-compute"
# 探活超时（B14 规约固定 5s）与真派发超时。
_PROBE_TIMEOUT_S = 5.0
_DISPATCH_TIMEOUT_S = 300.0
# RemoteError 里的 stderr 摘要长度上限，防异常工具刷屏。
_STDERR_TAIL = 600
_UNREACHABLE_MSG = "远程算力不可达——确认 remote-compute 可执行或改 where='local'"


class RemoteError(Exception):
    """远程派发失败：runner 不可达/派发非零退出/派发超时/'local' 误入本函数。"""


def dispatch_remote_training(task_package: dict, *, dry_run: bool = False) -> dict:
    """训练包远程派发到 remote-compute 算力（不实现真实协议，subprocess 调用层形状稳定）。

    task_package 形状：{'code_root': str（训练代码目录，须存在）, 'data_paths': [str]（非空）,
    'hyperparams': dict, 'entrypoint': str（模块.函数）, 'runner': str = 'remote-compute'}。

    - runner='remote-compute'：先形状校验（ValueError；code_root 相对路径先
      os.path.abspath 规范化再校验并入包），再环境发现 runner——shutil.which 命中
      即用；未命中再以 [runner, '--version'] 探活 5s，探活失败（异常/超时/非零退出）抛
      RemoteError（含「远程算力不可达——确认 remote-compute 可执行或改 where='local'」）。
    - hyperparams 序列化预检（B14 中#1）：json.dumps 试探——真派发路径失败即抛
      RemoteError（含「hyperparams 含不可序列化对象」与 TypeError 原文，先于探活
      快速失败）；dry_run 同样探测但不抛，package_summary 附 'serializable': bool
      如实标注（False 不放行绿灯，CI 验收可据此拒收）。
    - dry_run=True：完全不调 subprocess（runner_found 仅以 shutil.which 判定，CI 无工具时
      如实报 False 不抛出），返回 {'dispatched': False, 'dry_run': True, 'runner_found': bool,
      'package_summary': {键摘要}}——CI 验收用。
    - 真派发：包 JSON 序列化到临时文件，subprocess [runner, 'train', '--package', 路径]；
      成功返回 {'dispatched': True, 'runner': 执行体, 'job_id': 解析 stdout 首行, 'returncode': 0}；
      非零退出抛 RemoteError（含 stderr 尾部摘要），超时抛 RemoteError。
    - runner='local'：RemoteError——本地训练路径由调用方 train_classifier 处理，不经远程派发。
    """
    task_package = _validate_package(task_package)
    runner = task_package.get("runner", _DEFAULT_RUNNER)
    if not isinstance(runner, str) or runner not in _KNOWN_RUNNERS:
        raise ValueError(f"runner 必须为 {' 或 '.join(_KNOWN_RUNNERS)}，得到 {runner!r}")
    if runner == "local":
        raise RemoteError("runner='local' 不经远程派发——本地训练路径由调用方 train_classifier 处理")

    serial_err = _probe_hyperparams_serializable(task_package)
    if dry_run:
        summary = _package_summary(task_package, runner)
        summary["serializable"] = serial_err is None
        return {
            "dispatched": False,
            "dry_run": True,
            "runner_found": shutil.which(runner) is not None,
            "package_summary": summary,
        }

    if serial_err is not None:
        raise RemoteError(
            f"hyperparams 含不可序列化对象——真派发无法 JSON 序列化训练包（{serial_err}）"
        )
    exe = _discover_runner(runner)
    return _dispatch(exe, task_package, runner)


def _validate_package(task_package: dict) -> dict:
    """形状校验（dry_run 下同样执行）+ code_root 绝对路径规范化（B14 低#6），
    返回规范化后的包浅拷贝：必填四键齐全、路径/入口为非空 str、data_paths 非空
    [str]、hyperparams 为 dict、code_root（abspath 规范化后）目录存在。
    违例一律 ValueError——相对路径按进程 cwd 解析后再校验、入包。"""
    if not isinstance(task_package, dict):
        raise ValueError(f"task_package 必须为 dict，得到 {type(task_package).__name__}")
    for key in _REQUIRED_KEYS:
        if key not in task_package:
            raise ValueError(f"task_package 缺必填键 {key!r}（必填：{list(_REQUIRED_KEYS)}）")
    code_root = task_package["code_root"]
    if not isinstance(code_root, str) or not code_root:
        raise ValueError(f"code_root 必须为非空 str（训练代码目录），得到 {code_root!r}")
    abs_root = os.path.abspath(code_root)  # 相对路径绝对化：规范化后再校验+入包
    if not os.path.isdir(abs_root):
        raise ValueError(f"code_root 目录不存在：{abs_root!r}")
    data_paths = task_package["data_paths"]
    if not isinstance(data_paths, list) or not data_paths:
        raise ValueError(f"data_paths 必须为非空 [str] 列表，得到 {data_paths!r}")
    for idx, path in enumerate(data_paths):
        if not isinstance(path, str) or not path:
            raise ValueError(f"data_paths[{idx}] 必须为非空 str，得到 {path!r}")
    if not isinstance(task_package["hyperparams"], dict):
        raise ValueError(
            f"hyperparams 必须为 dict，得到 {type(task_package['hyperparams']).__name__}"
        )
    entrypoint = task_package["entrypoint"]
    if not isinstance(entrypoint, str) or not entrypoint:
        raise ValueError(f"entrypoint 必须为非空 str（模块.函数），得到 {entrypoint!r}")
    normalized = dict(task_package)
    normalized["code_root"] = abs_root
    return normalized


def _probe_hyperparams_serializable(task_package: dict) -> str | None:
    """hyperparams JSON 序列化预检（B14 中#1）：json.dumps 试探——可序列化返回
    None；失败返回 '<异常类型>: <原文>'（set/numpy 标量等），供 RemoteError 消息
    与 dry_run 摘要 'serializable' 标注共用。"""
    try:
        json.dumps(task_package["hyperparams"], ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def _package_summary(task_package: dict, runner: str) -> dict:
    """dry_run 返回用的包键摘要：入口/超参原样，数据路径带份数（code_root 已绝对化；
    'serializable' 标注由调用方附上）。"""
    return {
        "runner": runner,
        "code_root": task_package["code_root"],
        "entrypoint": task_package["entrypoint"],
        "hyperparams": dict(task_package["hyperparams"]),
        "data_paths": list(task_package["data_paths"]),
        "data_count": len(task_package["data_paths"]),
    }


def _discover_runner(runner: str) -> str:
    """环境发现 runner：shutil.which 命中返回绝对路径；未命中以 [runner, '--version']
    探活 5s（rc=0 视为可达）。任何探活失败抛含不可达提示的 RemoteError。"""
    found = shutil.which(runner)
    if found:
        return found
    try:
        proc = subprocess.run(
            [runner, "--version"],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RemoteError(f"{_UNREACHABLE_MSG}（探活异常：{exc!r}）") from exc
    if proc.returncode != 0:
        raise RemoteError(f"{_UNREACHABLE_MSG}（探活退出码 {proc.returncode}）")
    return runner


def _dispatch(exe: str, task_package: dict, runner: str) -> dict:
    """真派发：包 JSON 写临时文件→subprocess [exe, 'train', '--package', 路径]。
    非零退出/超时/执行体消失抛 RemoteError（含 stderr 尾部摘要）；成功解析 stdout
    首行为 job_id。临时文件无论成败均清理。"""
    payload = dict(task_package)
    payload.setdefault("runner", runner)
    try:  # 纵深防御：包内不可序列化对象（含必填四键外的附加键）在此兜住转 RemoteError
        blob = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise RemoteError(
            f"任务包含不可 JSON 序列化对象（{type(exc).__name__}: {exc}）——无法落盘派发"
        ) from exc
    fd, package_path = tempfile.mkstemp(prefix="trainpkg_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(blob)
        try:
            proc = subprocess.run(
                [exe, "train", "--package", package_path],
                capture_output=True,
                text=True,
                timeout=_DISPATCH_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as exc:
            raise RemoteError(
                f"远程派发超时（>{_DISPATCH_TIMEOUT_S:.0f}s）：{_exc_stderr(exc) or '无输出'}"
            ) from exc
        except OSError as exc:
            raise RemoteError(f"{_UNREACHABLE_MSG}（派发时执行体不可执行：{exc}）") from exc
    finally:
        try:
            os.remove(package_path)
        except OSError:
            pass
    stderr = proc.stderr or ""
    if proc.returncode != 0:
        raise RemoteError(
            f"远程派发失败（退出码 {proc.returncode}）：{_tail(stderr) or '无 stderr 输出'}"
        )
    return {
        "dispatched": True,
        "runner": exe,
        "job_id": _parse_job_id(proc.stdout),
        "returncode": proc.returncode,
    }


def _parse_job_id(stdout: str) -> str | None:
    """解析 stdout 首个非空行为 job_id：兼容裸值与 'job_id: X'/'job_id=X' 前缀两种口径。"""
    for line in (stdout or "").splitlines():
        text = line.strip()
        if not text:
            continue
        for sep in (":", "="):
            prefix = "job_id" + sep
            if text.startswith(prefix):
                return text[len(prefix):].strip() or None
        return text
    return None


def _tail(stderr: str) -> str:
    """stderr 尾部摘要：超限保留末尾 _STDERR_TAIL 字符。"""
    if len(stderr) <= _STDERR_TAIL:
        return stderr.strip()
    return "..." + stderr[-_STDERR_TAIL:]


def _exc_stderr(exc: subprocess.TimeoutExpired) -> str:
    """TimeoutExpired 携带的 stderr 归一为 str（None→''，bytes→容错解码）。"""
    data = exc.stderr
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)
