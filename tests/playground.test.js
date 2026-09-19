"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {markdownReview, validateConfiguration} = require("../docs/playground-core.js");

function sample() {
  return {
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
    probe: {max_tokens: 4, normal_request_max_tokens: 128}
  };
}

test("the sample configuration passes", () => {
  assert.deepEqual(validateConfiguration(sample()), []);
});

test("secret fields and secret-shaped values are rejected", () => {
  const withField = sample();
  withField.credential.api_key = "literal";
  assert.ok(validateConfiguration(withField).some(issue => issue.includes("credential field")));

  const withValue = sample();
  withValue.provider.name = "Authorization: Bearer syntheticvalue";
  assert.ok(validateConfiguration(withValue).some(issue => issue.includes("credential material")));

  const withTokenUrl = sample();
  withTokenUrl.provider.name = "https://example.test/?access_token=synthetic";
  assert.ok(validateConfiguration(withTokenUrl).some(issue => issue.includes("credential material")));
});

test("custom auth rejects routing, framing, proxy, and cookie headers", () => {
  for (const header of ["Host", "Content-Length", "Connection", "Transfer-Encoding", "Proxy-Authorization", "Cookie", "Set-Cookie"]) {
    const value = sample();
    value.credential = {...value.credential, auth: "header", header};
    assert.ok(
      validateConfiguration(value).some(issue => issue.includes("routing, framing, proxy, or cookie")),
      header
    );
  }
});

test("Markdown export escapes HTML, backticks, newlines, and table delimiters", () => {
  const value = sample();
  value.provider.name = "<script>alert(1)</script> `code`\n# heading | cell";
  value.provider.model = "model|`unsafe`";
  const output = markdownReview(value);
  assert.doesNotMatch(output, /<script>/);
  assert.doesNotMatch(output, /`code`/);
  assert.doesNotMatch(output, /\n# heading/);
  assert.doesNotMatch(output, /model\|/);
  assert.match(output, /&lt;script&gt;/);
  assert.match(output, /&grave;code&grave;/);
  assert.match(output, /&vert;/);
});
