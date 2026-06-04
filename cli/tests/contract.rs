//! Contract test (D-05-08): the CLI's hand-written wire DTOs must stay in sync
//! with the API. This loads `services/api/openapi.json`, synthesizes a minimal
//! sample satisfying each component schema's `required` set (resolving `$ref`,
//! `anyOf`, enums, and arrays), then deserializes it into the corresponding
//! `saferskills::api::dto` struct. A rename, a type change, or a newly-required
//! field the CLI can't satisfy fails here — the honest schema-fidelity gate.
//!
//! No typify/codegen: the CLI is an API consumer, not part of the repo's
//! 8-generator pipeline.

use saferskills::api::dto::{
    CapabilityRow, CatalogItemSummary, CatalogListEnvelope, EvidenceExcerpt, FindingResponse,
    HealthResponse, ItemDetailResponse, ScanReportDetail, ScanRunReportDetail,
};
use serde_json::{json, Value};

/// Load the committed OpenAPI document.
fn openapi() -> Value {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../services/api/openapi.json");
    let raw = std::fs::read_to_string(path).unwrap_or_else(|e| {
        panic!("cannot read {path}: {e} — run from the repo with openapi.json generated")
    });
    serde_json::from_str(&raw).expect("openapi.json is valid JSON")
}

/// All component schemas, keyed by name.
fn schemas(doc: &Value) -> &serde_json::Map<String, Value> {
    doc["components"]["schemas"]
        .as_object()
        .expect("openapi has components.schemas")
}

/// Build a minimal JSON value satisfying `schema`'s `required` set. Recursion is
/// depth-bounded to defend against any (unexpected) cyclic `$ref`.
fn sample(schema: &Value, defs: &serde_json::Map<String, Value>, depth: u8) -> Value {
    if depth > 12 {
        return Value::Null;
    }

    // $ref → resolve into components.schemas.
    if let Some(reff) = schema.get("$ref").and_then(|r| r.as_str()) {
        let name = reff.rsplit('/').next().unwrap_or_default();
        let target = defs
            .get(name)
            .unwrap_or_else(|| panic!("unresolved $ref: {reff}"));
        return sample(target, defs, depth + 1);
    }

    // anyOf / oneOf / allOf → first non-null branch.
    for key in ["anyOf", "oneOf", "allOf"] {
        if let Some(branches) = schema.get(key).and_then(|b| b.as_array()) {
            let chosen = branches
                .iter()
                .find(|b| b.get("type").and_then(|t| t.as_str()) != Some("null"))
                .unwrap_or(&branches[0]);
            return sample(chosen, defs, depth + 1);
        }
    }

    // enum → first allowed value.
    if let Some(values) = schema.get("enum").and_then(|e| e.as_array()) {
        if let Some(first) = values.first() {
            return first.clone();
        }
    }

    match schema.get("type").and_then(|t| t.as_str()) {
        Some("string") => json!("x"),
        Some("integer") => json!(1),
        Some("number") => json!(1.0),
        Some("boolean") => json!(true),
        Some("array") => {
            let item_schema = schema.get("items").cloned().unwrap_or(json!({}));
            json!([sample(&item_schema, defs, depth + 1)])
        }
        Some("object") | None => {
            let mut obj = serde_json::Map::new();
            let required: Vec<String> = schema
                .get("required")
                .and_then(|r| r.as_array())
                .map(|a| {
                    a.iter()
                        .filter_map(|v| v.as_str().map(String::from))
                        .collect()
                })
                .unwrap_or_default();
            if let Some(props) = schema.get("properties").and_then(|p| p.as_object()) {
                for key in &required {
                    if let Some(prop_schema) = props.get(key) {
                        obj.insert(key.clone(), sample(prop_schema, defs, depth + 1));
                    }
                }
            }
            Value::Object(obj)
        }
        Some(other) => panic!("unhandled schema type: {other}"),
    }
}

