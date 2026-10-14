// NRF24 被测链路固件主体（R86）——角色经构建宏 NODE_ROLE 区分：
//   NODE_ROLE=1 reporter=发送+上报节点（ESB 发送流+PLOS/ARC/RPD 串口 KPI 帧）
//   NODE_ROLE=2 peer=纯接收对端（同一链路地址开 RX 管，只收不发不吐帧）。
// 链路拓扑/帧协议/计数口径见 fn_docs/responsibility.md 与本工程 README.md。
#include <Arduino.h>

#include "frame_encoder.h"
#include "tasks.h"

// 角色参数定桩（真机联调 R87 可按手册口径调整）
constexpr uint8_t kLinkChannel = 76;       // 2400+76=2476MHz（落 2.4G 白名单内）
constexpr uint32_t kTxIntervalMs = 20;     // 发送节拍 20ms（≈50 包/秒）
constexpr uint16_t kTxPayloadLen = 32;     // 定长载荷 32B（前 8 字节为 ASCII seq）
constexpr uint32_t kReportPeriodMs = 500;  // KPI 帧上报周期 500ms

void setup() {
    Serial.begin(115200);
#if NODE_ROLE == 1
    // reporter 节点：ESB 发送流+周期 KPI 帧上报（PLOS 差分累计/ARC 逐包累计/RPD 监听窗）
    esb_traffic_task_begin(kLinkChannel, kTxIntervalMs, kTxPayloadLen);
    counter_report_task_begin(kReportPeriodMs);
#elif NODE_ROLE == 2
    // peer 节点：同一链路地址开 RX 管，纯接收排空（不发不吐帧）
    esb_traffic_task_begin(kLinkChannel, kTxIntervalMs, kTxPayloadLen);
#else
#error "NODE_ROLE 必须为 1（发送+上报）或 2（对端）"
#endif
}

void loop() {
#if NODE_ROLE == 1
    esb_traffic_task_tick();
    counter_report_task_tick();
#elif NODE_ROLE == 2
    esb_traffic_task_tick();
#endif
}
