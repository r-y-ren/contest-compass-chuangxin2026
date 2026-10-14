// ESP32 WiFi 被测链路固件主体（R85）——角色经构建宏 NODE_ROLE 区分：
//   NODE_ROLE=1 发送节点 / NODE_ROLE=2 接收节点。
// 重写规约见 fn_docs/responsibility.md；构建/烧录命令随工程 README 于实现批交付。
#include <Arduino.h>

#include "frame_encoder.h"
#include "tasks.h"

// unimplemented:fn:esp32_wifi_firmware
void setup() {
    Serial.begin(115200);
#if NODE_ROLE == 1
    // 参数为占位值，真机联调（R87）随手册口径定桩
    udp_stream_task_begin("192.168.4.1", 3333, 20, 256);
#elif NODE_ROLE == 2
    kpi_report_task_begin(500);
#else
#error "NODE_ROLE 必须为 1（发送）或 2（接收）"
#endif
}

// unimplemented:fn:esp32_wifi_firmware
void loop() {
#if NODE_ROLE == 1
    udp_stream_task_tick();
#elif NODE_ROLE == 2
    kpi_report_task_tick();
#endif
}
