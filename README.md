# jarvet

## O*NET graph data

The O*NET N-Triples graph database is downloaded from the
[O*NET Resource Center](https://www.onetcenter.org/database.html#graph) during
devcontainer setup. The extracted database is intentionally excluded from Git.

To initialize or restore it manually, run:

```bash
./scripts/init-onet-data.sh
```

The script defaults to O*NET 31.0. Set `ONET_VERSION` using underscores to
download another published version, for example `ONET_VERSION=30_2`.

## Web application

Jarvet runs at `http://localhost:8000` in the devcontainer. Copy `.env.example`
to `.env`, configure the host LLM, then start the service:

```bash
./scripts/start-web.sh
```

The browser never receives the LLM key. For Cloudflare Tunnel, route `jarvet.ai`
to `http://localhost:8000` inside the container or network namespace where
`cloudflared` runs.
