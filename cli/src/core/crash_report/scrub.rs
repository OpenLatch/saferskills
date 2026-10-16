//! Fail-closed projection of SDK exceptions. Never transmit panic/error text:
//! it can contain arbitrary submitted content, URLs, tokens or local paths.
//! Native addresses and debug IDs are retained for symbolication.
use posthog_rs::Event;
use serde_json::{json, Value};

pub fn scrub_event(event: Event) -> Option<Event> {
    if event.event_name() != "$exception" {
        return None;
    }
    let properties = event.properties();
    let mut exceptions = properties.get("$exception_list")?.as_array()?.clone();
    for exception in &mut exceptions {
        let object = exception.as_object_mut()?;
        object.retain(|key, _| matches!(key.as_str(), "type" | "value" | "stacktrace"));
        object.insert("type".into(), json!("RustPanic"));
        object.insert("value".into(), json!("Panic message omitted for privacy"));
        object.insert(
            "mechanism".into(),
            json!({"type": "panic", "handled": false, "synthetic": false}),
        );
        if let Some(stack) = object.get_mut("stacktrace") {
            let stack = stack.as_object_mut()?;
            stack.retain(|key, _| matches!(key.as_str(), "type" | "frames"));
            for frame in stack.get_mut("frames")?.as_array_mut()? {
                let frame = frame.as_object_mut()?;
                frame.retain(|key, _| {
                    matches!(
                        key.as_str(),
                        "filename"
                            | "function"
                            | "lineno"
                            | "colno"
                            | "in_app"
                            | "platform"
                            | "lang"
                            | "synthetic"
                            | "instruction_addr"
                            | "symbol_addr"
                            | "image_addr"
                            | "inline"
                            | "client_resolved"
                    )
                });
                if let Some(filename) = frame.get_mut("filename") {
                    *filename = json!(source_path(filename.as_str()?));
                }
            }
        }
    }
    // Rebuild rather than mutate: this drops SDK/user context added in future versions.
    let mut clean = Event::new_anon("$exception");
    clean.insert_prop("$exception_list", exceptions).ok()?;
    clean.insert_prop("$exception_level", "error").ok()?;
    clean.insert_prop("$geoip_disable", true).ok()?;
    // SDK identity is compile-time metadata needed by PostHog integration detection.
    for key in ["$lib", "$lib_version"] {
        if let Some(value) = properties.get(key).and_then(Value::as_str) {
            clean.insert_prop(key, value).ok()?;
        }
    }
    if let Some(images) = properties.get("$debug_images") {
        let mut images = images.as_array()?.clone();
        for image in &mut images {
            let image = image.as_object_mut()?;
            image.retain(|key, _| {
                matches!(
                    key.as_str(),
                    "type"
                        | "debug_id"
                        | "code_id"
                        | "image_addr"
                        | "image_vmaddr"
                        | "image_size"
                        | "arch"
                )
            });
        }
        clean.insert_prop("$debug_images", images).ok()?;
    }
    if let Some(file) = properties.get("$exception_panic_file") {
        clean
            .insert_prop("$exception_panic_file", source_path(file.as_str()?))
            .ok()?;
    }
    for key in ["$exception_panic_line", "$exception_panic_column"] {
        if let Some(value) = properties.get(key).and_then(Value::as_u64) {
            clean.insert_prop(key, value).ok()?;
        }
    }
    Some(clean)
}

/// Only crate-relative Rust source paths survive. Drop absolute machine paths,
/// dependency paths, filenames outside the crate, and path traversal.
fn source_path(path: &str) -> String {
    let path = path.replace('\\', "/");
    if path.starts_with("src/")
        && path.ends_with(".rs")
        && !path.contains("..")
        && path
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"/_-.".contains(&b))
    {
        path
    } else {
        "[source path omitted]".to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn removes_arbitrary_context_messages_and_machine_paths_preserving_symbols() {
        let mut event = Event::new("$exception", "private-user");
        event.insert_prop("token", "private-token").unwrap();
        event.insert_prop("$exception_list", json!([{"type":"panic", "value":"secret https://repo/private", "stacktrace":{"type":"raw", "frames":[{"filename":"C:\\Users\\private\\main.rs", "function":"saferskills::run", "instruction_addr":"0x42", "image_addr":"0x40", "client_resolved":true, "vars":{"token":"private-token"}}]}}])).unwrap();
        event
            .insert_prop(
                "$debug_images",
                json!([{"debug_id":"abc", "image_addr":"0x40", "image_vmaddr":"0x1000", "code_file":"/home/private/bin"}]),
            )
            .unwrap();
        let output = serde_json::to_string(&scrub_event(event).unwrap()).unwrap();
        assert!(!output.contains("private"));
        assert!(!output.contains("secret"));
        assert!(output.contains("0x42"));
        assert!(output.contains("abc"));
        let payload: Value = serde_json::from_str(&output).unwrap();
        assert_eq!(
            payload["properties"]["$debug_images"][0]["image_vmaddr"],
            "0x1000"
        );
        assert_eq!(
            payload["properties"]["$exception_list"][0]["stacktrace"]["frames"][0]
                ["client_resolved"],
            true
        );
        assert!(output.contains("saferskills::run"));
    }
    #[test]
    fn malformed_or_non_exception_events_are_dropped() {
        assert!(scrub_event(Event::new_anon("$exception")).is_none());
        assert!(scrub_event(Event::new_anon("unreviewed_event")).is_none());
    }
    #[test]
    fn source_paths_are_restricted_to_crate_rust_sources() {
        assert_eq!(source_path("src/main.rs"), "src/main.rs");
        assert_eq!(source_path(r"src\main.rs"), "src/main.rs");
        for path in [
            "/home/alice/src/main.rs",
            "src/../private.rs",
            "https://host/src/file.rs",
            "src/token?private.rs",
        ] {
            assert_eq!(source_path(path), "[source path omitted]");
        }
    }
}
