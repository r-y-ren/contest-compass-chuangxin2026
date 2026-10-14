# NRF24 被测链路固件（R86）

两块 ESP32（各挂一片 nRF24L01+ 模块）组成 ESB 被测链路：**reporter 节点**按固定节拍以
RF24 自动应答（ESB）模式向 **peer 节点**发 32B 定长载荷（前 8 字节为递增 seq 的 ASCII
十进制）；reporter 同时是报告节点——周期读发送侧状态寄存器（PLOS_CNT/ARC_CNT）、发包
间隙开监听窗采样 RPD 门限位，经 USB 串口吐 KPI 帧——
`NRF,<seq>,<sent>,<lost>,<retries>,<rpd>`，
与主机侧 `fn_work/src/drive_nrf24_link/parse_nrf24_frame.py`（协议唯一真值）逐字对齐。
角色经构建环境区分（`pio run -e reporter` / `pio run -e peer`），同一份源码两种映像。

## 拓扑（定桩：成对节点）

```
[reporter 节点]                          [peer 节点]
 ESP32 + nRF24L01+                       ESP32 + nRF24L01+
  esb_traffic_task                        esb_traffic_task（PRX）
   · 每 20ms 发 1 包（ESB 自动应答）        · 同链路地址开 RX 管 1
   · 载荷 32B 定长                         · 硬件自动回 ACK
   · 前 8B=seq（%08lu 零填充）             · 纯接收排空（不吐帧）
   · 通道 76=2476MHz（两端同通道）
  counter_report_task（每 500ms）
   · PLOS_CNT 读-差分-累计 → lost
   · ARC_CNT 逐包直读累计 → retries
   · 发包间隙 ~200µs RX 监听窗读 RPD
   · encode_nrf24_frame 吐串口 115200
                                      |
                                      +--> reporter USB 串口 115200 → 主机 parse_nrf24_frame
```

## 接线（两节点相同，ESP32 经典 VSPI 接法）

| nRF24L01+ 引脚 | ESP32 引脚 | 说明 |
| --- | --- | --- |
| VCC | 3V3 | **必须 3.3V**（5V 会烧模块；模块电流峰值 ~15mA，板载 3V3 足够） |
| GND | GND | 共地 |
| CE | GPIO4 | 片选使能（`RF24 radio(4, 5)`） |
| CSN | GPIO5 | SPI 片选 |
| SCK | GPIO18 | VSPI 时钟（RF24 库在 ESP32 默认用 VSPI） |
| MOSI | GPIO23 | VSPI 主出 |
| MISO | GPIO19 | VSPI 主入 |
| IRQ | 不接 | 本工程轮询状态，不用中断 |

两板各自 USB 供电；烧录与串口监视各占一个 USB 口，只有一台电脑时可先后复用同一口
（先烧录/监视 peer，再换 reporter）。模块天线对空放置，勿贴金属/并排堆叠。

## 构建与烧录

PlatformIO 已装入 `fn_work/.venv`（不动全局）；首次构建会联网下载 RF24 库
（`platformio.ini` 定 `lib_deps = nrf24/RF24@1.6.2`——**精确版本钉死**：曾用 `^1.4.10`
浮动约束，被 registry 按 `^` 语义解析为 1.6.2，现收紧为精确 pin 防 registry 漂移）。
在 `fn_work/firmware/nrf24_link/` 目录执行：

```bash
# reporter 节点（发送+KPI 上报）：构建 / 烧录 / 串口监视（115200）
../../.venv/bin/pio run -e reporter
../../.venv/bin/pio run -e reporter -t upload
../../.venv/bin/pio run -e reporter -t monitor    # Ctrl+] 退出

# peer 节点（对端接收）：构建 / 烧录 / 串口监视（115200）
../../.venv/bin/pio run -e peer
../../.venv/bin/pio run -e peer -t upload
../../.venv/bin/pio run -e peer -t monitor
```

先上电/烧录 peer（接收就绪），再上电 reporter（发送才有 ACK 应答对象）。串口监视波特率
115200（`platformio.ini` 已定 `monitor_speed`）。

## 串口帧示例

reporter 节点串口输出（每 500ms 一行，`\r\n` 结尾；启动时先有一行 `[reporter] ...`
横幅，之后为纯帧流）：

```
NRF,25,25,0,3,0
NRF,250,249,2,31,1
NRF,1200,1198,4,57,0
```

