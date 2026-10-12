"""dispatch_remote_training 对抗单测：subprocess/shutil.which 全 mock（slug=dispatch_remote，CI 验收走 dry_run）。"""
from __future__ import annotations

import json
import os
import subprocess

import pytest

from src.train_classifier import dispatch_remote_training as mod
from src.train_classifier.dispatch_remote_training import (
    RemoteError,
    dispatch_remote_training,
)

UNREACHABLE = "远程算力不可达——确认 remote-compute 可执行或改 where='local'"
FAKE_EXE = "/fake/bin/remote-compute"


def _package(tmp_path):
    """合法最小训练包：code_root 为真实临时目录（存在性校验用）。"""
    code_root = tmp_path / "train_code"
    code_root.mkdir()
    return {
        "code_root": str(code_root),
        "data_paths": [str(tmp_path / "a.sigmf"), str(tmp_path / "b.sigmf")],
        "hyperparams": {"lr": 1e-3, "epochs": 3},
        "entrypoint": "seven_cls.train",
    }


def _patch_which(monkeypatch, result):
    """替换模块内 shutil.which；result 为可执行路径或 None。"""
    monkeypatch.setattr(mod.shutil, "which", lambda name: result if result else None)


def _patch_run(monkeypatch, *, stdout="", stderr="", returncode=0, exc=None):
    """替换模块内 subprocess.run；返回 (calls, payloads)——calls 记录 (cmd, kwargs)，
    payloads 记录每次调用时 --package 临时文件的 JSON 内容（文件存在时）。"""
    calls = []
    payloads = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if "--package" in cmd:
            path = cmd[cmd.index("--package") + 1]
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    payloads.append(json.load(fh))
        if exc is not None:
            raise exc
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    return calls, payloads


def _forbid_run(monkeypatch):
    """哨兵：dry_run 下 subprocess.run 被调用即失败。"""

    def guard(cmd, **kwargs):
        raise AssertionError(f"dry_run 不应调用 subprocess：{cmd} {kwargs}")

    monkeypatch.setattr(mod.subprocess, "run", guard)


# --- dry_run：不真调 subprocess，runner_found 仅以 which 判定（CI 验收口径） ---


def test_dry_run_never_calls_subprocess(monkeypatch, tmp_path):
    """dry_run=True：哨兵断言全程不调 subprocess，返回 dispatched=False/dry_run=True。"""
    _patch_which(monkeypatch, FAKE_EXE)
    _forbid_run(monkeypatch)
    result = dispatch_remote_training(_package(tmp_path), dry_run=True)
    assert result["dispatched"] is False
    assert result["dry_run"] is True


def test_dry_run_runner_found_true_when_which_hits(monkeypatch, tmp_path):
    """which 命中可执行→runner_found=True（无需探活）。"""
    _patch_which(monkeypatch, FAKE_EXE)
    result = dispatch_remote_training(_package(tmp_path), dry_run=True)
    assert result["runner_found"] is True


def test_dry_run_runner_found_false_without_raising(monkeypatch, tmp_path):
    """CI 无 remote-compute（which=None）：dry_run 不探活不抛出，如实报 runner_found=False。"""
    _patch_which(monkeypatch, None)
    _forbid_run(monkeypatch)  # 证明未退化为 subprocess 探活
    result = dispatch_remote_training(_package(tmp_path), dry_run=True)
    assert result["runner_found"] is False
    assert result["dispatched"] is False


def test_dry_run_package_summary_carries_entrypoint_and_hyperparams(monkeypatch, tmp_path):
    """dry_run 摘要含 entrypoint/hyperparams 键且取值与包一致（另含 code_root/data 路径）。"""
    _patch_which(monkeypatch, FAKE_EXE)
    package = _package(tmp_path)
    result = dispatch_remote_training(package, dry_run=True)
    summary = result["package_summary"]
    assert summary["entrypoint"] == package["entrypoint"]
    assert summary["hyperparams"] == package["hyperparams"]
    assert summary["code_root"] == package["code_root"]
    assert summary["data_paths"] == package["data_paths"]
    assert summary["data_count"] == 2
    assert summary["runner"] == "remote-compute"


