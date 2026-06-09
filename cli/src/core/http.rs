//! HTTP client for the SaferSkills public API (D-05-08, D-05-09).
//!
//! Reads are unauthenticated + uncapped — no API key, no Turnstile, no rate
//! limit. The client is rustls-only (the `cli-rustls` CI lane greps the dep
//! tree to keep openssl-sys / native-tls out) with an explicit 10s timeout.

use serde::de::DeserializeOwned;
use serde::Serialize;

use crate::core::error::{
    SsError, ERR_API_DECODE, ERR_API_STATUS, ERR_ITEM_NOT_FOUND, ERR_NETWORK, ERR_RATE_LIMITED,
    ERR_SCAN_SUBMIT,
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

    /// `GET {base}{path}` with request headers → raw body bytes + the requested
    /// response-header values (in `want` order; `None` when a header is absent).
    /// The agent-scan pack fetch needs the body PLUS `X-Pack-Key-Id` /
    /// `X-Pack-Signature` headers. 403 → gate/token error; 410 → pack-gone.
    pub async fn get_bytes_with_headers(
        &self,
        path: &str,
        headers: &[(&str, &str)],
        want: &[&str],
    ) -> Result<(Vec<u8>, Vec<Option<String>>), SsError> {
        let url = format!("{}{}", self.base, path);
        let mut req = self.http.get(&url);
        for (k, v) in headers {
            req = req.header(*k, *v);
        }
        let resp = req.send().await.map_err(|e| self.transport_error(e))?;
        let status = resp.status();
        if !status.is_success() {
            return Err(self.agent_status_error(status));
        }
        let picked: Vec<Option<String>> = want
            .iter()
            .map(|h| {
                resp.headers()
                    .get(*h)
                    .and_then(|v| v.to_str().ok())
                    .map(String::from)
            })
            .collect();
        let body = resp
            .bytes()
            .await
            .map(|b| b.to_vec())
            .map_err(|e| self.decode_error(e))?;
        Ok((body, picked))
    }

    /// `POST {base}{path}` with a raw text body + `content_type` + extra headers →
    /// deserialize the 2xx body into `T`. Same 403 gate-error mapping as
    /// [`post_json_for`]. Used by `--submit-blob` (a `text/plain` paste-back body the
    /// server decodes).
    pub async fn post_text_for<T: DeserializeOwned>(
        &self,
        path: &str,
        body: String,
        content_type: &str,
        headers: &[(&str, &str)],
    ) -> Result<T, SsError> {
        let url = format!("{}{}", self.base, path);
        let mut req = self
            .http
            .post(&url)
            .header("content-type", content_type)
            .body(body);
        for (k, v) in headers {
            req = req.header(*k, *v);
        }
        let resp = req.send().await.map_err(|e| self.transport_error(e))?;
        self.read_submit_body(resp).await
    }

    /// `POST {base}{path}` with a JSON body; treats any 2xx (incl. 204) as ok.
    /// Used by anonymous install telemetry (the caller swallows errors — fail-open).
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

    /// `POST {base}{path}` with extra headers + no body; treats any 2xx (incl. 204)
    /// as ok. Used by the token-authed agent-scan abort (best-effort cancel).
    pub async fn post_for_status(
        &self,
        path: &str,
        headers: &[(&str, &str)],
    ) -> Result<(), SsError> {
        let url = format!("{}{}", self.base, path);
        let mut req = self.http.post(&url);
        for (k, v) in headers {
            req = req.header(*k, *v);
        }
        let resp = req.send().await.map_err(|e| self.transport_error(e))?;
        let status = resp.status();
        if !status.is_success() {
            return Err(self.agent_status_error(status));
        }
        Ok(())
    }

    /// `GET {base}{path}?<query>` with extra request headers → deserialize `T`.
    pub async fn get_with_headers<T: DeserializeOwned>(
        &self,
        path: &str,
        query: &[(&str, &str)],
        headers: &[(&str, &str)],
    ) -> Result<T, SsError> {
        let url = format!("{}{}", self.base, path);
        let mut req = self.http.get(&url).query(query);
        for (k, v) in headers {
            req = req.header(*k, *v);
        }
        let resp = req.send().await.map_err(|e| self.transport_error(e))?;
        let status = resp.status();
        if !status.is_success() {
            return Err(self.status_error(status));
        }
        resp.json::<T>().await.map_err(|e| self.decode_error(e))
    }

    /// `POST {base}{path}` with a JSON body + extra headers → deserialize the 2xx
    /// JSON body into `T` (unlike the fire-and-forget [`ApiClient::post_json`],
    /// scan-submit returns a body). A 403 maps to a distinct gate-failed error
    /// that surfaces the `{"error": …}` reason (PoW / captcha / rate-limit).
    pub async fn post_json_for<B: Serialize, T: DeserializeOwned>(
        &self,
        path: &str,
        body: &B,
        headers: &[(&str, &str)],
    ) -> Result<T, SsError> {
        let url = format!("{}{}", self.base, path);
        let mut req = self.http.post(&url).json(body);
        for (k, v) in headers {
            req = req.header(*k, *v);
        }
        let resp = req.send().await.map_err(|e| self.transport_error(e))?;
        self.read_submit_body(resp).await
    }

    /// `POST {base}{path}` with a multipart form + extra headers → deserialize the
    /// 2xx body into `T`. Same 403 gate-error mapping as [`post_json_for`].
    pub async fn post_multipart<T: DeserializeOwned>(
        &self,
        path: &str,
        form: reqwest::multipart::Form,
        headers: &[(&str, &str)],
    ) -> Result<T, SsError> {
        let url = format!("{}{}", self.base, path);
        let mut req = self.http.post(&url).multipart(form);
        for (k, v) in headers {
            req = req.header(*k, *v);
        }
        let resp = req.send().await.map_err(|e| self.transport_error(e))?;
        self.read_submit_body(resp).await
    }

    /// Shared submit-response reader: 2xx → deserialize `T`; 403 → gate-failed
    /// error parsing the `{"error": …}` reason; other non-2xx → `status_error`.
    async fn read_submit_body<T: DeserializeOwned>(
        &self,
        resp: reqwest::Response,
    ) -> Result<T, SsError> {
        let status = resp.status();
        if status.as_u16() == 403 {
            let reason = resp
                .json::<serde_json::Value>()
                .await
                .ok()
                .and_then(|v| v.get("error").and_then(|e| e.as_str()).map(String::from))
                .unwrap_or_else(|| "forbidden".to_string());
            return Err(SsError::new(
                ERR_SCAN_SUBMIT,
                format!("The scan was rejected by the API gate ({reason})."),
            )
            .with_suggestion(
                "If this persists, the human-verification gate may require the web UI at \
                 https://saferskills.ai/scan.",
            ));
        }
        if !status.is_success() {
            return Err(self.status_error(status));
        }
        resp.json::<T>().await.map_err(|e| self.decode_error(e))
    }

    fn decode_error(&self, e: reqwest::Error) -> SsError {
        SsError::new(
            ERR_API_DECODE,
            format!("Failed to decode API response: {e}"),
        )
        .with_suggestion(
            "This usually means the CLI is out of date — try `npx saferskills@latest`.",
        )
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

    /// Status mapping for the agent-scan surface, where 403 (bad/expired run token)
    /// and 410 (pack already spent) are meaningful and must not collapse into a
    /// generic network error.
    fn agent_status_error(&self, status: reqwest::StatusCode) -> SsError {
        match status.as_u16() {
            403 => SsError::new(
                ERR_SCAN_SUBMIT,
                "The agent-scan run token was rejected (bad, expired, or already spent).",
            ),
            404 => SsError::new(ERR_ITEM_NOT_FOUND, "Agent-scan run not found."),
            410 => SsError::new(
                ERR_API_STATUS,
                "The assessment pack is no longer available (the run already submitted).",
            ),
            429 => SsError::new(ERR_RATE_LIMITED, "Rate limited by the API — retry shortly."),
            code => SsError::new(ERR_API_STATUS, format!("API returned HTTP {code}.")),
        }
    }
}
