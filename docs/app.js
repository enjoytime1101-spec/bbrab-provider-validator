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

function runValidation() {
  errors.replaceChildren();
  try {
    const value = JSON.parse(input.value);
    const issues = BBRabPlayground.validateConfiguration(value);
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

document.querySelector("#load-example").addEventListener("click", reset);
document.querySelector("#validate").addEventListener("click", runValidation);
document.querySelector("#export-json").addEventListener("click", () => {
  if (runValidation()) download("provider.config.json", JSON.stringify(lastValid, null, 2) + "\n", "application/json");
});
document.querySelector("#export-markdown").addEventListener("click", () => {
  if (runValidation()) download("provider.config.review.md", BBRabPlayground.markdownReview(lastValid), "text/markdown");
});

reset();
