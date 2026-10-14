#pragma once
// ESP32 WiFi 链路固件任务面（R85）——重写规约见 fn_docs/responsibility.md。
// udp_stream_task：发送节点业务流（STA 连 rx 节点 AP，定长 UDP+递增 seq，固定节拍）。
// kpi_report_task：接收节点统计（seq 缺口=err/重复=retries/期望累计=sent/RSSI）与串口上报。
#include <cstdint>

// 链路共享常量：rx 节点 SoftAP 凭据=tx 节点 STA 凭据（必须一致；R87 真机联调可改）
constexpr const char *LINK_SSID = "esp32-link-r85";
constexpr const char *LINK_PASS = "link-r85-pass";
constexpr uint16_t LINK_UDP_PORT = 3333;            // rx 监听 / tx 发往的 UDP 端口
constexpr const char *AP_HOST_IP = "192.168.4.1";   // rx 节点 SoftAP 固定地址（tx 发往此处）

void udp_stream_task_begin(const char *host, uint16_t port, uint32_t interval_ms,
                           uint16_t payload_len);
void udp_stream_task_tick();

void kpi_report_task_begin(uint32_t period_ms);
void kpi_report_task_tick();
