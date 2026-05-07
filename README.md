# Voice Input Linux

Linux 桌面语音输入工具。按快捷键开始录音，再按一次停止；应用会把麦克风语音发送到你配置的 ASR 服务，拿到识别文本后粘贴到当前输入位置。

> 这个项目不是火山引擎或豆包官方客户端。使用豆包 ASR 时，你需要自行开通火山引擎语音识别服务并配置自己的 App Key / Access Key。

## 功能

- 系统托盘后台常驻，支持控制面板和轻量悬浮窗。
- 默认右 Alt 切换录音，也可绑定桌面环境的全局快捷键。
- 支持 X11 和 Wayland；Wayland 推荐配合 `ydotoold` 完成自动点击和粘贴。
- 接入火山引擎 / 豆包大模型语音识别，支持实时识别、二遍识别和整句返回模式。
- 支持模型自动标点、数字规整、语义顺滑，以及应用侧“末尾句号”开关。
- 支持麦克风下拉选择、麦克风电平测试、历史记录、环境检查。
- 设置修改后自动保存，不需要点击“保存”。
- 支持 AppImage 打包分发、桌面入口安装和 systemd user service 自启动。

## 适用场景

- 在 Linux 桌面上把语音快速输入到浏览器、编辑器、聊天工具或终端。
- 想用自己的 ASR 服务密钥，不希望依赖浏览器插件或云端账号同步。
- 需要 Wayland 下可工作的“录音 -> 识别 -> 粘贴”工作流。

不适合的场景：

- 离线识别。本项目当前默认使用在线 ASR。
- 多人会议转写。本项目定位是个人桌面输入，不是会议记录系统。
- 不允许任何模拟键鼠输入的环境。Wayland 自动粘贴通常需要 `ydotoold` 和 `/dev/uinput` 权限。

## 系统要求

- Linux x86_64 桌面环境。
- X11 或 Wayland 会话。
- PipeWire / PulseAudio / ALSA 中至少有一个可用麦克风输入。
- 推荐 systemd user service，用于后台常驻和自启动。
- AppImage 运行通常需要 FUSE；如果系统不能直接运行 AppImage，可使用 `APPIMAGE_EXTRACT_AND_RUN=1`。

AppImage 已包含 Python、PySide6、应用代码和主要 Python 依赖。它不包含这些宿主系统能力：

- `ydotool` / `ydotoold`
- `xdotool`
- `wl-copy` / `xclip` / `xsel`
- 音频服务、输入法、FUSE、glibc

## 快速开始：AppImage

从 GitHub Releases 下载最新的 `VoiceInputLinux-*-x86_64.AppImage`，然后运行：

```bash
chmod +x VoiceInputLinux-*-x86_64.AppImage
./VoiceInputLinux-*-x86_64.AppImage
```

首次运行会打开控制面板。建议先做三件事：

1. 打开“环境检查”，确认麦克风、ASR 配置和输入 backend 是否可用。
2. 打开“模型”页，填写豆包 ASR 的 App Key / Access Key。
3. 如果使用 Wayland，按下文配置 `ydotoold`。

安装桌面入口和自启动：

```bash
./VoiceInputLinux-*-x86_64.AppImage install
```

该命令会安装：

- 应用菜单入口：`~/.local/share/applications/voice-input-linux.desktop`
- 桌面快捷方式：`~/Desktop/voice-input-linux.desktop`，或系统 `XDG_DESKTOP_DIR` 指定的目录
- systemd user service：`voice-input-linux.service`

部分桌面环境会要求右键桌面快捷方式，选择“允许启动”或“信任此启动器”后才显示正常图标。

卸载：

```bash
./VoiceInputLinux-*-x86_64.AppImage uninstall
```

## 发行版依赖

Wayland 用户推荐安装 `ydotool` 和剪贴板工具：

```bash
# Arch / Manjaro
sudo pacman -S ydotool wl-clipboard

# Debian / Ubuntu
sudo apt install ydotool wl-clipboard

# Fedora
sudo dnf install ydotool wl-clipboard
```

X11 用户推荐安装：

