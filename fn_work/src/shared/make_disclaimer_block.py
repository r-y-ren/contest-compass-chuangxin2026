"""统一口径声明块（模拟/非CISPR/屏蔽盒/自建链路/GB42590 预研）——重写规约与签名意图详见 fn_docs/responsibility.md。"""
from __future__ import annotations

# 合法场景枚举（严格小写，大小写敏感：'EMC' 不在枚举内）。
VALID_SCENES: tuple[str, ...] = ("emc", "report", "emergency")

# 恒含行：emc/emergency 场景逐字携带；report 场景替换为标注口径行。
SIM_ALWAYS_LINE = "本测试为模拟演示，全部读数带 simulated 标记"
REPORT_ALWAYS_LINE = "报告中模拟部分均已标注"

# EMC 流程段（模拟后端声明——非 CISPR 16-1-1 测量接收机/模拟读数）。
EMC_LINES: tuple[str, ...] = (
    "EMC 摸底段口径：全部读数由模拟后端产生（simulated 读数），非 CISPR 16-1-1 测量接收机实测值。",
    "限值线比对结论仅用于演示余量计算方法，不构成符合性判定。",
    SIM_ALWAYS_LINE,
)

# 报告全局（屏蔽盒环境/仅自建链路/GB 42590 方法学预研定位/非 CISPR/数字纪律）。
# 注意：报告口径只声明"非 CISPR 意义上的测量"，不携带 emc 段专属的
# "CISPR 16-1-1 测量接收机"句式，两场景文案互不混入。
REPORT_LINES: tuple[str, ...] = (
    "报告全局口径：测量环境为屏蔽盒环境，全部结论仅在该环境内成立。",
    "受试对象仅限自建链路（自研发射/接收/馈线组合），不外推至其他受试设备。",
    "定位为 GB 42590 方法学预研：全文结论为方法学预研性质，非标准符合性测试。",
    "非 CISPR 意义上的测量：数据不可用于认证或符合性声明。",
    "数字纪律：报告关键数字均可回溯至原始数据文件，不做无出处修饰。",
    REPORT_ALWAYS_LINE,
)

# 急停页（停发射已执行声明）。
EMERGENCY_LINES: tuple[str, ...] = (
    "急停页口径：停发射已执行（stop_tx 静默与发射增益归零），安全路径不抛出异常。",
    "若静默步骤失败，事件记录中留有失败原因，可据此重试。",
    SIM_ALWAYS_LINE,
)

_SCENE_LINES: dict[str, tuple[str, ...]] = {
    "emc": EMC_LINES,
    "report": REPORT_LINES,
    "emergency": EMERGENCY_LINES,
}


def make_disclaimer_block(scene: str) -> str:
    """统一口径声明块（模拟/非CISPR/屏蔽盒/自建链路/GB42590 预研）。

    按 scene 枚举选取文案并逐行加 '> ' 前缀产出 markdown 引用块：
    - 'emc'：EMC 流程段——模拟后端声明（非 CISPR 16-1-1 测量接收机/模拟读数），
      恒含 SIM_ALWAYS_LINE（"全部读数带 simulated 标记"）；
    - 'report'：报告全局——屏蔽盒环境/仅自建链路/GB 42590 方法学预研定位/
      非 CISPR/数字纪律，恒含行替换为 REPORT_ALWAYS_LINE（"报告中模拟部分均已标注"）；
    - 'emergency'：急停页——停发射已执行声明，恒含 SIM_ALWAYS_LINE。

    每次调用都从模块级文案常量现拼新 str（内容幂等恒定、对象不复用）；
    scene 非 str 或不在枚举内（大小写敏感）→ ValueError，消息附合法枚举清单，
    供 run_emc_conduction_sim/run_emc_radiation_sim/run_emc_sweep/build_report
    四处调用方获得口径一致的声明文字。
    """
    if not isinstance(scene, str):
        raise ValueError(
            f"scene 必须为 str 枚举 {VALID_SCENES} 之一，"
            f"收到 {type(scene).__name__}: {scene!r}"
        )
    lines = _SCENE_LINES.get(scene)
    if lines is None:
        raise ValueError(
            f"未知声明场景: {scene!r}（大小写敏感），合法枚举: {VALID_SCENES}"
        )
    return "\n".join(f"> {line}" for line in lines)
