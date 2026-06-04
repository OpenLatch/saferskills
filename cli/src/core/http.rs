//! HTTP client for the SaferSkills public API (D-05-08, D-05-09).
//!
//! Reads are unauthenticated + uncapped — no API key, no Turnstile, no rate
//! limit. The client is rustls-only (the `cli-rustls` CI lane greps the dep
//! tree to keep openssl-sys / native-tls out) with an explicit 10s timeout.

use serde::de::DeserializeOwned;
use serde::Serialize;

use crate::core::error::{
    SsError, ERR_API_DECODE, ERR_API_STATUS, ERR_ITEM_NOT_FOUND, ERR_NETWORK, ERR_RATE_LIMITED,
};

/// A thin typed wrapper over `reqwest` for the SaferSkills API.
#[derive(Debug, Clone)]
pub struct ApiClient {
    base: String,
    http: reqwest::Client,
}

impl ApiClient {
    /// Build a client against `base` (already-resolved origin, no trailing
    /// slash). rustls TLS, 10s timeout, identifying user-agent.
    pub fn new(base: String) -> Result<Self, SsError> {
        let http = reqwest::Client::builder()
            .use_rustls_tls()
            .timeout(std::time::Duration::from_secs(10))
            .user_agent(concat!("saferskills/", env!("CARGO_PKG_VERSION")))
            .build()
            .map_err(|e| SsError::new(ERR_NETWORK, format!("Failed to build HTTP client: {e}")))?;
        Ok(Self { base, http })
    }

    /// The resolved API base origin.
    pub fn base(&self) -> &str {
        &self.base
    }

    /// `GET {base}{path}?<query>` → deserialize the JSON body into `T`.
    ///
    /// Error mapping (D-05-09): 404 → `SS-E-1200` (not-found, exit 3); 429 →
    /// `SS-E-1102` (rate-limit, exit 6 — shouldn't occur on reads); connect /
    /// timeout → `SS-E-1100` (network, exit 6); other non-2xx → `SS-E-1101`;
    /// body decode failure → `SS-E-1103`.
    pub async fn get<T: DeserializeOwned>(
        &self,
        path: &str,
        query: &[(&str, &str)],
    ) -> Result<T, SsError> {
        let url = format!("{}{}", self.base, path);
        let resp = self
            .http
            .get(&url)
            .query(query)
            .send()
            .await
            .map_err(|e| self.transport_error(e))?;

        let status = resp.status();
        if !status.is_success() {
            return Err(self.status_error(status));
        }

        resp.json::<T>().await.map_err(|e| {
            SsError::new(
                ERR_API_DECODE,
                format!("Failed to decode API response: {e}"),
            )
            .with_suggestion(
                "This usually means the CLI is out of date — try `npx saferskills@latest`.",
            )
        })
    }

    /// `GET {base}{path}` → raw response bytes (e.g. a stored-snapshot `.zip`).
    /// Same error mapping as [`ApiClient::get`].
    pub async fn get_bytes(&self, path: &str) -> Result<Vec<u8>, SsError> {
        let url = format!("{}{}", self.base, path);
        let resp = self
            .http
            .get(&url)
            .send()
            .await
            .map_err(|e| self.transport_error(e))?;
        let status = resp.status();
        if !status.is_success() {
            return Err(self.status_error(status));
        }
        resp.bytes().await.map(|b| b.to_vec()).map_err(|e| {
            SsError::new(
                ERR_API_DECODE,
                format!("Failed to read response bytes: {e}"),
            )
        })
    }

    /// `POST {base}{path}` with a JSON body; treats any 2xx (incl. 204) as ok.
    /// Used by opt-in install telemetry (the caller swallows errors — fail-open).
    pub async fn post_json<B: Serialize>(&self, path: &str, body: &B) -> Result<(), SsError> {
        let url = format!("{}{}", self.base, path);
        let resp = self
            .http
            .post(&url)
            .json(body)
            .send()
            .await
            .map_err(|e| self.transport_error(e))?;
        let status = resp.status();
        if !status.is_success() {
            return Err(self.status_error(status));
        }
        Ok(())
    }

    fn transport_error(&self, e: reqwest::Error) -> SsError {
        let detail = if e.is_timeout() {
            "request timed out"
        } else if e.is_connect() {
            "could not connect"
        } else {
            "network error"
        };
        SsError::new(ERR_NETWORK, format!("{detail} talking to {}", self.base)).with_suggestion(
            "Check your connection, or set SAFERSKILLS_API_URL to override the API origin.",
        )
    }

    fn status_error(&self, status: reqwest::StatusCode) -> SsError {
        match status.as_u16() {
            404 => SsError::new(ERR_ITEM_NOT_FOUND, "Not found in the catalog."),
            429 => SsError::new(ERR_RATE_LIMITED, "Rate limited by the API — retry shortly."),
            code => SsError::new(ERR_API_STATUS, format!("API returned HTTP {code}.")),
        }
    }
}