```bash
# Arch / Manjaro
sudo pacman -S xdotool xclip

# Debian / Ubuntu
sudo apt install xdotool xclip

# Fedora
sudo dnf install xdotool xclip
```

如果 AppImage 无法启动，按发行版安装 FUSE 兼容包，或临时使用：

```bash
APPIMAGE_EXTRACT_AND_RUN=1 ./VoiceInputLinux-*-x86_64.AppImage
```

## 配置豆包 ASR

配置文件默认位置：

```bash
~/.config/voice-input-linux.env
```

也可以用环境变量指定：

```bash
VOICE_INPUT_CONFIG_FILE=/path/to/voice-input-linux.env ./VoiceInputLinux-*-x86_64.AppImage
```

常用配置：

```bash
VOICE_INPUT_ASR=doubao

DOUBAO_ASR_APP_KEY=你的 App Key
DOUBAO_ASR_ACCESS_KEY=你的 Access Key
DOUBAO_ASR_RESOURCE_ID=volc.seedasr.sauc.duration
DOUBAO_ASR_MODE=realtime_final
DOUBAO_ASR_ENABLE_PUNC=true
DOUBAO_ASR_ENABLE_ITN=true
DOUBAO_ASR_ENABLE_DDC=false
DOUBAO_ASR_ENABLE_NONSTREAM=true

VOICE_INPUT_HOTKEY_BACKEND=auto
VOICE_INPUT_HOTKEY_KEY=right_alt

VOICE_INPUT_INJECTOR_BACKEND=auto
VOICE_INPUT_PASTE_AT_MOUSE=true
VOICE_INPUT_PASTE_HOTKEY=ctrl+v
VOICE_INPUT_APPEND_FINAL_PUNCTUATION=true

VOICE_INPUT_SAMPLE_RATE=16000
VOICE_INPUT_CHANNELS=1
VOICE_INPUT_CHUNK_MS=200
VOICE_INPUT_DEVICE=
```

`DOUBAO_ASR_RESOURCE_ID` 常见取值：

```text
volc.seedasr.sauc.duration    # 小时版
volc.seedasr.sauc.concurrent  # 并发版
```

如果你在火山控制台开通的是并发版，请改为 `volc.seedasr.sauc.concurrent`。

## 识别模式

可以在控制面板“模型 -> 识别模式”里修改：

| 模式 | 配置值 | 特点 |
| --- | --- | --- |
| 实时 + 二遍识别 | `realtime_final` | 默认推荐。先实时出字，再对分句做二遍识别，最终文本通常更稳。 |
| 实时逐字 | `realtime` | 延迟最低，最终结果可能不如二遍识别稳定。 |
| 整句返回 | `stream_input` | 持续上传音频，服务端整句返回，速度慢一点但结果更完整。 |
| 自定义 Endpoint | `custom` | 保留手动填写的 Endpoint 和二遍识别开关，适合调试或接入兼容服务。 |

标点相关配置：

- `VOICE_INPUT_APPEND_FINAL_PUNCTUATION=false`：不自动补末尾 `。` 或 `.`，并删除 ASR 返回的最终句号。
- `DOUBAO_ASR_ENABLE_PUNC=false`：关闭模型自动标点。模型返回的逗号、句号、问号等都会受影响。
- 这两个开关互相独立。前者只控制最终文本末尾，后者控制发给豆包 ASR 的请求参数。

## Wayland：配置 ydotoold

Wayland 默认不允许普通应用随意监听全局按键或模拟键鼠输入。`ydotool` 是命令行客户端，`ydotoold` 是后台守护进程；`ydotoold` 需要访问 `/dev/uinput`，用于创建虚拟键盘和鼠标。

检查 `/dev/uinput`：

```bash
ls -l /dev/uinput
```

如果不存在，加载内核模块：

```bash
sudo modprobe uinput
```

配置用户权限：

```bash
sudo groupadd -f uinput
sudo usermod -aG uinput "$USER"

sudo tee /etc/udev/rules.d/99-uinput.rules >/dev/null <<'EOF'
KERNEL=="uinput", GROUP="uinput", MODE="0660", OPTIONS+="static_node=uinput"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger
```

