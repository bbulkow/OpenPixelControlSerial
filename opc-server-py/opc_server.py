#!/usr/bin/env python3
"""
OpenPixelControlSerial - OPC Server
Receives OPC data over TCP and outputs to serial LED strips
"""

import sys
import json
import time
import argparse
import serial
import socket
import struct
import threading
import signal
from typing import Dict, Any
from queue import Queue, Empty, Full


class LEDOutput:
    """Handles serial output to LED strips with dedicated worker thread"""
    
    def __init__(self, config: Dict[str, Any], ddebug: bool = False):
        self.port = config['port']
        self.protocol = config['protocol']
        self.baud_rate = config['baud_rate']
        self.led_count = config['led_count']
        self.opc_channel = config['opc_channel']
        self.opc_offset = config.get('opc_offset', 0)
        self.pixel_format = config.get('pixel_format', None)
        self.ddebug = ddebug
        self.ser = None
        
        # Determine output stride based on pixel format
        if self.pixel_format in ('RGBW', 'GRBW'):
            self.stride = 4
        else:
            self.stride = 3
        
        # Queue and worker thread (one per serial output)
        self.queue = Queue(maxsize=1)
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
    
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
        self.running = False
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                # Port may already be disconnected - ignore errors during close
                pass
    
    def put_frame(self, pixel_data: bytearray):
        """
        Put frame in queue (called by main thread)
        Non-blocking - replaces old frame if queue is full
        """
        try:
            self.queue.put_nowait(pixel_data)
        except Full:
            # Queue full, replace with new frame
            try:
                self.queue.get_nowait()  # Discard old frame
            except Empty:
                pass  # Race condition - someone else got it
            try:
                self.queue.put_nowait(pixel_data)
            except Full:
                pass  # Still full somehow, skip this frame
    
    def _worker(self):
        """Worker thread - blocks waiting for frames, sends to serial"""
        while self.running:
            try:
                # Block until data available (efficient, no spinning)
                pixel_data = self.queue.get(timeout=0.1)
                self._send_frame(pixel_data)
            except Empty:
                # Timeout - check if still running
                continue
    
    def _send_frame(self, pixel_data: bytearray):
        """Send a frame to the LED strip"""
        if not self.ser:
            return False
        
        try:
            # Apply pixel format transformation if specified
            if self.pixel_format:
                pixel_data = self._transform_pixels(pixel_data)
            
            # Send frame based on protocol
            if self.protocol == 'awa':
                self._send_awa_frame(pixel_data)
            elif self.protocol == 'adalight':
                self._send_adalight_frame(pixel_data)
            else:
                print(f"Protocol {self.protocol} not yet implemented")
                return False
            
            return True
            
        except serial.SerialException as e:
            print(f"✗ Serial error on {self.port}: {e}")
            print(f"✗ Output {self.port} is now disconnected")
            self.ser = None  # Mark as disconnected
            return False
        except Exception as e:
            print(f"✗ Unexpected error on {self.port}: {e}")
            return False
    
    def _transform_pixels(self, pixel_data: bytearray) -> bytearray:
        """Transform RGB pixel data based on pixel_format"""
        # RGB passthrough - no transformation needed
        if self.pixel_format == 'RGB' or self.pixel_format is None:
            return pixel_data
        
        pixel_count = len(pixel_data) // 3
        
        # For same-size 3-channel transforms, transform in-place
        if self.pixel_format == 'GRB':
            # Swap R and G channels in place
            for i in range(pixel_count):
                idx = i * 3
                pixel_data[idx], pixel_data[idx + 1] = pixel_data[idx + 1], pixel_data[idx]
            return pixel_data
        
        elif self.pixel_format == 'BGR':
            # Reverse RGB to BGR in place
            for i in range(pixel_count):
                idx = i * 3
                pixel_data[idx], pixel_data[idx + 2] = pixel_data[idx + 2], pixel_data[idx]
            return pixel_data
        
        # RGBW transforms - different size output
        elif self.pixel_format in ('RGBW', 'GRBW'):
            # Create new buffer with stride 4
            transformed = bytearray(pixel_count * 4)
            
            for i in range(pixel_count):
                src_idx = i * 3
                dst_idx = i * 4
                r = pixel_data[src_idx]
                g = pixel_data[src_idx + 1]
                b = pixel_data[src_idx + 2]
                
                # Extract white channel and subtract from RGB
                w = min(r, g, b)
                
                if self.pixel_format == 'RGBW':
                    transformed[dst_idx] = r - w
                    transformed[dst_idx + 1] = g - w
                    transformed[dst_idx + 2] = b - w
                    transformed[dst_idx + 3] = w
                else:  # GRBW
                    transformed[dst_idx] = g - w
                    transformed[dst_idx + 1] = r - w
                    transformed[dst_idx + 2] = b - w
                    transformed[dst_idx + 3] = w
            
            return transformed
        
        # Unknown format - return unchanged
        return pixel_data
    
    def _send_adalight_frame(self, pixel_data: bytearray):
        """Send Adalight protocol frame (may raise SerialException)"""
        # Adalight header: 'Ada' + LED count high + LED count low + checksum
        led_count = len(pixel_data) // self.stride
        header = bytearray([
            0x41, 0x64, 0x61,  # 'Ada'
            (led_count >> 8) & 0xFF,
            led_count & 0xFF,
            (led_count >> 8) ^ (led_count & 0xFF) ^ 0x55
        ])
        
        # Construct complete frame
        frame = header + pixel_data
        
        # Debug: print raw frame being sent to serial
        if self.ddebug:
            print(f"[SERIAL] {self.port} Adalight: {len(frame)} bytes ({led_count} pixels)")
            hex_dump = ' '.join(f'{b:02x}' for b in frame)
            print(f"[SERIAL] Raw output: {hex_dump}")
        
        # Send frame: header + pixel data (may raise SerialException)
        self.ser.write(frame)
        self.ser.flush()
    
    def _send_awa_frame(self, pixel_data: bytearray):
        """Send AWA protocol frame (HyperSerialPico format, may raise SerialException)"""
        led_count = len(pixel_data) // self.stride
        
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
        
        # Calculate Fletcher checksums (matches HyperSerialPico implementation)
        fletcher1 = 0
        fletcher2 = 0
        fletcher_ext = 0
        position = 0
        
        for byte in pixel_data:
            fletcher1 = (fletcher1 + byte) % 255
            fletcher2 = (fletcher2 + fletcher1) % 255
            fletcher_ext = (fletcher_ext + (byte ^ position)) % 255
            position += 1
        
        # Special case: if fletcher_ext is 0x41 ('A'), use 0xaa instead
        if fletcher_ext == 0x41:
            fletcher_ext = 0xaa
        
        # Construct complete frame
        frame = header + pixel_data + bytearray([fletcher1, fletcher2, fletcher_ext])
        
        # Debug: print raw frame being sent to serial
        if self.ddebug:
            print(f"[SERIAL] {self.port} AWA: {len(frame)} bytes ({led_count} pixels)")
            print(f"[SERIAL] Header: {' '.join(f'{b:02x}' for b in header)}")
            print(f"[SERIAL] Fletcher: {fletcher1:02x} {fletcher2:02x} {fletcher_ext:02x}")
            hex_dump = ' '.join(f'{b:02x}' for b in frame)
            print(f"[SERIAL] Raw output: {hex_dump}")
        
        # Send frame: header + data + fletcher checksums
        self.ser.write(frame)
        self.ser.flush()


