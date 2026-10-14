// 主机侧等价 harness（R86）：不依赖 Arduino，仅与 frame_encoder.cpp 一起用
// g++ -std=c++17 -Wall -Wextra -Werror 编译（产物落 /tmp，不进仓库）。
//
// 协议：stdin 每行 "seq,sent,lost,retries,rpd"（全为无符号十进制）；
// stdout 对每行输出 encode_nrf24_frame 的帧文本（\n 结尾）。
// pytest 侧（tests/firmware_nrf24/test_nrf24_host_equivalence.py）断言输出与 Python
// compose_nrf24_frame 同输入逐字节一致。
#include <cstdio>

#include "frame_encoder.h"

int main() {
    char line[256];
    while (std::fgets(line, sizeof line, stdin)) {
        unsigned long seq, sent, lost, retries;
        unsigned rpd = 0;
        if (std::sscanf(line, "%lu,%lu,%lu,%lu,%u",
                        &seq, &sent, &lost, &retries, &rpd) != 5) {
            std::fprintf(stderr, "harness: bad input line: %s", line);
            return 2;
        }
        const std::string frame =
            encode_nrf24_frame(seq, sent, lost, retries, rpd);
        std::printf("%s\n", frame.c_str());
    }
    return 0;
}
