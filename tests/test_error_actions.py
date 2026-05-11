from voice_input.error_actions import describe_error


def test_describe_error_points_model_credentials_to_model_settings() -> None:
    error = describe_error("API Key 为空，请先填写阿里云百炼 API Key", "model")

    assert error.primary_action == "model"
    assert error.title == "模型配置不完整"
    assert "API Key" in error.suggestion


def test_describe_error_points_microphone_errors_to_settings() -> None:
    error = describe_error("sounddevice failed to open input device", "recording")

    assert error.primary_action == "settings"
    assert error.title == "麦克风不可用"
    assert "麦克风" in error.suggestion


def test_describe_error_points_injection_errors_to_environment() -> None:
    error = describe_error("无法输入文字: xdotool not found", "injection")

    assert error.primary_action == "environment"
    assert error.title == "文字输入失败"
    assert "环境检查" in error.suggestion
