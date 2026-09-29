# What the hosts let a connector do

Checked against primary documentation. Lines marked *(2026-09-29)* or *(2026-09-28)* were read on the page cited that
day; lines marked
*(2026-09-23)* on that day; the rest date from 2026-09-16, for an earlier design, and were not re-checked. **Re-verify
anything older than about three months before relying on it.** "S" after a claim: search-result text only, not a page
read. Where a line says "our backend" or "terms", read it as any server on the far side of a connector.

Legend: WORKS = works today · WORKAROUND = permitted workaround · FUTURE = needs host support · UNKNOWN = docs silent.

## ChatGPT (apps are "plugins" since 2026-07-09)

- *(2026-09-29, DevDay)* **MCP Events, on every plan**: told to watch something, a chat subscribes to a plugin's event
  and, when it arrives, "ChatGPT receives the event in the subscribed chat and follows the user's instructions",
  "even while you're away". Needs protocol 2026-07-28 (`server/discover` listing `events`), `events/list`,
  `events/subscribe`, `events/unsubscribe`, webhook delivery signed by Standard Webhooks, and a signed challenge
  echoed before delivery; events show beside the tools on the plugin page. Whether developer mode can subscribe:
  docs silent. — developers.openai.com/plugins/build/mcp-events.md, openai.com/index/devday-2026-recap
- *(2026-09-29)* Plugin extensions (every plan): a home in the sidebar, panels beside the chat, file viewers. A
  redesigned submission flow "provides clearer feedback"; better ranking and recommendation "in the directory and in
  conversations"; people approve each plugin's access. Shareable profiles (Free to Enterprise) list a person's
  plugins at one link. Sign in with ChatGPT: identity everywhere, plan usage on Plus and Pro. — devday-2026-recap
- *(2026-09-29)* Dots: always-on agents with their own cloud computer, on Pro, Business Premium and Enterprise (beta),
  "more users soon". They use connected plugins; in the background only with read-only tools; they message their
  person in ChatGPT, Slack or Teams (texting "coming soon"); what they may do alone is set by Custom Rules. —
  openai.com/index/introducing-dots
- *(2026-09-29)* The guidelines still require suitability for 13–17-year-olds, and still take no 18+ plugin. —
  developers.openai.com/plugins/plugin-guidelines.md
- *(2026-09-28)* The App Directory became the Plugin Directory on 07-09; a plugin can bundle skills, MCP apps and
  app templates. — help.openai.com/en/articles/6825453 (release notes)
- *(2026-09-28)* Publishing: platform.openai.com/plugins, with a verified individual or business identity, a public
  HTTPS MCP server, demo sign-in details without MFA, and test prompts; after approval the developer presses
  Publish. No stated review time; EU-residency projects cannot submit. — developers.openai.com/plugins/deploy/app-review.md, …/submission.md
- *(2026-09-28)* Guidelines: suitable for 13–17-year-olds, not aimed at under-13s; 18+ plugins "will arrive once" age
  verification exists; minimum data, never the full chat history; a message sent is a write the person confirms;
  no ads, no digital goods; "Trial or demo plugins will not be accepted". Nothing on matching, messaging between
  people or exchanging contacts. — developers.openai.com/plugins/app-guidelines.md
- *(2026-09-28)* Found by a direct link to its listing (`chatgpt.com/plugins/plugin_asdk_app_<id>`) or by searching
  its name; featuring and proactive suggestion only if OpenAI picks it. — …/deploy/app-review.md, chatgpt.com/plugins
- *(2026-09-28)* "Available across ChatGPT plans"; whether a given plugin installs depends on plan, region and
  workspace. Whether Free and Go get third-party plugins, and the EEA: docs silent (an older page said all but the
  EEA, Switzerland and the UK, S). — help.openai.com/en/articles/20001256
- *(2026-09-28)* A published plugin works on the web, desktop and mobile, and "installed plugins can add skills and
  MCP tools to new chats"; `@` picks one. — learn.chatgpt.com/docs/plugins
- *(2026-09-28)* Developer mode is unchanged: Plus, Pro, Business, Enterprise and Edu, on the web only, chosen per
  chat. — developers.openai.com/api/docs/guides/developer-mode.md
- *(2026-09-28)* Each tool declares `noauth` and/or `oauth2`; a published plugin has one fixed server address, so a
  secret per person in the URL cannot be identity: a public plugin needs OAuth (inferred). — developers.openai.com/plugins/llms-full.txt