# --- runner 不可达：which 未命中 + 探活失败 → RemoteError 含规约提示 ---


def test_unreachable_when_which_none_and_probe_filenotfound(monkeypatch, tmp_path):
    """which=None 且探活抛 FileNotFoundError→RemoteError 含不可达提示原文。"""
    _patch_which(monkeypatch, None)
    _patch_run(monkeypatch, exc=FileNotFoundError(2, "remote-compute"))
    with pytest.raises(RemoteError) as excinfo:
        dispatch_remote_training(_package(tmp_path))
    assert UNREACHABLE in str(excinfo.value)


def test_unreachable_when_probe_nonzero_exit(monkeypatch, tmp_path):
    """探活能跑但 rc=1（非 0）→同样视为不可达，RemoteError 含提示与退出码。"""
    _patch_which(monkeypatch, None)
    _patch_run(monkeypatch, returncode=1, stderr="broken install")
    with pytest.raises(RemoteError) as excinfo:
        dispatch_remote_training(_package(tmp_path))
    assert UNREACHABLE in str(excinfo.value)
    assert "1" in str(excinfo.value)


def test_unreachable_when_probe_timeout(monkeypatch, tmp_path):
    """探活 5s 超时（TimeoutExpired）→RemoteError 含不可达提示。"""
    _patch_which(monkeypatch, None)
    _patch_run(
        monkeypatch,
        exc=subprocess.TimeoutExpired(cmd=["remote-compute", "--version"], timeout=5.0),
    )
    with pytest.raises(RemoteError) as excinfo:
        dispatch_remote_training(_package(tmp_path))
    assert UNREACHABLE in str(excinfo.value)


# --- 形状校验：缺键/空数据/路径不存在（dry_run 下同样拒绝）→ ValueError ---


def test_missing_required_key_rejected(tmp_path):
    """缺 hyperparams 键→ValueError 点名缺失键。"""
    package = _package(tmp_path)
    del package["hyperparams"]
    with pytest.raises(ValueError, match="hyperparams"):
        dispatch_remote_training(package, dry_run=True)


def test_empty_data_paths_rejected(tmp_path):
    """data_paths=[]（空 list）→ValueError 拒绝。"""
    package = _package(tmp_path)
    package["data_paths"] = []
    with pytest.raises(ValueError, match="data_paths"):
        dispatch_remote_training(package, dry_run=True)


def test_non_str_data_path_rejected(tmp_path):
    """data_paths 混入非 str 元素→ValueError 拒绝。"""
    package = _package(tmp_path)
    package["data_paths"] = ["/data/a.sigmf", 123]
    with pytest.raises(ValueError, match=r"data_paths\[1\]"):
        dispatch_remote_training(package, dry_run=True)


def test_code_root_missing_rejected_even_in_dry_run(tmp_path):
    """code_root 目录不存在→ValueError；dry_run=True 也同样校验拒绝。"""
    package = _package(tmp_path)
    package["code_root"] = str(tmp_path / "no_such_dir")
    with pytest.raises(ValueError, match="code_root"):
        dispatch_remote_training(package, dry_run=True)
    with pytest.raises(ValueError, match="code_root"):
        dispatch_remote_training(package)  # dry_run=False 同拒


def test_task_package_not_dict_rejected():
    """task_package 非 dict→ValueError。"""
    with pytest.raises(ValueError, match="dict"):
        dispatch_remote_training(["not", "a", "dict"], dry_run=True)


# --- runner 分支：'local' 误入与未知 runner ---


def test_local_runner_raises_with_caller_hint(tmp_path):
    """runner='local'→RemoteError 提示本地路径归调用方 train_classifier 处理。"""
    package = _package(tmp_path)
    package["runner"] = "local"
    with pytest.raises(RemoteError) as excinfo:
        dispatch_remote_training(package)
    assert "train_classifier" in str(excinfo.value)


