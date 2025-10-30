use anyhow::Result;
use clap::Parser;
use std::fs;

mod config;
mod opc_server;
mod output;
mod pixel_format;
mod protocol;

use config::Config;
use opc_server::OpcServer;

#[derive(Parser)]
#[command(name = "opc_server")]
#[command(about = "OpenPixelControlSerial - OPC Server\n\nReceives OPC data over TCP and outputs to serial LED strips.", long_about = None)]
struct Cli {
    /// Path to configuration file (JSON)
    config: String,

    /// Enable debug output (statistics)
    #[arg(long)]
    debug: bool,

    /// Enable detailed debug (hex dumps every frame)
    #[arg(long)]
    ddebug: bool,
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    // Load configuration
    let config_data = fs::read_to_string(&cli.config)?;
    let config: Config = serde_json::from_str(&config_data)?;

    // ddebug implies debug
    let debug = cli.debug || cli.ddebug;
    
    // Create server
    let mut server = OpcServer::new(config, debug, cli.ddebug)?;
    
    // Set up Ctrl-C handler with graceful shutdown
    let running = server.get_running_flag();
    let debug_for_handler = debug;
    let result = ctrlc::set_handler(move || {
        if debug_for_handler {
            println!("\nShutting down...");
        }
        running.store(false, std::sync::atomic::Ordering::Relaxed);
    });
    
    if let Err(e) = result {
        eprintln!("Warning: Could not set Ctrl-C handler: {}", e);
    }
    
    // Run server (blocks until shutdown)
    server.run()?;
    
    // Graceful shutdown - send black frames to turn off LEDs
    server.shutdown();

    Ok(())
}
