//! Opt-in, notification-only update check (ADR 017 D3). DEFAULT OFF.
//!
//! When (and only when) the user opts in, this performs ONE HTTPS GET to the
//! release manifest, compares the latest version to the running build, and shows
//! a non-blocking notification with the release URL. It never downloads,
//! executes, or installs anything. Any failure is a silent no-op — a failed
//! update check must never affect launch.
//!
//! Opt-in resolution order: WEAVER_DESKTOP_UPDATE_CHECK env (1/true | 0/false)
//! wins; else %APPDATA%/Weaver/desktop/settings.json {"update_check": bool};
//! else false.

use std::path::Path;
use std::time::Duration;

const MANIFEST_URL: &str =
    "https://github.com/Trancend1/weaver/releases/latest/download/latest.json";
const RELEASES_URL: &str = "https://github.com/Trancend1/weaver/releases/latest";
const CHECK_TIMEOUT: Duration = Duration::from_secs(4);
const CURRENT_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Opt-in flag: env override wins; else settings.json; else false (default OFF).
pub fn update_check_enabled(data_dir: &Path) -> bool {
    if let Ok(v) = std::env::var("WEAVER_DESKTOP_UPDATE_CHECK") {
        match v.trim().to_ascii_lowercase().as_str() {
            "1" | "true" | "yes" | "on" => return true,
            "0" | "false" | "no" | "off" => return false,
            _ => {}
        }
    }
    let settings = data_dir.join("desktop").join("settings.json");
    let Ok(text) = std::fs::read_to_string(settings) else {
        return false;
    };
    serde_json::from_str::<serde_json::Value>(&text)
        .ok()
        .and_then(|v| v.get("update_check").and_then(serde_json::Value::as_bool))
        .unwrap_or(false)
}

/// Compare dotted numeric versions (e.g. "0.8.0"). `true` if `latest` > `current`.
/// Non-numeric/malformed input returns `false` (treat as "no update").
pub fn is_newer(latest: &str, current: &str) -> bool {
    let parse = |s: &str| -> Option<Vec<u64>> {
        s.trim()
            .trim_start_matches('v')
            .split('.')
            .map(|p| p.parse::<u64>().ok())
            .collect()
    };
    match (parse(latest), parse(current)) {
        (Some(a), Some(b)) => a > b,
        _ => false,
    }
}

/// Fetch the manifest and return the latest version string, if reachable.
fn fetch_latest_version() -> Option<String> {
    let resp = ureq::get(MANIFEST_URL)
        .timeout(CHECK_TIMEOUT)
        .set("User-Agent", "weaver-desktop")
        .call()
        .ok()?;
    if resp.status() != 200 {
        return None;
    }
    let body = resp.into_json::<serde_json::Value>().ok()?;
    body.get("version")
        .and_then(serde_json::Value::as_str)
        .map(str::to_owned)
}

/// Result of a completed check: `Some(url)` means notify with this release URL.
pub fn check_for_update(data_dir: &Path) -> Option<String> {
    if !update_check_enabled(data_dir) {
        return None;
    }
    let latest = fetch_latest_version()?;
    if is_newer(&latest, CURRENT_VERSION) {
        Some(RELEASES_URL.to_string())
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn newer_versions_detected() {
        assert!(is_newer("0.8.0", "0.7.0"));
        assert!(is_newer("1.0.0", "0.9.9"));
        assert!(is_newer("v0.7.1", "0.7.0"));
    }

    #[test]
    fn same_or_older_is_not_newer() {
        assert!(!is_newer("0.7.0", "0.7.0"));
        assert!(!is_newer("0.6.9", "0.7.0"));
    }

    #[test]
    fn malformed_versions_are_not_newer() {
        assert!(!is_newer("garbage", "0.7.0"));
        assert!(!is_newer("0.7.0", ""));
    }

    #[test]
    fn disabled_by_default_without_settings() {
        let dir = std::env::temp_dir().join("weaver-update-test-empty");
        let _ = std::fs::create_dir_all(&dir);
        std::env::remove_var("WEAVER_DESKTOP_UPDATE_CHECK");
        assert!(!update_check_enabled(&dir));
    }

    #[test]
    fn env_override_enables_and_disables() {
        let dir = std::env::temp_dir().join("weaver-update-test-env");
        let _ = std::fs::create_dir_all(&dir);
        std::env::set_var("WEAVER_DESKTOP_UPDATE_CHECK", "1");
        assert!(update_check_enabled(&dir));
        std::env::set_var("WEAVER_DESKTOP_UPDATE_CHECK", "0");
        assert!(!update_check_enabled(&dir));
        std::env::remove_var("WEAVER_DESKTOP_UPDATE_CHECK");
    }
}
