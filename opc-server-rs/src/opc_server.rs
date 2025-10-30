use anyhow::{Context, Result};
use std::io::{Read, ErrorKind};
use std::net::{TcpListener, TcpStream};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::thread;
use std::time::Duration;

use crate::config::Config;
use crate::output::Output;

const RECV_BUFFER_SIZE: usize = 16384; // 16KB

/// OPC Server that receives OPC data and distributes to serial outputs
pub struct OpcServer {
    config: Config,
    outputs: Vec<Output>,
    frames_received: Arc<AtomicU64>,
    running: Arc<AtomicBool>,
    debug: bool,
    ddebug: bool,
}

impl OpcServer {
    /// Get a clone of the running flag for signal handlers
    pub fn get_running_flag(&self) -> Arc<AtomicBool> {
        Arc::clone(&self.running)
    }
    
    /// Gracefully shutdown - send black frames to all outputs
    pub fn shutdown(&mut self) {
        if self.debug {
            println!("Turning off LEDs...");
        }
        
        for output in &self.outputs {
            let config = output.config();
            let black_data = vec![0u8; config.led_count * 3];
            
            // Send black frame
            let _ = output.send_frame(black_data);
        }
        
        // Give worker threads time to process the black frames
        thread::sleep(Duration::from_millis(100));
        
        if self.debug {
            println!("✓ Server stopped");
        }
    }
    
    /// Create a new OPC server
    pub fn new(config: Config, debug: bool, ddebug: bool) -> Result<Self> {
        let mut outputs = Vec::new();
        
        // Initialize all outputs
        for output_config in &config.outputs {
            match Output::new(output_config.clone(), debug, ddebug) {
                Ok(output) => outputs.push(output),
                Err(e) => eprintln!("✗ Failed to open {}: {}", output_config.port, e),
            }
        }
        
        if outputs.is_empty() {
            anyhow::bail!("No outputs could be opened");
        }
        
        Ok(OpcServer {
            config,
            outputs,
            frames_received: Arc::new(AtomicU64::new(0)),
            running: Arc::new(AtomicBool::new(true)),
            debug,
            ddebug,
        })
    }
    
    /// Run the OPC server
    pub fn run(&self) -> Result<()> {
        let addr = format!("{}:{}", self.config.opc.host, self.config.opc.port);
        let listener = TcpListener::bind(&addr)
            .context(format!("Failed to bind to {}", addr))?;
        
        // Set nonblocking so accept() can check running flag periodically
        listener.set_nonblocking(true)?;
        
        if self.debug {
            println!("✓ OPC Server listening on {}", addr);
            println!("Waiting for OPC client connection...");
            println!("(Press Ctrl-C to stop)");
        }
        
        // Spawn statistics thread if debug enabled
        if self.debug {
            self.spawn_stats_thread();
        }
        
        loop {
            // Check if we should stop
            if !self.running.load(Ordering::Relaxed) {
                break;
            }
            
            // Try to accept a connection
            match listener.accept() {
                Ok((stream, peer_addr)) => {
                    if self.debug {
                        println!("✓ Client connected from {}", peer_addr);
                    }
                    
                    if let Err(e) = self.handle_client(stream) {
                        eprintln!("Error handling client: {}", e);
                    }
                    
                    if self.debug {
                        println!("Client disconnected");
                    }
                }
                Err(e) if e.kind() == ErrorKind::WouldBlock || e.kind() == ErrorKind::TimedOut => {
                    // No connection ready, sleep briefly to avoid busy-waiting
                    thread::sleep(Duration::from_millis(100));
                }
                Err(e) => {
                    eprintln!("Error accepting connection: {}", e);
                    thread::sleep(Duration::from_millis(100));
                }
            }
        }
        
        Ok(())
    }
    