- *(2026-09-28)* MCP Apps UI, plus `window.openai` extras. — developers.openai.com/plugins/build/chatgpt-ui.md
- *(2026-09-28)* No documented link opens a chat with a plugin on; `chatgpt.com/?q=` prefill is undocumented (S).
- *(2026-09-28)* Scheduled tasks on every plan (Free: 3, at most daily; paid: hourly), notifying by push or email, and
  shareable as a link that the recipient schedules with their own apps. Whether a task can call a third-party
  plugin: UNKNOWN. Pulse closed on 06-17. Group chats closed to new ones on 07-09. — help.openai.com/en/articles/10291617, release notes
- *(2026-09-23)* An app's tool list is kept from when it was added; changes reach it only on Refresh, and new tools
  arrive switched off; until then a renamed tool fails as "Unknown tool" (a real user), so retired names keep
  working (`mcp_server._RETIRED`). — developer-mode guide
- Tool call context: model-chosen args + OAuth token + `_meta` hints only; no history, no email; servers "must
  not pull, reconstruct, or infer the full chat log". No server push. No evidence of a human's approval reaches the
  server. Inference on the user's plan. Sampling absent. — developers.openai.com/plugins/reference.md, app-guidelines.md

## Claude (claude.ai web, desktop, mobile)

- *(2026-09-28)* Directory: any Pro, Max, Team or Enterprise account submits at claude.ai/directory/manage (not Free;
  no partner programme). An automated policy scan, then listed as "Community"; "Verified" is decided automatically.
  — claude.com/docs/directory/publish.md, …/connectors/verification.md
- *(2026-09-28)* Requirements: every tool a `title` and `readOnlyHint` or `destructiveHint`; OAuth 2.0 for an
  authenticated service; a populated test account, public documentation, seven policy acknowledgements. A listing
  may take a URL pattern, each person typing their own address, slower to review. — …/connectors/building/submission.md, …/authentication.md
- *(2026-09-28)* Directory connectors on every plan, Free included; custom connectors: Free 1, Pro and Max any, Team
  and Enterprise owner only. — support.claude.com/en/articles/11176164, claude.com/docs/connectors/custom/add-unlisted.md
- *(2026-09-28)* Phones: browse and connect directory connectors on iOS and Android; installing custom connectors on
  mobile "is currently in beta". A listing has a page, `claude.ai/directory/connectors/<slug>`, with Connect. The
  custom prefill link is `https://claude.ai/customize/connectors?modal=add-custom-connector&connectorName=…&connectorUrl=…`,
  confirmed by the person; whether it works in a phone's browser: docs silent. — support 11176164, …/directory-vs-custom.md
- *(2026-09-28)* A connected connector is in every chat, on web, desktop and mobile, with a switch per chat; Claude
  suggests connected ones unasked, and listed ones even before they are connected. — support 14730684, directory-vs-custom.md
- *(2026-09-28)* MCP Apps render on the web and in the phone apps. Resource subscriptions and sampling are not
  supported. — …/mcp-apps/getting-started.md, …/connectors/building/index.md
- *(2026-09-28)* Policy: no moving money or crypto, no generated images, video or audio, no ads, no reading Claude's
  memory or chat history; nothing on matching, messaging or minors. — support.claude.com/en/articles/13145358
- *(2026-09-28)* Plugins bundle skills, commands, connectors, agents and hooks; installed at Customize → Plugins, on
  Pro, Max, Team and Enterprise only; a plugin's connector has a fixed URL and is connected separately. Not a way in
  for friends on Free. Skills: paid plans, with code execution on. — claude.com/docs/plugins/overview.md, …/platform-support.md, …/skills/overview.md
- *(2026-09-28)* Scheduled tasks on paid plans run in the cloud with no device on, use connectors, can be made from
  any chat, and notify the phone "when Claude finishes a task or needs your input". — support.claude.com/en/articles/13854387, 15520349
- *(2026-09-23)* Read-only tools run unasked; destructive ones always ask; per-tool "Always allow". No attested
  approval reaches the server. — claude.com/docs/connectors/building/review-criteria
- Auth: OAuth with PKCE S256, DCR or CIMD; callback `https://claude.ai/api/mcp/auth_callback`; one stored connection
  per person, reused across chats. Tool result ≈150,000 characters, call timeout 240 s. Protocol revisions
  2025-03-26, 2025-06-18, 2025-11-25. — claude.com/docs/connectors/building/authentication, …/building

## Meta Muse

- *(2026-09-29)* A free consumer agent, in the US since 09-08, in its own apps, on the web and inside WhatsApp; it can
  keep working after its app is closed. Connectors opened to developers on 09-18 ("You bring the API"; more than
  1,500 applications in a week); the protocol, the review and its rules are not public. — runtimewire.com (S for
  the numbers), unite.ai

## Gemini

