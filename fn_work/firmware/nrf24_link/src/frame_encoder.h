#pragma once
// NRF24 KPI 帧编码（R86）——协议与主机侧 parse_nrf24_frame 逐字对齐：
//   NRF,<seq>,<sent>,<lost>,<retries>,<rpd>（六字段非负整数，rpd∈{0,1}）
// 重写规约与签名意图详见 fn_docs/responsibility.md（域二十一）。
#include <string>

std::string encode_nrf24_frame(unsigned long seq, unsigned long sent,
                               unsigned long lost, unsigned long retries,
                               unsigned rpd);
