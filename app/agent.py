from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

import httpx

from app.onet import OnetGraph
from app.programs import discover_program_pages
from app.va import VaComparison

TrainingFetcher = Callable[[str, str], Awaitable[list[dict[str, str]] | None]]

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_occupations",
            "description": "Search O*NET occupations by a user's work goal, tasks, interests, or job title. Use this before choosing an occupation unless a current selected occupation still matches the user's goal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Concrete work goal or tasks, preserving the user's words."},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5, "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_occupation",
            "description": "Get authoritative O*NET facts for one occupation code. Calling this selects that occupation as the current direction.",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string", "description": "O*NET-SOC code returned by search_occupations."}},
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_related_occupations",
            "description": "Get O*NET-related occupations. Use only when the user explicitly asks for alternatives or agrees to broaden the occupation; never use merely because local results are empty.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 8, "default": 5},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_location",
            "description": "Resolve a city and state, state name, or ZIP to a geographic search anchor. When the user says near me, pass their known profile location instead of the words near me.",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_local_training",
            "description": "Find exact-occupation school programs from My Next Move/IPEDS near a city/state or ZIP. This never changes occupations. An empty result means keep the occupation and consider a wider geographic search or OJT source.",
            "parameters": {
                "type": "object",
                "properties": {
                    "occupation_code": {"type": "string"},
                    "location": {"type": "string", "description": "Known city/state or ZIP, not 'near me'."},
                },
                "required": ["occupation_code", "location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_va_facilities",
            "description": "Find VA-approved schools or employer/OJT providers near a location. For employer searches, supply occupation-relevant name keywords. Empty results should trigger a larger radius for the same occupation, not unrelated nearby employers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "Known city/state or ZIP, not 'near me'."},
                    "provider_type": {"type": "string", "enum": ["school", "employer"]},
                    "keywords": {"type": "array", "items": {"type": "string"}, "description": "Employer/provider name terms relevant to the exact career, such as painter, painting, decorating. Required for employers."},
                    "radius_miles": {"type": "number", "minimum": 5, "maximum": 500, "default": 50},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 8, "default": 6},
                },
                "required": ["location", "provider_type", "keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_va_facility",
            "description": "Find one previously named VA-approved provider by exact facility code or institution name and attach its official VA detail-page link. Use for follow-ups asking for a provider link or details.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Facility code or full provider name."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_official_resources",
            "description": "Attach trusted official action links relevant to the user's need.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topics": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["compare", "eligibility", "remaining", "other", "ojt", "apprenticeship", "vocational", "vre", "bright"]},
                    }
                },
                "required": ["topics"],
            },
        },
    },
]


