# OpenPixelControlSerial

A bridge service that translates Open Pixel Control (OPC) protocol to serial LED protocols (AdaLight and AWA), enabling modern LED strip control with legacy-compatible tooling.

## Overview

OpenPixelControlSerial provides a software replacement for the discontinued FadeCandy hardware controller. It accepts OPC commands over the network and translates them to serial protocols that work with readily available, inexpensive LED controllers connected via USB/serial ports.

This makes it possible to:
- Continue using OPC-compatible software and libraries
- Drive LED strips using cheap serial controllers (Arduino-based AdaLight, AWA protocol devices)
- Run on various platforms including Raspberry Pi, desktop computers, and servers
- Scale to multiple LED strips across multiple serial ports

## Background

The FadeCandy was a popular USB-connected LED controller that used the Open Pixel Control protocol. However, it has been unavailable for years, leaving a gap for developers and artists who built systems around OPC. This project fills that gap by implementing OPC server functionality that bridges to modern, readily available serial LED controllers.

## Project Structure

### `discover/` - Device Discovery Tool
Python-based tool for detecting serial LED controllers:
- Automatic device detection (AWA, Adalight, WLED protocols)
- Generates configuration files from discovered devices
- Cross-platform support (Windows, macOS, Linux)

### `validate/` - Configuration Validation Tool
Python-based tool for testing serial connections:
- Validates configuration and connectivity
- Test patterns (solid colors, blink, rainbow, chase)
- Verifies pixel format transformations

### `opc-server-py/` - Python OPC Server
Python-based OPC server implementation:
- Full OPC protocol server
- TCP network interface (standard port 7890)
- Per-channel single-depth queues for low latency
- Multi-output support with channel routing
- Both AWA and Adalight protocol output
- Debug mode with FPS statistics

### `opc-test/` - OPC Test Client
Shared test client for validating OPC servers:
- Works with both Python and Rust implementations
- Multiple test patterns (rainbow, chase, solid colors)
- Configurable FPS, LED count, and channels
- Useful for testing and demonstrations

### `config/` - Configuration Specifications
- JSON configuration format documentation
- Example configuration files
- Multi-output setup examples

### `opc-server-rs/` - Rust OPC Server (Planned)
High-performance Rust implementation for production use

## Cross-Platform Support

Both implementations are designed to run on:
- **Linux** (x86_64, ARM, including Raspberry Pi)
- **macOS** (Intel and Apple Silicon)
- **Windows** (10 and 11)

The code abstracts platform-specific serial port handling to ensure consistent behavior across all operating systems.

## Related Projects

