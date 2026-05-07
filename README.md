# Voice Input Linux

Linux 桌面语音输入应用。按右 Alt 开始录音，再按一次停止；应用把麦克风语音发给 ASR，识别完成后把文字输入到当前鼠标位置。

当前 MVP 已跑通：

- 系统托盘、轻量悬浮窗、设置窗口
- Right Alt 单击切换录音
- 豆包大模型流式语音识别模型 2.0
- 16 kHz / mono / PCM int16 little-endian 流式音频
- mock ASR 本地闭环测试
- 鼠标位置点击后自动粘贴
- systemd user service 自启动
- AppImage 打包分发

## 功能

- 后台常驻服务，托盘菜单包含开始/停止录音、设置、退出。
- 默认快捷键为右 Alt / `Alt_R` / `KEY_RIGHTALT`，不使用左 Alt。
- 快捷键 backend 抽象为 `pynput`、`evdev`、`none`，Wayland 下可改用 compositor 全局快捷键调用 CLI。
- 录音期间显示悬浮窗、计时和音量波形。
- 文本注入 backend 支持 `fcitx5`、`xdotool`、`wtype`、`ydotool`、剪贴板 fallback。
- `VOICE_INPUT_PASTE_AT_MOUSE=true` 时，识别结束会先点击当前鼠标位置，再粘贴文字。
- 控制面板统一提供录音、设置、自启动、桌面图标管理。
- 设置窗口可修改豆包 API 信息、快捷键、注入 backend、粘贴快捷键，并下拉选择麦克风。

## 快速开始

源码运行：

```bash
cd /home/ezhonghu/Developments/openShanDianShuo/voice_input_linux
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m voice_input.main
```

启动后会显示控制面板；关闭面板不会退出后台服务，应用会保留在系统托盘。

CLI 仍保留给系统服务、桌面全局快捷键和调试使用：

```bash
python -m voice_input.main run
python -m voice_input.main toggle
python -m voice_input.main start
python -m voice_input.main stop
python -m voice_input.main settings
python -m voice_input.main quit
```

## AppImage 用户依赖

AppImage 已经包含 Python、PySide6、应用代码和主要 Python 依赖；用户不需要安装 Python、pip 或本项目源码。

AppImage 不内置 `ydotool` / `ydotoold`。原因是 Wayland 下自动点击和自动粘贴依赖宿主系统的 `/dev/uinput` 权限，单纯把二进制打进 AppImage 也绕不开这一步。用户需要在系统里安装并启动 `ydotoold`。

推荐宿主依赖：

- Wayland：安装 `ydotool`，配置并启动 `ydotoold`。
- X11：安装 `xdotool`。
- 可选剪贴板工具：Wayland 可安装 `wl-clipboard` 提供 `wl-copy`；X11 可安装 `xclip` 或 `xsel`。
- AppImage 运行依赖：多数发行版需要 FUSE；如果 AppImage 无法启动，可安装发行版提供的 FUSE 兼容包，或用 `APPIMAGE_EXTRACT_AND_RUN=1` 运行。

常见发行版安装命令示例：

```bash
# Arch / Manjaro
sudo pacman -S ydotool xdotool wl-clipboard xclip

# Debian / Ubuntu
sudo apt install ydotool xdotool wl-clipboard xclip

# Fedora
sudo dnf install ydotool xdotool wl-clipboard xclip
```

安装后，Wayland 用户继续按下方 “ydotoold 配置” 完成 `/dev/uinput` 权限和后台服务配置。

## 配置文件

源码运行时默认优先读取当前目录 `.env`。AppImage 或安装后的 systemd 服务默认读取：

```bash
~/.config/voice-input-linux.env
```

也可以显式指定：

```bash
VOICE_INPUT_CONFIG_FILE=/path/to/voice-input-linux.env voice-input-linux
```

常用配置：

```bash
VOICE_INPUT_ASR=doubao
DOUBAO_ASR_ENDPOINT=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async
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
VOICE_INPUT_PREFER_FCITX5=true
VOICE_INPUT_PASTE_AT_MOUSE=true
VOICE_INPUT_PASTE_HOTKEY=ctrl+shift+v
VOICE_INPUT_APPEND_FINAL_PUNCTUATION=true

VOICE_INPUT_SAMPLE_RATE=16000
VOICE_INPUT_CHANNELS=1
VOICE_INPUT_CHUNK_MS=200
VOICE_INPUT_DEVICE=Wireless Mic Rx 模拟立体声
```

`VOICE_INPUT_DEVICE` 可填写 `sounddevice` 设备编号或设备名。设备编号会随插拔变化，稳定使用时更推荐使用设备名。也可以在应用的“设置 -> 高级 -> 麦克风”里直接下拉选择，保存后会自动写入这个配置项。

