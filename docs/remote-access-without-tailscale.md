# Remote access without Tailscale — options for review

Context: Remote Access currently uses Tailscale for two things bundled
together — HTTPS termination (`tailscale serve`) and off-LAN reachability
(their WireGuard mesh). The concern: relying on one company for a feature
before release. `media_server.py` itself has no Tailscale dependency — it's
a plain stdlib HTTP server bound to `0.0.0.0`. Tailscale is purely a
deployment-layer add-on, so switching away only touches the deployment doc,
not app code.

The problem splits into two independent pieces:

1. **HTTPS on the LAN** — needed because the Media Session API (lock-screen
   controls) only activates in a secure context, even for local traffic.
2. **Off-LAN reachability** — letting the phone reach the home server when
   it's not on the home wifi.

## Piece 1: local HTTPS without Tailscale

**`mkcert`** — generate your own local CA, install its root cert on the
phone once (one-time manual step, no ongoing dependency), then issue real
trusted certs for the server's LAN IP or hostname. Zero external services,
zero recurring cost, nothing that can be shut down or repriced. Only covers
LAN, not off-network access.

## Piece 2: off-LAN reachability — two options

Nobody escapes *all* infrastructure here — some stable rendezvous point is
needed. Ranked by how much you own:

- **Port forward + DDNS** — fully self-hosted, but only works with a real
  public IP from the ISP. Many ISPs (cable/cellular especially) do CGNAT,
  which silently breaks this. Also exposes the server's port directly to
  the internet.
- **Self-hosted WireGuard** — see comparison below.
- **Headscale** — see comparison below.
- **Own domain + Let's Encrypt** for a real (non-self-signed) cert if going
  the DDNS route. Let's Encrypt is lower risk than Tailscale specifically
  since ACME is an open protocol multiple CAs implement — not locked to one
  org even though it's technically still an external service.

## Option A: Headscale

Open-source (MIT), self-hosted reimplementation of Tailscale's
*coordination server*. The phone and home server keep running the normal
Tailscale client app (also open source), just pointed at a self-run
Headscale server instead of `login.tailscale.com`.

Still uses WireGuard under the hood and still does NAT traversal via DERP
relay servers — can point at Tailscale's public DERP servers, or self-host
those too. Run: one Go binary (Headscale) on a VPS or the home server, plus
a Postgres/SQLite DB it manages itself.

**Pros**
- Nearly identical UX to today — same client apps, same NAT traversal,
  same auto-reconnect.
- Client-side is Tailscale's actual open-source client — well-tested.
- Minimal migration effort from the current setup.

**Cons**
- Trails Tailscale's client releases; occasionally breaks on newer client
  versions until Headscale catches up. Community project, not a funded
  product.
- Default NAT traversal still leans on Tailscale's DERP relay
  infrastructure unless self-hosted too — a residual soft dependency.
- One more service (Headscale itself) to patch and monitor.

## Option B: Self-hosted WireGuard (no Tailscale software at all)

WireGuard configured directly — on the router (OPNsense, pfSense, OpenWrt,
some consumer routers with custom firmware) or a small VPS both the phone
and home server connect to. No coordination server at all; peer-to-peer
once configured with static keys/IPs.

**Pros**
- Maximum independence: no third-party software, no company, nothing that
  can shut down, reprice, or get acquired. Just a protocol and a config
  file.
- Smallest attack surface — one UDP port exposed.
- Works forever with zero ongoing service dependency.

**Cons**
- No NAT traversal magic — if both ends are behind NAT (common on mobile
  carriers), a fixed rendezvous point with a real public IP is needed:
  either the router has one (rare with home ISPs due to CGNAT) or a cheap
  VPS ($3–5/mo) becomes the WireGuard hub.
- All manual: new device = hand-generated keys and config, no app-based
  "add device" flow.
- No mobile-client convenience layer — hand-managing `.conf` files/QR
  codes instead of an account-based system.

## Comparison

| | Headscale | Self-hosted WireGuard |
|---|---|---|
| Company dependency | None (control plane) | None |
| Underlying protocol dependency | WireGuard + Tailscale client software | WireGuard only |
| NAT traversal | Automatic (via DERP, optionally self-hosted) | Manual — needs a public-IP hub if both ends are NATed |
| Setup effort | Low (swap server URL in existing client) | Medium–high (own VPS/router config, manual peer setup) |
| Ongoing maintenance | Headscale server updates, occasional client compat breaks | Very low — config rarely changes |
| Adding a new device | Same as Tailscale today (one command/QR) | Manual key generation + config edit |
| Cost | VPS/home box to run Headscale (~free–$5/mo) | VPS if needed for NAT traversal (~$3–5/mo), free if router-hosted |
| "True" independence | High, with one soft link (default DERP relays) | Total |

## Recommendation

Headscale if this should feel roughly like today with the company risk
removed; self-hosted WireGuard if "future-proof" means literally nothing
but a protocol standing between the data and the internet.

No changes have been made yet — this is written up for review. Next step
if greenlit: pick one, then update the Remote access deployment note in
CLAUDE.md and rework the setup docs (`docs/settings.md` / a new deployment
doc) accordingly.
