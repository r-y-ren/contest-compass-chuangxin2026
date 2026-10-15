"""EMC 报告节三流程分节渲染（R89）——重写规约与签名意图详见 fn_docs/responsibility.md R89 功能块。

映射层（run_demo._report_payload 改造点）按结果形状三分支+段内 'flow' 标签（形状回推
口径与 execute_scenario._streams_note 一致：readings 列表→conduction、spectrum dict→
radiation、其余含 points→sweep）；渲染层（本模块）按 flow 分节——传导=读数/裕量表+检波器
+passed+口径注记、辐射=谱图表（有界行渲染，全谱溯源归 result.json）+洁净度+补偿注记、
扫频=频点/读数(+spurious) 点表；标题随流程（EMC 传导摸底/EMC 辐射摸底/EMC 步进扫频）。

文本消毒助手（_sanitize_cell/_quoted_text_lines）为 build_report 模块私有——本模块
实现期经函数体内延迟导入复用（build_report→本模块为模块级导入，反向延迟防环），
不跨模块上提。
"""


#: 辐射谱 bin 渲染行数上限（有界渲染——超限截断并显式注明全谱去向，不静默截断）。
_RADIATION_MAX_ROWS = 16

#: 三子渲染器共用的模拟读数口径引言行（与原 build_report._emc_md 引言逐字一致）。
_SIMULATED_INTRO_LINE = (
    "> 本段读数全部由模拟后端产生（simulated 读数），非 CISPR 16-1-1 测量接收机实测值。"
)

#: 三子渲染器共用的行尾声明（全段读数带模拟标记）。
_SIMULATED_TAIL_LINE = "> simulated = True（本段全部读数带模拟标记）"


def render_emc_flow_section(result: dict, missing: "list[str]") -> "str | None":
    """EMC 报告节分发渲染（纯分发：形状判定+委派，无内联渲染）。

    :param result: 报告结果对象——无 'emc' 键→返回 None（不嵌段）。
    :param missing: 缺失清单（'emc' 非 dict→缺项段并记 missing，B18 低#15 口径，
        不据此附 simulated_parts/emc 级声明）。
    :return: EMC 段 markdown 文本或 None；dict→按 'flow' 标签分派三子渲染器之一
        （缺省形状回推：readings 列表→conduction / spectrum dict→radiation /
        其余→sweep）；三子器输出统一全段 '> ' 引用行+行尾 simulated=True 声明。
    :raises: 不抛（形状异常落缺项段如实标注）。
    """
    emc = result.get("emc")
    if emc is None:
        return None
    if not isinstance(emc, dict):
        missing.append("emc（result['emc'] 非 dict——EMC 段缺项）")
        # 缺项段标题不含具体流程（形状不可知——无从回推 conduction/radiation/sweep）。
        return "\n".join(
            [
                "## EMC 摸底（模拟）",
                "",
                "> 缺项：result['emc'] 形状异常（非 dict）——不虚构读数。",
            ]
        )

    # flow 判定：段内 'flow' 标签为三值之一则用之；未知/缺省→形状回推
    # （口径与 execute_scenario._streams_note 一致：readings 列表→conduction、
    # spectrum dict→radiation、其余→sweep）。
    flow = emc.get("flow")
    if flow not in ("conduction", "radiation", "sweep"):
        if isinstance(emc.get("readings"), list):
            flow = "conduction"
        elif isinstance(emc.get("spectrum"), dict):
            flow = "radiation"
        else:
            flow = "sweep"

    if flow == "conduction":
        return _emc_conduction_md(emc)
    if flow == "radiation":
        return _emc_radiation_md(emc)
    return _emc_sweep_md(emc)


