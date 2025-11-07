# OpenPixelControlSerial - Device Discovery

Discover serial LED controllers and automatically generate configuration files.

## Setup

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

Or if you prefer using a virtual environment:

```bash
# Create virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Device Discovery and Config Generation

Run the discover tool to find connected serial LED controllers and generate a configuration file:

```bash
python discover.py
```

This will:
1. List all available serial ports on your system
2. Display detailed information about each port (device path, description, hardware ID, etc.)
3. Attempt to detect LED controller protocols on each port:
   - **AdaLight**: Listens for periodic 'Ada' frames (NOT YET IMPLEMENTED)
   - **WLED**: Queries device via JSON API over serial (NOT YET IMPLEMENTED)
   - **AWA**: Detects HyperSerialPico and AWA protocol devices
4. **Generate `config.json`** in the current directory with discovered devices

**Note**: If `config.json` already exists, you'll receive a warning but the file will be overwritten.

### Debug Mode

For detailed discovery information:

```bash
python discovery.py --debug
# or
python discovery.py -d
```

### Example Output

```
OpenPixelControlSerial - Python Implementation
==================================================

Found 2 serial port(s):

Port: /dev/ttyUSB0
  Description: USB Serial Device
  Hardware ID: USB VID:PID=1A86:7523
  
Port: /dev/ttyACM0
  Description: Raspberry Pi Pico
  Hardware ID: USB VID:PID=2E8A:000A

==================================================
Attempting protocol discovery on each port...
==================================================

Scanning /dev/ttyUSB0...
  Trying AdaLight... ✓ DETECTED
  Trying WLED... ✗
  Trying AWA... ✗

Scanning /dev/ttyACM0...
  Trying AdaLight... ✗
  Trying WLED... ✗
  Trying AWA... ✓ DETECTED

==================================================
Discovery Summary
==================================================

/dev/ttyUSB0:
  - AdaLight
    protocol: adalight
    detected_by: periodic_frame
    baud_rate: 115200

/dev/ttyACM0:
  - AWA
    protocol: awa
    detected_by: handshake
    baud_rate: 2000000
```

## Architecture

### Protocol Discovery Classes

The code uses an abstract base class pattern for protocol discovery:

```
ProtocolDiscovery (ABC)
├── AdaLightDiscovery
├── WLEDDiscovery
└── AWADiscovery
```

Each protocol class implements:
- `discover()`: Attempts to detect if a port speaks this protocol
- `get_protocol_name()`: Returns the protocol name
- `get_device_info()`: Returns discovered device information

### Adding New Protocols

To add support for a new protocol:

1. Create a new class inheriting from `ProtocolDiscovery`
2. Implement the required methods
3. Add the class to the `discover_protocols()` function

Example:
```python
class MyProtocolDiscovery(ProtocolDiscovery):
    def get_protocol_name(self) -> str:
        return "MyProtocol"
    
    def discover(self) -> bool:
        # Implement detection logic
        try:
            with serial.Serial(self.port, 115200, timeout=2) as ser:
                # ... detection code ...
                return True
        except:
            return False
