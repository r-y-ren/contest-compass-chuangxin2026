// 主机侧等价 harness（R85）：不依赖 Arduino，仅与 frame_encoder.cpp 一起用
// g++ -std=c++17 -Wall -Wextra -Werror 编译（产物落 /tmp，不进仓库）。
//
// 协议：stdin 每行 "seq,sent,err,retries,rssi,ck"（rssi 取 NA/nan/inf/-inf 或十进制数，
// ck 取 0/1）；stdout 对每行输出 encode_esp32_frame 的帧文本（\n 结尾）。
// pytest 侧（tests/firmware_esp32/test_host_equivalence.py）断言输出与 Python
// compose_esp32_frame 同输入逐字节一致。
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "frame_encoder.h"

int main() {
    char line[256];
    while (std::fgets(line, sizeof line, stdin)) {
        unsigned long seq, sent, err, retries;
        char rssi_text[64];
        int ck = 0;
        if (std::sscanf(line, "%lu,%lu,%lu,%lu,%63[^,],%d",
                        &seq, &sent, &err, &retries, rssi_text, &ck) != 6) {
            std::fprintf(stderr, "harness: bad input line: %s", line);
            return 2;
        }
        // NA 与非有限统一走编码器的 NA 钳制路径
        const double rssi = (std::strcmp(rssi_text, "NA") == 0)
                                ? std::nan("")
                                : std::strtod(rssi_text, nullptr);
        const std::string frame =
            encode_esp32_frame(seq, sent, err, retries, rssi, ck != 0);
        std::printf("%s\n", frame.c_str());
    }
    return 0;
}
