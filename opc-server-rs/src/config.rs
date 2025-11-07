use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Config {
    pub opc: OpcConfig,
    pub outputs: Vec<OutputConfig>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct OpcConfig {
    pub host: String,
    pub port: u16,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct OutputConfig {
    pub port: String,
    pub protocol: String,
    pub baud_rate: u32,
    /// Optional baud rate for initial handshake/configuration (e.g., WLED JSON protocol)
    /// If specified, the port will open at this speed first, then switch to baud_rate for LED data
    pub handshake_baud_rate: Option<u32>,
    /// Optional hardware type identifier (e.g., "WLED")
    /// When set to "WLED", triggers WLED-specific initialization including JSON handshake and speed switching
    pub hardware_type: Option<String>,
    pub opc_channel: u8,
    pub led_count: usize,
    #[serde(default)]
    pub opc_offset: usize,
    pub pixel_format: Option<String>,
}
