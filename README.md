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

### `opc-server-rs/` - Rust OPC Server
High-performance Rust implementation for production use:
- High-performance async I/O with Tokio
- Zero-copy buffer management
- True parallel serial port handling
- Skip-ahead frame dropping
- Same functionality as Python version with better performance

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

⚠️ **Important Limitation**: HyperSerialPico firmware has known stability issues when processing frames larger than approximately 80 pixels (~240 bytes). The firmware **does not implement flow control** (neither hardware RTS/CTS nor software XON/XOFF), which can lead to buffer overruns and unrecoverable hangs when sending large frames at high data rates. Once the device enters this hung state, it typically requires a power cycle to recover and may not work reliably even with smaller frame sizes afterward.

**Recommendations when using HyperSerialPico:**
- Limit frame size to 50 pixels or fewer for reliable operation
- Lower frame rates if experiencing instability
- Consider alternative hardware for installations requiring >80 pixels
- The lack of flow control is a fundamental architectural limitation of the HyperSerialPico firmware

This limitation is specific to the HyperSerialPico firmware implementation and does not affect other AWA protocol devices that implement proper flow control.

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

**Frame Structure:**
```
[Header: 6 bytes] [Pixel Data: N * 3 bytes]
```

**Header Format:**

| Byte | Value | Description |
|------|-------|-------------|
| 0 | 0x41 | Magic byte 'A' |
| 1 | 0x64 | Magic byte 'd' |
| 2 | 0x61 | Magic byte 'a' |
| 3 | (count-1) >> 8 | LED count high byte |
| 4 | (count-1) & 0xFF | LED count low byte |
| 5 | checksum | XOR of bytes 3, 4, and 0x55 |

**⚠️ CRITICAL: LED Count Field**

The LED count field (bytes 3-4) contains **(actual_led_count - 1)**, NOT the actual count.

This matches the AWA protocol convention and is essential for proper frame synchronization. Sending the wrong count will cause the receiver to expect the wrong number of bytes, leading to frame desync and potential interpretation of pixel data as commands.

**Examples:**
- 1 LED → send `0x00 0x00` (value 0)
- 10 LEDs → send `0x00 0x09` (value 9)
- 100 LEDs → send `0x00 0x63` (value 99)
- 256 LEDs → send `0x00 0xFF` (value 255)
- 257 LEDs → send `0x01 0x00` (value 256)

**Pixel Data:**
Following the header, RGB pixel data is sent as triplets: `[R][G][B] [R][G][B] ...`

Total frame size = 6 bytes (header) + (led_count × 3) bytes (pixel data)

### AWA Protocol

AWA (Advanced Wireless Addressable) is another serial protocol for LED control with additional features for timing and synchronization. This project has been tested with HyperSerialPico implementing the AWA protocol.

### WLED Serial Protocol

WLED is popular ESP32/ESP8266 firmware for controlling addressable LEDs. When connected via serial (USB), WLED supports multiple protocols and a unique baud rate switching capability.

#### Supported Protocols
WLED devices support these serial protocols:
- **AdaLight** - Standard AdaLight protocol (same format as above)
- **TPM2** - Alternative streaming protocol
- **JSON API** - Configuration and state queries (WLED-specific)

#### Baud Rate Switching

WLED has a critical feature for optimal performance: **dynamic baud rate switching**. This allows initial handshaking at a standard speed, then switching to higher speeds for LED data transmission.

**Why This Matters:**
- WLED defaults to 115200 baud for JSON API communication
- LED data transmission can benefit from higher speeds (up to 2Mbps)
- Baud rate changes are **temporary** and reset on power cycle
- Must detect the default baud rate before attempting to change it

**Baud Rate Change Commands:**

WLED accepts single-byte commands when in idle state (not mid-frame):

