# Storykeeper friction log

Kept while building Storykeeper for the Build, Ship, Shape: Amazon Developer Hackathon (Oct 2026). Each entry: task, steps, expected vs actual, severity, workaround, suggestion.

**1. Bedrock model invocation blocked on a new account. Severity: Critical**
- *Task:* call Amazon Nova 2 Lite through the Converse API.
- *Steps:* created an AWS account (AISPL), completed customer verification ("Verified", 23 Oct 14:20 IST), created an IAM user with Bedrock access, configured CLI credentials, then called `converse` with `us.amazon.nova-2-lite-v1:0`.
- *Expected:* a response, since Nova needs no separate access form.
- *Actual:* `AccessDeniedException: Your account is currently being verified`, later `ValidationException: Operation not allowed`. It persisted for the whole hackathon window across Nova 2 Lite, Nova Lite, Nova Micro and Nova Pro. Listing models (control plane) worked.
- *Workaround:* built a deterministic offline fallback for every model call; the demo runs in that mode.
- *Suggestion:* show Bedrock readiness in the console with an ETA, and return one explicit error code ("AccountNotReadyForInvocation") everywhere.

**2. Same root cause, different errors per region. Severity: High**
- *Task:* rule out a regional problem.
- *Steps:* called Converse in us-east-1, us-west-2, ap-south-1 and eu-west-1 with matching inference profiles.
- *Expected:* the same error everywhere.
- *Actual:* `ValidationException: Operation not allowed` in US regions, `AccessDeniedException: ...being verified` elsewhere. The first reads like a bad request, which sent us debugging our own code.
- *Workaround:* tried multiple regions to infer it was account-level.
- *Suggestion:* make account-state errors consistent and clearly account-level.

**3. Model ID vs inference profile ID. Severity: Medium**
- *Task:* pick the right `modelId` for Nova 2 Lite.
- *Steps:* tried the base model ID, then listed inference profiles to find `us.` / `global.` variants.
- *Expected:* the model page to state the exact ID to use with Converse on demand.
- *Actual:* needed `list_inference_profiles` to discover it.
- *Suggestion:* put a copyable "Converse modelId" on every model card.

**4. New IAM user has no permissions and no guidance. Severity: Medium**
- *Task:* create credentials for a local Bedrock app.
- *Steps:* created the IAM user; the confirmation page showed "Permissions policies (0)".
- *Expected:* a prompt to attach Bedrock permissions.
- *Actual:* calls failed until a policy was attached manually.
- *Workaround:* attached AmazonBedrockFullAccess (broader than needed).
- *Suggestion:* a "Bedrock developer" least-privilege template in the create-user flow.

**5. No way to test a self-hosted MCP server with Alexa+. Severity: High**
- *Task:* hear our MCP tools driven by Alexa+.
- *Steps:* built the server to spec 2025-11-25+ over Streamable HTTP; looked for a device, simulator or console path.
- *Expected:* a test console or simulator that accepts an MCP URL.
- *Actual:* none available to us.
- *Workaround:* built a simulated Alexa+ panel in the web app calling the same tools, plus an MCP client smoke test.
- *Suggestion:* an Alexa+ MCP test console showing tool calls, arguments and the spoken response.

**6. MCP Python SDK 2.x rename. Severity: Medium**
- *Task:* start an MCP server from current tutorials.
- *Steps:* followed examples using `FastMCP`.
- *Expected:* examples to run on the current SDK.
- *Actual:* the server class is now `MCPServer` (`mcp.server.mcpserver`); older examples break.
- *Workaround:* read the SDK source.
- *Suggestion:* a migration note and redirects from old docs.

**7. `aws configure` mixes setup prompts with promotional output. Severity: Low**
- *Task:* enter CLI credentials.
- *Actual:* the output included installation messages for agent tooling, which made it unclear whether configuration had succeeded.
- *Suggestion:* keep `aws configure` output to configuration only; offer extras as a separate command.
