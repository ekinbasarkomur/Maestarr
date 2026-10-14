# Security policy

Maestarr can add and delete things in your media library and holds API keys for
your other apps. Please treat it like any other admin tool.

## Running it safely

- Keep it on a trusted network. The default compose file publishes it on
  `127.0.0.1` only; put a reverse proxy with TLS, or a VPN such as Tailscale, in
  front of it to reach it from elsewhere.
- Create the account during setup right away — until an account exists, the
  setup endpoints are open.
- API keys for MCP clients can be revoked under *Settings → API & MCP*.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's
[private vulnerability reporting](https://github.com/ekinbasarkomur/Maestarr/security/advisories/new)
with steps to reproduce and the version you run. You will get a reply within a
week; fixes are released as a patch version and credited in the changelog unless
you prefer otherwise.

Only the latest release is supported.
