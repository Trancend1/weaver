//! Weaver desktop shell (Sprint N — Tauri Shell Alpha).
//!
//! Orchestrates the sidecar lifecycle on top of the FastAPI cockpit:
//!
//!   1. resolve launch config (exe, data dir, free port, session token)
//!   2. show a local loading window immediately (fast first paint)
//!   3. on a background thread: spawn `weaver serve`, poll `/healthz` (≤5s)
//!   4. on ready  → open the cockpit WebView (with the session-header
//!      interceptor) and close the loading window
//!   5. on failure → show a crash window with the mapped exit code + console tail
//!   6. on window close / app exit → shut the sidecar down (no orphan)
//!
//! No JS↔Rust command bridge, no UI rewrite. See ../docs/SIDECAR_CONTRACT.md.

mod launch_config;
mod sidecar;
mod webview_session;

use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder, WindowEvent};

use launch_config::LaunchConfig;
use sidecar::{Poll, Sidecar};

/// Total budget for the cockpit to answer `/healthz` before we declare failure.
const HEALTH_BUDGET: Duration = Duration::from_secs(5);
const POLL_INTERVAL: Duration = Duration::from_millis(50);

/// The live sidecar, owned globally so the boot thread, the close handler, and
/// the exit handler can all reach it. `None` before spawn and after shutdown.
static SIDECAR: Mutex<Option<Sidecar>> = Mutex::new(None);

pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let cfg = match LaunchConfig::resolve() {
                Ok(cfg) => cfg,
                Err(err) => {
                    // Could not even reserve a port / token — show crash directly.
                    show_crash(
                        app.handle(),
                        crash_payload(
                            "Weaver could not start",
                            &err,
                            None,
                            &cfg_fallback_log_path(),
                            &[],
                        ),
                    );
                    return Ok(());
                }
            };

            // Loading window first — keeps double-click → first paint snappy (N1).
            WebviewWindowBuilder::new(app, "loading", WebviewUrl::App("loading.html".into()))
                .title("Weaver")
                .inner_size(900.0, 600.0)
                .min_inner_size(640.0, 420.0)
                .center()
                .build()?;

            let handle = app.handle().clone();
            std::thread::spawn(move || boot(handle, cfg));
            Ok(())
        })
        .on_window_event(|window, event| {
            if !matches!(event, WindowEvent::CloseRequested { .. }) {
                return;
            }
            match window.label() {
                // The cockpit window closing ends the session.
                "main" => shutdown_sidecar(),
                // Closing the loading window is a teardown ONLY when it's a user
                // cancel during boot. When `open_cockpit` closes it after the
                // cockpit opened, "main" already exists — so we must NOT kill the
                // sidecar we just handed off.
                "loading" if window.app_handle().get_webview_window("main").is_none() => {
                    shutdown_sidecar();
                }
                _ => {}
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building the Weaver desktop shell")
        .run(|_app, event| {
            if let RunEvent::ExitRequested { .. } = event {
                shutdown_sidecar();
            }
        });
}

/// Background boot sequence: spawn the sidecar and poll until healthy, dead, or
/// timed out. Runs off the main thread; all window work is marshalled back.
fn boot(handle: AppHandle, cfg: LaunchConfig) {
    let spawned = match Sidecar::spawn(&cfg) {
        Ok(sidecar) => sidecar,
        Err(err) => {
            show_crash(
                &handle,
                crash_payload(
                    "Weaver could not start",
                    &err,
                    None,
                    &cfg.logs_dir.join("sidecar.console.log").display().to_string(),
                    &[],
                ),
            );
            return;
        }
    };

    // Store globally BEFORE polling so a close during boot still kills it.
    *SIDECAR.lock().unwrap() = Some(spawned);

    let healthz = cfg.healthz_url();
    let log_path = cfg.logs_dir.join("sidecar.console.log").display().to_string();
    let deadline = Instant::now() + HEALTH_BUDGET;

    loop {
        let tick = {
            let mut guard = SIDECAR.lock().unwrap();
            match guard.as_mut() {
                // Taken by a close/exit during boot — abort silently.
                None => return,
                Some(sidecar) => sidecar.poll_once(&healthz),
            }
        };

        match tick {
            Poll::Ready => {
                open_cockpit(handle, cfg);
                return;
            }
            Poll::Exited(code) => {
                let tail = console_tail();
                shutdown_sidecar();
                show_crash(
                    &handle,
                    crash_payload(
                        "The cockpit stopped during startup",
                        "The backend process exited before it became ready.",
                        Some(code),
                        &log_path,
                        &tail,
                    ),
                );
                return;
            }
            Poll::Pending => {}
        }

        if Instant::now() >= deadline {
            let tail = console_tail();
            shutdown_sidecar();
            show_crash(
                &handle,
                crash_payload(
                    "The cockpit did not respond in time",
                    "The backend did not answer /healthz within 5 seconds.",
                    None,
                    &log_path,
                    &tail,
                ),
            );
            return;
        }

        std::thread::sleep(POLL_INTERVAL);
    }
}

/// Open the cockpit WebView (external URL + session-header interceptor) and
/// close the loading window. Marshalled onto the main thread.
fn open_cockpit(handle: AppHandle, cfg: LaunchConfig) {
    let _ = handle.clone().run_on_main_thread(move || {
        let url = match tauri::Url::parse(&cfg.ui_url()) {
            Ok(url) => url,
            Err(err) => {
                show_crash(
                    &handle,
                    crash_payload(
                        "Weaver could not open the cockpit",
                        &format!("Invalid cockpit URL: {err}"),
                        None,
                        &cfg.logs_dir.join("sidecar.console.log").display().to_string(),
                        &console_tail(),
                    ),
                );
                return;
            }
        };

        let built = WebviewWindowBuilder::new(&handle, "main", WebviewUrl::External(url))
            .title("Weaver")
            .inner_size(1280.0, 800.0)
            .min_inner_size(900.0, 600.0)
            .center()
            .build();

        match built {
            Ok(window) => {
                webview_session::install_session_header(&window, &cfg.token);
                if let Some(loading) = handle.get_webview_window("loading") {
                    let _ = loading.close();
                }
            }
            Err(err) => {
                show_crash(
                    &handle,
                    crash_payload(
                        "Weaver could not open the cockpit",
                        &format!("Failed to create the application window: {err}"),
                        None,
                        &cfg.logs_dir.join("sidecar.console.log").display().to_string(),
                        &console_tail(),
                    ),
                );
            }
        }
    });
}

/// Build a crash window with the payload baked in via an initialization script
/// (no fetch, no navigation race), then close the loading window.
fn show_crash(handle: &AppHandle, payload: serde_json::Value) {
    let handle = handle.clone();
    let _ = handle.clone().run_on_main_thread(move || {
        if handle.get_webview_window("crash").is_some() {
            return; // already showing one
        }
        let script = format!("window.__WEAVER_CRASH__ = {payload};");
        let built = WebviewWindowBuilder::new(&handle, "crash", WebviewUrl::App("crash.html".into()))
            .title("Weaver — startup failed")
            .inner_size(820.0, 620.0)
            .min_inner_size(560.0, 420.0)
            .center()
            .initialization_script(&script)
            .build();
        if built.is_ok() {
            if let Some(loading) = handle.get_webview_window("loading") {
                let _ = loading.close();
            }
        }
    });
}

fn console_tail() -> Vec<String> {
    SIDECAR
        .lock()
        .unwrap()
        .as_ref()
        .map(Sidecar::console_tail)
        .unwrap_or_default()
}

fn shutdown_sidecar() {
    // Take under the lock, then drop the guard before the (up to 5s) shutdown so
    // a concurrent close/exit handler isn't blocked holding the mutex.
    let taken = SIDECAR.lock().unwrap().take();
    if let Some(mut sidecar) = taken {
        sidecar.shutdown();
    }
}

fn crash_payload(
    headline: &str,
    detail: &str,
    exit_code: Option<i32>,
    log_path: &str,
    tail: &[String],
) -> serde_json::Value {
    serde_json::json!({
        "headline": headline,
        "detail": detail,
        "exitCode": exit_code,
        "exitMeaning": exit_meaning(exit_code),
        "logPath": log_path,
        "logTail": tail,
    })
}

/// Map sidecar exit codes to human text (SIDECAR_CONTRACT.md §5).
fn exit_meaning(code: Option<i32>) -> Option<&'static str> {
    match code {
        Some(0) => Some("clean shutdown (unexpected during startup)"),
        Some(64) => Some("configuration error (refused bind, missing extra, or invalid flags)"),
        Some(65) => Some("port already in use"),
        Some(66) => Some("data-directory error (cannot write WEAVER_DATA_DIR)"),
        Some(_) => Some("unknown failure"),
        None => None,
    }
}

/// Best-effort log path before a `LaunchConfig` exists (config resolution failed).
fn cfg_fallback_log_path() -> String {
    "the Weaver logs directory".to_string()
}
