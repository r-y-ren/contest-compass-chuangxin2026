#include "frame_encoder.h"

#include <cassert>
#include <cstdio>

// 五计数值→KPI 帧文本行（不含换行），与 Python 参考实现 compose_nrf24_frame 同规格：
//   NRF,<seq>,<sent>,<lost>,<retries>,<rpd>
// 值域口径（固件侧只吐合法帧，不因指标异常断流）：
//   - 四计数参数为 unsigned long——类型层面即非负，负数无从进入（调用方计数均为
//     单调递增累计），编码结果恒为合法非负十进制；全整型域内无浮点、无截断风险；
//   - rpd 为 1bit 门限位：按 !=0 归一到 0/1（调用方只可能传 0/1，此钳制纯防御性，
//     保证任何路径下都不吐 rpd∉{0,1} 的非法帧）；
//   - 协议无校验和后缀（与 ESP 帧的差异点：NRF24 走 ESB 硬件 CRC，帧文本不缀 *hex）。
std::string encode_nrf24_frame(unsigned long seq, unsigned long sent,
                               unsigned long lost, unsigned long retries,
                               unsigned rpd) {
    char body[120];  // 4 个计数各至多 20 位十进制+前缀+分隔+rpd 1 位足量
    const int written = std::snprintf(body, sizeof body, "NRF,%lu,%lu,%lu,%lu,%u",
                                      seq, sent, lost, retries,
                                      rpd != 0u ? 1u : 0u);
    // 防御性缓冲断言：snprintf 返回"应写长度"，超缓冲即编码口径被破坏（不应可达）
    assert(written >= 0 && (size_t)written < sizeof body);
    return std::string(body);
}
