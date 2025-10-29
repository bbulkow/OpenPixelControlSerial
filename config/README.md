# Configuration Format

JSON-based configuration for OpenPixelControlSerial supporting multiple serial outputs with color mapping, gamma correction, and RGBW conversion.

## Structure

```json
{
  "opc": {
    "host": "0.0.0.0",
    "port": 7890
  },
  "target_fps": 30,
  "outputs": [
    {
      "port": "COM4",
      "protocol": "awa",
      "baud_rate": 2000000,
      "led_count": 300,
      "opc_offset": 0,
      "pixel_format": "GRB"
    }
  ]
}
```

## Fields

### OPC Server (`opc`)
- **host** (string): Bind address for OPC server (e.g., "0.0.0.0", "127.0.0.1")
- **port** (integer): TCP port for OPC server (default: 7890)

### Performance (`target_fps`)
- **target_fps** (integer, optional): Target frames per second for LED updates
  - Default: 30 FPS
  - Depends on LED controller capabilities and serial bandwidth
  - AWA/HyperSerialPico: typically 60+ FPS
  - Standard Adalight: typically 30 FPS

### Output Devices (`outputs`)
Array of serial output configurations. Each output:

#### Required Fields
- **port** (string): Serial port path (e.g., "/dev/ttyUSB0", "COM4")
- **protocol** (string): Serial protocol type
  - `"awa"` - AWA/HyperSerialPico (high-speed Adalight)
  - `"adalight"` - Standard Adalight
  - `"wled"` - WLED over serial
- **baud_rate** (integer): Serial baud rate (e.g., 115200, 2000000)
- **led_count** (integer): Number of LEDs on this output
- **opc_channel** (integer): OPC channel to listen to (0-255)
  - Channel 0 is broadcast (all outputs receive)
  - Channels 1-255 address specific outputs
  - Default: 0 if not specified
- **opc_offset** (integer): Starting pixel index within the OPC channel's data
  - Used to map a portion of channel data to this output
  - For example, offset 0 = first LED, offset 150 = 151st LED

#### Optional Fields
- **pixel_format** (string): Pixel format for this LED strip
  - **Default: pass-through** (OPC RGB data sent directly without transformation)
  - Common formats: `"RGB"`, `"GRB"`, `"BGR"`, `"RGBW"`, `"GRBW"`
  - System remaps OPC RGB triples to specified format
  - For RGBW formats: automatically converts RGB→RGBW (white derived from min(R,G,B))

#### Future/Example Transformations (Not Yet Implemented)
- **gamma** (float): Per-output gamma correction
  - Example: `2.2` for standard gamma correction
  - Would allow different gamma for different LED types

## OPC Channel and Address Space Mapping

### Understanding OPC Channels

OPC (Open Pixel Control) messages contain:
- **Channel** (0-255): Which output strand/group
- **Command**: What to do (0 = SetPixelColors)
- **Data**: RGB pixel array

Each output in your config specifies:
- **opc_channel**: Which OPC channel to listen to
- **opc_offset**: Which pixels within that channel's data

### Common Mapping Patterns

**Pattern 1: Broadcast (Single Channel)**
All outputs listen to channel 0 (broadcast):
```json
"outputs": [
  {"port": "/dev/ttyUSB0", "opc_channel": 0, "led_count": 150, "opc_offset": 0},
  {"port": "/dev/ttyUSB1", "opc_channel": 0, "led_count": 150, "opc_offset": 150}
]
```
OPC channel 0, pixels 0-149 → USB0
OPC channel 0, pixels 150-299 → USB1

**Pattern 2: Separate Channels**
Each output on its own channel:
```json
"outputs": [
  {"port": "/dev/ttyUSB0", "opc_channel": 1, "led_count": 150, "opc_offset": 0},
  {"port": "/dev/ttyUSB1", "opc_channel": 2, "led_count": 100, "opc_offset": 0}
]
```
OPC channel 1 → USB0 (150 LEDs)
OPC channel 2 → USB1 (100 LEDs)

