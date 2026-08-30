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

The devcontainer then bulk-loads every N-Triples file into an embedded,
disk-backed Oxigraph store. Jarvet queries occupation relationships and features
with SPARQL rather than loading the 2.4 GB graph into Python memory. Rebuild the
store after changing datasets with:

```bash
.venv/bin/python scripts/init-onet-store.py
```

Initialization also downloads O*NET OnLine's official Bright Outlook CSV and
joins its current growth, openings, and new/emerging categories to occupations
by O*NET-SOC code.

## VA provider and benefit data

Initialization downloads the official VA GI Bill Comparison Tool workbook and
the Census Bureau's 2025 ZIP Code Tabulation Area Gazetteer. The VA workbook is
streamed into a compact SQLite index rather than loaded wholly into memory. The
Census coordinates let Jarvet estimate proximity from a supplied ZIP-area
centroid to the facility coordinates published in the VA workbook.

Rebuild the VA index manually with:

```bash
.venv/bin/python scripts/init-va-data.py
```

To download the latest published VA workbook and Census file before rebuilding,
run:

```bash
REFRESH_VA_DATA=1 ./scripts/init-onet-data.sh
.venv/bin/python scripts/init-va-data.py
```

The generated source files and SQLite index are excluded from Git. The index
contains provider identity, approval and provider type, location, the published
monthly housing/living-allowance rate, Post-9/11 usage/payment aggregates,
Yellow Ribbon fields, accreditation, military-credit policy, and VA caution
flags. Jarvet presents the workbook's housing rate as a facility-level reference,
not a personalized payment quote. Actual payments depend on the veteran's
eligibility, benefit chapter and tier, rate of pursuit, training modality, and
applicable dates.

## Web application

Jarvet runs at `http://localhost:8000` in the devcontainer. Copy `.env.example`
to `.env`, configure the host LLM, then start the service:

```bash
./scripts/start-web.sh
```

The browser never receives the LLM key. For Cloudflare Tunnel, route `jarvet.ai`
to `http://localhost:8000`. Add the remotely managed tunnel token to `.env` as
`TUNNEL_TOKEN`; the devcontainer starts `cloudflared` automatically alongside
Jarvet. Tunnel credentials and logs remain outside Git.

Jarvet uses the configured OpenAI-compatible model as a tool-calling agent. The
model decides when to search O*NET, inspect one occupation, resolve a named area
or ZIP, query exact-occupation My Next Move programs, search relevant VA
providers over a chosen radius, or attach official resources. Python validates
tool arguments and returns structured source facts; it does not automatically
switch occupations or inject the nearest unrelated provider when a search is
empty. Geographic broadening and occupational broadening are separate actions,
and related occupations are available only through an explicit agent tool. Each
recommended VA provider includes a facility-specific VA Comparison Tool detail
link derived from its official facility code. Exact provider-name or code lookup
also supports follow-up requests for the link to a previously named provider.

Benefit, school, vocational, and on-the-job-training starting points link to
official VA.gov guidance and the GI Bill Comparison Tool. Jarvet does not make
eligibility decisions or treat O*NET occupation data as a school inventory.

When a career and location are known, Jarvet loads nearby programs from My Next
Move for Veterans using the occupation's O*NET-SOC code. Users may supply a city
and state or a ZIP code. For named cities, Jarvet resolves an area center and a
representative ZIP from its local VA and Census indexes because the My Next Move
endpoint itself accepts only ZIP codes. Those results are based on the current
IPEDS directory and completions data plus the CIP to O*NET-SOC crosswalk. Jarvet
shows recent-award counts as evidence of program activity, not as a quality
ranking. For each displayed result, Jarvet performs a bounded crawl of the
institution's own site and verifies subject terms before promoting a program,
degree, certificate, curriculum, or catalog page. If no official program page
can be verified, the action is labeled as a My Next Move source listing instead
of presenting the institution homepage as program details. Trusted program and
provider actions are linked at their names in the response and repeated in the
resource list below it.
My Next Move/IPEDS identifies occupation-related school programs; the VA index
separately verifies approved facilities and supplies benefit comparison facts.
Nearby approved employer records are proximity leads, not proof that an employer
offers training for the selected O*NET occupation.

Successful chat turns are cached in `.cache/chat-responses.sqlite`. To preheat a
demo, walk through the intended paths once; repeating the same choices will reuse
the complete response, including profile state, suggestions, and trusted links,
across browser refreshes and server restarts. Cache entries expire after seven
days and the 500 least-recently-used limit is configurable with
`JARVET_CACHE_TTL_SECONDS` and `JARVET_CACHE_MAX_ENTRIES`. Increment
`JARVET_CACHE_VERSION` when response behavior changes and old warm entries should
be ignored. `/api/health` reports cache entries, hits, and misses, while each chat
response includes `X-Jarvet-Cache: HIT` or `MISS`.
