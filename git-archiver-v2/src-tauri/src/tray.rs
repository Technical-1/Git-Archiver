use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Manager};

/// Set up the system tray icon with a context menu.
///
/// Menu items:
/// - Open Git Archiver (reopens the main window)
/// - Last sync: Never (disabled, updated by scheduler)
/// - Quit (exits the app)
///
/// Left-click (or right-click) on the tray icon shows the context menu.
pub fn setup_tray(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let open_item = MenuItem::with_id(app, "open", "Open Git Archiver", true, None::<&str>)?;
    let last_sync_item =
        MenuItem::with_id(app, "last_sync", "Last sync: Never", false, None::<&str>)?;
    let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
    let sep1 = PredefinedMenuItem::separator(app)?;
    let sep2 = PredefinedMenuItem::separator(app)?;

    let menu = Menu::with_items(
        app,
        &[&open_item, &sep1, &last_sync_item, &sep2, &quit_item],
    )?;

    TrayIconBuilder::with_id("main")
        .icon(
            app.default_window_icon()
                .expect("default window icon must be configured in tauri.conf.json")
                .clone(),
        )
        .tooltip("Git Archiver")
        .menu(&menu)
        .show_menu_on_left_click(true)
        .on_menu_event(move |_app, event| match event.id().as_ref() {
            "open" => show_main_window(_app),
            "quit" => {
                // Use std::process::exit directly because the RunEvent::ExitRequested
                // handler in lib.rs unconditionally prevents exit (to keep the app alive
                // when windows are closed). app.exit(0) triggers that handler and gets
                // blocked, so we bypass it here for an explicit user-initiated quit.
                std::process::exit(0);
            }
            _ => {}
        })
        .build(app)?;

    Ok(())
}

/// Show and focus the main window.
fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }

    // On macOS, show in dock when window is visible
    #[cfg(target_os = "macos")]
    let _ = app.set_activation_policy(tauri::ActivationPolicy::Regular);
}

/// Update the "Last sync" text in the tray context menu.
pub fn update_last_sync_text(app: &AppHandle, text: &str) {
    // Access the tray icon and rebuild the menu item text.
    // Tauri v2 doesn't expose menu items by ID after creation,
    // so we retrieve the tray and set a new menu with updated text.
    if let Some(tray) = app.tray_by_id("main") {
        let open_item =
            MenuItem::with_id(app, "open", "Open Git Archiver", true, None::<&str>).ok();
        let last_sync_item = MenuItem::with_id(app, "last_sync", text, false, None::<&str>).ok();
        let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>).ok();
        let sep1 = PredefinedMenuItem::separator(app).ok();
        let sep2 = PredefinedMenuItem::separator(app).ok();

        if let (Some(o), Some(s1), Some(ls), Some(s2), Some(q)) =
            (open_item, sep1, last_sync_item, sep2, quit_item)
        {
            if let Ok(menu) = Menu::with_items(app, &[&o, &s1, &ls, &s2, &q]) {
                let _ = tray.set_menu(Some(menu));
            }
        }
    }
}