**Pattern 3: Mixed Channels**
Some outputs share a channel, others separate:
```json
"outputs": [
  {"port": "/dev/ttyUSB0", "opc_channel": 1, "led_count": 150, "opc_offset": 0},
  {"port": "/dev/ttyUSB1", "opc_channel": 1, "led_count": 150, "opc_offset": 150},
  {"port": "/dev/ttyUSB2", "opc_channel": 2, "led_count": 200, "opc_offset": 0}
]
```
OPC channel 1, pixels 0-149 → USB0
OPC channel 1, pixels 150-299 → USB1
OPC channel 2, pixels 0-199 → USB2

## Examples

### Single AWA Output (Broadcast Channel)
```json
{
  "opc": {"host": "0.0.0.0", "port": 7890},
  "outputs": [{
    "port": "COM4",
    "protocol": "awa",
    "baud_rate": 2000000,
    "opc_channel": 0,
    "led_count": 300,
    "opc_offset": 0
  }]
}
```

### Single Output with GRB Format
```json
{
  "opc": {"host": "0.0.0.0", "port": 7890},
  "outputs": [{
    "port": "COM4",
    "protocol": "awa",
    "baud_rate": 2000000,
    "opc_channel": 0,
    "led_count": 300,
    "opc_offset": 0,
    "pixel_format": "GRB"
  }]
}
```

### Multiple Outputs on Same Channel (Split Long Strip)
```json
{
  "opc": {"host": "0.0.0.0", "port": 7890},
  "outputs": [
    {
      "port": "/dev/ttyUSB0",
      "protocol": "awa",
      "baud_rate": 2000000,
      "opc_channel": 0,
      "led_count": 150,
      "opc_offset": 0,
      "pixel_format": "GRB"
    },
    {
      "port": "/dev/ttyUSB1",
      "protocol": "adalight",
      "baud_rate": 115200,
      "opc_channel": 0,
      "led_count": 100,
      "opc_offset": 150,
      "pixel_format": "RGB"
    }
  ]
}
```

### Multiple Outputs on Different Channels
```json
{
  "opc": {"host": "127.0.0.1", "port": 7890},
  "outputs": [
    {
      "port": "/dev/ttyUSB0",
      "protocol": "awa",
      "baud_rate": 2000000,
      "opc_channel": 1,
      "led_count": 150,
      "opc_offset": 0,
      "pixel_format": "GRB"
    },
    {
      "port": "/dev/ttyUSB1",
      "protocol": "adalight",
      "baud_rate": 115200,
      "opc_channel": 2,
      "led_count": 100,
      "opc_offset": 0,
      "pixel_format": "RGB"
    }
  ]
}
```

### RGBW Format Example
```json
{
  "opc": {"host": "0.0.0.0", "port": 7890},
  "outputs": [{
    "port": "COM3",
    "protocol": "awa",
    "baud_rate": 2000000,
    "opc_channel": 0,
    "led_count": 200,
    "opc_offset": 0,
    "pixel_format": "GRBW"
  }]
}
```

### Future: With Gamma Correction (Example)
```json
{
  "opc": {"host": "0.0.0.0", "port": 7890},
  "outputs": [{
    "port": "COM4",
    "protocol": "awa",
    "baud_rate": 2000000,
    "opc_channel": 0,
    "led_count": 300,
    "opc_offset": 0,
    "pixel_format": "GRB",
    "gamma": 2.2
  }]
}
```

## Processing Order

Current implementation:
1. Extract RGB pixel from OPC data at `opc_offset + pixel_index`
2. If `pixel_format` specified: remap/convert channels per format
   - RGB→GRB, RGB→RGBW, etc.
3. Send to serial `port` via `protocol`

Future transformations (not yet implemented):
- Gamma correction
- Other per-output color transforms

## File Location

Default: `config/config.json` (relative to project root)

Can be overridden via command-line argument or environment variable.
