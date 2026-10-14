#pragma once
// NRF24 链路固件任务面（R86）——重写规约见 fn_docs/responsibility.md。
// esb_traffic_task：ESB（自动应答）定长包业务流。
// counter_report_task：PLOS_CNT/ARC_CNT 计数累计+发包间隙监听窗读 RPD+串口上报。
#include <cstdint>

void esb_traffic_task_begin(uint8_t channel, uint32_t interval_ms, uint16_t payload_len);
void esb_traffic_task_tick();

void counter_report_task_begin(uint32_t period_ms);
void counter_report_task_tick();
