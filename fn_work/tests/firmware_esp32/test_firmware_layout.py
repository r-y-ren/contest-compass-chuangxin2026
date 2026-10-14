"""firmware/esp32_wifi 工程镜像自证（R85）：断言 platformio.ini 与 src 四文件在位、
两构建环境（tx/rx）定桩完好。对应 responsibility.md 核验命令「测试: firmware_esp32」。"""
from __future__ import annotations

from pathlib import Path

_FW_DIR = Path(__file__).resolve().parents[2] / "firmware" / "esp32_wifi"

# 工程交付物清单（platformio.ini + src 四文件 + 构建/烧录说明 README）
_EXPECTED_FILES = [
    "platformio.ini",
    "src/main.cpp",
    "src/tasks.cpp",
    "src/tasks.h",
    "src/frame_encoder.cpp",
    "src/frame_encoder.h",
    "README.md",
]


def test_firmware_project_files_present():
    missing = [rel for rel in _EXPECTED_FILES if not (_FW_DIR / rel).is_file()]
    assert not missing, f"firmware/esp32_wifi 缺交付文件: {missing}"


def test_platformio_envs_pinned_tx_rx():
    """两角色环境（tx=NODE_ROLE 1 / rx=NODE_ROLE 2）与串口波特率定桩在位。"""
    ini = (_FW_DIR / "platformio.ini").read_text(encoding="utf-8")
    assert "default_envs = tx, rx" in ini
    assert "[env:tx]" in ini and "-DNODE_ROLE=1" in ini
    assert "[env:rx]" in ini and "-DNODE_ROLE=2" in ini
    assert "monitor_speed = 115200" in ini
