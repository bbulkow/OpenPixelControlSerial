# Build Notes

## Windows Build Requirements

To build Rust projects on Windows, you need one of the following:

### Option 1: Install Visual Studio Build Tools (Recommended)

1. Download [Build Tools for Visual Studio](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022)
2. Run the installer
3. Select "C++ build tools" workload
4. Install and restart your terminal
5. Run `cargo build --release`

### Option 2: Install via Chocolatey (Windows Package Manager)

If you have [Chocolatey](https://chocolatey.org/) installed:

```bash
choco install visualstudio2022-workload-vctools
```

Then restart your terminal and run `cargo build --release`

### Option 3: Use GNU Toolchain

Alternatively, you can use the GNU toolchain:

```bash
# Switch to GNU target
rustup default stable-x86_64-pc-windows-gnu

# Install MinGW-w64 (via MSYS2 or standalone)
# Then build
cargo build --release
```

## Linux Build

On Linux, you may need development packages:

```bash
# Ubuntu/Debian
sudo apt install build-essential pkg-config libudev-dev

# Fedora/RHEL
sudo dnf install gcc pkg-config systemd-devel

# Then build
cargo build --release
```

## macOS Build

On macOS, ensure Xcode Command Line Tools are installed:

```bash
xcode-select --install
cargo build --release
```

## Verifying the Build Environment

To check if your Rust toolchain is properly configured:

```bash
rustc --version
cargo --version
```

## Cross-Platform Note

The code is platform-independent and will compile on any platform with proper Rust toolchain setup. The compilation failure you may have seen is only due to missing build tools, not code issues.
