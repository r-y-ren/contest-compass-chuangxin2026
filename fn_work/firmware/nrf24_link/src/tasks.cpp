#include "tasks.h"

#include <Arduino.h>
#include <RF24.h>
#include <nRF24L01.h>

#include <cstdio>
#include <cstring>

#include "frame_encoder.h"

namespace {

// ---- 内部定桩常量 ----
constexpr uint16_t kMinPayloadLen = 8;             // 前 8 字节必须放得下 seq 文本
constexpr uint16_t kMaxPayloadLen = 32;            // NRF24 ESB 单载荷上限（定长 32B）
constexpr unsigned long kSeqTextMax = 99999999UL;  // 载荷 seq 文本 8 位十进制上限
constexpr char kPayloadFiller = '#';               // seq 之外载荷填充字节（内容对统计无意义）
constexpr uint8_t kArcRetryDelay = 2;              // ESB 自动重试等待 2×250µs=500µs
constexpr uint8_t kArcRetryCount = 15;             // ESB 自动重试上限 15（ARC_CNT 4bit 域内满值）
constexpr uint32_t kRpdListenUs = 200;  // RPD 采样监听窗时长（µs，名义 200µs——扣除 RX settle
                                        // 后有效采样窗≈70µs，真机口径见 README/R87 校准）

// RF24 的 read_register 为 protected——最小派生类只开一个 OBSERVE_TX 读口，不改任何行为
class ObserveRf24 : public RF24 {
  public:
    using RF24::RF24;
    uint8_t observe_tx() { return read_register(nRF24L01::OBSERVE_TX); }
};

// ---- 链路射频对象（reporter/peer 各环境经 NODE_ROLE 编译各自分支） ----
ObserveRf24 radio(NRF24_CE_PIN, NRF24_CSN_PIN);
bool radio_ready = false;
uint8_t link_channel = 76;

// ---- esb_traffic_task 状态（reporter 侧） ----
uint32_t tx_interval_ms = 0;
uint16_t tx_payload_len = 0;
uint8_t tx_payload[kMaxPayloadLen];
unsigned long tx_seq = 0;            // 已发最后一个 seq（从 1 起，8 位十进制零填充）
unsigned long tx_send_ok = 0;        // sent=收到 ACK 的发送累计（ESB 交付口径）
unsigned long tx_send_fail = 0;      // 发送失败（MAX_RT）累计（内部计数，不上帧——与 lost 同源）
unsigned long tx_lost_total = 0;     // lost=PLOS_CNT 周期差分累计
unsigned long tx_retries_total = 0;  // retries=ARC_CNT 逐包直读累计
uint8_t last_plos = 0;              // 上一报告周期 PLOS 读数基线（差分用）
uint32_t tx_next_send_ms = 0;

// ---- counter_report_task 状态（reporter 侧） ----
uint32_t report_period_ms = 0;
bool report_started = false;
uint32_t next_report_ms = 0;

// ---- peer 侧接收排空缓冲 ----
uint8_t rx_payload[kMaxPayloadLen];

#if NODE_ROLE == 1
// ARC 累计：ARC_CNT（OBSERVE_TX 低 4 位）为"按包复位"语义——新包发送开始即清零，因此
// 发送完成时刻的读数恰为该包重传数，直加即得总重传（不做差分：按包复位语义下差分会把
// 读数回落误判为回绕而虚增）。仅由发送路径每包调用一次；报告周期不调用，防双计。
void accumulate_arc_after_send() {
    tx_retries_total += radio.observe_tx() & 0x0F;
}

// PLOS 累计：PLOS_CNT（OBSERVE_TX 高 4 位）为跨包累计、只在写 RF_CH 时清零、饱和保护于
// 15——每报告周期"读-差分-累计"，随后写 RF_CH（同值 setChannel 重写）清零，把饱和钳口
// 窗压缩到单个报告周期内（500ms≈25 包，周期内丢包 >15 才钳口漏计，README 口径声明）。
void accumulate_plos_periodic() {
    const uint8_t plos = (radio.observe_tx() >> 4) & 0x0F;
    // 无回绕处理：PLOS_CNT 按 datasheet 饱和于 15 不回绕，且每周期写 RF_CH 清零后基线
    // last_plos 恒 0，恒满足 plos>=last_plos（原 nibble+16 回绕分支为不可达死码，已删）。
    tx_lost_total += (uint8_t)(plos - last_plos);
    radio.setChannel(link_channel);  // 写 RF_CH=datasheet 指定的 PLOS_CNT 唯一复位途径
    last_plos = 0;                   // 清零后下周期基线归零
}
#endif  // NODE_ROLE == 1

}  // namespace

