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

## Cross-Platform Compatibility

This implementation uses `pyserial` which provides cross-platform serial port support:

- **Linux**: `/dev/ttyUSB0`, `/dev/ttyACM0`, etc.
- **macOS**: `/dev/cu.usbserial-*`, `/dev/cu.usbmodem-*`, etc.
- **Windows**: `COM1`, `COM2`, etc.

The serial port detection automatically handles platform differences.

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
