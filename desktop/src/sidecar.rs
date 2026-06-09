//! Sidecar process lifecycle: spawn `weaver serve`, tee its console output,
//! poll `/healthz`, and shut it down without leaving an orphan.
//!
//! Logging note (deliberate): the cockpit owns `runtime.log` through a
//! long-lived rotating file handler (`weaver.services.logging_setup`). A second
//! writer on Windows would break that handler's rotation rename, so the host
//! writes the child's stdout/stderr to a SEPARATE file, `sidecar.console.log`,
//! in the same `logs_dir`. The structured cockpit logs (incl. `runtime.log`)
//! still land there via the child itself — satisfying Sprint N's N4.

use std::collections::VecDeque;
use std::fs::OpenOptions;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use crate::launch_config::LaunchConfig;

const CONSOLE_LOG: &str = "sidecar.console.log";
const RING_CAP: usize = 50;
const POLL_INTERVAL: Duration = Duration::from_millis(50);
const SHUTDOWN_GRACE: Duration = Duration::from_secs(5);
const HEALTH_TIMEOUT: Duration = Duration::from_millis(200);

/// Outcome of a single boot-poll tick.
pub enum Poll {
    Pending,
    Ready,
    /// The child exited during boot, with this process exit code.
    Exited(i32),
}

pub struct Sidecar {
    child: Child,
    pid: u32,
    console: Arc<Mutex<VecDeque<String>>>,
    log_path: PathBuf,
    shut_down: bool,
}

impl Sidecar {
    /// Spawn the cockpit with the desktop security baseline. The session token,
    /// loopback host, random port, docs-off flag, and the shared data dir are
    /// all set here per SIDECAR_CONTRACT.md §2. Provider keys are NEVER set.
    pub fn spawn(cfg: &LaunchConfig) -> Result<Self, String> {
        let _ = std::fs::create_dir_all(&cfg.logs_dir);

        let mut cmd = Command::new(&cfg.weaver_exe);
        cmd.arg("serve")
            .arg("--host")
            .arg("127.0.0.1")
            .arg("--port")
            .arg(cfg.port.to_string())
            .arg("--no-browser")
            .env("WEAVER_ENV", "desktop")
            .env("WEAVER_SESSION_TOKEN", &cfg.token)
            .env("WEAVER_HOST", "127.0.0.1")
            .env("WEAVER_PORT", cfg.port.to_string())
            .env("WEAVER_DOCS", "false")
            .env("WEAVER_DATA_DIR", &cfg.data_dir)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        #[cfg(windows)]
        {
            // CREATE_NO_WINDOW: weaver.exe is a console app; without this a
            // console window flashes when launched from a GUI parent.
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }

        let mut child = cmd.spawn().map_err(|e| {
            format!(
                "could not start the cockpit ({}): {e}",
                cfg.weaver_exe.display()
            )
        })?;
        let pid = child.id();

        let console = Arc::new(Mutex::new(VecDeque::with_capacity(RING_CAP)));
        let log_path = cfg.logs_dir.join(CONSOLE_LOG);
        if let Some(out) = child.stdout.take() {
            spawn_tee(out, console.clone(), log_path.clone(), "out");
        }
        if let Some(err) = child.stderr.take() {
            spawn_tee(err, console.clone(), log_path.clone(), "err");
        }

        Ok(Self {
            child,
            pid,
            console,
            log_path,
            shut_down: false,
        })
    }

    /// One non-blocking boot tick: report early exit, readiness, or pending.
    pub fn poll_once(&mut self, healthz_url: &str) -> Poll {
        if let Ok(Some(status)) = self.child.try_wait() {
            return Poll::Exited(status.code().unwrap_or(-1));
        }
        if health_ok(healthz_url) {
            Poll::Ready
        } else {
            Poll::Pending
        }
    }

    /// Last lines of the sidecar console, oldest first (for the crash screen).
    pub fn console_tail(&self) -> Vec<String> {
        self.console
            .lock()
            .map(|ring| ring.iter().cloned().collect())
            .unwrap_or_default()
    }

    pub fn log_path(&self) -> &PathBuf {
        &self.log_path
    }

    fn already_exited(&mut self) -> bool {
        matches!(self.child.try_wait(), Ok(Some(_)))
    }

    /// Graceful-then-forced shutdown. Idempotent. After this returns the OS
    /// process is gone (N3: no orphan).
    pub fn shutdown(&mut self) {
        if self.shut_down {
            return;
        }
        self.shut_down = true;

        if self.already_exited() {
            return;
        }

        #[cfg(windows)]
        {
            // Graceful: terminate the process tree WITHOUT /F (SIDECAR_CONTRACT.md §7).
            let _ = Command::new("taskkill")
                .args(["/T", "/PID", &self.pid.to_string()])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();

            let deadline = Instant::now() + SHUTDOWN_GRACE;
            while Instant::now() < deadline {
                if self.already_exited() {
                    return;
                }
                std::thread::sleep(Duration::from_millis(100));
            }

            // Forced: kill the tree.
            let _ = Command::new("taskkill")
                .args(["/F", "/T", "/PID", &self.pid.to_string()])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
        }

        #[cfg(not(windows))]
        {
            // Sprint O: send SIGTERM, wait SHUTDOWN_GRACE, then SIGKILL.
            // Std's `kill()` is SIGKILL only; the graceful POSIX path needs
            // libc/nix and is deferred with cross-platform header injection.
            let _ = self.child.kill();
        }

        let _ = self.child.wait();
    }
}

impl Drop for Sidecar {
    fn drop(&mut self) {
        // Safety net: never let the process outlive its handle.
        self.shutdown();
    }
}

/// Read a child stream line-by-line, appending to `sidecar.console.log` and a
/// bounded in-memory ring (the crash-screen tail).
fn spawn_tee(
    stream: impl Read + Send + 'static,
    ring: Arc<Mutex<VecDeque<String>>>,
    log_path: PathBuf,
    tag: &'static str,
) {
    std::thread::spawn(move || {
        let reader = BufReader::new(stream);
        for line in reader.lines() {
            let Ok(line) = line else { break };
            let stamped = format!("[{tag}] {line}");

            if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(&log_path) {
                let _ = writeln!(file, "{stamped}");
            }

            if let Ok(mut ring) = ring.lock() {
                if ring.len() == RING_CAP {
                    ring.pop_front();
                }
                ring.push_back(stamped);
            }
        }
    });
}

/// `GET /healthz` → 200 with `{"ok": true}`. Any error/timeout is "not ready".
fn health_ok(url: &str) -> bool {
    match ureq::get(url).timeout(HEALTH_TIMEOUT).call() {
        Ok(resp) if resp.status() == 200 => match resp.into_json::<serde_json::Value>() {
            Ok(body) => body.get("ok").and_then(serde_json::Value::as_bool) == Some(true),
            Err(_) => false,
        },
        _ => false,
    }
}