### Chromatik LED Project
This project is designed to work seamlessly with [Chromatik](https://github.com/chromatik/chromatik), a powerful LED control framework. OpenPixelControlSerial serves as a hardware bridge, allowing Chromatik to drive physical LED installations through OPC.

### HyperSerialPico (awawa-dev)
This code has been tested extensively with the [HyperSerialPico](https://github.com/awawa-dev/HyperSerialPico) project by awawa-dev. HyperSerialPico provides AWA protocol support on RP2040-based devices, making it an excellent hardware target for this bridge.

## Architecture

```
┌─────────────────────┐
│  OPC Client Apps    │
│ (Chromatik, etc)    │
└──────────┬──────────┘
           │ Network (TCP)
           │ OPC Protocol
┌──────────▼──────────┐
│ OpenPixelControl    │
│      Serial         │
│   (This Project)    │
└──────────┬──────────┘
           │ USB/Serial
           │ AdaLight/AWA
┌──────────▼──────────┐
│   LED Controllers   │
│ (HyperSerialPico,   │
│  Arduino, etc)      │
└──────────┬──────────┘
           │
      ╔════▼════╗
      ║ LEDs    ║
      ╚═════════╝
```

## Features

- **OPC Server**: Full Open Pixel Control protocol server implementation
- **Multiple Serial Protocols**: 
  - AdaLight protocol support
  - AWA protocol support
- **Multi-Port Support**: Drive multiple LED strips on different serial ports simultaneously
- **Cross-Platform**: Runs on Linux (including Raspberry Pi), Windows, and macOS
- **Layer Compatible**: Drop-in replacement for FadeCandy in existing OPC setups
- **Dual Implementations**: Choose Python for flexibility or Rust for performance

## Requirements

- **Hardware**:
  - Computer with USB ports (Raspberry Pi, desktop, server)
  - Serial LED controller (HyperSerialPico, Arduino running AdaLight, AWA-compatible device)
  - WS2812/NeoPixel or compatible LED strips

- **Software**:
  - Python 3.8+ (for Python implementation) OR Rust toolchain (for Rust implementation)
  - Serial port access permissions
  - Network connectivity for OPC clients

## Installation

### Python OPC Server

1. Install dependencies:
```bash
cd opc-server-py/
pip install -r requirements.txt
```

2. Create a configuration file (see `config/config.example.json`)

3. Run the server:
```bash
python opc_server.py config.json
```

4. Test with the shared test client:
```bash
cd ../opc-test
python test_client.py --pattern rainbow --leds 100
```

See `opc-server-py/README.md` for detailed documentation.

### Rust OPC Server (Coming Soon)
```bash
cd opc-server-rs/
cargo run -- config.json
```

## Protocols

### Open Pixel Control (OPC)

OPC is a simple protocol for controlling arrays of RGB lights. It uses TCP and is designed to be easy to implement in any language. The protocol is documented at [openpixelcontrol.org](http://openpixelcontrol.org/).

### AdaLight Protocol

AdaLight is a simple serial protocol developed for Arduino-based LED controllers. It's widely supported and easy to implement on microcontrollers.

**Frame format:**
```
'A' 'd' 'a' [LED count high] [LED count low] [checksum] [LED data...]
```

### AWA Protocol

AWA (Advanced Wireless Addressable) is another serial protocol for LED control with additional features for timing and synchronization. This project has been tested with HyperSerialPico implementing the AWA protocol.

## Supported LED Types

- WS2812/WS2812B (NeoPixel)
- WS2811
- APA102 (via compatible controllers)
- SK6812
- And other addressable RGB(W) LED strips

## Performance

- Supports high frame rates (limited by serial bandwidth and LED strip refresh rates)
- Minimal latency (typically <10ms for translation)
- Efficient multi-port handling
- Rust implementation provides maximum performance for demanding installations

## Roadmap

- [x] Core OPC server implementation (Python)
- [ ] Core OPC server implementation (Rust)
- [x] AdaLight protocol output
- [x] AWA protocol output
- [ ] Multi-port management
- [ ] Command-line interface
- [ ] Cross-platform testing (Windows, macOS, Linux)
- [ ] Raspberry Pi optimization
- [ ] Systemd service files
- [ ] Performance benchmarking
- [ ] Documentation and examples

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

## License

See [LICENSE](LICENSE) file for details.

## Acknowledgments

- Original OPC protocol design by Micah Elizabeth Scott
- FadeCandy project for inspiration
- AdaLight protocol by Adafruit
- [HyperSerialPico](https://github.com/awawa-dev/HyperSerialPico) by awawa-dev for AWA protocol testing
- [Chromatik LED project](https://github.com/chromatik/chromatik) community
- The LED art and maker communities

## Resources

- [Open Pixel Control Protocol](http://openpixelcontrol.org/)
- [AdaLight Project](https://learn.adafruit.com/adalight-diy-ambient-tv-lighting)
- [FadeCandy (archived)](https://github.com/scanlime/fadecandy)
- [HyperSerialPico](https://github.com/awawa-dev/HyperSerialPico)
- [Chromatik](https://github.com/chromatik/chromatik)

## Contact

For questions, issues, or contributions, please use the GitHub issue tracker.

---

**Status**: 🚧 Under Active Development 🚧
