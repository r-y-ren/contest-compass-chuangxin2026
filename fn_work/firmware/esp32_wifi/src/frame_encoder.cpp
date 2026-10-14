#include "frame_encoder.h"

#include <cmath>
#include <cstdio>

// 五指标→KPI 帧文本行（不含换行），与 Python 参考实现 compose_esp32_frame 同规格：
//   ESP,<seq>,<sent>,<err>,<retries>,<rssi>[*<hex>]
// 值域钳制（固件侧只吐合法帧，不因指标异常断流）：
//   - 计数参数为 unsigned long——类型层面即非负，负数无从进入（调用方计数均为
//     单调递增累计），编码结果恒为合法非负十进制；
//   - rssi 非有限（NaN/±inf，如纯 AP 节点读不到 STA RSSI）→ 按 NA 输出；
//   - rssi 数值定 1 位小数（%.1f），与 Python 侧 f"{v:.1f}" 逐字节一致
//     （host 等价测试据此做跨语言逐字节比对）；
//   - 校验和=帧体（ESP 起、* 前）字节和 & 0xFF，两位小写十六进制（解析侧大小写均可）。
std::string encode_esp32_frame(unsigned long seq, unsigned long sent,
                               unsigned long err, unsigned long retries,
                               double rssi_dbm, bool with_checksum) {
    char body[160];  // 4 个计数各至多 20 位十进制+前缀+分隔+rssi(%.1f) 足量；越界安全截断
    if (std::isfinite(rssi_dbm)) {
        std::snprintf(body, sizeof body, "ESP,%lu,%lu,%lu,%lu,%.1f",
                      seq, sent, err, retries, rssi_dbm);
    } else {
        std::snprintf(body, sizeof body, "ESP,%lu,%lu,%lu,%lu,NA",
                      seq, sent, err, retries);
    }
    std::string frame(body);
    if (!with_checksum) {
        return frame;
    }
    unsigned sum = 0;
    for (unsigned char ch : frame) {
        sum += ch;
    }
    char tail[8];
    std::snprintf(tail, sizeof tail, "*%02x", sum & 0xFFu);
    return frame + tail;
}
