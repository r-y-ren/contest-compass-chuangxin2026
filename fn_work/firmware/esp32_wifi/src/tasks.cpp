#include "tasks.h"

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "frame_encoder.h"

namespace {

// ---- 内部定桩常量 ----
constexpr uint16_t kStreamLocalPort = 3334;       // tx 节点本地 UDP 源端口（rx 监听 3333）
constexpr uint32_t kReconnectIntervalMs = 5000;   // STA 掉线重连尝试节流间隔
constexpr uint32_t kStatusIntervalMs = 5000;      // tx 节点串口状态行节流间隔
constexpr uint16_t kMaxPayloadLen = 1024;         // 载荷缓冲上限（默认 256B，钳到 [8,1024]）
constexpr unsigned long kSeqTextMax = 99999999UL; // 载荷 seq 文本 8 位十进制上限
constexpr unsigned long kSeqWrapThreshold = 50000000UL;  // rx 侧回绕判定阈值（回退幅度巨量）
constexpr char kPayloadFiller = '#';              // seq 之外载荷填充字节（内容对统计无意义）

// ---- udp_stream_task（发送节点）状态 ----
char tx_host[64];
uint16_t tx_port = 0;
uint32_t tx_interval_ms = 0;
uint16_t tx_payload_len = 0;
char tx_payload[kMaxPayloadLen];
unsigned long tx_seq = 0;         // 已发最后一个 seq（从 1 起，8 位十进制零填充）
unsigned long tx_send_fail = 0;   // 发送失败累计（含掉线期间尝试）
unsigned long tx_reconnects = 0;  // 掉线后重连尝试次数累计（首次连接不计）
bool tx_ever_connected = false;
uint32_t tx_next_send_ms = 0;
uint32_t tx_next_reconnect_ms = 0;
uint32_t tx_next_status_ms = 0;
WiFiUDP tx_udp;

// ---- kpi_report_task（接收节点）状态 ----
uint32_t rx_period_ms = 0;
bool rx_started = false;
bool rx_have_seq = false;
unsigned long rx_max_seq = 0;      // sent=期望包数=已见最大 seq（同时作帧内 seq 上报）
unsigned long rx_gap_err = 0;      // err=seq 缺口累计
unsigned long rx_dup_retries = 0;  // retries=重复/回退包累计
bool rx_seq_wrapped = false;       // 计数回绕标记（置位后继续统计，不断流）
uint32_t rx_next_report_ms = 0;
char rx_packet[kMaxPayloadLen];
WiFiUDP rx_udp;

}  // namespace

// ===================== udp_stream_task：发送节点业务流 =====================

void udp_stream_task_begin(const char *host, uint16_t port, uint32_t interval_ms,
                           uint16_t payload_len) {
    std::strncpy(tx_host, host, sizeof(tx_host) - 1);
    tx_host[sizeof(tx_host) - 1] = '\0';
    tx_port = port;
    tx_interval_ms = interval_ms > 0 ? interval_ms : 1;
    // 载荷长钳制到 [8, kMaxPayloadLen]：前 8 字节必须放得下 seq 文本
    if (payload_len < 8) {
        payload_len = 8;
    }
    if (payload_len > kMaxPayloadLen) {
        payload_len = kMaxPayloadLen;
    }
    tx_payload_len = payload_len;
    std::memset(tx_payload, kPayloadFiller, sizeof(tx_payload));
    // STA 连接对端 AP（凭据与 rx 节点 SoftAP 一致）；连接在后台进行，tick 内轮询状态
    WiFi.mode(WIFI_STA);
    WiFi.begin(LINK_SSID, LINK_PASS);
    tx_udp.begin(kStreamLocalPort);  // 发送前需绑定本地端口
    tx_next_send_ms = millis();
    Serial.printf("[tx] UDP 流目标 %s:%u，节拍 %lums，载荷 %uB\r\n",
                  tx_host, (unsigned)tx_port, (unsigned long)tx_interval_ms,
                  (unsigned)tx_payload_len);
}

