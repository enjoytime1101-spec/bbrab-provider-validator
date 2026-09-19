(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.BBRabPlayground = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const SECRET_KEYS = new Set([
    "api_key", "apikey", "secret", "token", "access_token", "password",
    "authorization", "proxy_authorization", "cookie", "set_cookie"
  ]);
  const FORBIDDEN_AUTH_HEADERS = new Set([
    "host", "content-length", "connection", "transfer-encoding",
    "proxy-authorization", "cookie", "set-cookie"
  ]);
  const SECRET_VALUE_PATTERNS = [
    /\bbearer\s+[A-Za-z0-9._~+/=-]{6,}/i,
    /\bsk-[A-Za-z0-9_-]{8,}\b/,
    /[?&](?:access_token|api_key|token|key|sig|signature|auth|session|cookie)=/i,
    /\b(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*[:=]/i,
    /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/
  ];

  function findCredentialMaterial(value, path = "config", found = []) {
    if (Array.isArray(value)) {
      value.forEach((item, index) => findCredentialMaterial(item, `${path}[${index}]`, found));
    } else if (value && typeof value === "object") {
      Object.entries(value).forEach(([key, child]) => {
        if (SECRET_KEYS.has(key.toLowerCase().replaceAll("-", "_"))) {
          found.push("configuration contains a forbidden credential field");
        }
        findCredentialMaterial(child, `${path}.${key}`, found);
      });
    } else if (typeof value === "string" && SECRET_VALUE_PATTERNS.some(pattern => pattern.test(value))) {
      found.push("configuration contains forbidden credential material");
    }
    return found;
  }

  function hasControlCharacters(value) {
    return typeof value === "string" && /[\u0000-\u001f\u007f]/.test(value);
  }

  function validateConfiguration(value) {
    const issues = findCredentialMaterial(value);
    if (!value || typeof value !== "object" || Array.isArray(value)) return [...issues, "configuration must be an object"];
    if (value.schema_version !== 1 || typeof value.schema_version !== "number") issues.push("schema_version must be 1");
    const provider = value.provider;
    if (!provider || typeof provider !== "object" || Array.isArray(provider)) return [...issues, "provider must be an object"];
    ["name", "base_url", "environment", "model"].forEach(key => {
      if (typeof provider[key] !== "string" || !provider[key].trim()) issues.push(`provider.${key} must be a non-empty string`);
      else if (hasControlCharacters(provider[key])) issues.push(`provider.${key} cannot contain control characters`);
    });
    let host = "";
    try {
      const url = new URL(provider.base_url);
      host = url.hostname;
      if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error();
    } catch {
      issues.push("provider.base_url must be an HTTP(S) URL without credentials, query, or fragment");
    }
    if (!["local", "test", "staging", "production"].includes(provider.environment)) issues.push("provider.environment is invalid");
    const credential = value.credential;
    if (!credential || typeof credential !== "object" || Array.isArray(credential)) issues.push("credential must be an object");
    else {
      if (!/^[A-Z_][A-Z0-9_]{1,127}$/.test(credential.env || "")) issues.push("credential.env must be an uppercase environment-variable name");
      if (credential.environment !== provider.environment) issues.push("credential.environment must match provider.environment");
      const auth = credential.auth || "bearer";
      if (!["bearer", "header"].includes(auth)) issues.push("credential.auth must be bearer or header");
      if (auth === "header") {
        if (typeof credential.header !== "string" || !/^[A-Za-z0-9-]{1,80}$/.test(credential.header)) {
          issues.push("credential.header must be a valid header name");
        } else if (FORBIDDEN_AUTH_HEADERS.has(credential.header.toLowerCase())) {
          issues.push("credential.header cannot be a routing, framing, proxy, or cookie header");
        }
      }
    }
    const allowed = value.isolation?.allowed_hosts;
    if (!Array.isArray(allowed) || !allowed.length || allowed.some(item => typeof item !== "string" || !item)) {
      issues.push("isolation.allowed_hosts must be a non-empty string list");
    } else if (host && !allowed.map(item => item.toLowerCase()).includes(host.toLowerCase())) {
      issues.push("provider host is outside isolation.allowed_hosts");
    }
    const environmentHeader = value.isolation?.response_environment_header || "";
    if (environmentHeader && !/^[A-Za-z0-9-]{1,80}$/.test(environmentHeader)) issues.push("isolation.response_environment_header is invalid");
    const max = value.probe?.max_tokens ?? 4;
    const normal = value.probe?.normal_request_max_tokens ?? 128;
    if (!Number.isInteger(max) || max < 1 || max > 16) issues.push("probe.max_tokens must be an integer from 1 to 16");
    if (!Number.isInteger(normal) || normal < 1) issues.push("probe.normal_request_max_tokens must be a positive integer");
    else if (max > normal) issues.push("probe budget cannot exceed the normal request budget");
    return [...new Set(issues)];
  }

  function markdownEscape(value) {
    return String(value)
      .replace(/[\u0000-\u001f\u007f]+/g, " ")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll("`", "&grave;")
      .replaceAll("|", "&vert;")
      .replaceAll("\\", "\\\\")
      .replace(/([\[\](){}*_~#!+.!-])/g, "\\$1");
  }

  function markdownReview(value) {
    return [
      "# Provider configuration review",
      "",
      "- Shape: **passed**",
      `- Provider: ${markdownEscape(value.provider.name)}`,
      `- Environment: ${markdownEscape(value.provider.environment)}`,
      `- Host: ${markdownEscape(new URL(value.provider.base_url).hostname)}`,
      `- Model: ${markdownEscape(value.provider.model)}`,
      `- Credential reference: ${markdownEscape(value.credential.env)}`,
      "",
      "> This browser-only review does not validate provider responses. Run the Python CLI with an offline fixture.",
      ""
    ].join("\n");
  }

  return {findCredentialMaterial, markdownEscape, markdownReview, validateConfiguration};
}));