`VOICE_INPUT_APPEND_FINAL_PUNCTUATION=false` 时，识别结果末尾不会再由应用自动补 `。` 或 `.`；ASR 自己返回的问号、感叹号、句号等仍会保留。

`DOUBAO_ASR_ENABLE_PUNC=false` 时，豆包 ASR 请求会关闭模型自动标点；这会同时影响逗号、问号、句号等由模型预测的标点。设置界面里“应用自动补句号”和“模型自动标点”是两个开关：前者只控制本应用后处理，后者控制豆包 ASR 请求参数。

`DOUBAO_ASR_ENABLE_NONSTREAM=true` 会在双向流式优化版里开启二遍识别：先实时出字，再对分句音频复识别，以提高最终结果准确率。

`DOUBAO_ASR_MODE` 可在设置界面用“识别模式”修改：

- `realtime_final`：实时 + 二遍识别，默认推荐。
- `realtime`：实时逐字，最快，最终结果可能不如二遍稳定。
- `stream_input`：流式输入、整句返回，更稳但会慢一点。
- `custom`：保留手动填写的 Endpoint 和二遍识别开关。

## 豆包 ASR

当前接入的是火山引擎 / 豆包大模型流式语音识别 API：

- Endpoint：`wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async`
- Resource ID：`volc.seedasr.sauc.duration`
- 请求模型名：`bigmodel`
- 默认开启模型自动标点、ITN 和二遍识别；关闭自动标点可设置 `DOUBAO_ASR_ENABLE_PUNC=false`
- 音频：16 kHz、单声道、PCM signed 16-bit little-endian
- 分包：约 200 ms

模型 2.0 的关键资源参数是 `X-Api-Resource-Id`：

```text
volc.seedasr.sauc.duration    # 小时版
volc.seedasr.sauc.concurrent  # 并发版
```

如果控制台开通的是并发版，把 `DOUBAO_ASR_RESOURCE_ID` 改为 `volc.seedasr.sauc.concurrent`。

## Mock 测试

没有豆包 Key 时，先用 mock 验证录音、快捷键和粘贴闭环：

```bash
VOICE_INPUT_ASR=mock
VOICE_INPUT_MOCK_TEXT=这是一次语音输入测试。
```

打开任意输入框，把鼠标停在目标位置，按右 Alt 开始录音，再按右 Alt 停止。应用会粘贴 mock 文本。

## 鼠标位置粘贴

默认流程：

1. 把识别文本写入剪贴板。
2. 用 `ydotool click 0xC0` 点击当前鼠标位置。
3. 发送配置的粘贴快捷键。

不同应用的粘贴快捷键不同：

```bash
# 普通图形应用常用
VOICE_INPUT_PASTE_HOTKEY=ctrl+v

# GNOME Terminal / Konsole / Kitty / WezTerm 等终端常用
VOICE_INPUT_PASTE_HOTKEY=ctrl+shift+v

# 很多终端和传统 X11 应用也支持
VOICE_INPUT_PASTE_HOTKEY=shift+insert
```

如果某个终端把 `Ctrl+V` 绑定为粘贴图片或其他动作，把粘贴快捷键改为 `ctrl+shift+v` 或 `shift+insert`。

## X11 与 Wayland

X11：

- 全局快捷键通常可用 `pynput`。
- 文本输入可用 `xdotool type` 或剪贴板粘贴。

Wayland：

- 全局按键监听受 compositor 限制，`pynput` 可能监听不到。
- 推荐在 KDE/GNOME/Sway/Hyprland 的全局快捷键里绑定：

```bash
/path/to/VoiceInputLinux.AppImage toggle
```

源码运行时可绑定：

```bash
/home/ezhonghu/Developments/openShanDianShuo/voice_input_linux/.venv/bin/python -m voice_input.main toggle
```

绑定 compositor 快捷键后，把内置监听关闭，避免重复触发：

```bash
VOICE_INPUT_HOTKEY_BACKEND=none
```

Right Alt 在部分键盘布局里会表现为 AltGr。如果监听不到，改用 `evdev` 并配置 `VOICE_INPUT_EVDEV_KEY=KEY_RIGHTALT`，或改成其他可用按键。

## ydotoold 配置

Wayland 下推荐使用 `ydotoold` 完成鼠标点击和粘贴快捷键发送。`ydotool` 是命令行客户端，`ydotoold` 是后台守护进程；守护进程需要访问 `/dev/uinput`，相当于创建一个虚拟键盘/鼠标。

先检查系统是否有 `/dev/uinput`：

```bash
ls -l /dev/uinput
```

如果文件不存在，先加载 `uinput` 内核模块：

```bash
sudo modprobe uinput
```

然后配置用户权限：

```bash
sudo groupadd -f uinput
sudo usermod -aG uinput "$USER"

sudo tee /etc/udev/rules.d/99-uinput.rules >/dev/null <<'EOF'
KERNEL=="uinput", GROUP="uinput", MODE="0660", OPTIONS+="static_node=uinput"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger
```