重新登录一次，让当前会话拿到 `uinput` 组权限。验证：

```bash
id
ls -l /dev/uinput
```

启动 `ydotoold`：

```bash
systemctl --user enable --now ydotool.service
```

如果发行版没有提供 `ydotool.service`，创建用户服务：

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/ydotool.service <<'EOF'
[Unit]
Description=ydotool daemon

[Service]
Type=simple
ExecStart=/usr/bin/ydotoold
Restart=on-failure

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now ydotool.service
```

验证：

```bash
systemctl --user status ydotool.service --no-pager
ls -l "$XDG_RUNTIME_DIR/.ydotool_socket"
ydotool type -- ''
```

看到 `$XDG_RUNTIME_DIR/.ydotool_socket`，且 `ydotool type -- ''` 不报错，就表示 `ydotoold` 可用。

## Wayland：全局快捷键

Wayland 下内置 `pynput` 可能监听不到全局快捷键。推荐在 GNOME / KDE / Sway / Hyprland 等桌面环境里，把全局快捷键绑定到：

```bash
/path/to/VoiceInputLinux-*-x86_64.AppImage toggle
```

然后在设置里把“快捷键 backend”改为 `none`，避免按一次触发两次。

源码运行时可绑定：

```bash
python -m voice_input.main toggle
```

## X11

X11 下通常可以直接使用默认设置：

- 快捷键 backend：`pynput`
- 输入 backend：`xdotool` 或剪贴板 fallback

如果当前应用无法接收模拟输入，可以改用剪贴板粘贴：

```bash
VOICE_INPUT_INJECTOR_BACKEND=clipboard
```

## 粘贴快捷键

普通图形应用通常使用：

```bash
VOICE_INPUT_PASTE_HOTKEY=ctrl+v
```

终端常用：

```bash
VOICE_INPUT_PASTE_HOTKEY=ctrl+shift+v
```

也可以尝试：

```bash
VOICE_INPUT_PASTE_HOTKEY=shift+insert
```

如果 `VOICE_INPUT_PASTE_AT_MOUSE=true`，应用会在识别结束后先点击当前鼠标位置，再发送粘贴快捷键。

## 麦克风选择

图形界面方式：

1. 打开控制面板。
2. 进入“设置 -> 录音 -> 麦克风”。
3. 从下拉框选择有声音的输入设备。
4. 点击“测试”查看电平。

命令行列出设备：

```bash
python - <<'PY'
import sounddevice as sd

for i, d in enumerate(sd.query_devices()):
    if d.get("max_input_channels", 0) > 0:
        print(i, d["name"], d.get("default_samplerate"))
PY
```

`VOICE_INPUT_DEVICE` 可以填写设备编号或设备名。设备编号可能随插拔变化，长期使用建议填写设备名。

## CLI

AppImage 和源码运行都支持同一组命令：

```bash
voice-input-linux              # 启动后台服务并显示控制面板
voice-input-linux run          # 只启动后台服务
voice-input-linux show         # 显示控制面板
voice-input-linux toggle       # 切换录音
voice-input-linux start        # 开始录音
voice-input-linux stop         # 停止录音
voice-input-linux settings     # 打开设置
voice-input-linux quit         # 退出后台服务
voice-input-linux install      # 安装桌面入口和 user service
voice-input-linux uninstall    # 卸载桌面入口和 user service
```

AppImage 用法示例：

```bash
./VoiceInputLinux-*-x86_64.AppImage toggle
```

## 源码运行

```bash
git clone https://github.com/ezhonghu/openShanDianShuo.git
cd openShanDianShuo/voice_input_linux

python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

