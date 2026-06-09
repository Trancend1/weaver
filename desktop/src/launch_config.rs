//! Resolves everything the host needs to launch the cockpit sidecar:
//! the `weaver` executable, the shared app-data/log directory, a free
//! loopback port, and the per-session token.
//!
//! Path resolution intentionally mirrors `weaver.services.app_paths`
//! (`%APPDATA%/Weaver` on Windows, `~/Library/Application Support/Weaver`
//! on macOS, `~/.weaver` otherwise) so the host and the sidecar agree on
//! `logs_dir`. The host then passes the resolved directory back to the child
//! via `WEAVER_DATA_DIR`, making the agreement explicit rather than implied.

use std::net::TcpListener;
use std::path::PathBuf;

/// Env var a maintainer can set to point at a specific `weaver` binary
/// (e.g. a bundled sidecar in Sprint O). When unset, the host relies on
/// `weaver` being resolvable on `PATH`.
const SIDECAR_OVERRIDE_ENV: &str = "WEAVER_DESKTOP_SIDECAR";

#[derive(Clone, Debug)]
pub struct LaunchConfig {
    /// The `weaver` executable to spawn (`Command::new` resolves bare names via PATH).
    pub weaver_exe: PathBuf,
    /// App-data root shared with the sidecar (passed as `WEAVER_DATA_DIR`).
    pub data_dir: PathBuf,
    /// `data_dir/logs` — where the cockpit writes `runtime.log` and where the
    /// host writes `sidecar.console.log`.
    pub logs_dir: PathBuf,
    /// OS-assigned free port on 127.0.0.1.
    pub port: u16,
    /// Opaque per-launch session token (64 hex chars / 32 bytes).
    pub token: String,
}

impl LaunchConfig {
    pub fn resolve() -> Result<Self, String> {
        let data_dir = resolve_data_dir();
        let logs_dir = data_dir.join("logs");
        Ok(Self {
            weaver_exe: resolve_weaver_exe(),
            data_dir,
            logs_dir,
            port: pick_free_port()?,
            token: generate_token()?,
        })
    }

    /// The cockpit URL the WebView opens (`/` redirects here anyway).
    pub fn ui_url(&self) -> String {
        format!("http://127.0.0.1:{}/ui", self.port)
    }

    pub fn healthz_url(&self) -> String {
        format!("http://127.0.0.1:{}/healthz", self.port)
    }
}

fn resolve_weaver_exe() -> PathBuf {
    if let Ok(v) = std::env::var(SIDECAR_OVERRIDE_ENV) {
        if !v.trim().is_empty() {
            return PathBuf::from(v);
        }
    }
    // Bare name; `std::process::Command` resolves it through PATH. On Windows
    // the `.exe` suffix is applied automatically by the OS loader.
    PathBuf::from("weaver")
}

fn resolve_data_dir() -> PathBuf {
    if let Ok(v) = std::env::var("WEAVER_DATA_DIR") {
        if !v.trim().is_empty() {
            return PathBuf::from(v);
        }
    }

    #[cfg(windows)]
    {
        if let Ok(appdata) = std::env::var("APPDATA") {
            if !appdata.trim().is_empty() {
                return PathBuf::from(appdata).join("Weaver");
            }
        }
    }

    #[cfg(target_os = "macos")]
    {
        if let Some(home) = home_dir() {
            return home
                .join("Library")
                .join("Application Support")
                .join("Weaver");
        }
    }

    home_dir().unwrap_or_else(|| PathBuf::from(".")).join(".weaver")
}

fn home_dir() -> Option<PathBuf> {
    #[cfg(windows)]
    {
        std::env::var_os("USERPROFILE").map(PathBuf::from)
    }
    #[cfg(not(windows))]
    {
        std::env::var_os("HOME").map(PathBuf::from)
    }
}

/// Bind 127.0.0.1:0, read the assigned port, drop the listener. The contract
/// (SIDECAR_CONTRACT.md §6) endorses this over parsing stdout; a small
/// bind→close→reuse race is accepted.
fn pick_free_port() -> Result<u16, String> {
    let listener =
        TcpListener::bind(("127.0.0.1", 0)).map_err(|e| format!("cannot reserve a port: {e}"))?;
    listener
        .local_addr()
        .map(|addr| addr.port())
        .map_err(|e| format!("cannot read reserved port: {e}"))
}

fn generate_token() -> Result<String, String> {
    let mut buf = [0u8; 32];
    getrandom::getrandom(&mut buf).map_err(|e| format!("cannot generate session token: {e}"))?;
    let mut hex = String::with_capacity(64);
    for byte in buf {
        hex.push_str(&format!("{byte:02x}"));
    }
    Ok(hex)
}
