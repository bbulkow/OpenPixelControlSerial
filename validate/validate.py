#!/usr/bin/env python3
"""
OpenPixelControlSerial - Validation Tool
Tests serial connections and LED strips with various patterns
"""

import sys
import json
import time
import argparse
import serial
from typing import List, Tuple, Dict, Any
import colorsys


class LEDOutput:
    """Handles serial output to LED strips"""
    
    def __init__(self, config: Dict[str, Any]):
        self.port = config['port']
        self.protocol = config['protocol']
        self.baud_rate = config['baud_rate']
        self.led_count = config['led_count']
        self.pixel_format = config.get('pixel_format', None)  # None = passthrough
        self.ser = None
    
    def open(self):
        """Open serial connection"""
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=1)
            time.sleep(0.1)  # Allow device to initialize
            return True
        except serial.SerialException as e:
            print(f"Error opening {self.port}: {e}")
            return False
    
    def close(self):
        """Close serial connection"""
        if self.ser:
            self.ser.close()
    
    def send_frame(self, pixels: List[Tuple[int, int, int]], debug=False):
        """
        Send a frame of RGB pixels to the LED strip
        pixels: List of (R, G, B) tuples
        """
        if not self.ser:
            return False
        
        # Pad or truncate to led_count
        while len(pixels) < self.led_count:
            pixels.append((0, 0, 0))
        pixels = pixels[:self.led_count]
        
        if debug:
            print(f"  Sending frame: {len(pixels)} pixels, first pixel: {pixels[0] if pixels else 'none'}")
        
        # Apply pixel format transformation if specified
        if self.pixel_format:
            pixels = self._transform_pixels(pixels)
        
        # Send frame based on protocol
        if self.protocol == 'awa':
            self._send_awa_frame(pixels, debug=debug)
        elif self.protocol == 'adalight':
            self._send_adalight_frame(pixels)
        else:
            print(f"Protocol {self.protocol} not yet implemented")
            return False
        
        return True
    
    def _transform_pixels(self, pixels: List[Tuple[int, int, int]]) -> List[Tuple]:
        """Transform RGB pixels based on pixel_format"""
        # RGB passthrough - no transformation needed
        if self.pixel_format == 'RGB' or self.pixel_format is None:
            return pixels
        
        # For same-size 3-channel transforms, transform in place
        if self.pixel_format in ('GRB', 'BGR'):
            pixel_count = len(pixels)
            # Pre-allocate list
            transformed = [None] * pixel_count
            
            if self.pixel_format == 'GRB':
                for i in range(pixel_count):
                    r, g, b = pixels[i]
                    transformed[i] = (g, r, b)
            else:  # BGR
                for i in range(pixel_count):
                    r, g, b = pixels[i]
                    transformed[i] = (b, g, r)
            
            return transformed
        
        # RGBW transforms - different size output
        if self.pixel_format in ('RGBW', 'GRBW'):
            pixel_count = len(pixels)
            # Pre-allocate list for 4-channel output
            transformed = [None] * pixel_count
            
            if self.pixel_format == 'RGBW':
                for i in range(pixel_count):
                    r, g, b = pixels[i]
                    # Extract white channel and subtract from RGB
                    w = min(r, g, b)
                    transformed[i] = (r - w, g - w, b - w, w)
            else:  # GRBW
                for i in range(pixel_count):
                    r, g, b = pixels[i]
                    # Extract white channel and subtract from RGB
                    w = min(r, g, b)
                    transformed[i] = (g - w, r - w, b - w, w)
            
            return transformed
        
        # Unknown format - return unchanged
        return pixels
    
    def _send_adalight_frame(self, pixels: List[Tuple]):
        """Send Adalight protocol frame"""
        # Adalight header: 'Ada' + LED count high + LED count low + checksum
        led_count = len(pixels)
        header = bytearray([
            0x41, 0x64, 0x61,  # 'Ada'
            (led_count >> 8) & 0xFF,
            led_count & 0xFF,
            (led_count >> 8) ^ (led_count & 0xFF) ^ 0x55
        ])
        
        # Build pixel data
        data = bytearray()
        for pixel in pixels:
            for channel in pixel:
                data.append(channel & 0xFF)
        
        # Send frame
        self.ser.write(header + data)
        self.ser.flush()
    
    def _send_awa_frame(self, pixels: List[Tuple], debug=False):
        """Send AWA protocol frame (HyperSerialPico format)"""
        led_count = len(pixels)
        
        # AWA header: 'Awa' + LED count high + LED count low + CRC
        count_hi = (led_count - 1) >> 8 & 0xFF
        count_lo = (led_count - 1) & 0xFF
        crc = (count_hi ^ count_lo) ^ 0x55
        
        header = bytearray([
            0x41, 0x77, 0x61,  # 'Awa'
            count_hi,
            count_lo,
            crc
        ])
        
        if debug:
            print(f"  AWA Header: {header.hex()}, LED count: {led_count}")
        
        # Build pixel data
        data = bytearray()
        for pixel in pixels:
            for channel in pixel:
                data.append(channel & 0xFF)
        
        if debug:
            print(f"  Pixel data: {len(data)} bytes, first 12 bytes: {data[:12].hex() if len(data) >= 12 else data.hex()}")
        
        # Calculate Fletcher checksums (matches HyperSerialPico implementation)
        fletcher1 = 0
        fletcher2 = 0
        fletcher_ext = 0
        position = 0
        
        for byte in data:
            fletcher1 = (fletcher1 + byte) % 255
            fletcher2 = (fletcher2 + fletcher1) % 255
            fletcher_ext = (fletcher_ext + (byte ^ position)) % 255
            position += 1
        
        # Special case: if fletcher_ext is 0x41 ('A'), use 0xaa instead
        if fletcher_ext == 0x41:
            fletcher_ext = 0xaa
        
        if debug:
            print(f"  Fletcher: {fletcher1:02x} {fletcher2:02x} {fletcher_ext:02x}")
        
        # Send frame: header + data + fletcher checksums
        frame = header + data + bytearray([fletcher1, fletcher2, fletcher_ext])
        
        if debug:
            print(f"  Total frame size: {len(frame)} bytes")
        
        self.ser.write(frame)
        self.ser.flush()


