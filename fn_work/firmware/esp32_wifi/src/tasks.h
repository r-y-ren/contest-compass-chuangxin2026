#pragma once
// ESP32 WiFi 链路固件任务面（R85）——重写规约见 fn_docs/responsibility.md。
// udp_stream_task：发送节点业务流（定长 UDP+递增 seq，固定节拍）。
// kpi_report_task：接收节点统计（seq 缺口=err/重复=retries/期望累计=sent/RSSI）与串口上报。
#include <cstdint>

void udp_stream_task_begin(const char *host, uint16_t port, uint32_t interval_ms,
                           uint16_t payload_len);
void udp_stream_task_tick();

void kpi_report_task_begin(uint32_t period_ms);
void kpi_report_task_tick();