class OPCServer:
    """OPC Server that receives OPC data and outputs to serial"""
    
    # Receive buffer size (supports large frames)
    RECV_BUFFER_SIZE = 16384  # 16KB
    
    def __init__(self, config: Dict[str, Any], debug: bool = False, ddebug: bool = False):
        self.config = config
        self.debug = debug
        self.ddebug = ddebug
        self.host = config['opc']['host']
        self.port = config['opc']['port']
        self.outputs = []
        self.running = False
        self.server_socket = None
        
        # Statistics
        self.frames_received = 0
        self.frames_sent = 0
        self.last_stats_time = time.time()
    
    def setup_outputs(self):
        """Initialize serial outputs (each with worker thread)"""
        for output_config in self.config['outputs']:
            output = LEDOutput(output_config, ddebug=self.ddebug)
            if output.open():
                self.outputs.append(output)
                print(f"✓ Opened {output.port} (channel {output.opc_channel}, offset {output.opc_offset}, "
                      f"{output.protocol} @ {output.baud_rate} baud, {output.led_count} LEDs)")
            else:
                print(f"✗ Failed to open {output.port}")
        
        if not self.outputs:
            print("Error: No outputs could be opened")
            return False
        
        return True
    
    def start(self):
        """Start the OPC server"""
        if not self.setup_outputs():
            return False
        
        self.running = True
        
        # Start server socket
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            print(f"✓ OPC Server listening on {self.host}:{self.port}")
        except Exception as e:
            print(f"Error starting server: {e}")
            return False
        
        # Start stats thread if debug enabled
        if self.debug:
            stats_thread = threading.Thread(target=self._stats_worker, daemon=True)
            stats_thread.start()
        
        return True
    
    def _stats_worker(self):
        """Print statistics periodically"""
        while self.running:
            time.sleep(5.0)
            current_time = time.time()
            elapsed = current_time - self.last_stats_time
            
            if elapsed > 0:
                fps_received = self.frames_received / elapsed
                fps_sent = self.frames_sent / elapsed
                print(f"[Stats] Received: {fps_received:.1f} fps, Sent: {fps_sent:.1f} fps")
            
            self.frames_received = 0
            self.frames_sent = 0
            self.last_stats_time = current_time
    
    def run(self):
        """Main server loop"""
        print("Waiting for OPC client connection...")
        print("(Press Ctrl-C to stop)")
        
        # Set socket timeout so accept() doesn't block forever
        self.server_socket.settimeout(1.0)
        
        try:
            while self.running:
                try:
                    # Accept client connection (with timeout)
                    client_socket, client_address = self.server_socket.accept()
                    print(f"✓ Client connected from {client_address}")
                    
                    try:
                        self._handle_client(client_socket)
                    except Exception as e:
                        print(f"Error handling client: {e}")
                        if self.debug:
                            import traceback
                            traceback.print_exc()
                    finally:
                        client_socket.close()
                        print("Client disconnected")
                
                except socket.timeout:
                    # Timeout on accept - check if still running
                    continue
                except OSError as e:
                    # Socket closed
                    if self.running:
                        print(f"Socket error: {e}")
                    break
        
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.stop()
    
    def _handle_client(self, client_socket):
        """Handle OPC client connection with non-blocking TCP drain"""
        # Set socket to non-blocking mode
        client_socket.setblocking(False)
        buffer = b''
        
        while self.running:
            # Drain TCP socket (read all available data)
            while True:
                try:
                    data = client_socket.recv(self.RECV_BUFFER_SIZE)
                    if not data:
                        # Connection closed
                        return
                    buffer += data
                except BlockingIOError:
                    # No more data available right now
                    break
                except Exception as e:
                    if self.debug:
                        print(f"Error reading from socket: {e}")
                    return
            
            # Process complete OPC messages in buffer
            while len(buffer) >= 4:
                # OPC header: channel (1 byte), command (1 byte), length (2 bytes, big-endian)
                channel = buffer[0]
                command = buffer[1]
                length = struct.unpack('>H', buffer[2:4])[0]
                
                # Check if we have the complete message
                message_size = 4 + length
                if len(buffer) < message_size:
                    break
                
                # Extract message data as bytearray
                message_data = bytearray(buffer[4:message_size])
                buffer = buffer[message_size:]
                
                # Process OPC message
                if command == 0:  # Set pixel colors
                    self._process_pixel_data(channel, message_data)
                    self.frames_received += 1
            
            # Small sleep to avoid busy loop (1ms)
            time.sleep(0.001)
    
    def _process_pixel_data(self, channel: int, pixel_data: bytearray):
        """
        Process OPC pixel data - slice and distribute to serial outputs
        Each output gets its slice based on opc_offset and led_count
        """
        if self.ddebug:
            print(f"[DEBUG] Received: channel={channel}, byte_count={len(pixel_data)}, "
                  f"pixel_count={len(pixel_data)//3}")
            # Show first few pixels as hex
            hex_dump = ' '.join(f'{b:02x}' for b in pixel_data[:30])
            print(f"[DEBUG] First 30 bytes received: {hex_dump}")
        
        # Distribute to each serial output listening to this channel
        for output in self.outputs:
            # Does this output listen to this channel?
            # Broadcast (channel 0) goes to outputs configured for channel 0
            # Other channels go to matching outputs
            if output.opc_channel != channel:
                # Skip if not the right channel
                if not (channel == 0 and output.opc_channel == 0):
                    continue
            
            # Calculate byte offset and length for this output
            offset_bytes = output.opc_offset * 3  # RGB stride
            needed_bytes = output.led_count * 3
            
            # Slice data for this output (handles overlaps gracefully)
            end_byte = offset_bytes + needed_bytes
            sliced_data = bytearray(pixel_data[offset_bytes:end_byte])
            
            # DO NOT pad with zeros - send only the data we received
            # If we got fewer pixels than configured, send fewer pixels
            
            # Send to this output's queue (non-blocking)
            if self.ddebug:
                print(f"[DEBUG] Output {output.port}: sliced={len(sliced_data)} bytes "
                      f"({len(sliced_data)//3} pixels), needed={needed_bytes} bytes")
                hex_dump = ' '.join(f'{b:02x}' for b in sliced_data[:30])
                print(f"[DEBUG] First 30 bytes to output: {hex_dump}")
            output.put_frame(sliced_data)
            self.frames_sent += 1
    
    def stop(self):
        """Stop the server and cleanup"""
        self.running = False
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        
        # Stop all outputs
        for output in self.outputs:
            try:
                # Try to turn off LEDs (may fail if port disconnected)
                blank_data = bytearray(output.led_count * 3)
                output.put_frame(blank_data)
                # Give worker thread a moment to process
                time.sleep(0.05)
            except Exception:
                pass
            
            # Close will stop worker thread and serial port
            output.close()
        
        print("✓ Server stopped")


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


def main():
    parser = argparse.ArgumentParser(
        description='OpenPixelControlSerial - OPC Server\n\nReceives OPC data over TCP and outputs to serial LED strips.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('config', 
                       help='Path to configuration file (JSON)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug output (statistics only)')
    parser.add_argument('--ddebug', action='store_true',
                       help='Enable detailed debug (hex dumps every frame)')
    
    args = parser.parse_args()
    
    # --ddebug implies --debug
    if args.ddebug:
        args.debug = True
    
    # Load configuration
    config = load_config(args.config)
    
    # Validate config
    if 'opc' not in config:
        print("Error: Config must contain 'opc' section")
        sys.exit(1)
    
    if 'outputs' not in config or not config['outputs']:
        print("Error: No outputs defined in config file")
        sys.exit(1)
    
    # Create and start server
    server = OPCServer(config, debug=args.debug, ddebug=args.ddebug)
    
    if not server.start():
        sys.exit(1)
    
    # Run server
    server.run()


if __name__ == "__main__":
    main()
