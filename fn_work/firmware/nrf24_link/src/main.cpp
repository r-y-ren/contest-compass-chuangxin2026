// NRF24 被测链路固件主体（R86）——NODE_ROLE=1 发送+上报节点 / NODE_ROLE=2 对端。
// 重写规约见 fn_docs/responsibility.md；构建/烧录命令随工程 README 于实现批交付。
#include <Arduino.h>

#include "frame_encoder.h"
#include "tasks.h"

// unimplemented:fn:nrf24_link_firmware
void setup() {
    Serial.begin(115200);
#if NODE_ROLE == 1
    // 参数为占位值（channel 76=2476MHz，落 2.4G 白名单内）；真机联调（R87）定桩
    esb_traffic_task_begin(76, 20, 32);
    counter_report_task_begin(500);
#elif NODE_ROLE == 2
    // 对端节点：接收业务流（实现批交付）
#else
#error "NODE_ROLE 必须为 1（发送+上报）或 2（对端）"
#endif
}

// unimplemented:fn:nrf24_link_firmware
void loop() {
#if NODE_ROLE == 1
    esb_traffic_task_tick();
    counter_report_task_tick();
#endif
}