python -m voice_input.main
```

开发模式安装命令：

```bash
pip install -e .
voice-input-linux
```

## AppImage 打包

在 x86_64 Linux 上构建：

```bash
./packaging/appimage/build_appimage.sh
```

指定版本号：

```bash
VERSION=0.1.0 ./packaging/appimage/build_appimage.sh
```

输出文件：

```bash
dist/VoiceInputLinux-YYYY.MM.DD-x86_64.AppImage
```

为了提高兼容性，建议在你希望支持的最老 Linux 发行版上构建，例如 Ubuntu 22.04 或 Debian stable。

构建脚本也提供实验性的 glibc 打包模式：

```bash
BUNDLE_GLIBC=1 VERSION=0.1.0-glibc ./packaging/appimage/build_appimage.sh
```

这个模式只能作为兼容性实验。正式分发仍建议用较老发行版或容器构建。

## 常见问题

### 监听不到快捷键

- Wayland 下推荐绑定桌面环境的全局快捷键到 `AppImage toggle`。
- Right Alt 在部分键盘布局里会表现为 AltGr，可以改用其他快捷键或 `evdev`。
- 如果已经绑定桌面环境全局快捷键，把应用内快捷键 backend 改为 `none`。

### 无法自动粘贴

- Wayland 下确认 `ydotoold` 正在运行。
- 检查 `$XDG_RUNTIME_DIR/.ydotool_socket` 是否存在。
- 终端里把粘贴快捷键改为 `ctrl+shift+v` 或 `shift+insert`。
- 某些应用禁止模拟输入时，识别文本仍会保留在剪贴板，可手动粘贴。

### 麦克风没声音

- 打开“环境检查”，看当前麦克风是否可见。
- 在“设置 -> 录音 -> 麦克风”里换一个输入设备。
- USB 麦克风插拔后，设备编号可能变化，建议使用设备名。

### 如何让末尾没有句号

关闭“末尾句号 / 保留/补末尾句号”即可。对应配置：

```bash
VOICE_INPUT_APPEND_FINAL_PUNCTUATION=false
```

关闭后，应用不会补句号，也会删除 ASR 返回的最终 `。` 或 `.`。如果你想去掉句子中间由模型生成的所有标点，再关闭“模型自动标点”：

```bash
DOUBAO_ASR_ENABLE_PUNC=false
```

### AppImage 打不开

- 确认文件有执行权限：`chmod +x VoiceInputLinux-*-x86_64.AppImage`
- 安装 FUSE 兼容包。
- 临时使用：`APPIMAGE_EXTRACT_AND_RUN=1 ./VoiceInputLinux-*-x86_64.AppImage`
- 如果目标系统 glibc 太旧，请在更老的发行版上重新构建 AppImage。

## 隐私与安全

- App Key 和 Access Key 只保存在本机配置文件，不会写入日志。
- 录音音频会发送到你配置的 ASR 服务；请确认你使用的服务条款和隐私政策。
- `ydotoold` 具备模拟全局键鼠输入的能力，只应授予可信用户。
- AppImage 分发包不包含用户配置和密钥。
- 日志可能包含错误信息、请求 ID、环境检测结果和识别流程状态；提交 issue 前请检查日志里是否有敏感信息。

## 开发

运行测试：

```bash
. .venv/bin/activate
pytest
```

编译检查：

```bash
python -m compileall -q voice_input tests
```

测试覆盖包括：

- 配置读写和默认配置生成
- 豆包 ASR 请求参数、帧解析和文本提取
- 音频重采样
- 文本后处理
- hotkey backend 配置
- 剪贴板和输入 backend
- 环境检查报告
- 设置界面滚轮误触保护

## 贡献

欢迎提交 issue 和 pull request。建议在 PR 里说明：

- 你使用的桌面环境：GNOME / KDE / Sway / Hyprland / 其他
- 会话类型：X11 或 Wayland
- 发行版和版本
- 使用的输入 backend：`fcitx5` / `xdotool` / `wtype` / `ydotool` / `clipboard`
- 复现步骤和相关日志

提交代码前请运行：

```bash
pytest
python -m compileall -q voice_input tests
```

## 开源协议

本项目使用 MIT License，详见 [LICENSE](LICENSE)。

MIT 是宽松开源协议，适合这个项目的目标：让用户、发行版维护者和其他开发者可以低成本使用、修改、打包和二次分发，同时保留版权声明和免责声明。