class TestPattern:
    """Base class for test patterns"""
    
    def generate(self, frame: int, led_count: int) -> List[Tuple[int, int, int]]:
        """Generate pixel data for a given frame number"""
        raise NotImplementedError


class SolidColor(TestPattern):
    """Solid color pattern"""
    
    def __init__(self, r: int, g: int, b: int):
        self.r = r
        self.g = g
        self.b = b
    
    def generate(self, frame: int, led_count: int) -> List[Tuple[int, int, int]]:
        return [(self.r, self.g, self.b)] * led_count


class Blink(TestPattern):
    """Blinking pattern"""
    
    def __init__(self, r: int, g: int, b: int, interval: float = 0.5):
        self.r = r
        self.g = g
        self.b = b
        self.interval = interval
    
    def generate(self, frame: int, led_count: int) -> List[Tuple[int, int, int]]:
        # Blink on/off based on time
        on = (int(time.time() / self.interval) % 2) == 0
        if on:
            return [(self.r, self.g, self.b)] * led_count
        else:
            return [(0, 0, 0)] * led_count


class HueCircle(TestPattern):
    """Rainbow hue circle that rotates"""
    
    def __init__(self, speed: float = 0.1):
        self.speed = speed
    
    def generate(self, frame: int, led_count: int) -> List[Tuple[int, int, int]]:
        pixels = []
        offset = frame * self.speed
        
        for i in range(led_count):
            # Calculate hue based on position
            hue = ((i / led_count) + offset) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            pixels.append((int(r * 255), int(g * 255), int(b * 255)))
        
        return pixels


