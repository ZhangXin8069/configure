# 字体配置操作

## 资源说明

| 文件 | 目标平台 | 主要内容 |
|---|---|---|
| `LinuxFonts.tar.xz` | Linux/macOS | Intel One Mono 与方正中文字体 |
| `WindowsFonts.tar.xz` | 已授权的 Windows 环境 | Windows 系统字体集合 |

先查看包内文件，确认名称和体积：

```bash
tar -tJf lib/_font/LinuxFonts.tar.xz | head -40
tar -tJf lib/_font/WindowsFonts.tar.xz | head -40
du -h lib/_font/*.tar.xz
```

## Linux

为当前用户安装：

```bash
font_dir="$HOME/.local/share/fonts/configure"
mkdir -p "$font_dir"
tar -xJf lib/_font/LinuxFonts.tar.xz -C /tmp
find /tmp/LinuxFonts -maxdepth 1 -type f \( -iname '*.ttf' -o -iname '*.otf' \) \
  -exec cp -v {} "$font_dir/" \;
fc-cache -fv "$font_dir"
fc-list | grep -iE 'intel one mono|方正|FZ'
```

系统级安装需要 root，通常不是必要操作：

```bash
sudo install -d -m 0755 /usr/local/share/fonts/configure
find /tmp/LinuxFonts -maxdepth 1 -type f \( -iname '*.ttf' -o -iname '*.otf' \) \
  -exec sudo cp -v {} /usr/local/share/fonts/configure/ \;
sudo fc-cache -f
```

## macOS

Linux 字体包中的 OTF/TTF 可由 Font Book 为当前用户安装：

```bash
mkdir -p "$HOME/Library/Fonts"
tar -xJf lib/_font/LinuxFonts.tar.xz -C /tmp
find /tmp/LinuxFonts -maxdepth 1 -type f \( -iname '*.ttf' -o -iname '*.otf' \) \
  -exec cp -v {} "$HOME/Library/Fonts/" \;
```

随后在 Font Book 中启用字体。macOS 没有 `fc-cache` 的统一等价步骤。

## Windows

Windows 10/11 自带 `tar.exe` 可解压 `.tar.xz`：

```powershell
$dest = Join-Path $env:TEMP 'configure-fonts'
New-Item -ItemType Directory -Force -Path $dest | Out-Null
tar -xJf .\lib\_font\WindowsFonts.tar.xz -C $dest
explorer.exe (Join-Path $dest 'WindowsFonts')
```

在资源管理器中选中字体文件，右键选择“安装”或“为所有用户安装”。也可以只安装实际需要的字体，避免覆盖现有系统字体。

## 授权与安全

1. `WindowsFonts.tar.xz` 来自 Microsoft Windows 字体集合。只应在已有 Windows 授权覆盖的设备上使用。
2. 不要对外分发、上传到公共仓库或用于无法确认授权的容器镜像。
3. 字体文件属于二进制内容。发布前应记录来源与 SHA-256。

```bash
shasum -a 256 lib/_font/*.tar.xz
```

## 验证和回滚

Linux 验证：

```bash
fc-list | grep -i 'Intel One Mono'
fc-list | grep -iE 'Microsoft YaHei|SimSun|方正'
```

用户级字体回滚只需移除对应目录并刷新缓存：

```bash
rm -rf "$HOME/.local/share/fonts/configure"
fc-cache -f
```

该删除仅涉及本页创建的用户目录。删除前先确认路径变量非空且指向预期目录。

macOS 可在 Font Book 中检查字体；Windows 可在“设置 → 个性化 → 字体”中检查。
