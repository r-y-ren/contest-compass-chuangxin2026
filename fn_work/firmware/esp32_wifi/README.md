# ESP32 WiFi 被测链路固件（R85）

两块 ESP32 组成 WiFi UDP 被测链路：**tx 节点**按固定节拍向 **rx 节点**发定长 UDP 载荷
（前 8 字节为递增 seq 的 ASCII 十进制）；**rx 节点**按 seq 缺口/重复统计丢包与应用层重发计数，
周期经 USB 串口吐 KPI 帧——`ESP,<seq>,<sent>,<err>,<retries>,<rssi>[*<hex>]`，
与主机侧 `fn_work/src/drive_esp32_link/parse_esp32_frame.py`（协议唯一真值）逐字对齐。
角色经构建环境区分（`pio run -e tx` / `pio run -e rx`），同一份源码两种映像。

## 拓扑（定桩：成对节点）

```
[tx 节点 ESP32]                        [rx 节点 ESP32]
 STA (LINK_SSID/LINK_PASS)  ~~WiFi~~>  SoftAP 192.168.4.1（同一凭据）
 udp_stream_task                        kpi_report_task
  · 每 20ms 发 1 包                      · UDP :3333 收包
  · 载荷 256B 定长                       · seq 缺口→err、重复→retries
  · 前 8B=seq（%08lu 零填充）            · 最大 seq→sent
  · 发往 192.168.4.1:3333               · 每 500ms 吐一帧到串口 115200
                                      |
                                      +--> USB 串口 115200 → 主机 parse_esp32_frame
```

## 接线

无需接线：两板各自 USB 供电（或 5V 供电），使用板载天线即可，靠空气中 WiFi 信道
（SoftAP 默认信道 1）互通。烧录与串口监视各占一个 USB 口；只有一台电脑时也可先后
复用同一口（先烧录/监视 rx，再换 tx）。

## 构建与烧录

PlatformIO 已装入 `fn_work/.venv`（不动全局）。在 `fn_work/firmware/esp32_wifi/` 目录执行：

```bash
# rx 节点（接收+KPI 上报）：构建 / 烧录 / 串口监视（115200）
../../.venv/bin/pio run -e rx
../../.venv/bin/pio run -e rx -t upload
../../.venv/bin/pio run -e rx -t monitor        # Ctrl+] 退出

# tx 节点（发送流）：构建 / 烧录 / 串口监视（115200）
../../.venv/bin/pio run -e tx
../../.venv/bin/pio run -e tx -t upload
../../.venv/bin/pio run -e tx -t monitor
```

先上电/烧录 rx（AP 就绪），再上电 tx（STA 才有目标可连）。串口监视波特率 115200
（`platformio.ini` 已定 `monitor_speed`）。

## 串口帧示例

rx 节点串口输出（每 500ms 一行，`\r\n` 结尾）：

```
ESP,1200,1200,3,0,NA*3c
ESP,1225,1225,3,0,NA*4a
```

纯 SoftAP 节点读不到 STA RSSI → 帧中 rssi 恒为 `NA`（见下方口径）；若 R87 联调改用
STA+AP 共存模式，数值形态为 `ESP,2400,2400,6,1,-58.0*af`（**格式示意，非实测值**）。
校验和=帧体（`ESP` 起、`*` 前）字节和 `& 0xFF`，两位小写十六进制（解析侧大小写均可）。

## 计数口径声明

- `sent` = 期望包数 = rx 已见最大 seq（tx 的 seq 从 1 起，8 位十进制零填充于载荷前 8 字节）；
- `err` = seq 缺口累计 = Σ(新最大 seq − 旧最大 seq − 1)；
- `retries` = 重复/回退包累计（seq ≤ 已见最大 seq 的到达包按重复计）；
- 帧内 `seq` 与 `sent` 同源（均为已见最大 seq）；
- `rssi`：rx 为纯 SoftAP 节点、无 STA 关联，`WiFi.RSSI()` 不可得 → 恒走 NA 路径；
- 计数回绕：tx 侧 8 位 seq 到顶（99999999）回绕从 1 重新递增；rx 侧检测到巨量回退
  （幅度 > 5000 万）按回绕处理——置标记位并以新 seq 为基线继续统计，不断流；
- tx 侧发送失败与掉线重连均在内部计数并经 `[tx] ...` 状态行（每 5s 一行）人读监视，
  不计入 KPI 帧。

## 实测数字【待实测】

丢包率、重连次数、RSSI、吞吐等**真机实测数字禁止预写**——本 README 只锁拓扑、协议与
计数口径；实测值随 R87 真机联调（烧录+射频联测）校准后回填。