/// Build a sample for a named component, and (optionally) splice extra
/// optional fields in to exercise nested types the `required` set omits.
fn sample_named(doc: &Value, name: &str, extra: &[(&str, &str)]) -> Value {
    let defs = schemas(doc);
    let schema = defs
        .get(name)
        .unwrap_or_else(|| panic!("missing component schema: {name}"));
    let mut value = sample(schema, defs, 0);
    if let Some(props) = schema["properties"].as_object() {
        for (field, _) in extra {
            if let (Some(obj), Some(prop_schema)) = (value.as_object_mut(), props.get(*field)) {
                obj.insert((*field).to_string(), sample(prop_schema, defs, 0));
            }
        }
    }
    value
}

fn assert_deserializes<T: serde::de::DeserializeOwned>(value: Value, label: &str) {
    if let Err(e) = serde_json::from_value::<T>(value.clone()) {
        panic!("DTO drift for {label}: {e}\nsample was: {value}");
    }
}

#[test]
fn component_schemas_exist() {
    let doc = openapi();
    let defs = schemas(&doc);
    for name in [
        "CatalogItemSummary",
        "CatalogListEnvelope",
        "ItemDetailResponse",
        "ScanReportDetail",
        "FindingResponse",
        "EvidenceExcerpt",
        "ScanRunReportDetail",
        "CapabilityRow",
        "HealthResponse",
    ] {
        assert!(
            defs.contains_key(name),
            "openapi.json is missing schema `{name}` — API drift"
        );
    }
}

#[test]
fn dto_catalog_item_summary_matches() {
    let doc = openapi();
    assert_deserializes::<CatalogItemSummary>(
        sample_named(&doc, "CatalogItemSummary", &[]),
        "CatalogItemSummary",
    );
}

#[test]
fn dto_catalog_list_envelope_matches() {
    let doc = openapi();
    // Exercise the `data` element type too.
    assert_deserializes::<CatalogListEnvelope>(
        sample_named(&doc, "CatalogListEnvelope", &[("data", "")]),
        "CatalogListEnvelope",
    );
}

#[test]
fn dto_item_detail_matches() {
    let doc = openapi();
    // Splice the optional `latest_scan` so its nested ScanReportDetail is checked.
    assert_deserializes::<ItemDetailResponse>(
        sample_named(&doc, "ItemDetailResponse", &[("latest_scan", "")]),
        "ItemDetailResponse",
    );
}

#[test]
fn dto_scan_report_matches() {
    let doc = openapi();
    assert_deserializes::<ScanReportDetail>(
        sample_named(&doc, "ScanReportDetail", &[]),
        "ScanReportDetail",
    );
}

#[test]
fn dto_finding_matches() {
    let doc = openapi();
    // Splice the optional evidence_excerpt so EvidenceExcerpt + EvidenceLine are checked.
    assert_deserializes::<FindingResponse>(
        sample_named(&doc, "FindingResponse", &[("evidence_excerpt", "")]),
        "FindingResponse",
    );
}

#[test]
fn dto_evidence_excerpt_matches() {
    let doc = openapi();
    assert_deserializes::<EvidenceExcerpt>(
        sample_named(&doc, "EvidenceExcerpt", &[]),
        "EvidenceExcerpt",
    );
}

#[test]
fn dto_scan_run_matches() {
    let doc = openapi();
    assert_deserializes::<ScanRunReportDetail>(
        sample_named(&doc, "ScanRunReportDetail", &[("capabilities", "")]),
        "ScanRunReportDetail",
    );
}

#[test]
fn dto_capability_row_matches() {
    let doc = openapi();
    assert_deserializes::<CapabilityRow>(sample_named(&doc, "CapabilityRow", &[]), "CapabilityRow");
}

#[test]
fn dto_health_matches() {
    let doc = openapi();
    assert_deserializes::<HealthResponse>(
        sample_named(&doc, "HealthResponse", &[]),
        "HealthResponse",
    );
}

#[test]
fn list_envelope_uses_data_not_items() {
    // Guard the load-bearing naming contract: paginated lists key on `data`.
    let doc = openapi();
    let env = &schemas(&doc)["CatalogListEnvelope"];
    let props = env["properties"].as_object().unwrap();
    assert!(
        props.contains_key("data"),
        "list envelope must expose `data`"
    );
    assert!(
        !props.contains_key("items"),
        "list envelope must NOT use `items`"
    );
}
