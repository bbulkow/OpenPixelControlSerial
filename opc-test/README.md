# OPC Test Client

Simple test client for validating OPC (Open Pixel Control) servers. Can be used to test both the Python and Rust implementations.

## Overview

This test client sends OPC frames over TCP to test OPC server implementations. It includes various test patterns and is useful for:
- Validating OPC server functionality
- Testing LED installations without dedicated OPC client software
- Debugging OPC protocol implementations
- Demonstrating OPC frame generation

## Installation

No additional dependencies required beyond Python's standard library.

## Usage

### Basic Usage

```bash
python test_client.py --pattern rainbow --leds 100
```

### Command-Line Options

```
--host HOST           OPC server host (default: localhost)
--port PORT           OPC server port (default: 7890)
--channel CHANNEL     OPC channel (default: 0)
--leds LEDS          Number of LEDs (default: 100)
--pattern PATTERN    Test pattern (see below)
--duration DURATION  Duration in seconds (default: 10)
--fps FPS           Frames per second (default: 30)
```

### Available Patterns

- **solid**: Gray solid color (128, 128, 128)
- **red**: Solid red
- **green**: Solid green  
- **blue**: Solid blue
- **white**: Solid white
- **rainbow**: Rotating rainbow color wheel (default)
- **chase**: Chasing/running white light

### Examples

Test with rainbow pattern at 60 FPS:
```bash
python test_client.py --pattern rainbow --fps 60 --leds 300
```

Send solid red to channel 1:
```bash
python test_client.py --pattern red --channel 1 --leds 100
```

Test chase pattern for 30 seconds:
```bash
python test_client.py --pattern chase --duration 30
```

Connect to remote server:
```bash
python test_client.py --host 192.168.1.100 --pattern rainbow
```

## OPC Protocol

The test client implements the standard OPC protocol:

**Message Format:**
```
| Channel (1 byte) | Command (1 byte) | Length (2 bytes BE) | Data (length bytes) |
```

- **Channel**: 0-255, where 0 is typically broadcast
- **Command**: 0 for "Set Pixel Colors"
- **Length**: Number of bytes in pixel data (LED count × 3 for RGB)
- **Data**: RGB values for each pixel (R, G, B, R, G, B, ...)

## Testing OPC Servers

### Python Server

```bash
# Terminal 1: Start the Python OPC server
cd opc-server-py
python opc_server.py config.json

# Terminal 2: Run the test client
cd opc-test
python test_client.py --pattern rainbow --leds 300
```

### Rust Server (when available)

```bash
# Terminal 1: Start the Rust OPC server
cd opc-server-rs
cargo run -- config.json

# Terminal 2: Run the test client
cd opc-test
python test_client.py --pattern rainbow --leds 300
```

## Pattern Details

### Rainbow Pattern
Generates a smooth rainbow color wheel that rotates around the LED strip. Each LED displays a different hue based on its position, creating a flowing rainbow effect.

### Chase Pattern
Creates a moving "comet" of 10 white LEDs that travels along the strip. Good for testing timing and frame rate.

### Solid Colors
Useful for:
- Verifying color channels are working correctly
- Testing pixel format transformations
- Checking for color accuracy
- Basic connectivity tests

## Troubleshooting

### "Connection refused"
- Ensure the OPC server is running
- Check that host and port are correct
- Verify firewall settings

### Pattern not displaying correctly
- Verify LED count matches your configuration
- Check that the correct channel is specified
- Ensure the server is configured with matching outputs

### Frame rate issues
- Lower FPS if system can't keep up
- Check network latency to remote servers
- Monitor CPU usage on both client and server

## Implementation Notes

The test client creates a new TCP connection for each frame. While this is less efficient than maintaining a persistent connection, it:
- Simplifies the code
- Works well for testing purposes
- Helps identify connection issues
- Is sufficient for moderate frame rates (<100 FPS)

For production applications requiring high frame rates, consider implementing a persistent connection with proper buffering.

## Use Cases

- **Development**: Test OPC server implementations during development
- **Debugging**: Isolate issues by sending controlled test patterns
- **Demonstrations**: Show LED capabilities without complex client software
- **Validation**: Verify new hardware setups are working correctly
- **Learning**: Understand OPC protocol by examining the simple implementation

## Extending the Test Client

The code is intentionally simple and well-commented. You can easily add new patterns by:

1. Creating a new pattern generation function
2. Adding the pattern name to the choices list
3. Adding a case in the main loop to call your pattern function

Example:
```python
def pattern_sparkle(led_count, frame):
    """Random sparkle pattern"""
    import random
    pixels = [(0, 0, 0)] * led_count
    for _ in range(led_count // 10):
        idx = random.randint(0, led_count - 1)
        pixels[idx] = (255, 255, 255)
    return pixels