def test_unknown_runner_value_rejected(tmp_path):
    """runner='gpu-cluster'（未知值）→ValueError 形状拒绝。"""
    package = _package(tmp_path)
    package["runner"] = "gpu-cluster"
    with pytest.raises(ValueError, match="runner"):
        dispatch_remote_training(package, dry_run=True)


# --- 真派发：subprocess 全 mock（接口形状稳定，不实现真实 remote-compute 协议） ---


def test_dispatch_success_job_id_and_command_shape(monkeypatch, tmp_path):
    """which 命中→[exe,'train','--package',临时文件] 派发：包 JSON 落盘内容正确、
    job_id 取 stdout 首行、returncode=0、临时文件用后清理。"""
    _patch_which(monkeypatch, FAKE_EXE)
    calls, payloads = _patch_run(monkeypatch, stdout="job-2026-101\nqueued for gpu0\n")
    package = _package(tmp_path)
    result = dispatch_remote_training(package)
    assert result == {
        "dispatched": True,
        "runner": FAKE_EXE,
        "job_id": "job-2026-101",
        "returncode": 0,
    }
    cmd, kwargs = calls[0]
    assert cmd[:3] == [FAKE_EXE, "train", "--package"]
    package_path = cmd[3]
    assert not os.path.exists(package_path)  # 派发后临时文件已清理
    assert payloads == [  # --package 收到的是完整包（runner 缺省已补记）
        dict(package, runner="remote-compute")
    ]
    assert kwargs.get("capture_output") is True
    assert kwargs.get("timeout") == mod._DISPATCH_TIMEOUT_S


def test_dispatch_parses_job_id_prefixed_line(monkeypatch, tmp_path):
    """stdout 首行为 'job_id: j-77' 前缀口径→job_id 解析为裸值 'j-77'。"""
    _patch_which(monkeypatch, FAKE_EXE)
    _patch_run(monkeypatch, stdout="job_id: j-77\ntraining started\n")
    result = dispatch_remote_training(_package(tmp_path))
    assert result["job_id"] == "j-77"


def test_dispatch_nonzero_returncode_raises_with_stderr(monkeypatch, tmp_path):
    """派发 rc=2→RemoteError 含退出码与 stderr 摘要原文。"""
    _patch_which(monkeypatch, FAKE_EXE)
    _patch_run(monkeypatch, returncode=2, stderr="OOM: gpu mem exhausted\n")
    with pytest.raises(RemoteError) as excinfo:
        dispatch_remote_training(_package(tmp_path))
    assert "2" in str(excinfo.value)
    assert "OOM: gpu mem exhausted" in str(excinfo.value)


def test_dispatch_timeout_raises_remote_error(monkeypatch, tmp_path):
    """派发超时（TimeoutExpired）→RemoteError 含超时字样。"""
    _patch_which(monkeypatch, FAKE_EXE)
    _patch_run(
        monkeypatch,
        exc=subprocess.TimeoutExpired(
            cmd=[FAKE_EXE, "train"], timeout=mod._DISPATCH_TIMEOUT_S
        ),
    )
    with pytest.raises(RemoteError) as excinfo:
        dispatch_remote_training(_package(tmp_path))
    assert "超时" in str(excinfo.value)


def test_dispatch_runner_vanished_between_discover_and_spawn(monkeypatch, tmp_path):
    """which 命中但派发瞬间执行体消失（OSError）→RemoteError 含不可达提示。"""
    _patch_which(monkeypatch, FAKE_EXE)
    _patch_run(monkeypatch, exc=FileNotFoundError(2, FAKE_EXE))
    with pytest.raises(RemoteError) as excinfo:
        dispatch_remote_training(_package(tmp_path))
    assert UNREACHABLE in str(excinfo.value)