重新登录一次，让当前用户会话拿到 `uinput` 组权限。验证：

```bash
id
ls -l /dev/uinput
```

`id` 输出里应该包含 `uinput`，`/dev/uinput` 的组也应该是 `uinput`。

启动 `ydotoold`：

```bash
systemctl --user enable --now ydotool.service
```

如果发行版没有提供 `ydotool.service`，创建一个用户服务：

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

如果当前登录会话的 `id` 还没有 `uinput` 组，但暂时不想重新登录，可给 user service 加 override：

```bash
mkdir -p ~/.config/systemd/user/ydotool.service.d
cat > ~/.config/systemd/user/ydotool.service.d/override.conf <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/bin/sg uinput -c /usr/bin/ydotoold
EOF

systemctl --user daemon-reload
systemctl --user reset-failed ydotool.service
systemctl --user enable --now ydotool.service
```

最后验证：

```bash
systemctl --user status ydotool.service --no-pager
ls -l "$XDG_RUNTIME_DIR/.ydotool_socket"
ydotool type -- ''
```

看到 `$XDG_RUNTIME_DIR/.ydotool_socket`，并且 `ydotool type -- ''` 不报错，就表示 `ydotoold` 已可用。之后运行 AppImage，打开控制面板里的“环境检查”，`ydotool` 和“鼠标位置点击”应显示可用。

## systemd 自启动

AppImage 用户不需要记安装命令。直接运行 AppImage，打开控制面板后点击“开启自启动”和“安装桌面图标”即可。

“安装桌面图标”会同时写入应用菜单入口和桌面快捷方式：

- `~/.local/share/applications/voice-input-linux.desktop`
- `~/Desktop/voice-input-linux.desktop`，或系统 `XDG_DESKTOP_DIR` 配置的桌面目录。

部分桌面环境第一次显示从应用创建的快捷方式时，会要求右键图标并选择“允许启动”或“信任此启动器”。

源码安装：

```bash
cd /home/ezhonghu/Developments/openShanDianShuo/voice_input_linux
chmod +x install.sh
./install.sh
systemctl --user enable --now voice-input-linux.service
```

也可以用命令安装 AppImage 自启动，主要用于脚本或调试：

```bash
./VoiceInputLinux-2026.05.04-x86_64.AppImage install
```

该命令会安装应用菜单入口、桌面快捷方式和 systemd user service，并启用自启动。单独安装服务：

```bash
./VoiceInputLinux-2026.05.04-x86_64.AppImage install-service
```

查看状态：

```bash
systemctl --user status voice-input-linux.service --no-pager
journalctl --user -u voice-input-linux.service -f
```

卸载：

```bash
./VoiceInputLinux-2026.05.04-x86_64.AppImage uninstall
```

## AppImage 打包

在 x86_64 Linux 上构建：

```bash
cd /home/ezhonghu/Developments/openShanDianShuo/voice_input_linux
./packaging/appimage/build_appimage.sh
```

输出文件位于：

```bash
dist/VoiceInputLinux-YYYY.MM.DD-x86_64.AppImage
```

指定版本号：

```bash
VERSION=0.1.0 ./packaging/appimage/build_appimage.sh
```

构建脚本会：

1. 安装 Python 依赖和 `pyinstaller`。
2. 用 PyInstaller 生成 `dist/voice-input-linux/`。
3. 组装 AppDir，包括 `.desktop`、图标和 AppRun。
4. 如果系统没有 `appimagetool`，自动下载 AppImageKit continuous 版。
5. 生成可执行 AppImage。

运行打包结果：

```bash
./dist/VoiceInputLinux-0.1.0-x86_64.AppImage
```

无参数运行会启动后台服务并显示控制面板。面板里可以开始/停止录音、打开设置、环境检查、开启自启动、安装桌面图标。再次运行同一个 AppImage 会唤出已运行的控制面板。

内部仍支持 `run`、`toggle`、`settings`、`quit` 等参数，用于 systemd、自定义全局快捷键和问题排查。

注意：AppImage 打包 Python、PySide6、应用代码和主要 Python 依赖；`ydotoold`、`wl-copy`、`xdotool`、音频服务、输入法、FUSE 和 glibc 仍由宿主系统提供。

### 环境检查

控制面板里的“环境检查”会检测：

- 桌面会话类型：X11 / Wayland
- glibc 版本和 AppImage 是否使用实验性内置 glibc
- sounddevice 是否能枚举到麦克风，以及当前 `VOICE_INPUT_DEVICE` 是否可见
- ASR 配置是否完整
- `pynput` / `evdev` 快捷键 backend 是否可用
- `fcitx5`、`wtype`、`xdotool`、`ydotool`、剪贴板 fallback 是否可用
- `systemctl --user` 是否可用