    /// Handle a single client connection with NON-BLOCKING TCP reads
    fn handle_client(&self, mut stream: TcpStream) -> Result<()> {
        // CRITICAL: Set socket to non-blocking mode (like Python's setblocking(False))
        stream.set_nonblocking(true)
            .context("Failed to set socket to non-blocking mode")?;
        
        let mut buffer = Vec::new();
        let mut read_buf = vec![0u8; RECV_BUFFER_SIZE];
        
        while self.running.load(Ordering::Relaxed) {
            // NON-BLOCKING TCP DRAIN: Read all available data (like Python)
            // This loop continues until we get WouldBlock (no more data available)
            loop {
                match stream.read(&mut read_buf) {
                    Ok(0) => {
                        // Connection closed by client
                        return Ok(());
                    }
                    Ok(n) => {
                        // Got data, append to buffer and continue draining
                        buffer.extend_from_slice(&read_buf[..n]);
                    }
                    Err(e) if e.kind() == ErrorKind::WouldBlock => {
                        // No more data available right now - this is expected in non-blocking mode
                        break;
                    }
                    Err(e) if e.kind() == ErrorKind::Interrupted => {
                        // Interrupted by signal, try again
                        continue;
                    }
                    Err(e) => {
                        // Real error
                        return Err(e.into());
                    }
                }
            }
            
            // Process complete OPC messages from buffer
            while buffer.len() >= 4 {
                // OPC header: channel (1 byte), command (1 byte), length (2 bytes, big-endian)
                let channel = buffer[0];
                let command = buffer[1];
                let length = u16::from_be_bytes([buffer[2], buffer[3]]) as usize;
                
                // Check if we have the complete message
                let message_size = 4 + length;
                if buffer.len() < message_size {
                    break; // Wait for more data
                }
                
                // Extract and process message
                let message_data: Vec<u8> = buffer.drain(..message_size).skip(4).collect();
                
                // Process OPC message
                if command == 0 {
                    // Set pixel colors
                    self.process_pixel_data(channel, &message_data);
                    self.frames_received.fetch_add(1, Ordering::Relaxed);
                }
            }
            
            // Small sleep to avoid busy-looping (like Python's 1ms sleep)
            thread::sleep(Duration::from_millis(1));
        }
        
        Ok(())
    }
    
    /// Process OPC pixel data and distribute to outputs
    fn process_pixel_data(&self, channel: u8, pixel_data: &[u8]) {
        if self.ddebug {
            eprintln!("[DEBUG] Received: channel={}, byte_count={}, pixel_count={}",
                     channel, pixel_data.len(), pixel_data.len() / 3);
            let hex: String = pixel_data.iter().take(30)
                .map(|b| format!("{:02x}", b)).collect::<Vec<_>>().join(" ");
            eprintln!("[DEBUG] First 30 bytes received: {}", hex);
        }
        
        // Distribute to each output listening to this channel
        for output in &self.outputs {
            let output_config = output.config();
            
            // Check if this output listens to this channel
            if output_config.opc_channel != channel {
                continue;
            }
            
            // Calculate byte offset and length for this output
            let offset_bytes = output_config.opc_offset * 3; // RGB stride
            let needed_bytes = output_config.led_count * 3;
            
            // Slice data for this output - send exactly what we get, AWA header will match
            let end_byte = (offset_bytes + needed_bytes).min(pixel_data.len());
            let sliced_data = if offset_bytes < pixel_data.len() {
                pixel_data[offset_bytes..end_byte].to_vec()
            } else {
                // No data for this output
                Vec::new()
            };
            
            if self.ddebug {
                eprintln!("[DEBUG] Output {}: sliced={} bytes ({} pixels), needed={} bytes",
                         output_config.port, sliced_data.len(), sliced_data.len() / 3, needed_bytes);
                let hex: String = sliced_data.iter().take(30)
                    .map(|b| format!("{:02x}", b)).collect::<Vec<_>>().join(" ");
                eprintln!("[DEBUG] First 30 bytes to output: {}", hex);
            }
            
            // Send to output (non-blocking, skip-ahead)
            let _ = output.send_frame(sliced_data);
        }
    }
    
    /// Spawn statistics thread
    fn spawn_stats_thread(&self) {
        let frames_received = Arc::clone(&self.frames_received);
        let running = Arc::clone(&self.running);
        let output_counters: Vec<_> = self.outputs.iter().map(|o| {
            (o.config().port.clone(), o.frames_sent_counter())
        }).collect();
        
        thread::spawn(move || {
            let mut last_received = 0u64;
            let mut last_sent: Vec<u64> = vec![0; output_counters.len()];
            
            while running.load(Ordering::Relaxed) {
                thread::sleep(Duration::from_secs(5));
                
                let current_received = frames_received.load(Ordering::Relaxed);
                let received_delta = current_received - last_received;
                let received_fps = received_delta as f64 / 5.0;
                
                print!("[Stats] Received: {:.1} fps", received_fps);
                
                for (i, (port, counter)) in output_counters.iter().enumerate() {
                    let current = counter.load(Ordering::Relaxed);
                    let delta = current - last_sent[i];
                    let fps = delta as f64 / 5.0;
                    print!(", {}: {:.1} fps", port, fps);
                    last_sent[i] = current;
                }
                
                println!();
                
                last_received = current_received;
            }
        });
    }
    
}