// ===================== esb_traffic_task：ESB 业务流（两角色） =====================

void esb_traffic_task_begin(uint8_t channel, uint32_t interval_ms, uint16_t payload_len) {
    link_channel = channel > 125 ? 125 : channel;  // RF_CH 域钳制（2.400~2.525GHz）
    tx_interval_ms = interval_ms > 0 ? interval_ms : 1;
    // 载荷长钳制到 [8, 32]：前 8 字节必须放得下 seq 文本，上限=NRF24 单载荷 32B
    if (payload_len < kMinPayloadLen) {
        payload_len = kMinPayloadLen;
    }
    if (payload_len > kMaxPayloadLen) {
        payload_len = kMaxPayloadLen;
    }
    tx_payload_len = payload_len;
    std::memset(tx_payload, kPayloadFiller, sizeof tx_payload);
#if NODE_ROLE == 1
    // reporter：PTX 配置——ESB 自动应答+自动重试，写管=链路地址
    if (!radio.begin()) {  // SPI/射频初始化失败：置未就绪并告警（保持 loop 不崩）
        Serial.println("[reporter] RF24 begin 失败：检查接线 CE=4/CSN=5/MOSI=23/MISO=19/SCK=18");
        return;
    }
    radio.setChannel(link_channel);                     // 2400+channel MHz
    radio.setPayloadSize((uint8_t)tx_payload_len);      // ESB 静态定长载荷
    radio.setAutoAck(true);                             // ESB 自动应答
    radio.setRetries(kArcRetryDelay, kArcRetryCount);   // 自动重试 500µs×15
    radio.openWritingPipe(NRF24_LINK_ADDRESS);
    radio.stopListening();  // PTX 常态：非监听
    radio_ready = true;
    tx_next_send_ms = millis();
    Serial.printf("[reporter] ESB 通道 %u（%u MHz）节拍 %lums 载荷 %uB 地址 %.5s\r\n",
                  (unsigned)link_channel, (unsigned)(2400 + link_channel),
                  (unsigned long)tx_interval_ms, (unsigned)tx_payload_len,
                  (const char *)NRF24_LINK_ADDRESS);
#elif NODE_ROLE == 2
    // peer：PRX 配置——同一链路地址开 RX 管，纯接收排空（不发不吐帧）
    if (!radio.begin()) {
        Serial.println("[peer] RF24 begin 失败：检查接线 CE=4/CSN=5/MOSI=23/MISO=19/SCK=18");
        return;
    }
    radio.setChannel(link_channel);                // 与 reporter 同通道
    radio.setPayloadSize((uint8_t)tx_payload_len); // 与 reporter 同定长
    radio.setAutoAck(true);                        // RX 侧硬件自动回 ACK（ESB 对端义务）
    radio.openReadingPipe(1, NRF24_LINK_ADDRESS);  // 开 RX 管与 reporter 写管同址
    radio.startListening();                        // PRX 常态：常监听
    radio_ready = true;
    Serial.printf("[peer] ESB 通道 %u（%u MHz）RX 管已开，纯接收排空\r\n",
                  (unsigned)link_channel, (unsigned)(2400 + link_channel));
#endif
}