class JarvetTools:
    def __init__(
        self, onet: OnetGraph, va: VaComparison, fetch_training: TrainingFetcher,
        official_resources: dict[str, dict[str, str]], selected: dict[str, str] | None,
    ) -> None:
        self.onet = onet
        self.va = va
        self.fetch_training = fetch_training
        self.official_resources = official_resources
        self.selected = selected
        self.matches: list[dict[str, Any]] = []
        self.resources: list[dict[str, Any]] = []
        self.resolved_location: dict[str, Any] | None = None

    def _add_resource(self, resource: dict[str, Any]) -> None:
        if resource.get("url") and all(
            (item["url"], item["label"]) != (resource["url"], resource["label"])
            for item in self.resources
        ):
            self.resources.append(resource)

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "search_occupations":
            limit = max(1, min(int(arguments.get("limit", 5)), 5))
            results = self.onet.search(str(arguments.get("query", "")), limit)
            self.matches = results
            return results

        if name == "get_occupation":
            occupation = self.onet.result_by_code(str(arguments.get("code", "")))
            if occupation is None:
                return {"error": "Unknown O*NET-SOC code."}
            self.selected = {"code": occupation["code"], "title": occupation["title"]}
            self.matches = [occupation]
            return occupation

        if name == "get_related_occupations":
            occupation = self.onet.result_by_code(str(arguments.get("code", "")))
            if occupation is None:
                return {"error": "Unknown O*NET-SOC code."}
            limit = max(1, min(int(arguments.get("limit", 5)), 8))
            return [
                {key: item[key] for key in ("code", "title", "description")}
                for item in self.onet.related_results(occupation, limit)
            ]

        if name == "resolve_location":
            location = self.va.resolve_location(str(arguments.get("location", "")))
            if location is None:
                return {"error": "Location could not be resolved. Ask for a city and state or ZIP."}
            self.resolved_location = location
            return location

        if name == "find_local_training":
            occupation = self.onet.result_by_code(str(arguments.get("occupation_code", "")))
            if occupation is None:
                return {"error": "Unknown O*NET-SOC code."}
            location = self.va.resolve_location(str(arguments.get("location", "")))
            if location is None:
                return {"error": "Location could not be resolved. Ask for a city and state or ZIP."}
            self.resolved_location = location
            programs = await self.fetch_training(occupation["code"], location["representative_zip"])
            source_url = (
                f"https://www.mynextmove.org/vets/profile/localtraining/{occupation['code']}"
                f"?zip={location['representative_zip']}"
            )
            if programs:
                programs = await discover_program_pages(programs[:4])
                self._add_resource({
                    "label": f"Find {occupation['title']} training near {location['label']}",
                    "url": source_url,
                })
                for program in programs[:4]:
                    program_url = program.get("program_url")
                    self._add_resource({
                        "label": (
                            f"View {program['program']} details at {program['school']}"
                            if program_url else
                            f"View the source listing for {program['program']} at {program['school']}"
                        ),
                        "url": program_url or source_url,
                        "inline_labels": [program["school"]],
                        "kind": "program-details" if program_url else "source-listing",
                    })
            return {
                "occupation": self.selected or {"code": occupation["code"], "title": occupation["title"]},
                "location": location["label"],
                "programs": programs or [],
                "source": "My Next Move for Veterans / IPEDS",
                "note": (
                    "Results are for this exact occupation only. A verified_official_program_page "
                    "links to institution program details; source_listing_only links back to the "
                    "exact My Next Move results page and must not be described as a direct program "
                    "page. Recent awards are context, not quality rankings."
                ),
            }

        if name == "find_va_facilities":
            location = self.va.resolve_location(str(arguments.get("location", "")))
            if location is None:
                return {"error": "Location could not be resolved. Ask for a city and state or ZIP."}
            self.resolved_location = location
            provider_type = str(arguments.get("provider_type", ""))
            keywords = [str(item) for item in arguments.get("keywords", []) if str(item).strip()]
            if provider_type == "employer" and not keywords:
                return {"error": "Employer searches require occupation-relevant keywords."}
            radius = max(5.0, min(float(arguments.get("radius_miles", 50)), 500.0))
            limit = max(1, min(int(arguments.get("limit", 6)), 8))
            facilities = self.va.search_nearby(
                location["latitude"], location["longitude"], keywords,
                employer=provider_type == "employer", limit=limit, max_miles=radius,
            )
            self._add_resource(self.official_resources["compare"])
            for facility in facilities[:4]:
                self._add_resource({
                    "label": f"View {facility['institution']} in the VA Comparison Tool",
                    "url": facility["detail_url"],
                    "inline_labels": [facility["institution"]],
                    "kind": "provider-details",
                })
            return {
                "location": location["label"],
                "provider_type": provider_type,
                "keywords": keywords,
                "radius_miles": radius,
                "facilities": facilities,
                "source": "VA GI Bill Comparison Tool",
                "note": "Name-keyword relevance is a lead, not confirmation of a specific approved program. Published housing rates are not personal payment quotes.",
            }

        if name == "get_va_facility":
            facility = self.va.find_facility(str(arguments.get("query", "")))
            if facility is None:
                return {"error": "No approved VA facility matched that name or code."}
            self._add_resource({
                "label": f"View {facility['institution']} in the VA Comparison Tool",
                "url": facility["detail_url"],
                "inline_labels": [facility["institution"]],
                "kind": "provider-details",
            })
            return {
                "facility": facility,
                "source": "VA GI Bill Comparison Tool",
                "note": "This official detail page verifies the facility record. Contact and current program availability may still require provider confirmation.",
            }

        if name == "get_official_resources":
            resources = []
            for topic in arguments.get("topics", []):
                if topic in self.official_resources:
                    resource = self.official_resources[topic]
                    self._add_resource(resource)
                    resources.append(resource)
            return resources

        return {"error": f"Unknown tool: {name}"}


