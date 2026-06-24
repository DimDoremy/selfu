# selfu - 打包、安装、发布脚本
#
# 用法（just 参数为位置式）：
#   just build                 # 使用 PyInstaller 打包，生成 dist/ 下的版本化二进制与 tar.gz
#   just install               # 安装二进制到 ~/.local/bin（或 $SELFU_PREFIX/bin）
#   just install /usr/local/bin  # 安装到指定目录
#   just release               # 在 GitHub 上创建 release（标签 v+版本号）并上传 tar.gz
#   just release v0.0.2          # 指定 release 标签
#   just release v0.0.2 "说明"    # 指定标签与发布说明
#   just all                   # build -> install -> release 一条龙

# 项目根目录
project_dir := justfile_directory()

# 从 pyproject.toml 读取版本号
version := `grep -m1 '^version' pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/'`

# 操作系统与架构标签：linux-x86_64 / darwin-arm64 ...
os_tag := if `uname -s` == "Darwin" { "darwin" } else { "linux" }
arch_tag := if `uname -m` == "aarch64" { "arm64" } else if `uname -m` == "x86_64" { "x86_64" } else { `uname -m` }
platform := os_tag + "-" + arch_tag

# 打包产物命名
bin_name := "selfu"
dist_bin := project_dir / "dist" / bin_name
versioned := bin_name + "-" + version + "-" + platform
dist_versioned := project_dir / "dist" / versioned
archive := dist_versioned + ".tar.gz"
default_tag := "v" + version

# 安装前缀（可覆盖）
prefix := env_var_or_default("SELFU_PREFIX", home_dir() / ".local") / "bin"

# 默认配方：显示帮助
default:
    @just --list

# 1. 打包：PyInstaller 生成二进制，重命名为版本化名称并压缩
build:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ project_dir }}"
    echo "==> 版本: {{ version }}  平台: {{ platform }}"
    # 确保 pyinstaller 可用（开发依赖）
    uv run --with pyinstaller pyinstaller --noconfirm --clean selfu.spec
    # 复制为版本化名称
    cp -f "{{ dist_bin }}" "{{ dist_versioned }}"
    # 生成 tar.gz
    tar -C dist -czf "{{ archive }}" "{{ versioned }}"
    echo "==> 打包完成："
    ls -lh "{{ dist_versioned }}" "{{ archive }}"

# 2. 安装：将二进制复制到 prefix/bin（默认 ~/.local/bin）
install prefix=prefix:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "{{ prefix }}"
    install -m 0755 "{{ dist_versioned }}" "{{ prefix }}/{{ bin_name }}"
    echo "==> 已安装 {{ bin_name }} -> {{ prefix }}/{{ bin_name }}"
    echo "==> 请确保 {{ prefix }} 在 PATH 中"

# 3. 发布：在 GitHub 创建 release 并上传 tar.gz 资产
release name=default_tag notes="":
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ project_dir }}"
    [ -f "{{ archive }}" ] || { echo "错误：找不到 {{ archive }}，请先 just build"; exit 1; }
    tag="{{ name }}"
    echo "==> 创建 GitHub release：$tag"
    if [ -n "{{ notes }}" ]; then
        gh release create "$tag" "{{ archive }}" \
            --title "$tag" --notes "{{ notes }}" --generate-notes
    else
        gh release create "$tag" "{{ archive }}" \
            --title "$tag" --generate-notes
    fi
    echo "==> 发布完成：$tag"

# 一条龙：打包 -> 安装 -> 发布
all: build install release
