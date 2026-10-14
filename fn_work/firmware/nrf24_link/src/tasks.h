#pragma once
// NRF24 链路固件任务面（R86）——重写规约见 fn_docs/responsibility.md。
// esb_traffic_task：ESB（自动应答）定长包业务流（reporter=发送节拍 / peer=纯接收排空，
// 角色经构建宏 NODE_ROLE 分发）。
// counter_report_task：PLOS_CNT/ARC_CNT 计数累计+发包间隙监听窗读 RPD+串口上报（reporter 侧）。
#include <cstdint>

// 链路引脚（ESP32 经典 VSPI 接线，README 接线表全列）：CE=4/CSN=5，SPI 走默认
// MOSI=23/MISO=19/SCK=18（RF24 库在 ESP32 上默认使用 VSPI）
constexpr uint8_t NRF24_CE_PIN = 4;
constexpr uint8_t NRF24_CSN_PIN = 5;
// 5 字节链路地址：reporter 写管与 peer RX 管同址（ESB 自动应答要求两端同址）
constexpr uint8_t NRF24_LINK_ADDRESS[5] = {'N', 'R', 'F', '8', '6'};

void esb_traffic_task_begin(uint8_t channel, uint32_t interval_ms, uint16_t payload_len);
void esb_traffic_task_tick();

void counter_report_task_begin(uint32_t period_ms);
void counter_report_task_tick();
