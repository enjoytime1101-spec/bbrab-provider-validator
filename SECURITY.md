# Security policy

Report suspected vulnerabilities privately to the repository maintainers. Do not include a working credential, private provider response, customer data, or production URL. Use synthetic fixtures and describe the impact and affected version.

## Credential handling

The only supported secret source is a named local environment variable. Configuration rejects common literal-secret keys, and values with control characters are rejected before transport. The value is read immediately before a live run, used only in request headers, and excluded from reports. Because process environments can be inspected by sufficiently privileged local software, run the CLI on a trusted workstation and unset the variable afterward.

Live transport ignores default proxy variables, does not follow redirects, limits response bodies, rechecks DNS policy for every request, and connects to the checked IP while preserving the original TLS hostname verification. Only literal loopback names and addresses are allowed to reach private space, and only in local/test environments.

Redaction is defense in depth, not permission to place secrets in input. If a secret may have entered a file, terminal transcript, CI log, issue, or commit, revoke it with the provider first and then remove the exposed copy.

## Supported versions

Before 1.0, security updates target the latest tagged release and the default branch. Older pre-1.0 releases are not maintained.