| Byte | Baud Rate | Hex  | Description |
|------|-----------|------|-------------|
| 0xB0 | 115200    | `\xB0` | Default speed, recommended for JSON |
| 0xB1 | 230400    | `\xB1` | 2x faster |
| 0xB2 | 460800    | `\xB2` | 4x faster |
| 0xB3 | 500000    | `\xB3` | ~4.3x faster |
| 0xB4 | 576000    | `\xB4` | 5x faster |
| 0xB5 | 921600    | `\xB5` | 8x faster |
| 0xB6 | 1000000   | `\xB6` | 8.7x faster |
| 0xB7 | 1500000   | `\xB7` | 13x faster |
| 0xB8 | 2000000   | `\xB8` | 17x faster (maximum) |

**Protocol Flow:**

1. **Initial Connection**: Open serial port at 115200 baud (WLED default)
2. **JSON Handshake**: Send `{"v":true}\n` to query device info
3. **Extract Configuration**: Parse JSON response for LED count, pixel format, etc.
4. **Baud Rate Switch**: Send single byte (e.g., `0xB8` for 2Mbps)
5. **Response**: WLED replies with `"Baud is now 2000000\n"`
6. **Reconnect**: Close port, reopen at new baud rate
7. **LED Data**: Send AdaLight frames at higher speed

**Important Implementation Notes:**

- **Power Cycle Reset**: Baud rate changes do NOT persist across reboots
- **Always Start at 115200**: Discovery/initialization must begin at default speed
- **Idle State Only**: Send baud commands between frames, not mid-frame
- **Single Byte**: Command is exactly one byte, no framing
- **Response Timeout**: Wait ~200ms for confirmation response
- **Configuration Storage**: Store both speeds in config:
  - `handshake_baud_rate`: Speed for JSON API (typically 115200)
  - `baud_rate`: Speed for LED data (can be up to 2000000)

**Configuration Example:**
```json
{
  "port": "COM4",
  "protocol": "adalight",
  "hardware_type": "WLED",
  "handshake_baud_rate": 115200,
  "baud_rate": 2000000,
  "led_count": 300,
  "pixel_format": "GRB"
}
```

**Implementation Sequence for opc-server-py and opc-server-rs:**

```
1. Read config, find hardware_type: "WLED"
2. Open serial at handshake_baud_rate (115200)
3. Send JSON query: {"v":true}\n
4. Parse response, validate WLED device
5. If baud_rate != handshake_baud_rate:
   a. Send baud change byte (e.g., 0xB8)
   b. Wait for "Baud is now..." response
   c. Close serial port
   d. Reopen at new baud_rate
6. Begin normal AdaLight frame transmission
```

**Python Example:**
```python
# Initial handshake at 115200
ser = serial.Serial(port, 115200)
ser.write(b'{"v":true}\n')
response = ser.read(1000)  # Get JSON

# Switch to 2Mbps
ser.write(b'\xB8')  # 0xB8 = 2000000 baud
time.sleep(0.2)
response = ser.read(100)  # "Baud is now 2000000"
ser.close()

# Reopen at high speed
ser = serial.Serial(port, 2000000)
# Now send AdaLight frames...
```

**Rust Example:**
```rust
// Initial handshake
let mut port = serialport::new(port_name, 115200).open()?;
port.write_all(b"{\"v\":true}\n")?;
// ... read and parse JSON ...

// Switch baud rate
port.write_all(&[0xB8])?;  // 2000000 baud
thread::sleep(Duration::from_millis(200));
// ... read confirmation ...
drop(port);

// Reopen at high speed
let mut port = serialport::new(port_name, 2000000).open()?;
// Now send AdaLight frames...
```

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
- [x] Core OPC server implementation (Rust)
- [x] AdaLight protocol output
- [x] AWA protocol output
- [x] Multi-port management
- [x] Command-line interface
- [ ] Cross-platform testing (Windows, macOS, Linux)
- [ ] Raspberry Pi optimization
- [ ] Systemd service files
- [ ] Performance benchmarking
- [x] Documentation and examples

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