如果换到另一台 Linux 设备，先运行 AppImage，打开“环境检查”，按失败项安装对应宿主依赖。

### glibc 兼容性

默认 AppImage 不内置 glibc。Linux 桌面 AppImage 的稳妥分发方式是在较老的目标发行版上构建，例如 Ubuntu 22.04 / Debian stable，这样生成的二进制能在更新发行版上运行。

构建脚本提供实验开关，可以把构建机上的 glibc 和动态加载器复制进 AppImage：

```bash
BUNDLE_GLIBC=1 VERSION=0.1.0-glibc ./packaging/appimage/build_appimage.sh
```

启用后，AppRun 会优先使用 AppImage 内的 `ld-linux` 启动主程序。这个模式只能作为兼容性实验，不建议作为正式分发策略：glibc 还涉及 NSS、DNS、locale、内核 ABI 和宿主系统工具交互，内置当前构建机的新版 glibc 不一定能解决老系统兼容问题。正式分发仍建议用旧发行版容器构建。

## 麦克风设备探测

如果识别结果为空，先看日志里的录音音量：

```bash
journalctl --user -u voice-input-linux.service -n 120 --no-pager
```

关键日志：

```text
Recording stopped; audio stats chunks=20 max_level=0.0000
```

`max_level=0.0000` 说明程序录到的是静音，优先检查麦克风设备。

图形界面方式：

1. 打开控制面板，点击“设置”。
2. 进入“高级”页，在“麦克风”下拉框里选择有声音的输入设备。
3. 如果刚插入新麦克风，点击“刷新”。
4. 修改后重新录音测试。

列出设备：

```bash
python - <<'PY'
import sounddevice as sd
for i, d in enumerate(sd.query_devices()):
    if d.get("max_input_channels", 0) > 0:
        print(i, d["name"], d.get("default_samplerate"))
PY
```

测试设备电平：

```bash
python - <<'PY'
import numpy as np
import sounddevice as sd
for i, d in enumerate(sd.query_devices()):
    if d.get("max_input_channels", 0) <= 0:
        continue
    try:
        sr = int(d.get("default_samplerate") or 48000)
        data = sd.rec(int(sr * 0.8), samplerate=sr, channels=1, dtype="int16", device=i)
        sd.wait()
        arr = np.asarray(data, dtype=np.float32).reshape(-1)
        print(i, d["name"], "peak=", float(np.max(np.abs(arr))) if arr.size else 0.0)
    except Exception as exc:
        print(i, d["name"], exc)
PY
```

如果要手动改配置，把有声音的设备名写入配置：

```bash
VOICE_INPUT_DEVICE=Wireless Mic Rx 模拟立体声
```

## 常见问题

### 监听不到快捷键

- Wayland 下优先使用 compositor 全局快捷键调用 `toggle`。
- Right Alt 可能是 AltGr，尝试 `VOICE_INPUT_HOTKEY_BACKEND=evdev`。
- 如果已经配置 compositor 快捷键，把内置监听设为 `none`，避免按一次触发两次。

### 麦克风没声音

- 检查系统输入源是否切到当前麦克风。
- 看日志里的 `max_level`；如果一直是 0，在“设置 -> 高级 -> 麦克风”里换一个输入设备。
- USB 麦克风插拔后，数字设备编号可能变化，建议使用设备名。

### 无法输入到当前应用

- Wayland 下确认 `ydotoold` 正在运行。
- 终端常用 `VOICE_INPUT_PASTE_HOTKEY=ctrl+shift+v`。
- 某些应用禁止模拟输入时，文本仍会保留在剪贴板，可手动粘贴。

### Wayland 下无法全局监听

这是 Wayland 安全模型限制。把桌面环境的全局快捷键绑定到：

```bash
./VoiceInputLinux-0.1.0-x86_64.AppImage toggle
```

然后设置：

```bash
VOICE_INPUT_HOTKEY_BACKEND=none
```

### API 鉴权失败

检查：

```text
DOUBAO_ASR_APP_KEY
DOUBAO_ASR_ACCESS_KEY
DOUBAO_ASR_RESOURCE_ID
DOUBAO_ASR_ENDPOINT
```

日志会记录 `request_id` 和火山 `logid`，不会打印 App Key 或 Access Key。

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

当前测试覆盖：

- 配置读写和默认配置生成
- 豆包 ASR 帧解析
- 音频重采样
- 文本后处理
- hotkey backend 禁用配置
- 剪贴板粘贴快捷键
- 环境检查报告格式

## 安全说明

- App Key 和 Access Key 只保存在本机配置文件，不会写入日志。
- `ydotoold` 和 `/dev/uinput` 可以模拟全局键鼠输入，只应授予可信用户。
- AppImage 分发包不内置用户配置和密钥。
