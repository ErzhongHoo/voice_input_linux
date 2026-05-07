from voice_input.environment import EnvironmentCheck, format_check_report, summarize_checks


def test_summarize_checks_reports_failures_first() -> None:
    checks = [
        EnvironmentCheck("系统", "A", "ok", "ok"),
        EnvironmentCheck("输入", "B", "warn", "warn"),
        EnvironmentCheck("音频", "C", "fail", "fail"),
    ]

    assert summarize_checks(checks) == "1 项失败，1 项需要注意，1 项正常"


def test_format_check_report_includes_detail() -> None:
    checks = [EnvironmentCheck("音频", "麦克风", "fail", "不可见", "选择另一个设备")]

    report = format_check_report(checks)

    assert "[失败] 音频 / 麦克风: 不可见" in report
    assert "选择另一个设备" in report
