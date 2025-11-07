# OpenPixelControlSerial

A bridge service that translates Open Pixel Control (OPC) protocol to serial LED protocols (AdaLight and AWA, including WLED discovery protocols), enabling modern LED strip control with legacy-compatible tooling. 

## Overview

I was thinking of this project because my supply of the beloved FadeCandy has dwindled, but I have LED control software - Chromatik - that is very suitable for Raspberry pi. While I often use larger more industrial LED controllers with Ethernet or ARTx, there's a place for small and simple. 

OpenPixelControlSerial provides a software replacement for the discontinued FadeCandy hardware controller. It accepts OPC commands over the network and translates them to serial protocols that work with readily available, inexpensive LED controllers connected via USB/serial ports.

Arguably, in retrospec, I'm finding that WLED with the Athom controllers that support Ethernet, are a better
solution, assuming one has the physical space. At (2025) USD 25 for an ethernet based one or two channel 
controller, Ethernet so wins over serial it's a better solution. Serial is a solution if you don't have
space or don't have money. The ItsyBitsy RP2040 is incredibly small, requiers no level shifters, and is closer
to $10, compared to $25.

This makes it possible to:
- Continue using OPC-compatible software and libraries
- Drive LED strips using cheap serial controllers (Arduino-based AdaLight, AWA protocol devices)
- Run on various platforms including Raspberry Pi, desktop computers, and servers
- Scale to multiple LED strips across multiple serial ports
- Apply simple conversions like RGB to RGBW, gamma, etc in cases where your controller doesn't

Because of the hard-to-discover nature of serial, I have built a "discovery" program, that allows
you to hook up your controller and some LEDs, blink them, and create a template config
file based on that. After you get the template right, you can switch to the OPC server.

I have built both a Python and Rust version. As this will run on the RPI with other software,
the efficiency of RUST might be important. I also intend better transformations, like gamma
or potentially temporal dithering, to be implemented only in rust.

## Caveats

The nature of Serial is you open and blast, and if the receiver isn't receiving packets or receiving
gibberish, you usually don't know. This makes reliability a very sketchy thing.

DO test your intended hardware! I've learned that the "it probably goes X speed" is TO BE TAKEN WITH
A LARGE GRAIN OF SALT, and it's CRITICAL to actually try your "brain" + LED Controller, and probably
knock a point off the fastest speed it SEEMS reliable. I am finding these small embedded devices are
closer to 240kbit.

If using WLED, it has cool features in that you can read the LED configuration (number and byte order)
from the controller. It also has a sophisticated method for changing serial port speed "on the fly", 
which this code uses - and then has to attempt to sense the current speed of a controller
on every restart. While this is all very cool, you'll want to think about how to set up your WLED config.

## State of the project

AWA protocol ( HyperSerial ) has been tested with the ItsyBitsy RP2040.

WLED discovery plus ADALIGHT has been tested with WLED 0.15 and Athom / IOTorero controllers.

Tested with Windows and Linux. Please drop a line if it works on MacOS.

Multiple serial output support is designed and implemented and code reviewed but not
tested. There may be dragons. Please submit issues.

Please submit issues - but honestly this is kind of a one-shot for me, so not sure how
much support going forward.

As I had a lot of little relaibility gotchas, there is substantial debug code.

Note: this project coded HEAVILY with Claude - Opus 4.1 then Sonnet 4.5. License is open
due to my feeling that Anthropic AI leaned heavily on open source, so while this is not a
"derivitave work" in the legal sense, it is morally correct to have this code be open
source as well.

## Todo

I would like to put Gamma in the RUST code.

I would like the Rust code to buffer OPC and always output 30 FPS. This allows overcoming WLED's propensity
to "timeout" (can't set timeout to infinite) on case of a hang of the sender. Also, it can be used to implement
temporal dithering.

I would like to put RGBW *with temp correction* in the RUST code (LEDs that support W advertise the temperature
of W, but I have never seen an RGB to RGBW converter that takes temp into account).

I would like to support something other than OPC. OPC being TCP based. ARTNET is more common, DDP is more
efficient, OPC is more legacy. Again, maybe just in the RUST code.

## Project Structure

### `config/` - Configuration Specifications
- JSON configuration format documentation
- Example configuration files
- Multi-output setup examples
 
 
### `discover/` - Device Discovery Tool
Python-based tool for detecting serial LED controllers:
- Automatic device detection (AWA, Adalight, WLED protocols)
- Generates configuration files from discovered devices
- Cross-platform support (Windows, macOS, Linux)

### `validate/` - Configuration Validation Tool
This is essentially depracated because the discover program
flashes LEDs. It still works and has different patterns so I'm leaving
it in.

### `opc-server-py/` - Python OPC Server
Python-based OPC server implementation:
- Full OPC protocol server input (TCP, configurable port)
- Per-channel single-depth queues for low latency
- Multi-output support with channel routing

### `opc-test/` - OPC Test Client
Shared test client for validating OPC servers:
- Works with both Python and Rust implementations
- Multiple test patterns (rainbow, chase, solid colors)
- Configurable FPS, LED count, and channels
- Useful for testing and demonstrations
- Easy place to add more patterns, good for validating other OPC servers

### `opc-server-rs/` - Rust OPC Server
High-performance Rust implementation for production use:
- High-performance async I/O using std libraries
- Zero-copy buffer management
- True parallel serial port handling
- Skip-ahead frame dropping
- All the features of the Python server, but higher performance, and a good place to add new features

## Cross-Platform Support

Both implementations are designed to run on:
- **Linux** (TESTED WITH 2025 Raspberry Pi 4, other linuxes UNTESTED)
- **macOS** (UNTESTED)
- **Windows** (11))

