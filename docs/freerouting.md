# Freerouting setup

KiRouter uses [Freerouting](https://github.com/freerouting/freerouting) as
its first routing engine. Freerouting is a free, mature, open-source
autorouter that has been used in the KiCad ecosystem for many years. We
do not modify it; we just call it as a subprocess.

## What you need

- **Java 17 or newer**
  Download from [Adoptium Temurin](https://adoptium.net/temurin/releases/).
  Pick the JDK or JRE for your OS. After install, `java -version` should
  print 17 or higher.

- **The Freerouting JAR**
  Download from
  [github.com/freerouting/freerouting/releases](https://github.com/freerouting/freerouting/releases).
  Pick the latest `freerouting-X.Y.Z.jar` (typical size 5–15 MB).

## Where to put the JAR

KiRouter looks in three places, in order:

1. The path in the `KIROUTER_FREEROUTING_JAR` environment variable.
2. `router/kirouter/freerouting/bin/freerouting.jar` (inside this repo).
3. `~/.kirouter/freerouting.jar` (your home directory).

The simplest setup is #2: drop the JAR into
`router/kirouter/freerouting/bin/`. Done.

If you don't want to put the JAR in the repo (for example you keep
multiple Freerouting versions around), use #3 or set the env var.

## Verifying

Start KiRouter (`./start_kirouter.sh` or `START_KIROUTER.bat`), open
`http://localhost:8765/api/engines` in your browser. You should see:

```json
{
  "engines": [
    {
      "name": "freerouting",
      "available": {
        "ok": true,
        "java": "/usr/bin/java",
        "jar":  "/home/you/kibridge/router/kirouter/freerouting/bin/freerouting.jar",
        "jar_size": 12345678,
        "errors": []
      }
    }
  ]
}
```

If `ok` is `false`, the `errors` array tells you exactly what's missing
and where KiRouter looked.

## Common issues

**"java: command not found"**
Install Java 17+ and make sure it's on your PATH. On Windows, after
installing JDK, log out and back in (or restart) so the PATH update
takes effect.

**"freerouting JAR not found"**
Check spelling and location. The filename must start with `freerouting`
and end with `.jar`. The runner uses `glob("freerouting*.jar")` so
`freerouting-1.9.0.jar`, `freerouting-2.0.0.jar`, etc. all work.

**"freerouting exited with code N"**
Look at the log tail in the UI's Routing panel — Freerouting prints
human-readable diagnostics. Most often the DSN file has an issue
(missing rules, malformed coords). Open an issue on the KiBridge
repo with the log if you can't tell why.

**Routing takes a very long time**
Reduce `max_passes` from 30 to 5 or 10 for a quick first attempt. You can
re-route specific nets later. The default 600-second timeout will kill
runs that exceed it.

## Why don't you bundle Freerouting?

Two reasons:

1. **License hygiene.** Freerouting is GPL v3. We're Apache 2.0. Calling
   it as a subprocess is fine; bundling it inside our distribution would
   raise license-aggregation questions we'd rather avoid.
2. **Version freedom.** New Freerouting releases come out periodically.
   We don't want to chase them in this repo. You pick the version you
   trust for your boards.
