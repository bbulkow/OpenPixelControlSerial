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
    pub opc_channel: u8,
    pub led_count: usize,
    #[serde(default)]
    pub opc_offset: usize,
    pub pixel_format: Option<String>,
}