## Related Projects

### Chromatik LED Project
This project is designed to work seamlessly with [Chromatik](https://github.com/chromatik/chromatik), a powerful LED control framework. OpenPixelControlSerial serves as a bridge to hardware support, intended to be run on 
the same box as Chromatik, although its use of TCP based OpenPixelControl could enable more complex uses.

### HyperSerialPico (awawa-dev)
This code has been tested extensively with the [HyperSerialPico](https://github.com/awawa-dev/HyperSerialPico) project by awawa-dev. HyperSerialPico provides AWA protocol support on RP2040-based devices, making it an excellent hardware target for this bridge.

awawa-dev 's repos also include amusements like a WLED AWA implementation (replacing ADALIGHT with AWA).

⚠️ **Important Limitation**: I found HyperSerialPico firmware did not support the number of pixels per frame
that I hoped, in the version I used, on the RP2040 hardware. I have suspicions that this is related
to an underlying software flaw or lack of flow control support, but didn't debug the issue. Please
test on your hardware before trusting.

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


## Installation

### Python OPC Server

1. Install dependencies:
```bash
cd opc-server-py/
pip install -r requirements.txt
```

2. Create a configuration file using 'discover' or by hand (see `config/config.example.json`)

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

### Rust OPC Server

Same as Python (above), but with Rust

```bash
cd opc-server-rs/
cargo run -- config.json
```

## Configuring WLED

Zeroeth, make sure your WLED is compiled with ADALIGHT support. That compile
flag enables the JSON Serial components and ADALIGHT. I found the ATHOM / IOTORERO devices
with a serial port come with 0.15 with Serial Live enabled. I did *not* find I needed
to enable "live" in the WLED firmware independatly. The easiest way to test is open
the serial port with a computer and type 'v'. If you have the inital speed right, and a version
that supports serial, WLED will respond with "WLED" and a build version string.

First, WLED expects its ADALIGHT input to be in RGB, and if you set the strips in WLED
to be a different format, set OpenPixelControlSerial to be **RGB** not the same configuration
as WLED. Probably setting OPCS to RGBW will not play nice with WLED!

Second, consider the serial port speed. To *persistantly* set WLED's serial port speed,
you need to use the web interface. The protocol below is for ad-hoc changes. I recommend leaving
the WLED serial speed to 115200, the lowest common denominator. That's why this code
shifts up to a higher speed after discovery. This code *also* checks for valid WLED
version handshake on every boot, to discover cases where the device has lingered
in the non-default speed.

Third, WLED is an abstraction that also supports Gamma or other transforms. Please be thoughtful
so you do gamma correct, but don't gamma correct twice, if OPCS supports gamma.

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

If using WLED, the dangerous byte is "change serial port speed" which if sent outside a data frame leads 
to what seems like a non-responsive controller until reboot (although it is responsive, just on a different baud).

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

AWA (Advanced Wireless Addressable) is another serial protocol for LED control with additional features for timing and synchronization. This project has been tested with HyperSerialPico implementing the AWA protocol. It appears
only that github author has written AWA, which they use with their control software "HyperHDR".

In general, it seems Adalight may be a better protocol, as it is simply more common.

### WLED Serial Protocol

WLED is popular ESP32/ESP8266 firmware for controlling addressable LEDs. When connected via serial (USB), WLED supports multiple protocols and a unique baud rate switching capability.

#### Supported Protocols
WLED devices support these serial protocols:
- **AdaLight** - Standard AdaLight protocol (same format as above)
- **TPM2** - Alternative streaming protocol (not well tested by this code)
- **JSON API** - Configuration and state queries (WLED-specific)

#### Baud Rate Switching

WLED has a critical feature for optimal performance: **dynamic baud rate switching**. This allows initial handshaking at a standard speed, then switching to higher speeds for LED data transmission. The initial
handshake speed is set persistantly **ONLY** through the web interface.

This feature of Baud Rate Switching is *ONLY* done when the hardware type is WLED. If the device
is ADALIGHT but has any other hardware string, the feature is not attempted.

**Why This Matters:**
- WLED defaults to 115200 baud for JSON API and discovery
- LED data transmission can benefit from higher speeds (these cheap embedded controlers are stable at 230k or 500k)
- Baud rate changes are **temporary** and reset on power cycle
- Must detect the default baud rate before attempting to use the controller

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

For questions, issues, or contributions, please use the GitHub issue tracker and author bbulkow (brian@bulkowski.org)

---

**Status**: 🚧 may or may not respond to bugs 🚧
