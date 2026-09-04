# Securing Credentials with the OS Keyring

This guide explains how to keep the sensitive credentials — the **AVI password**
and the **Kentik API token** — out of `telegraf.conf` and your `.env` file by
using Telegraf's **OS secret store** plugin (`secretstores.os`), which stores
secrets in the operating system's native keyring:

| OS | Backend used by `secretstores.os` |
|----|-----------------------------------|
| Linux | Kernel keyring (`user` scope) |
| macOS | Keychain |
| Windows | Credential Manager |

> Requires Telegraf v1.25.0 or newer.

## Scope: only passwords and API keys

Only two values in this integration are actually sensitive — everything else
(controller IP, username, email, tags) is not a secret and can stay in `.env`:

| Secret | Where it is used | Secret-aware field? |
|--------|------------------|---------------------|
| `KENTIK_API_TOKEN` | `[outputs.http.headers]` → `X-CH-Auth-API-Token` | ✅ Yes |
| `AVI_PASSWORD` | `inputs.http` `cookie_auth_body` (JSON login) | ❌ No |

Secret references use the syntax `@{<store-id>:<key>}` and are only resolved in
plugin options that are **secret-aware**. `inputs.http` supports secrets for
`username`, `password`, `token`, `headers`, and `cookie_auth_headers` — but
**not** `cookie_auth_body`. Because the AVI controller requires a JSON login
body (`{"username": ..., "password": ...}`), the AVI password cannot be
referenced directly with `@{...}`; see
[Securing the AVI password](#securing-the-avi-password) for the recommended
pattern.

The **Kentik API token is the highest-value secret** here (it grants write
access to your Kentik org), and it *can* be fully secured with the keyring.
The non-secret `KENTIK_API_EMAIL` and `AVI_USERNAME` stay as ordinary `${VAR}`
environment variables.

## 1. Define the secret store

Add a `secretstores.os` block near the top of `telegraf.conf`. The `id` is how
plugins reference the store.

```toml
[[secretstores.os]]
  ## Referenced in plugins as @{avi_kentik:<key>}
  id = "avi_kentik"

  ## Linux: kernel keyring name.
  ## macOS: Keychain name. (ignored on Windows)
  keyring = "telegraf"

  ## macOS only: optional Keychain service name (ignored elsewhere)
  # collection = ""

  ## macOS only: password to unlock the Keychain. If omitted, Telegraf
  ## prompts at startup. For a headless service, source it from an
  ## environment variable instead, e.g. password = "$${KEYCHAIN_PASSWORD}".
  # password = ""

  ## Re-read secrets from the store on every access (for rotating secrets).
  # dynamic = false
```

## 2. Create the keyring entry

Store the Kentik API token using the `telegraf secrets` CLI. Point it at the
config that defines the store:

```bash
# You are prompted for the value (input is hidden) — nothing is written to shell history
telegraf --config telegraf.conf secrets set avi_kentik kentik_api_token
```

Verify what is stored (values are redacted unless you explicitly `get` one):

```bash
telegraf --config telegraf.conf secrets list
telegraf --config telegraf.conf secrets get avi_kentik kentik_api_token
```

> Avoid passing the value as a CLI argument
> (`secrets set avi_kentik kentik_api_token <value>`) — it would be visible in
> your shell history and process list. Let Telegraf prompt for it instead.

### Managing the keyring directly

You can also inspect/manage the entries with native OS tools:

```bash
# macOS — the entry appears in the "telegraf" keychain
security find-generic-password -s kentik_api_token -w

# Linux — list keys in the user keyring
keyctl list @u
```

## 3. Reference the token in the Kentik output

Replace only the plaintext token header value in `telegraf.conf` with a secret
reference. The email is not a secret and stays as an env var:

```toml
[[outputs.http]]
  url = "${KENTIK_API_ENDPOINT}"
  data_format = "influx"
  method = "POST"
  timeout = "30s"

  [outputs.http.headers]
    X-CH-Auth-Email     = "${KENTIK_API_EMAIL}"
    X-CH-Auth-API-Token = "@{avi_kentik:kentik_api_token}"
    Content-Type        = "application/influx"
```

With this in place you can remove `KENTIK_API_TOKEN` from `.env` entirely — the
endpoint URL and email contain no secret and can stay.

## Securing the AVI password

Because `cookie_auth_body` is not secret-aware, the cleanest keyring-based
pattern is to store the AVI **password** in the OS keyring and export it as an
environment variable in a small launcher, then let Telegraf's normal `${VAR}`
substitution place it into the login body. The username is not a secret and
stays in `.env`.

`telegraf.conf` keeps the env-substituted body it already uses:

```toml
[[inputs.http]]
  # ... AVI virtualservice input ...
  cookie_auth_url    = "https://${AVI_CONTROLLER_IP}/login"
  cookie_auth_method = "POST"
  cookie_auth_body   = '{"username":"${AVI_USERNAME}","password":"${AVI_PASSWORD}"}'
  cookie_auth_headers = {Content-Type = "application/json"}
```

Store the password once:

```bash
# macOS
security add-generic-password -a "$USER" -s avi_password -w   # prompts for value

# Linux (libsecret)
secret-tool store --label="AVI password" service telegraf key avi_password
```

Launch Telegraf through a wrapper that reads the password from the keyring into
the environment (so it never touches disk in plaintext):

```bash
#!/usr/bin/env bash
# run-telegraf.sh
set -euo pipefail

# macOS
export AVI_PASSWORD="$(security find-generic-password -s avi_password -w)"

# Linux (libsecret) — use this line instead on Linux:
# export AVI_PASSWORD="$(secret-tool lookup service telegraf key avi_password)"

exec telegraf --config telegraf.conf
```

The non-secret `AVI_USERNAME` and `AVI_CONTROLLER_IP` remain plain env vars in
`.env`; only the password and the Kentik token are moved into the keyring.

## Containers and Docker

Access to the Linux kernel keyring is **disabled by default** inside Docker
containers. Using `secretstores.os` in a container will fail with:

```
opening keyring failed: Specified keyring backend not available
```

You can grant keyring access, but the kernel keyring is **not namespaced** —
keys added in one container become readable by *all* containers on the host.
Additionally, Telegraf's memory-locking requires the `IPC_LOCK` capability:

```yaml
# docker-compose.yml (only if you must use the kernel keyring in a container)
services:
  telegraf:
    cap_add:
      - IPC_LOCK
    security_opt:
      - seccomp=unconfined   # allow keyring syscalls (weakens isolation)
```

For containerized deployments prefer one of:

- **Docker/Compose secrets** mounted as files, exported to env by an entrypoint
  wrapper (same pattern as `run-telegraf.sh` above).
- **The `secretstores.jose` plugin** — an encrypted on-disk store that does not
  depend on the host keyring and works well in containers.

## Rotation and verification

- Rotate a secret by overwriting it, then restart Telegraf (or set
  `dynamic = true` on the store so it is re-read on each access):

  ```bash
  telegraf --config telegraf.conf secrets set avi_kentik kentik_api_token
  ```

- Confirm the config still parses and resolves secrets:

  ```bash
  telegraf --config telegraf.conf --test
  ```

- On Linux, remember the kernel keyring is tied to the user session and is
  cleared on reboot — re-provision secrets after a host restart, or use the
  `jose` store for persistence.

## Best practices

- Never commit real credentials to `.env`, `telegraf.conf`, or examples.
- Restrict the launcher/wrapper script permissions (`chmod 700`).
- Give the AVI service account read-only Analytics access.
- Scope the Kentik API token to the minimum permissions required.
- Prefer secret prompts over passing values as CLI arguments.
