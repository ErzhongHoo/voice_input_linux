from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActionableError:
    title: str
    summary: str
    suggestion: str
    primary_action: str


def describe_error(message: str, context: str = "") -> ActionableError:
    text = " ".join(str(message).split())
    lower = f"{context} {text}".lower()
    if any(token in lower for token in ["api key", "access key", "token", "resource id", "app key", "密钥", "key 为空"]):
        return ActionableError(
            title="模型配置不完整",
            summary="模型凭证缺失或不可用。",
            suggestion="打开模型设置，检查 API Key、Access Key、Resource ID 和模型名。",
            primary_action="model",
        )
    if any(token in lower for token in ["websocket", "timeout", "timed out", "http", "连接", "network", "网络", "endpoint"]):
        return ActionableError(
            title="模型连接失败",
            summary="模型服务暂时无法连接。",
            suggestion="打开模型设置检查 Endpoint 和模型名；如果配置正确，请稍后重试。",
            primary_action="model",
        )
    if any(token in lower for token in ["sounddevice", "麦克风", "audio", "input device", "无法打开默认麦克风", "recorder"]):
        return ActionableError(
            title="麦克风不可用",
            summary="当前麦克风无法打开或没有输入。",
            suggestion="打开设置选择另一个麦克风，或在环境检查里确认系统录音权限。",
            primary_action="settings",
        )
    if any(token in lower for token in ["fcitx", "xdotool", "wtype", "ydotool", "clipboard", "剪贴板", "无法输入", "inject"]):
        return ActionableError(
            title="文字输入失败",
            summary="识别完成了，但文字没有成功输入到当前窗口。",
            suggestion="打开环境检查确认输入法、剪贴板和注入工具是否可用。",
            primary_action="environment",
        )
    if any(token in lower for token in ["hotkey", "evdev", "pynput", "快捷键"]):
        return ActionableError(
            title="快捷键不可用",
            summary="当前快捷键后端无法监听按键。",
            suggestion="打开设置重新录入快捷键；Wayland 下也可以安装后台服务并绑定系统快捷键。",
            primary_action="settings",
        )
    if any(token in lower for token in ["empty", "为空", "无结果", "没有识别"]):
        return ActionableError(
            title="没有识别到文字",
            summary="这次录音没有得到有效文本。",
            suggestion="确认麦克风音量条有输入后再重试，必要时换一个麦克风。",
            primary_action="settings",
        )
    return ActionableError(
        title="操作失败",
        summary=text[:80] or "发生未知错误。",
        suggestion="复制错误信息后检查配置，或打开环境检查定位依赖问题。",
        primary_action="copy",
    )