void esb_traffic_task_tick() {
#if NODE_ROLE == 1
    if (!radio_ready) {
        return;  // begin 失败（接线问题）时空转，保持 loop 不崩
    }
    const uint32_t now = millis();
    // 固定节拍发送：落后过多时不补发连发，直接对齐到下一拍
    if ((int32_t)(now - tx_next_send_ms) >= 0) {
        tx_next_send_ms = now + tx_interval_ms;
        // seq 从 1 递增；到 8 位十进制上限后回绕从 1 重新开始
        if (tx_seq >= kSeqTextMax) {
            tx_seq = 0;
        }
        tx_seq += 1;
        std::snprintf((char *)tx_payload, 9, "%08lu", tx_seq);  // 前 8 字节=ASCII 十进制零填充
        tx_payload[8] = kPayloadFiller;  // 修复 snprintf 结尾 NUL，保持定长
        // ESB 阻塞写：硬件自动应答+自动重试（500µs×15），返回 true=收到 ACK
        const bool ok = radio.write(tx_payload, (uint8_t)tx_payload_len);
        if (ok) {
            tx_send_ok += 1;
        } else {
            tx_send_fail += 1;  // MAX_RT 重试掏空（lost 同源；内部计数不上帧）
            radio.flush_tx();   // 清掉滞留 FIFO 的失败载荷，避免堵塞后续发送
        }
        accumulate_arc_after_send();  // 按包复位语义：完成时刻读数=该包重传数
    }
#elif NODE_ROLE == 2
    // peer：非阻塞排空 RX FIFO（纯接收对端：不解析内容、不吐帧）
    while (radio_ready && radio.available()) {
        radio.read(rx_payload, (uint8_t)sizeof rx_payload);
    }
#endif
}

// ===================== counter_report_task：reporter 侧计数与上报 =====================

void counter_report_task_begin(uint32_t period_ms) {
#if NODE_ROLE == 1
    report_period_ms = period_ms > 0 ? period_ms : 1;
    report_started = true;
    next_report_ms = millis() + report_period_ms;
#endif
}

void counter_report_task_tick() {
#if NODE_ROLE == 1
    if (!report_started || !radio_ready) {
        return;  // 未 begin/射频未就绪（角色配错）时空转，保持 loop 不崩
    }
    if ((int32_t)(millis() - next_report_ms) >= 0) {
        next_report_ms += report_period_ms;
        if ((int32_t)(millis() - next_report_ms) >= 0) {
            next_report_ms = millis() + report_period_ms;  // 长阻塞后重对齐，不连发补帧
        }
        // 1) PLOS 读-差分-累计（ARC 已在发送路径逐包累计，此处不重复调用防双计）
        accumulate_plos_periodic();
        // 2) RPD 采样：发送间隙短暂进 RX 监听窗（名义 ~200µs）读 1bit 锁存位——门限
        //    -64dBm，仅 nRF24L01+（P 型）硬件有效（非 + 型恒读 0）；窗内读数=该窗内信道上
        //    是否出现过 >-64dBm 的信号（置位源=同频其他射频/环境干扰——本拓扑对端纯接收
        //    不发射，仅回 ESB ACK 且不在监听窗内，口径见 README）
        radio.startListening();
        delayMicroseconds(kRpdListenUs);
        const unsigned rpd = radio.testRPD() ? 1u : 0u;  // 窗内仍在 RX 态时读锁存位
        // 回 PTX 常态。RF24 1.6.2 的 stopListening 仅在启用 ack payload 时才 flush_tx
        // （本工程未启用）——TX FIFO 由写路径管理：成功包硬件随 ACK 出队，失败包由上面
        // MAX_RT 分支显式 flush_tx，此处不依赖 stopListening 清发送缓冲。
        radio.stopListening();
        // 3) 编码吐串口（115200，\r\n 结尾）：NRF,<seq>,<sent>,<lost>,<retries>,<rpd>
        Serial.println(encode_nrf24_frame(tx_seq, tx_send_ok, tx_lost_total,
                                          tx_retries_total, rpd)
                           .c_str());
    }
#endif
}