async def run_agent(
    *, messages: list[dict[str, str]], profile: dict[str, list[str]],
    selected_occupation: dict[str, str] | None, onet: OnetGraph, va: VaComparison,
    fetch_training: TrainingFetcher, official_resources: dict[str, dict[str, str]],
    base_url: str, api_key: str, model: str,
) -> dict[str, Any]:
    tools = JarvetTools(onet, va, fetch_training, official_resources, selected_occupation)
    system = f"""You are Jarvet, an agentic education and career facilitator for veterans. Solve the user's actual problem by deciding which tools to call, inspecting their results, and adapting your next step. Do not follow a fixed questionnaire.

Operating principles:
- Use tools for every factual claim about occupations, programs, providers, geography, VA approval, and benefits. Never invent results.
- Preserve the current selected occupation unless the user clearly changes career goals. If they do, search and then call get_occupation for the best supported match.
- Treat spelling errors and conversational wording intelligently. Search by concrete work tasks when a title is unclear.
- Accept city/state, region, or ZIP. "Near me" means the known profile location. Never interpret pronouns as state abbreviations and never demand a ZIP when a named area is known.
- When local results are empty, broaden geography for the SAME occupation: try a larger radius or explain the exact-source gap. Never switch occupations or interests merely to produce a result. Call get_related_occupations only if the user explicitly asks for alternatives or agrees to broaden occupationally.
- For OJT/employer searches, use specific occupation-relevant keywords. Do not present arbitrary nearby approved employers as relevant. A keyword name match is still only a lead to verify in the official VA tool.
- Every recommended VA facility must have its official facility-detail resource attached. For a follow-up asking for a provider's link, call get_va_facility instead of returning only a general VA page.
- Local training results may include a verified program_url from the institution's official website. Distinguish it from school_url and source_url. Recommend program details using program_url when present; never describe an institution homepage as program details.
- Respect each training result's link_status. Say a result has direct program details only for verified_official_program_page. Describe source_listing_only as the My Next Move source listing, never as a direct program page.
- When naming specific programs or providers in the final answer, mention only results that have an attached resource. Keep the shortlist focused rather than listing unlinked results returned by a tool.
- My Next Move/IPEDS results are school programs, not employer OJT. VA employer facilities are approved providers, but their names alone do not prove a particular trade program.
- Published housing/living allowance is a facility reference, not a personal payment quote. Eligibility and payment depend on the veteran's circumstances.
- Ask at most one question, only when a missing fact blocks useful action. Otherwise use the tools and answer.
- Keep the response concise and candid about source limitations. The frontend renders content as literal text: do not use Markdown syntax, numbered formatting, asterisks, headings, or raw URLs. Official links called through get_official_resources appear separately as buttons.
- Do not offer actions Jarvet cannot perform, such as contacting providers. Suggest a concrete next search or verification step instead.

Current profile:
{json.dumps(profile)}

Current selected occupation:
{json.dumps(selected_occupation)}

Return the final answer as one JSON object only:
{{"message":"plain text","suggestions":[{{"label":"short label","value":"message sent when chosen"}}],"profile":{{"interests":[],"strengths":[],"goals":[],"preferences":[],"constraints":[],"education":[],"location":[],"notes":[]}}}}
Preserve valid profile facts, update direct user corrections, and do not infer sensitive traits."""
    conversation: list[dict[str, Any]] = [{"role": "system", "content": system}, *messages[-16:]]
    headers = {"Authorization": f"Bearer {api_key}"}
    endpoint = f"{base_url.rstrip('/')}/chat/completions"

    async with httpx.AsyncClient(timeout=180) as client:
        for _ in range(8):
            payload: dict[str, Any] = {
                "model": model,
                "messages": conversation,
                "tools": TOOL_SCHEMAS,
                "tool_choice": "auto",
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            }
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            assistant = response.json()["choices"][0]["message"]
            conversation.append(assistant)
            tool_calls = assistant.get("tool_calls") or []
            if not tool_calls:
                return {
                    "content": assistant.get("content") or "{}",
                    "matches": tools.matches,
                    "resources": tools.resources,
                    "selected_occupation": tools.selected,
                    "resolved_location": tools.resolved_location,
                }
            for tool_call in tool_calls:
                function = tool_call.get("function", {})
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except json.JSONDecodeError:
                    result = {"error": "Tool arguments were not valid JSON."}
                else:
                    result = await tools.call(function.get("name", ""), arguments)
                conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": function.get("name", ""),
                    "content": json.dumps(result, default=str),
                })

        response = await client.post(endpoint, headers=headers, json={
            "model": model,
            "messages": conversation + [{
                "role": "system",
                "content": "Stop calling tools and return the required final JSON using only gathered facts.",
            }],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        })
        response.raise_for_status()
        return {
            "content": response.json()["choices"][0]["message"].get("content") or "{}",
            "matches": tools.matches,
            "resources": tools.resources,
            "selected_occupation": tools.selected,
            "resolved_location": tools.resolved_location,
        }
