// ESP32 WiFi 被测链路固件主体（R85）——角色经构建宏 NODE_ROLE 区分：
//   NODE_ROLE=1 发送节点（STA+udp_stream_task）/ NODE_ROLE=2 接收节点（SoftAP+kpi_report_task）。
// 链路拓扑/帧协议/计数口径见 fn_docs/responsibility.md 与本工程 README.md。
#include <Arduino.h>

#include "frame_encoder.h"
#include "tasks.h"

// 角色参数定桩（真机联调 R87 可按手册口径调整）
constexpr uint32_t kTxIntervalMs = 20;       // 发送节拍 20ms（≈50 包/秒）
constexpr uint16_t kTxPayloadLen = 256;      // 定长载荷 256B（前 8 字节为 ASCII seq）
constexpr uint32_t kRxReportPeriodMs = 500;  // KPI 帧上报周期 500ms

void setup() {
    Serial.begin(115200);
#if NODE_ROLE == 1
    // 发送节点：STA 连 rx 节点 AP（凭据 LINK_SSID/LINK_PASS），定长 UDP 流发往 192.168.4.1:3333
    udp_stream_task_begin(AP_HOST_IP, LINK_UDP_PORT, kTxIntervalMs, kTxPayloadLen);
#elif NODE_ROLE == 2
    // 接收节点：SoftAP(192.168.4.1)+UDP 3333 收包统计，周期吐 KPI 帧到串口
    kpi_report_task_begin(kRxReportPeriodMs);
#else
#error "NODE_ROLE 必须为 1（发送）或 2（接收）"
#endif
}

void loop() {
#if NODE_ROLE == 1
    udp_stream_task_tick();
#elif NODE_ROLE == 2
    kpi_report_task_tick();
#endif
}