void udp_stream_task_tick() {
    const uint32_t now = millis();

    // 掉线检测+节流重连（不阻塞主循环；首次连接不计入重连计数）
    if (WiFi.status() != WL_CONNECTED) {
        if ((int32_t)(now - tx_next_reconnect_ms) >= 0) {
            tx_next_reconnect_ms = now + kReconnectIntervalMs;
            if (tx_ever_connected) {
                tx_reconnects += 1;
            }
            WiFi.disconnect();  // 清残留连接状态后重新发起（各核心版本通用 API）
            WiFi.begin(LINK_SSID, LINK_PASS);
        }
    } else {
        tx_ever_connected = true;
    }

    // 固定节拍发送：落后过多时不补发连发，直接对齐到下一拍
    if ((int32_t)(now - tx_next_send_ms) >= 0) {
        tx_next_send_ms = now + tx_interval_ms;
        // seq 从 1 递增；到 8 位十进制上限后回绕从 1 重新开始（rx 侧按新基线统计）
        if (tx_seq >= kSeqTextMax) {
            tx_seq = 0;
        }
        tx_seq += 1;
        std::snprintf(tx_payload, 9, "%08lu", tx_seq);  // 前 8 字节=ASCII 十进制零填充
        tx_payload[8] = kPayloadFiller;                 // 修复 snprintf 结尾 NUL，保持定长
        const bool ok = tx_udp.beginPacket(tx_host, tx_port) == 1 &&
                        tx_udp.write((const uint8_t *)tx_payload, tx_payload_len) ==
                            (size_t)tx_payload_len &&
                        tx_udp.endPacket() == 1;
        if (!ok) {
            tx_send_fail += 1;  // 发送失败（含掉线期间）计数并继续
        }
    }

    // 周期状态行（tx 节点串口仅作人读监视，不作帧流解析）
    if ((int32_t)(now - tx_next_status_ms) >= 0) {
        tx_next_status_ms = now + kStatusIntervalMs;
        Serial.printf("[tx] seq=%lu fail=%lu reconnects=%lu rssi=%d\r\n",
                      tx_seq, tx_send_fail, tx_reconnects, (int)WiFi.RSSI());
    }
}

// ===================== kpi_report_task：接收节点统计上报 =====================

void kpi_report_task_begin(uint32_t period_ms) {
    rx_period_ms = period_ms > 0 ? period_ms : 1;
    // SoftAP 模式：固定 192.168.4.1（tx 节点写死发往该地址）；凭据与 tx 节点 STA 一致
    WiFi.mode(WIFI_AP);
    WiFi.softAP(LINK_SSID, LINK_PASS);
    WiFi.softAPConfig(IPAddress(192, 168, 4, 1), IPAddress(192, 168, 4, 1),
                      IPAddress(255, 255, 255, 0));
    rx_udp.begin(LINK_UDP_PORT);
    rx_started = true;
    rx_next_report_ms = millis() + rx_period_ms;
}

void kpi_report_task_tick() {
    if (!rx_started) {
        return;  // 未 begin（角色配错）时空转，保持 loop 不崩
    }

    // 1) 非阻塞收包：定长载荷前 8 字节为 ASCII 十进制 seq，按口径更新计数
    while (rx_udp.parsePacket() > 0) {
        const int len = rx_udp.read((uint8_t *)rx_packet, sizeof(rx_packet));
        if (len >= 8) {
            char seq_text[9];
            std::memcpy(seq_text, rx_packet, 8);
            seq_text[8] = '\0';
            const unsigned long seq = std::strtoul(seq_text, nullptr, 10);
            // 计数口径（与工程 README.md 声明一致）：
            //   sent=期望包数=最大 seq；err=新最大相对旧最大的缺口；retries=重复/回退包
            if (!rx_have_seq) {
                rx_have_seq = true;
                rx_max_seq = seq;
            } else if (seq > rx_max_seq) {
                const unsigned long delta = seq - rx_max_seq;
                if (delta > 1) {
                    rx_gap_err += delta - 1;
                }
                rx_max_seq = seq;
            } else if (seq == rx_max_seq) {
                rx_dup_retries += 1;
            } else if (rx_max_seq - seq > kSeqWrapThreshold) {
                // 回绕（tx 侧 8 位 seq 到顶重启）：置标记位并按新基线继续，不断流
                rx_seq_wrapped = true;
                rx_max_seq = seq;
            } else {
                rx_dup_retries += 1;  // 小幅回退包按重复计
            }
        }
    }

    // 2) 周期上报：RSSI 不可得→非有限→NA 路径（rx 为纯 SoftAP 节点、无 STA 关联）
    if ((int32_t)(millis() - rx_next_report_ms) >= 0) {
        rx_next_report_ms += rx_period_ms;
        if ((int32_t)(millis() - rx_next_report_ms) >= 0) {
            rx_next_report_ms = millis() + rx_period_ms;  // 长阻塞后重对齐，不连发补帧
        }
        const int32_t rssi_raw = WiFi.RSSI();
        const bool rssi_valid =
            (WiFi.status() == WL_CONNECTED) && rssi_raw < 0;  // 有效 RSSI 为负 dBm
        const double rssi_dbm = rssi_valid ? (double)rssi_raw : NAN;
        Serial.println(encode_esp32_frame(rx_max_seq, rx_max_seq, rx_gap_err,
                                          rx_dup_retries, rssi_dbm, true)
                           .c_str());
    }
}