以上为**格式示意**（与 Python 参考实现 `compose_nrf24_frame` 逐字节同构、均可被
`parse_nrf24_frame` 接受），**非实测值**。帧协议：六字段 CSV 单行、全严格非负十进制整数、
`rpd∈{0,1}`、ASCII、`\n` 结尾——**无校验和后缀**（NRF24 走 ESB 硬件 CRC，帧文本不缀
`*hex`，这点与 ESP 帧不同）。peer 节点串口只有一行 `[peer] ...` 启动横幅，不吐帧。

## 计数口径声明

帧字段与发送侧状态寄存器（`OBSERVE_TX`）的对应及累计口径：

- `seq` = 已发最后一个载荷序号（从 1 起，8 位十进制零填充于载荷前 8 字节，到 99999999
  **静默回绕**从 1 重新开始——内部 99999999→0→1，帧面无任何回绕标记，主机侧缺口统计
  会把回绕计作一次大缺口（参考域已知限界）；20ms 缺省节拍下需连续发送 ≈23 天跑满，
  真机演示时长内不可达——【待实测】纪律：回绕场景不进真机演示断言）；
- `sent` = `write()` 返回 true（收到 ACK，ESB 交付成功）的累计；发送失败（MAX_RT 重试
  掏空）只进内部计数 `tx_send_fail`，不上帧——其事件源与 `lost` 同一（见下）；
- `lost` = **PLOS_CNT（OBSERVE_TX 高 4 位）读-差分-累计**。按 datasheet，PLOS_CNT 为
  跨包累计、只在写 RF_CH 时清零、**饱和保护于 15 不回绕**：本固件每报告周期（500ms）
  读数与上次差分累加，随后写 RF_CH（同值 `setChannel` 重写）清零，把饱和钳口窗压缩到
  单个周期内——500ms≈25 包，单周期丢包 >15 才会漏计（>60% 瞬时丢包率场景，真机联调
  若需更细分辨率可缩短上报周期）。**无回绕修正分支**：每周期清零后差分基线恒 0，恒
  满足 plos≥last（"读数回落=回绕"在本语义下不可达，代码与口径一致）；
- `retries` = **ARC_CNT（OBSERVE_TX 低 4 位）逐包直读累计**。按 datasheet，ARC_CNT 为
  按包复位语义——新包发送开始即清零，因此发送完成时刻的读数恰为该包重传数，直加即得
  总重传。**刻意不做差分/回绕修正**：按包复位语义下差分会把读数回落误判为回绕（每周期
  虚增 ~13-16），与"累计-回绕"模型不可兼得，此处按 datasheet 语义取直读口径；
- `rpd` = 发包间隙短暂进 RX 监听窗（名义 ~200µs）读 `testRPD()` 锁存位（0/1）。门限
  -64dBm，仅 nRF24L01+（P 型）硬件有效（非 + 型恒 0）。窗内读到的是该窗口内信道上是
  否出现过 >-64dBm 的信号。置位源口径：**「对端常发」在本拓扑不可达**——peer 纯接收
  不发射，仅回 ESB ACK，且 ACK 发生在 reporter 自身 `write()` 期间、不在 RPD 采样窗
  内；实际两口径为 ① **同频其他射频源**（环境干扰、相邻 WiFi/蓝牙、其他 NRF24 链路
  均会置位）② **主发射压制**（本机主发射后前端恢复期压制窗内早期灵敏度——即下条有
  效窗口径的另一面）。综合口径为"信道忙指示"，不是本链路信号质量的直接度量；
- RPD 窗为**名义窗**：200µs 名义值需扣除 RX settle（datasheet Tstby2rx≈130µs），有效
  采样窗≈70µs——真机域，随 R87 实测校准；
- **host 等价 64 位域限界**：跨语言等价测试在 host 编译 `frame_encoder`，host
  `unsigned long` 为 64 位（Python 参考域更宽），可生成固件 32 位 `unsigned long`
  不可产生的超大计数值——**host/Python 参考域为固件域的超集**，等价断言的计数域以
  固件 32 位为准（等价用例上限即钉在 4294967295）；
- 每帧字段全为软件累计值；固件域（ESP32）`unsigned long` 为 32 位，计数回绕只发生在
  4294967295 满值（编译级域内无截断风险，见 `encode_nrf24_frame`）。

## 实测数字【待实测】

丢包率、重传数、RPD 置位率、链路吞吐等**真机实测数字禁止预写**——本 README 只锁拓扑、
协议与计数口径；实测值随 R87 真机联调（烧录+射频联测）校准后回填。