- *(2026-09-28)* Custom MCP apps are added in the web app (18+, US, personal account, English, Keep Activity on) and
  then work on mobile; `@` picks one; writes are confirmed by hand. No directory or submission path. —
  support.google.com/gemini/answer/17209137
- *(2026-09-28)* Spark schedules (Google AI Pro or Ultra, 18+, personal account, not the EEA, UK, Switzerland or
  Nigeria) can use a custom connected app. — support.google.com/gemini/answer/17094507, 17094710

## Cross-host consequences

1. A server can wake one host: ChatGPT, through MCP Events, in a chat that subscribed. Elsewhere nothing runs while
   the person is absent unless they schedule it: Claude scheduled tasks (paid) and Gemini Spark.
2. The backend sees only what the host model chose to put in tool arguments.
3. No host gives the server proof that a human approved anything.
4. A listing in either directory takes one address for everyone, so sign-in is by OAuth (PROTOCOL.md §5). Claude's
   is self-serve with an automated review; ChatGPT's needs identity verification and a human review for 13–17.

## MCP protocol (spec revision 2026-07-28 — a breaking rewrite)

- Changes: no `initialize` handshake, no sessions/`Mcp-Session-Id`, no GET SSE stream, mandatory `server/discover`, per-request `_meta` capabilities. — modelcontextprotocol.io/specification/2026-07-28/changelog
- claude.ai documents support for 2025-03-26 / 06-18 / 11-25 (see Claude section). ChatGPT/Gemini: undocumented. Sibling project's SDK 2.2.0 server worked with claude.ai on 2026-09-16. Use the SDK's negotiation; do not hand-roll the protocol.
- Elicitation: form mode (flat JSON-Schema; MUST NOT request credentials) + URL mode (out-of-band browser; content never transits the client). As of 2026-07-28 it is a **retry pattern** (server returns `InputRequiredResult`, client re-calls with `inputResponses`+`requestState`), only on `tools/call`, `resources/read`, `prompts/get`. Hosts: VS Code, Cursor, ChatGPT, Claude Code (form+URL) WORKS; claude.ai UNKNOWN (listed in neither supported nor unsupported); Gemini CLI FUTURE. — /specification/2026-07-28/client/elicitation ; /basic/patterns/mrtr
- Sampling: **deprecated** (SEP-2577; removal ≥2027-07-28); only VS Code ever supported it. — FUTURE and dying — /specification/2026-07-28/deprecated
- Tasks: moved to extension `io.modelcontextprotocol/tasks` (poll `tasks/get`, `tasks/update` for mid-flight input); no host in the official client matrix. — FUTURE — /extensions/tasks/overview
- Server→client push with no request in flight: server MUST NOT send independent requests; only `subscriptions/listen` (client-initiated long POST-SSE carrying `*_list_changed`/`resources/updated`). No consumer host documents holding it open while the user is absent. Claude Code has a non-standard `claude/channel` push (CLI only). — FUTURE — /basic/transports/streamable-http ; /development/roadmap
- Authorization: OAuth 2.1, RFC 9728 PRM required, RFC 8707 `resource` required, audience validation, no token passthrough; **DCR (RFC 7591) deprecated in favour of Client ID Metadata Documents**; identity MUST come from the access token `sub`. — WORKS — /specification/2026-07-28/basic/authorization
- Delegated authority: Enterprise-Managed Authorization extension (ID-JAG) shipped, one implementer; Agent Identity WG forming (DPoP, token exchange, "human-presence attestation" — roadmap, framed around "acting for a user who isn't present"). — SPECULATIVE/partly shipped — /extensions/auth/enterprise-managed-authorization

## A2A (v1.0.0, 2026-03-12; Linux Foundation / Agentic AI Foundation)
- Specifies Agent Card, 8-state task lifecycle (incl. `input-required`, `auth-required`), messages/artifacts, webhook push, auth schemes, three bindings. No negotiation, consent, or multi-party primitives. — a2a-protocol.org/latest/specification
- No consumer assistant (ChatGPT, Claude, Gemini app) is an A2A client; Google's surface is Gemini Enterprise. — FUTURE

## Corrections log
- 2026-09-16 peer review (Fable): ChatGPT tasks→custom plugin downgraded to UNKNOWN; Cowork push/"go-ahead" downgraded to UNKNOWN and Dispatch separated; 150k/240s citation moved to claude.com/docs/connectors/building; claude.ai supported revisions added.
- 2026-09-28: re-checked ChatGPT, Claude and Gemini for sign-in and listing. Claude's directory no longer needs a
  Team/Enterprise org; ChatGPT apps are plugins; Pulse and ChatGPT group chats are gone.
