#pragma once
// ESP32 KPI 帧编码（R85）——协议与主机侧 parse_esp32_frame 逐字对齐：
//   ESP,<seq>,<sent>,<err>,<retries>,<rssi>[*<hex>]
// 校验和=帧体（ESP 起、* 前）sum&0xFF 十六进制；rssi 非有限时输出 NA。
// 重写规约与签名意图详见 fn_docs/responsibility.md（域二十一）。
#include <string>

std::string encode_esp32_frame(unsigned long seq, unsigned long sent,
                               unsigned long err, unsigned long retries,
                               double rssi_dbm, bool with_checksum);