def _emc_conduction_md(emc: dict) -> str:
    """传导摸底段渲染（表体演化自原 build_report._emc_md 正文——行为等价迁移）。

    :param emc: emc 段 dict（readings 列表/detector/passed/compliance_note|
        limit_note|reading_note|conversion_note/warnings/disclaimer）。
    :return: 段 markdown——标题「EMC 传导摸底（模拟）」+模拟读数口径引言行+读数/
        裕量表（频点 Hz/读数 dBm/换算 dBµV/裕量 dB——margin None→「未判定（未提供
        限值线）」）+检波器行（detector 空/纯空白→跳过该行不输出——I-1 不抛口径）
        +passed 判定行（None→未判定；True/False→合规/不合规
        （演示口径，非认证））+注记行+warnings 逐条+disclaimer+simulated=True 行；
        动态文本单元格消毒（换行折叠 ' / '、'|' 转义——B18 中#8/#9）。
    :raises: 不抛（readings 空→缺项行「无读数——不虚构」）。
    """
    # 延迟导入（build_report 将模块级导入本模块，反向顶层导入成环——模块 docstring 口径）。
    from src.build_report.build_report import _quoted_text_lines, _sanitize_cell

    lines = [
        "## EMC 传导摸底（模拟）",
        "",
        _SIMULATED_INTRO_LINE,
    ]
    readings = emc.get("readings")
    if isinstance(readings, list) and readings:
        lines.append("> 频点 (Hz) | 读数 (dBm) | 换算 (dBµV) | 裕量 (dB)")
        for reading in readings:
            if not isinstance(reading, dict):
                continue
            margin = reading.get("margin_db")
            margin_text = (
                "未判定（未提供限值线）" if margin is None else f"{margin} dB"
            )
            lines.append(
                f"> {_sanitize_cell(str(reading.get('freq_hz')))} Hz"
                f" | {_sanitize_cell(str(reading.get('power_dbm')))} dBm"
                f" | {_sanitize_cell(str(reading.get('power_dbuv')))} dBµV"
                f" | {_sanitize_cell(margin_text)}"
            )
    else:
        lines.append("> 缺项：无读数（readings 为空）——不虚构。")
    # 空/纯空白 detector → 跳过检波器行渲染（I-1："" 时 splitlines() 为空列表，
    # 取 [0] 会 IndexError 违反「不抛」契约——不输出该行，不虚构）。
    detector = str(emc.get("detector")) if emc.get("detector") is not None else None
    if detector is not None and detector.strip():
        lines.append(f"> 检波器：{_sanitize_cell(detector.splitlines()[0])}")
        lines.extend(
            f"> {_sanitize_cell(part)}" for part in detector.splitlines()[1:]
        )
    passed = emc.get("passed")
    if passed is None:
        lines.append("> passed：未判定（未提供限值线）")
    else:
        verdict = "合规（演示口径，非认证）" if passed else "不合规（演示口径，非认证）"
        lines.append(f"> passed：{verdict}")
    for key in ("compliance_note", "limit_note", "reading_note", "conversion_note"):
        value = emc.get(key)
        if isinstance(value, str):
            lines.extend(_quoted_text_lines(value))
    warnings = emc.get("warnings")
    if isinstance(warnings, list):
        for item in warnings:
            lines.extend(_quoted_text_lines(str(item)))
    disclaimer = emc.get("disclaimer")
    if isinstance(disclaimer, str):
        lines.extend(_quoted_text_lines(disclaimer))
    lines.append(_SIMULATED_TAIL_LINE)
    return "\n".join(lines)


def _emc_radiation_md(emc: dict) -> str:
    """辐射摸底段渲染。

    :param emc: emc 段 dict（spectrum{freqs,power_db}/cleanliness{in_band_peaks,
        out_of_band_ratio_db,peak_threshold_db,criterion}/compensated/
        compensation_note/uncertainty_db/compensation_confidence?/warnings/disclaimer）。
    :return: 段 markdown——标题「EMC 辐射摸底（模拟）」+模拟读数口径引言行+谱图表
        （频点 Hz/功率 dB——全谱 bin 有界渲染：行数上限+超限注明「全谱见
        result.json」，不静默截断；freqs/power_db 长度不齐→按短者渲染并附
        不齐注记行——M-1 不静默截短）+洁净度结论区（三指标+criterion 判据文字）+补偿区
        （compensated+note+不确定度+置信度汇总（如有））+warnings 逐条+disclaimer+
        simulated=True 行；消毒同传导。
    :raises: 不抛（spectrum 空/缺键→缺项行如实标注）。
    """
    # 延迟导入（build_report 将模块级导入本模块，反向顶层导入成环——模块 docstring 口径）。
    from src.build_report.build_report import _quoted_text_lines, _sanitize_cell

    lines = [
        "## EMC 辐射摸底（模拟）",
        "",
        _SIMULATED_INTRO_LINE,
    ]

    def _cell(value) -> str:
        """数值/文本单元格统一消毒（str() 后过 _sanitize_cell）。"""
        return _sanitize_cell(str(value))

    # 谱图表：freqs/power_db zip 逐行，行数有界——超限截断并注明全谱去向（result.json）。
    spectrum = emc.get("spectrum")
    freqs = spectrum.get("freqs") if isinstance(spectrum, dict) else None
    power_db = spectrum.get("power_db") if isinstance(spectrum, dict) else None
    bins = (
        list(zip(freqs, power_db))
        if isinstance(freqs, list) and isinstance(power_db, list)
        else []
    )
    # 长度不齐注记（M-1）：zip 按短者截短不再静默——两 list 在场且长度不齐时
    # 如实注明（真实 sim 输出恒同长，此为防御路径的如实标注）。
    length_mismatch = (
        isinstance(freqs, list)
        and isinstance(power_db, list)
        and len(freqs) != len(power_db)
    )
    if bins:
        lines.append("> 频点 (Hz) | 功率 (dB)")
        for freq, power in bins[:_RADIATION_MAX_ROWS]:
            lines.append(f"> {_cell(freq)} Hz | {_cell(power)} dB")
        if len(bins) > _RADIATION_MAX_ROWS:
            lines.append(
                f"> 谱 bin 共 {len(bins)} 行，此处列前 {_RADIATION_MAX_ROWS} 行"
                "——全谱见 result.json（不静默截断）"
            )
        if length_mismatch:
            lines.append(
                f"> 谱 freqs/power_db 长度不齐（{len(freqs)}/{len(power_db)}），"
                "按短者渲染"
            )
    else:
        lines.append("> 缺项：无谱数据（spectrum 缺失或为空）——不虚构。")
        if length_mismatch:
            lines.append(
                f"> 谱 freqs/power_db 长度不齐（{len(freqs)}/{len(power_db)}），"
                "按短者渲染"
            )

    # 洁净度区：三指标各一行 + criterion 判据文字多行（缺→缺项行）。
    cleanliness = emc.get("cleanliness")
    if isinstance(cleanliness, dict):
        for key, label, unit in (
            ("in_band_peaks", "带内峰簇数（in_band_peaks）", ""),
            ("out_of_band_ratio_db", "带外杂散比（out_of_band_ratio_db）", " dB"),
            ("peak_threshold_db", "峰判定阈值（peak_threshold_db）", " dB"),
        ):
            value = cleanliness.get(key)
            value_text = _cell(value) if value is not None else "未记录"
            suffix = unit if value is not None else ""
            lines.append(f"> {label}：{value_text}{suffix}")
        criterion = cleanliness.get("criterion")
        if criterion is not None:
            lines.extend(_quoted_text_lines(str(criterion)))
    else:
        lines.append("> 缺项：无洁净度结论（cleanliness 缺失或形状异常）——不虚构。")

    # 补偿区：compensated 布尔行 + note + 不确定度（如有）+ 置信度逐键汇总（如有）。
    compensated = emc.get("compensated")
    compensated_text = (
        "已补偿（compensated=True）" if compensated else "未补偿（compensated=False）"
    )
    lines.append(f"> 补偿：{compensated_text}")
    compensation_note = emc.get("compensation_note")
    if isinstance(compensation_note, str):
        lines.extend(_quoted_text_lines(compensation_note))
    uncertainty_db = emc.get("uncertainty_db")
    if uncertainty_db is not None:
        lines.append(f"> 谱不确定度（uncertainty_db）：{_cell(uncertainty_db)} dB")
    confidence = emc.get("compensation_confidence")
    if isinstance(confidence, dict):
        for key, count in confidence.items():
            lines.append(f"> 补偿置信度（{_cell(key)}）：{_cell(count)}")

    warnings = emc.get("warnings")
    if isinstance(warnings, list):
        for item in warnings:
            lines.extend(_quoted_text_lines(str(item)))
    disclaimer = emc.get("disclaimer")
    if isinstance(disclaimer, str):
        lines.extend(_quoted_text_lines(disclaimer))
    lines.append(_SIMULATED_TAIL_LINE)
    return "\n".join(lines)