# --- B14 中#1 序列化逃逸：hyperparams JSON 序列化预检（真派发拒/dry_run 标注） ---


def test_real_dispatch_rejects_unserializable_hyperparams_before_probe(monkeypatch, tmp_path):
    """真派发前预检：hyperparams 含 set 值 json.dumps 失败→RemoteError 含
    「hyperparams 含不可序列化对象」与 TypeError 原文（含类型名）；预检先于
    runner 探活——which 未命中也不调 subprocess。"""
    _patch_which(monkeypatch, None)
    _forbid_run(monkeypatch)
    package = _package(tmp_path)
    package["hyperparams"] = {"lr": 1e-3, "tags": {1, 2}}
    with pytest.raises(RemoteError) as excinfo:
        dispatch_remote_training(package)
    msg = str(excinfo.value)
    assert "hyperparams 含不可序列化对象" in msg
    assert "TypeError" in msg
    assert "set" in msg  # TypeError 原文点名不可序列化类型


def test_dry_run_summary_flags_unserializable_hyperparams_no_green_light(monkeypatch, tmp_path):
    """dry_run 同样探测但不抛：package_summary 附 'serializable': False
    （不放行绿灯——CI 验收可据此拒收），dispatched 仍 False。"""
    _patch_which(monkeypatch, FAKE_EXE)
    _forbid_run(monkeypatch)
    package = _package(tmp_path)
    package["hyperparams"] = {"tags": {"a", "b"}}
    result = dispatch_remote_training(package, dry_run=True)
    assert result["dispatched"] is False
    assert result["package_summary"]["serializable"] is False


def test_dry_run_summary_serializable_true_for_plain_hyperparams(monkeypatch, tmp_path):
    """合法 hyperparams（纯 JSON 域）→ dry_run 摘要 'serializable': True。"""
    _patch_which(monkeypatch, FAKE_EXE)
    result = dispatch_remote_training(_package(tmp_path), dry_run=True)
    assert result["package_summary"]["serializable"] is True


# --- B14 低#6 相对路径：code_root abspath 规范化后再校验+入包 ---


def test_relative_code_root_normalized_to_absolute_in_payload(monkeypatch, tmp_path):
    """code_root='.'（相对）→ 按进程 cwd 绝对化后入包：真派发 payload 收到绝对路径。"""
    monkeypatch.chdir(tmp_path)
    _patch_which(monkeypatch, FAKE_EXE)
    calls, payloads = _patch_run(monkeypatch, stdout="job-rel-1\n")
    package = _package(tmp_path)
    package["code_root"] = "."
    result = dispatch_remote_training(package)
    assert result["dispatched"] is True
    assert payloads[0]["code_root"] == str(tmp_path)
    assert os.path.isabs(payloads[0]["code_root"])


def test_relative_code_root_normalized_in_dry_run_summary(monkeypatch, tmp_path):
    """dry_run 摘要同样透传绝对化后的 code_root（'.' → cwd 绝对路径）。"""
    monkeypatch.chdir(tmp_path)
    _patch_which(monkeypatch, FAKE_EXE)
    package = _package(tmp_path)
    package["code_root"] = "."
    result = dispatch_remote_training(package, dry_run=True)
    assert result["package_summary"]["code_root"] == str(tmp_path)
    assert result["package_summary"]["code_root"] != "."


def test_relative_code_root_resolved_against_cwd_not_literal(monkeypatch, tmp_path):
    """相对路径按进程 cwd 解析后校验：'./train_code' 在 cwd=tmp 下存在→通过；
    同一字符串换 cwd 到别处（目录不存在）→ ValueError 拒。"""
    _patch_which(monkeypatch, FAKE_EXE)
    package = _package(tmp_path)
    package["code_root"] = "./train_code"
    monkeypatch.chdir(tmp_path)
    assert dispatch_remote_training(package, dry_run=True)["dry_run"] is True
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    with pytest.raises(ValueError, match="code_root"):
        dispatch_remote_training(package, dry_run=True)