class Chase(TestPattern):
    """Chasing light pattern"""
    
    def __init__(self, r: int, g: int, b: int, length: int = 5, speed: float = 0.1):
        self.r = r
        self.g = g
        self.b = b
        self.length = length
        self.speed = speed
    
    def generate(self, frame: int, led_count: int) -> List[Tuple[int, int, int]]:
        pixels = [(0, 0, 0)] * led_count
        position = int(frame * self.speed) % led_count
        
        for i in range(self.length):
            idx = (position + i) % led_count
            pixels[idx] = (self.r, self.g, self.b)
        
        return pixels


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from JSON file"""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}")
        sys.exit(1)


def run_test(outputs: List[LEDOutput], pattern: TestPattern, duration: float, fps: int, debug: bool = False):
    """Run a test pattern on all outputs"""
    print(f"Running pattern for {duration:.1f} seconds at {fps} FPS...")
    
    frame_time = 1.0 / fps
    start_time = time.time()
    frame = 0
    
    try:
        while (time.time() - start_time) < duration:
            frame_start = time.time()
            
            # Generate and send frame to all outputs
            # Debug first frame only to avoid spam
            show_debug = debug and frame == 0
            if show_debug:
                print(f"\n[Frame {frame} debug]")
            
            for output in outputs:
                pixels = pattern.generate(frame, output.led_count)
                output.send_frame(pixels, debug=show_debug)
            
            # Maintain frame rate
            elapsed = time.time() - frame_start
            if elapsed < frame_time:
                time.sleep(frame_time - elapsed)
            
            frame += 1
        
        # Clear all LEDs at end
        for output in outputs:
            output.send_frame([(0, 0, 0)] * output.led_count)
        
        print(f"✓ Completed {frame} frames")
        
    except KeyboardInterrupt:
        print("\n✗ Test interrupted")
        # Clear LEDs
        for output in outputs:
            output.send_frame([(0, 0, 0)] * output.led_count)


def main():
    # Available patterns for help text
    available_patterns = {
        'solid': 'Solid color - requires --r, --g, --b',
        'blink': 'Blinking color - requires --r, --g, --b',
        'white-blink': 'Blinking white light',
        'hue-circle': 'Rotating rainbow color wheel',
        'chase': 'Chasing/running light - requires --r, --g, --b'
    }
    
    pattern_help = "Available patterns:\n" + "\n".join([f"  {name:12} - {desc}" for name, desc in available_patterns.items()])
    
    parser = argparse.ArgumentParser(
        description='OpenPixelControlSerial - Configuration Validation Tool\n\nValidate serial LED connections with test patterns.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
{pattern_help}

Examples:
  python validate.py --pattern white-blink
  python validate.py --config config.json --pattern solid --r 255 --g 0 --b 0
  python validate.py --pattern hue-circle --duration 10
  python validate.py --config myconfig.json --pattern chase --r 0 --g 255 --b 0
        """
    )
    
    parser.add_argument('--config', '-c', default='config.json',
                       help='Path to config file (default: config.json)')
    parser.add_argument('--pattern', '-p', default='white-blink',
                       help='Test pattern name (default: white-blink)')
    parser.add_argument('--duration', '-d', type=float, default=5.0,
                       help='Test duration in seconds (default: 5.0)')
    parser.add_argument('--r', type=int, metavar='R',
                       help='Red value (0-255) for patterns requiring RGB')
    parser.add_argument('--g', type=int, metavar='G',
                       help='Green value (0-255) for patterns requiring RGB')
    parser.add_argument('--b', type=int, metavar='B',
                       help='Blue value (0-255) for patterns requiring RGB')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug output (shows first frame details)')
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    if 'outputs' not in config or not config['outputs']:
        print("Error: No outputs defined in config file")
        sys.exit(1)
    
    # Create output handlers
    outputs = []
    for output_config in config['outputs']:
        output = LEDOutput(output_config)
        if output.open():
            outputs.append(output)
            print(f"✓ Opened {output.port} ({output.protocol} @ {output.baud_rate} baud, {output.led_count} LEDs)")
        else:
            print(f"✗ Failed to open {output.port}")
    
    if not outputs:
        print("\nError: No outputs could be opened")
        sys.exit(1)
    
    # Get target FPS from config, with fallback to 30
    target_fps = config.get('target_fps', 30)
    print(f"Target FPS: {target_fps}")
    
    # Create test pattern
    pattern = None
    pattern_name = args.pattern.lower()
    
    try:
        if pattern_name == 'solid':
            if args.r is None or args.g is None or args.b is None:
                print("Error: solid pattern requires --r, --g, --b values")
                sys.exit(1)
            pattern = SolidColor(args.r, args.g, args.b)
            print(f"Test Pattern: Solid RGB({args.r}, {args.g}, {args.b})")
        
        elif pattern_name == 'blink':
            if args.r is None or args.g is None or args.b is None:
                print("Error: blink pattern requires --r, --g, --b values")
                sys.exit(1)
            pattern = Blink(args.r, args.g, args.b)
            print(f"Test Pattern: Blink RGB({args.r}, {args.g}, {args.b})")
        
        elif pattern_name == 'white-blink':
            pattern = Blink(255, 255, 255)
            print("Test Pattern: White Blink")
        
        elif pattern_name == 'hue-circle':
            pattern = HueCircle()
            print("Test Pattern: Hue Circle (Rainbow)")
        
        elif pattern_name == 'chase':
            if args.r is None or args.g is None or args.b is None:
                print("Error: chase pattern requires --r, --g, --b values")
                sys.exit(1)
            pattern = Chase(args.r, args.g, args.b)
            print(f"Test Pattern: Chase RGB({args.r}, {args.g}, {args.b})")
        
        else:
            print(f"Error: Unknown pattern '{args.pattern}'")
            print("\nAvailable patterns:")
            for name, desc in available_patterns.items():
                print(f"  {name:12} - {desc}")
            sys.exit(1)
    
    except (ValueError, TypeError) as e:
        print(f"Error: Invalid pattern arguments - {e}")
        sys.exit(1)
    
    # Run test
    print()
    try:
        run_test(outputs, pattern, args.duration, target_fps, debug=args.debug)
    finally:
        # Close all outputs
        for output in outputs:
            output.close()
    
    print("\n✓ Validation complete")


if __name__ == "__main__":
    main()