```

## Protocol Implementation Notes

### Improv Protocol

The Improv WiFi provisioning protocol is used by WLED and other ESP32-based devices for device identification and WiFi configuration over serial. The protocol has some poorly documented details that are important to implement correctly.

#### Packet Format (RPC Command)

**Request Device Info Command (12 bytes):**
```
Byte 1-6:  "IMPROV" (0x49 0x4D 0x50 0x52 0x4F 0x56) - Header
Byte 7:    0x01 - Version
Byte 8:    0x03 - Type (RPC Command)
Byte 9:    0x02 - Length (command byte + data length byte)
Byte 10:   0x03 - Command (Request device information)
Byte 11:   0x00 - Data length (0 for this command)
Byte 12:   CHECKSUM - Sum of ALL bytes 1-11, mod 256
```

Example packet: `494d50524f560103020300e6`

**CRITICAL IMPLEMENTATION DETAILS:**

1. **Length field (Byte 9)**: Must be 0x02 (not 0x01), representing the command byte AND the data length byte, even when data length is 0
2. **Checksum**: Includes the IMPROV header bytes (bytes 1-11 total)
3. **Data length byte (Byte 11)**: Must be present even when 0x00

#### Response Format (RPC Result)

Devices may respond with multiple Improv packets. For example, WLED sends:
1. An error/state packet (Type 0x02)
2. The RPC result packet (Type 0x04) containing the actual data

**RPC Result Packet Structure:**
```
Byte 1-6:  "IMPROV" header
Byte 7:    Version
Byte 8:    0x04 - Type (RPC Result)
Byte 9:    Total packet length
Byte 10:   Command echo (which command this is a response to)
Byte 11:   Total data length (sum of all string lengths + their length bytes)
Byte 12+:  Length-prefixed strings
```

**String Format:**
Each string is prefixed with its length byte:
```
[length byte][string bytes][length byte][string bytes]...
```

For Request Device Info, the response contains 4 strings:
1. Firmware name (e.g., "WLED")
2. Firmware version (e.g., "0.15.0/2412100")
3. Hardware (e.g., "esp32")
4. Device name (e.g., "wled-2F8F70")

#### Common Pitfalls

1. **Missing data length byte**: Omitting byte 11 (even when 0x00) causes devices to reject the packet
2. **Wrong length field**: Using 0x01 instead of 0x02 for the length field
3. **Parsing offset errors**: Forgetting to account for command echo and total data length bytes in response
4. **Single packet assumption**: Not handling multiple packets in the response buffer

#### Reference Implementation

See `ImprovDiscovery` class in `discover.py` for a working implementation.

#### Official Documentation

- Improv WiFi Spec: https://www.improv-wifi.com/serial/
- WLED Implementation: https://github.com/Aircoookie/WLED

**Note**: The official Improv spec does not clearly document all packet format details, particularly the checksum calculation and length field semantics. The implementation here is based on analysis of WLED's source code and empirical testing.

## Cross-Platform Compatibility

This implementation uses `pyserial` which provides cross-platform serial port support:

- **Linux**: `/dev/ttyUSB0`, `/dev/ttyACM0`, etc.
- **macOS**: `/dev/cu.usbserial-*`, `/dev/cu.usbmodem-*`, etc.
- **Windows**: `COM1`, `COM2`, etc.

The serial port detection automatically handles platform differences.

## Configuring WLED Devices

After discovering WLED devices, you'll typically need to **enable LIVE mode** for them to accept serial LED data. WLED devices ship with LIVE mode disabled by default, which means they'll run internal effects/patterns instead of accepting real-time data.

Use the **WLED Configuration Tool** to enable LIVE mode:

```bash
cd ../wled-config
python wled_config.py --enable-live
```

For more information, see the [WLED Configuration Tool documentation](../wled-config/README.md).

**Why LIVE mode is required:**
- **LIVE mode DISABLED**: Device runs internal effects, ignores serial LED data
- **LIVE mode ENABLED**: Device accepts Adalight/AWA/TPM2 serial LED data

The discovery tool will warn you if LIVE mode is disabled on detected WLED devices.

## Next Steps

- [ ] Implement OPC server (TCP listener)
- [ ] Add protocol output handlers (write LED data to serial)
- [ ] Configuration file support
- [ ] Multi-port simultaneous operation
- [ ] Performance optimization

## Troubleshooting

### Permission Denied on Linux

If you get permission errors accessing serial ports on Linux:

```bash
# Add your user to the dialout group
sudo usermod -a -G dialout $USER

# Log out and back in for changes to take effect
```

### No Devices Detected

- Ensure your LED controller is connected and powered on
- Check that drivers are installed for your USB-to-serial adapter
- Try unplugging and reconnecting the device
- Check `dmesg` (Linux) or Device Manager (Windows) to verify the device is recognized

## License

See the main project [LICENSE](../LICENSE) file.
