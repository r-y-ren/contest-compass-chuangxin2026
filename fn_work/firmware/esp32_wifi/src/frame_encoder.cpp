#include "frame_encoder.h"

#include <cmath>
#include <cstdio>

// 五指标→KPI 帧文本行（不含换行），与 Python 参考实现 compose_esp32_frame 同规格：
//   ESP,<seq>,<sent>,<err>,<retries>,<rssi>[*<hex>]
// 值域钳制（固件侧只吐合法帧，不因指标异常断流）：
//   - 计数参数为 unsigned long——类型层面即非负，负数无从进入（调用方计数均为
//     单调递增累计），编码结果恒为合法非负十进制；
//   - rssi 语义域 [-1000.0, 1000.0] dBm（WiFi.RSSI() 语义域 int32 的宽裕超集）；
//     钳制序=**语义域检查先于编码**：非有限（NaN/±inf，如纯 AP 节点读不到 STA
//     RSSI）或域外大有限值（如 1e300，%.1f 表示远超缓冲）一律按 NA 输出——
//     域外不吐数值帧（B33 对抗 F1：旧口径大有限值落入 snprintf 截断路径，
//     可产出校验和自洽的可解析合法错帧，跨语言等价宣称破）；
//   - rssi 数值定 1 位小数（%.1f），与 Python 侧 f"{v:.1f}" 逐字节一致
//     （host 等价测试据此做跨语言逐字节比对）；
//   - 校验和=帧体（ESP 起、* 前）字节和 & 0xFF，两位小写十六进制（解析侧大小写均可）。
std::string encode_esp32_frame(unsigned long seq, unsigned long sent,
                               unsigned long err, unsigned long retries,
                               double rssi_dbm, bool with_checksum) {
    char body[160];  // 4 个计数各至多 20 位十进制+前缀+分隔+rssi 足量
    // 语义域检查先行：域内值 %.1f 最长 "-1000.0"（7 字符），缓冲 160 绰绰
    // 有余，截断路径不可达；snprintf 返回值仍防御性复核（负值/超长→NA 兜底）。
    const bool rssi_in_domain =
        std::isfinite(rssi_dbm) && rssi_dbm >= -1000.0 && rssi_dbm <= 1000.0;
    int n = -1;
    if (rssi_in_domain) {
        n = std::snprintf(body, sizeof body, "ESP,%lu,%lu,%lu,%lu,%.1f",
                          seq, sent, err, retries, rssi_dbm);
    }
    if (!rssi_in_domain || n < 0 || static_cast<size_t>(n) >= sizeof body) {
        // NA 兜底：最长 "ESP,"+4×20 位+4 分隔+"NA"=90 字符+结尾符，缓冲内必成。
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
