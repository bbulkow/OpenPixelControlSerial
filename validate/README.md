# OpenPixelControlSerial - Configuration Validation

Validate serial LED connections and configurations with test patterns.

## Purpose

This tool validates that:
1. Your configuration file is correct
2. Serial connections are working
3. LED strips respond to commands
4. Pixel format transformations work correctly

## Setup

```bash
cd validate
pip install -r requirements.txt
```

## Usage

```bash
python validate.py [options]
```

### Options

- `--config`, `-c` - Path to config file (default: config.json)
- `--pattern`, `-p` - Test pattern name (default: white-blink)
- `--duration`, `-d` - Test duration in seconds (default: 5.0)
- `--r` - Red value (0-255) for color patterns
- `--g` - Green value (0-255) for color patterns
- `--b` - Blue value (0-255) for color patterns

**Note:** Target FPS is read from the config file (`target_fps` field, defaults to 30)

## Test Patterns

### solid
Displays a solid color on all LEDs.

**Examples:**
```bash
python validate.py --pattern solid --r 255 --g 0 --b 0      # Red
python validate.py --pattern solid --r 0 --g 255 --b 0      # Green
python validate.py --pattern solid --r 0 --g 0 --b 255      # Blue
python validate.py --pattern solid --r 255 --g 255 --b 255  # White
```

### blink
Blinks a specified color on/off.

**Examples:**
```bash
python validate.py --pattern blink --r 255 --g 0 --b 0      # Blink red
python validate.py --pattern blink --r 0 --g 255 --b 255    # Blink cyan
```

### white-blink
Blinks white light (convenience shortcut for testing).

**Example:**
```bash
python validate.py --pattern white-blink
python validate.py --pattern white-blink --duration 10
```

### hue-circle
Displays a rotating rainbow color wheel across the LED strip.

**Examples:**
```bash
python validate.py --pattern hue-circle
python validate.py --pattern hue-circle --duration 10
```

### chase
Creates a chasing/running light effect.

**Examples:**
```bash
python validate.py --pattern chase --r 255 --g 0 --b 0      # Red chase
python validate.py --pattern chase --r 0 --g 255 --b 0      # Green chase
```

## Complete Examples

### Quick connectivity test (uses defaults: config.json and white-blink pattern)
```bash
python validate.py
```

### Use config from discover directory
```bash
python validate.py --config ../discover/config.json
```

### Verify all colors work
```bash
python validate.py --pattern solid --r 255 --g 0 --b 0     # Test red
python validate.py --pattern solid --r 0 --g 255 --b 0     # Test green
python validate.py --pattern solid --r 0 --g 0 --b 255     # Test blue
```

### Test pixel format (GRB vs RGB)
If colors appear wrong, your pixel_format may be incorrect:
```bash
# Should be red - if it's green, you need GRB format
python validate.py --pattern solid --r 255 --g 0 --b 0
```

### Long-running test
```bash
python validate.py --pattern hue-circle --duration 60
```

## Troubleshooting

### No LEDs light up

1. Check physical connections (power, data, ground)
2. Verify LED strip is powered (most strips need external 5V power)
3. Check serial port path is correct in config.json
4. Verify baud rate matches your device
5. Try a simple white-blink test first

### Wrong colors appear

This usually indicates incorrect `pixel_format` in config.json:

- If you send **red** but get **green**: Use `"pixel_format": "GRB"`
- If you send **red** but get **blue**: Use `"pixel_format": "BGR"`
- If colors are completely wrong: Try different formats (RGB, GRB, BGR)

### LEDs only partially light up

Check `led_count` in your config.json matches your physical LED count.

### Choppy/slow animation

Increase `--fps` value or check if serial baud rate is high enough for your LED count:
- 115200 baud: ~150 RGB LEDs at 30 FPS
- 2000000 baud: ~2000 RGB LEDs at 30 FPS

## Exit

Press `Ctrl+C` to stop any running test pattern. LEDs will automatically turn off.

## What Gets Tested

This validation tool tests:
- ✓ Config file parsing
- ✓ Serial port connectivity
- ✓ Protocol implementation (Adalight/AWA)
- ✓ Pixel format transformations (RGB/GRB/BGR/RGBW/GRBW)
- ✓ Frame rate handling
- ✓ LED addressing and count

## Next Steps

Once validation is successful, you can proceed to:
1. Run the main OPC server
2. Connect OPC clients (Processing, Chromatik, etc.)
3. Create your LED art!
