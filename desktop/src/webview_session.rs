//! Attaches `X-Weaver-Session` to every request the cockpit WebView makes.
//!
//! The cockpit gates `/ui` and all API/HTMX routes behind the session header
//! (only `/healthz`, `/health`, `/version`, `/static` are public). The UI uses
//! BOTH full-page `<a href="/ui/...">` navigations AND HTMX XHR, so the header
//! must be added at the network layer — a JS shim cannot add a header to a
//! top-level navigation request.
//!
//! Windows (Sprint N alpha target): WebView2 `WebResourceRequested` adds the
//! header to every request context. macOS (WKWebView) and Linux (WebKitGTK)
//! are deferred to Sprint O — see the no-op below.

use tauri::WebviewWindow;

#[cfg(windows)]
pub fn install_session_header(window: &WebviewWindow, token: &str) {
    let token = token.to_string();

    // `with_webview` hands us the raw platform WebView on its own thread.
    let result = window.with_webview(move |webview| {
        // UNVERIFIED: this block compiles only once `webview2-com`/`windows`
        // are pinned to the versions Tauri resolves (see Cargo.toml note).
        // `PlatformWebview::controller()` returns the `ICoreWebView2Controller`
        // from THAT webview2-com version; a mismatch is the usual first-build
        // error here.
        use webview2_com::Microsoft::Web::WebView2::Win32::{
            ICoreWebView2WebResourceRequestedEventArgs, COREWEBVIEW2_WEB_RESOURCE_CONTEXT_ALL,
        };
        use webview2_com::WebResourceRequestedEventHandler;
        use windows::core::{w, HSTRING};
        use windows::Win32::System::WinRT::EventRegistrationToken;

        unsafe {
            let core = match webview.controller().CoreWebView2() {
                Ok(core) => core,
                Err(_) => return,
            };

            // Intercept every resource context (document, XHR, image, script…).
            if core
                .AddWebResourceRequestedFilter(w!("*"), COREWEBVIEW2_WEB_RESOURCE_CONTEXT_ALL)
                .is_err()
            {
                return;
            }

            let header_name = HSTRING::from("X-Weaver-Session");
            let header_value = HSTRING::from(token.as_str());

            let handler = WebResourceRequestedEventHandler::create(Box::new(
                move |_sender, args: Option<ICoreWebView2WebResourceRequestedEventArgs>| {
                    if let Some(args) = args {
                        let request = args.Request()?;
                        let headers = request.Headers()?;
                        // Overwrites if present; sets if absent.
                        headers.SetHeader(&header_name, &header_value)?;
                    }
                    Ok(())
                },
            ));

            let mut token_reg = EventRegistrationToken::default();
            let _ = core.add_WebResourceRequested(&handler, &mut token_reg);
        }
    });

    if let Err(e) = result {
        eprintln!("[weaver-desktop] could not install session-header interceptor: {e}");
    }
}

#[cfg(not(windows))]
pub fn install_session_header(_window: &WebviewWindow, _token: &str) {
    // Sprint O portability: implement request-header injection for WKWebView
    // (macOS) and WebKitGTK (Linux). Until then, gated requests on those
    // platforms would 401 — the alpha targets Windows/WebView2 only.
    eprintln!(
        "[weaver-desktop] session-header injection is Windows-only in the Sprint N alpha; \
         this platform is unsupported until Sprint O."
    );
}