def _emc_sweep_md(emc: dict) -> str:
    """步进扫频段渲染（points 形状原生渲染——修正扫频误挂传导标题+空裕量列的既有瑕疵）。

    :param emc: emc 段 dict（points 列表[{freq_hz,power_dbm,spurious?}]/n_points/
        warnings/disclaimer）。
    :return: 段 markdown——标题「EMC 步进扫频（模拟）」+模拟读数口径引言行+扫频点表
        （频点 Hz/读数 dBm+spurious 标记（如有））+n_points 总数行+warnings 逐条+
        disclaimer+simulated=True 行；消毒同传导。
    :raises: 不抛（points 空→缺项行如实标注）。
    """
    # 延迟导入（build_report 将模块级导入本模块，反向顶层导入成环——模块 docstring 口径）。
    from src.build_report.build_report import _quoted_text_lines, _sanitize_cell

    lines = [
        "## EMC 步进扫频（模拟）",
        "",
        _SIMULATED_INTRO_LINE,
    ]
    points = emc.get("points")
    if isinstance(points, list) and points:
        lines.append("> 频点 (Hz) | 读数 (dBm) | spurious")
        for point in points:
            if not isinstance(point, dict):
                continue
            spurious = point.get("spurious")
            spurious_text = "-" if spurious is None else str(spurious)
            lines.append(
                f"> {_sanitize_cell(str(point.get('freq_hz')))} Hz"
                f" | {_sanitize_cell(str(point.get('power_dbm')))} dBm"
                f" | {_sanitize_cell(spurious_text)}"
            )
        n_points = emc.get("n_points")
        n_points_text = _sanitize_cell(str(n_points)) if n_points is not None else "未记录"
        lines.append(f"> 扫频点总数（n_points）：{n_points_text}")
    else:
        lines.append("> 缺项：无扫频点（points 为空）——不虚构。")
    warnings = emc.get("warnings")
    if isinstance(warnings, list):
        for item in warnings:
            lines.extend(_quoted_text_lines(str(item)))
    disclaimer = emc.get("disclaimer")
    if isinstance(disclaimer, str):
        lines.extend(_quoted_text_lines(disclaimer))
    lines.append(_SIMULATED_TAIL_LINE)
    return "\n".join(lines)
