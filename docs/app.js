"use strict";

const example = {
  schema_version: 1,
  provider: {
    name: "Example staging provider",
    base_url: "https://api.example.invalid/v1",
    environment: "staging",
    model: "example-chat"
  },
  credential: {
    env: "EXAMPLE_STAGING_API_KEY",
    environment: "staging",
    auth: "bearer"
  },
  isolation: {
    allowed_hosts: ["api.example.invalid"],
    response_environment_header: "X-Provider-Environment"
  },
  probe: {
    max_tokens: 4,
    normal_request_max_tokens: 128
  }
};

const input = document.querySelector("#config");
const status = document.querySelector("#status");
const errors = document.querySelector("#errors");
const preview = document.querySelector("#preview");
let lastValid = null;

function reset() {
  input.value = JSON.stringify(example, null, 2);
  status.className = "status idle";
  status.textContent = "Not checked";
  errors.replaceChildren();
  preview.textContent = "Run validation to produce an export preview.";
  lastValid = null;
}

function findSecretKeys(value, path = "config", found = []) {
  const forbidden = new Set(["api_key", "apikey", "secret", "token", "access_token", "password", "authorization", "cookie", "set_cookie"]);
  if (Array.isArray(value)) value.forEach((item, index) => findSecretKeys(item, `${path}[${index}]`, found));
  else if (value && typeof value === "object") {
    Object.entries(value).forEach(([key, child]) => {
      if (forbidden.has(key.toLowerCase().replaceAll("-", "_"))) found.push(`${path}.${key} is forbidden`);
      findSecretKeys(child, `${path}.${key}`, found);
    });
  }
  return found;
}

function validate(value) {
  const issues = findSecretKeys(value);
  if (value.schema_version !== 1) issues.push("schema_version must be 1");
  const provider = value.provider;
  if (!provider || typeof provider !== "object") return [...issues, "provider must be an object"];
  ["name", "base_url", "environment", "model"].forEach(key => {
    if (typeof provider[key] !== "string" || !provider[key].trim()) issues.push(`provider.${key} must be a non-empty string`);
  });
  let host = "";
  try {
    const url = new URL(provider.base_url);
    host = url.hostname;
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error();
  } catch { issues.push("provider.base_url must be an HTTP(S) URL without credentials, query, or fragment"); }
  if (!["local", "test", "staging", "production"].includes(provider.environment)) issues.push("provider.environment is invalid");
  const credential = value.credential;
  if (!credential || typeof credential !== "object") issues.push("credential must be an object");
  else {
    if (!/^[A-Z_][A-Z0-9_]{1,127}$/.test(credential.env || "")) issues.push("credential.env must be an uppercase environment-variable name");
    if (credential.environment !== provider.environment) issues.push("credential.environment must match provider.environment");
  }
  const allowed = value.isolation?.allowed_hosts;
  if (!Array.isArray(allowed) || !allowed.length) issues.push("isolation.allowed_hosts must be a non-empty list");
  else if (host && !allowed.map(item => String(item).toLowerCase()).includes(host.toLowerCase())) issues.push("provider host is outside isolation.allowed_hosts");
  const max = value.probe?.max_tokens ?? 4;
  const normal = value.probe?.normal_request_max_tokens ?? 128;
  if (!Number.isInteger(max) || max < 1 || max > 16) issues.push("probe.max_tokens must be an integer from 1 to 16");
  if (!Number.isInteger(normal) || normal < 1 || max > normal) issues.push("probe budget cannot exceed the normal request budget");
  return issues;
}

function runValidation() {
  errors.replaceChildren();
  try {
    const value = JSON.parse(input.value);
    const issues = validate(value);
    issues.forEach(issue => {
      const item = document.createElement("li");
      item.textContent = issue;
      errors.append(item);
    });
    if (issues.length) {
      status.className = "status fail";
      status.textContent = `${issues.length} issue${issues.length === 1 ? "" : "s"}`;
      preview.textContent = "Fix the listed issues before export.";
      lastValid = null;
      return false;
    }
    status.className = "status pass";
    status.textContent = "Shape passed";
    lastValid = value;
    preview.textContent = JSON.stringify(value, null, 2);
    return true;
  } catch (error) {
    const item = document.createElement("li");
    item.textContent = `Invalid JSON: ${error.message}`;
    errors.append(item);
    status.className = "status fail";
    status.textContent = "Invalid JSON";
    preview.textContent = "Fix the JSON syntax before export.";
    lastValid = null;
    return false;
  }
}

function download(name, content, type) {
  const blob = new Blob([content], {type});
  const anchor = document.createElement("a");
  anchor.href = URL.createObjectURL(blob);
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(anchor.href);
}

function markdown(value) {
  return [
    "# Provider configuration review",
    "",
    "- Shape: **passed**",
    `- Provider: ${value.provider.name}`,
    `- Environment: \`${value.provider.environment}\``,
    `- Host: \`${new URL(value.provider.base_url).hostname}\``,
    `- Model: \`${value.provider.model}\``,
    `- Credential reference: \`${value.credential.env}\``,
    "",
    "> This browser-only review does not validate provider responses. Run the Python CLI with an offline fixture.",
    ""
  ].join("\n");
}

document.querySelector("#load-example").addEventListener("click", reset);
document.querySelector("#validate").addEventListener("click", runValidation);
document.querySelector("#export-json").addEventListener("click", () => {
  if (runValidation()) download("provider.config.json", JSON.stringify(lastValid, null, 2) + "\n", "application/json");
});
document.querySelector("#export-markdown").addEventListener("click", () => {
  if (runValidation()) download("provider.config.review.md", markdown(lastValid), "text/markdown");
});

reset();
