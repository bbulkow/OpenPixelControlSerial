# OpenPixelControlSerial - Python OPC Server

Python-based OPC (Open Pixel Control) server that receives LED data over TCP and outputs to serial LED strips using various protocols.

## Overview

This server implements the OPC protocol to receive pixel data over TCP/IP and route it to serial LED strips. It supports multiple outputs with different channels and protocols, making it ideal for controlling large LED installations.

## Architecture

### Non-Blocking TCP with Worker Threads

The server uses an efficient **non-blocking TCP drain** with **per-output worker threads**:

- **Main Thread**: Non-blocking TCP socket drains all available data (no blocking recv)
- **Worker Threads**: One persistent thread per serial output (blocks efficiently on queue)
- **Single-Depth Queues**: Each serial output has its own Queue(maxsize=1) with automatic frame replacement
- **Parallel Transmission**: Multiple serial outputs transmit simultaneously (GIL released during I/O)

### Queue System

**Per-Serial-Output Queues** (not per OPC channel):
- Each serial output (e.g., COM3, COM4) has its own Queue(maxsize=1)
- Worker thread blocks efficiently on `queue.get()` when no data (no CPU spinning)
- Main thread uses non-blocking `queue.put_nowait()` with automatic replacement
- Old frames are automatically discarded when new frames arrive

**Why per-serial-output?** This enables multiple serial outputs on the same OPC channel with different offsets:
```
OPC Channel 1 (200 bytes):
├─ COM3: offset=0,  count=33 → bytes [0:99]
└─ COM4: offset=33, count=33 → bytes [99:198]
```

### Data Flow

1. **TCP Drain**: Non-blocking loop reads all available data from socket (no blocking on small frames)
2. **Frame Parsing**: Parse complete OPC messages from accumulated buffer
3. **Slice & Distribute**: Each serial output gets its slice based on `opc_offset` and `led_count`
4. **Queue Update**: Non-blocking put to each output's queue (replaces old frame if queue full)
5. **Parallel Transmission**: Worker threads independently send to serial ports simultaneously

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Create a configuration file (see `../config/config.example.json` for reference)

## Usage

### Basic Usage

```bash
python opc_server.py config.json
```

### With Debug Statistics

```bash
python opc_server.py config.json --debug
```

Debug mode prints FPS statistics every 5 seconds showing received and sent frame rates.

## Configuration

The server uses the same configuration format as other tools in this project. Key sections:

### OPC Section

```json
{
  "opc": {
    "host": "0.0.0.0",
    "port": 7890
  }
}
```

- `host`: IP address to bind to (use "0.0.0.0" for all interfaces)
- `port`: TCP port for OPC connections (7890 is standard)

### Outputs

```json
{
  "outputs": [
    {
      "port": "COM4",
      "protocol": "awa",
      "baud_rate": 2000000,
      "opc_channel": 0,
      "led_count": 300,
      "opc_offset": 0,
      "pixel_format": "GRB"
    }
  ]
}
```

**Per-output parameters:**
- `port`: Serial port (e.g., "COM4" on Windows, "/dev/ttyUSB0" on Linux)
- `protocol`: Output protocol ("awa" or "adalight")
- `baud_rate`: Serial baud rate (typically 2000000 for high-speed)
- `opc_channel`: OPC channel to listen on (0 = broadcast)
- `led_count`: Number of LEDs in the strip
- `opc_offset`: Start position in OPC data (for strip chaining)
- `pixel_format`: Color order ("RGB", "GRB", "BGR", "RGBW", "GRBW", or null for passthrough)

## OPC Protocol

The server implements the standard OPC protocol:

**Message Format:**
```
| Channel (1 byte) | Command (1 byte) | Length (2 bytes BE) | Data (length bytes) |
```

**Supported Commands:**
- `0x00`: Set pixel colors (the only command currently implemented)

**Channel Behavior:**
- Channel 0: Broadcast to all outputs configured for channel 0
- Channels 1-255: Route to specific outputs configured for that channel

## Multiple Outputs

You can configure multiple serial outputs with different channels:

```json
{
  "outputs": [
    {
      "port": "COM3",
      "opc_channel": 0,
      "led_count": 100,
      "protocol": "awa",
      "baud_rate": 2000000,
      "pixel_format": "GRB"
    },
    {
      "port": "COM4",
      "opc_channel": 1,
      "led_count": 200,
      "protocol": "adalight",
      "baud_rate": 1000000,
      "pixel_format": "RGB"
    }
  ]
}
```

In this example:
- Sending to channel 0 updates the first strip (broadcast)
- Sending to channel 1 updates the second strip only
- If channel 0 data arrives, it clears pending channel 1 data

## Supported Protocols

### AWA Protocol (HyperSerialPico)

**Status: Tested and working**

High-speed protocol with Fletcher checksum for data integrity:
- Header: `'Awa' + LED_count_high + LED_count_low + CRC`
- Data: RGB bytes for each pixel
- Footer: Fletcher checksums (3 bytes)

### Adalight Protocol

**Status: Experimental - Not tested**

Standard Adalight protocol:
- Header: `'Ada' + LED_count_high + LED_count_low + checksum`
- Data: RGB bytes for each pixel

**Note:** The Adalight protocol implementation is included but has not been tested with actual hardware. Use AWA protocol for production use.

## Testing

### Using the Included Test Client

A test client is provided in the `opc-test/` directory:

```bash
# Terminal 1: Start the server
python opc_server.py config.json

# Terminal 2: Run test client
cd ../opc-test
python test_client.py --pattern rainbow --leds 300
```

See `../opc-test/README.md` for full test client documentation.

### Using Custom OPC Clients

You can also test with any OPC client. Simple Python example:

```python
import socket
import struct

def send_opc_frame(host, port, channel, pixels):
    """Send OPC frame. pixels is list of (r,g,b) tuples"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    
    # Build pixel data
    data = bytearray()
    for r, g, b in pixels:
        data.extend([r, g, b])
    
    # Build OPC message
    message = struct.pack('>BBH', channel, 0, len(data)) + data
    sock.send(message)
    sock.close()

# Example: Send red to 100 pixels on channel 0
pixels = [(255, 0, 0)] * 100
send_opc_frame('localhost', 7890, 0, pixels)
```

## Performance Notes

- The server reads TCP data as fast as possible to prevent socket buffer overflow
- Stale frames are automatically discarded (single-depth queues)
- Serial writes are blocking but typically fast at high baud rates
- Debug mode adds minimal overhead (statistics calculated every 5 seconds)

## Troubleshooting

### "Error opening [port]"
- Check that the serial port exists and is not in use by another application
- On Linux, ensure you have permission to access the serial port (`sudo usermod -a -G dialout $USER`)

### Low frame rates
- Increase baud rate if supported by your LED controller
- Reduce LED count if possible
- Check for serial connection issues

### LEDs showing wrong colors
- Verify `pixel_format` matches your LED strip (common: "GRB" for WS2812B)
- Test with the validation tool first (`../validate/`)

### Connection refused
- Check that the specified host/port is available
- On Windows, may need to allow through firewall
- Try binding to "127.0.0.1" for local-only access

## Architecture Decisions

### Why single-depth queues?

Real-time LED control requires showing the most current data. Buffering old frames adds latency without benefit. The single-depth queue ensures:
- Minimal latency between OPC data arrival and LED output
- Automatic stale frame discard under high input rates
- Simple, efficient implementation

### Why immediate serial output?

Rather than using a separate output thread with async buffering, the server sends to serial immediately after receiving OPC data. This:
- Keeps the code simple (no double-buffering complexity)
- Reduces latency
- Matches the synchronous nature of serial communication
- Still handles multiple outputs efficiently

### Broadcasting semantics

Channel 0 clears other channels because in a typical setup, channel 0 is used for whole-installation effects that should override individual channel control. This prevents "stuck" pixels from old channel-specific data.

## Future Enhancements (Rust)

While this Python implementation is functional and suitable for many use cases, the project will include a Rust version for:
- Higher performance and lower latency
- Better resource efficiency
- Cross-platform deployment advantages
- More sophisticated buffering strategies if needed

The Python version serves as a reference implementation and is fully usable for production.
