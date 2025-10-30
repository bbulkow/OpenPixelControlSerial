#!/usr/bin/env python3
"""
Simple OPC test client
Sends test patterns to OPC server for validation
"""

import socket
import struct
import time
import argparse
import colorsys
import signal
import sys


class OPCClient:
    """OPC client with persistent connection"""
    
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
    
    def connect(self):
        """Connect to OPC server"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            return True
        except Exception as e:
            print(f"Error connecting: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from server"""
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None
    
    def send_frame(self, channel, pixels, debug=False):
        """
        Send OPC frame to server
        pixels: list of (r, g, b) tuples
        Returns: True on success, False on failure
        """
        # Build pixel data
        data = bytearray()
        for r, g, b in pixels:
            data.extend([r & 0xFF, g & 0xFF, b & 0xFF])
        
        # Build OPC message: channel, command(0), length(2 bytes BE), data
        message = struct.pack('>BBH', channel, 0, len(data)) + data
        
        if debug:
            print(f"[DEBUG] Sending: channel={channel}, pixel_count={len(pixels)}, byte_count={len(data)}, "
                  f"message_size={len(message)}, first_pixel={pixels[0] if pixels else None}")
            # Show first few pixels as hex
            hex_dump = ' '.join(f'{b:02x}' for b in data[:30])  # First 10 pixels
            print(f"[DEBUG] First 30 bytes (10 pixels): {hex_dump}")
        
        try:
            self.sock.sendall(message)
            return True
        except Exception as e:
            print(f"Error sending frame: {e}")
            return False


def pattern_solid(led_count, r, g, b):
    """Solid color pattern"""
    return [(r, g, b)] * led_count


def pattern_rainbow(led_count, offset=0.0):
    """Rainbow pattern"""
    pixels = []
    for i in range(led_count):
        hue = ((i / led_count) + offset) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        pixels.append((int(r * 255), int(g * 255), int(b * 255)))
    return pixels


def pattern_chase(led_count, position, length, r, g, b):
    """Chasing light pattern"""
    pixels = [(0, 0, 0)] * led_count
    for i in range(length):
        idx = (position + i) % led_count
        pixels[idx] = (r, g, b)
    return pixels


def main():
    parser = argparse.ArgumentParser(description='OPC Test Client - Send test patterns to OPC server')
    parser.add_argument('--host', default='localhost', help='OPC server host (default: localhost)')
    parser.add_argument('--port', type=int, default=7890, help='OPC server port (default: 7890)')
    parser.add_argument('--channel', type=int, default=0, help='OPC channel (default: 0)')
    parser.add_argument('--leds', type=int, default=100, help='Number of LEDs (default: 100)')
    parser.add_argument('--pattern', default='rainbow', 
                       choices=['solid', 'rainbow', 'chase', 'red', 'green', 'blue', 'white'],
                       help='Test pattern (default: rainbow)')
    parser.add_argument('--duration', type=float, default=10.0, help='Duration in seconds (default: 10)')
    parser.add_argument('--fps', type=int, default=30, help='Frames per second (default: 30)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output (stats only)')
    parser.add_argument('--ddebug', action='store_true', help='Enable detailed debug (hex dumps every frame)')
    
    args = parser.parse_args()
    
    # --ddebug implies --debug
    if args.ddebug:
        args.debug = True
    
    print(f"OPC Test Client")
    print(f"Connecting to {args.host}:{args.port}, channel {args.channel}")
    print(f"Pattern: {args.pattern}, LEDs: {args.leds}, Duration: {args.duration}s, FPS: {args.fps}")
    
    # Create client and connect
    client = OPCClient(args.host, args.port)
    if not client.connect():
        print("Failed to connect to server")
        sys.exit(1)
    
    print("✓ Connected")
    print()
    
    frame_time = 1.0 / args.fps
    start_time = time.time()
    frame = 0
    
    try:
        while (time.time() - start_time) < args.duration:
            frame_start = time.time()
            
            # Generate pattern
            if args.pattern == 'solid':
                pixels = pattern_solid(args.leds, 128, 128, 128)
            elif args.pattern == 'red':
                pixels = pattern_solid(args.leds, 255, 0, 0)
            elif args.pattern == 'green':
                pixels = pattern_solid(args.leds, 0, 255, 0)
            elif args.pattern == 'blue':
                pixels = pattern_solid(args.leds, 0, 0, 255)
            elif args.pattern == 'white':
                pixels = pattern_solid(args.leds, 255, 255, 255)
            elif args.pattern == 'rainbow':
                offset = (frame * 0.01) % 1.0
                pixels = pattern_rainbow(args.leds, offset)
            elif args.pattern == 'chase':
                position = int(frame * 0.5) % args.leds
                pixels = pattern_chase(args.leds, position, 10, 255, 255, 255)
            else:
                pixels = [(0, 0, 0)] * args.leds
            
            # Send frame (ddebug shows hex dumps)
            if not client.send_frame(args.channel, pixels, debug=args.ddebug):
                print("Failed to send frame, exiting")
                break
            
            # Status update
            if frame % args.fps == 0 and frame > 0:
                elapsed = time.time() - start_time
                actual_fps = frame / elapsed if elapsed > 0 else 0
                print(f"Frame {frame}, elapsed: {elapsed:.1f}s, actual FPS: {actual_fps:.1f}")
            
            # Maintain frame rate
            elapsed = time.time() - frame_start
            if elapsed < frame_time:
                time.sleep(frame_time - elapsed)
            
            frame += 1
        
        # Send blank frame at end
        pixels = [(0, 0, 0)] * args.leds
        client.send_frame(args.channel, pixels)
        
        print(f"\n✓ Completed {frame} frames")
        
    except KeyboardInterrupt:
        print("\n✗ Interrupted, clearing LEDs")
        pixels = [(0, 0, 0)] * args.leds
        client.send_frame(args.channel, pixels)
    
    finally:
        client.disconnect()
        print("✓ Disconnected")


if __name__ == "__main__":
    main()
