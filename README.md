# HR Policy & Leave Assistant

An internal HR agent for Microsoft Copilot Studio that answers policy questions with citations, tailors answers to each employee's state and employment type, books leave, routes travel approvals, and hands sensitive issues to a human in HR.

This repo has the two halves of the build described in the PRD:

| Folder | What it is |
| --- | --- |
| `copilot-studio/` | Agent instructions, 6 skill files, the OpenAPI spec to import as tools, and a 14-question evaluation set |
| `app/` | The tools API (FastAPI): worker context, leave validation and submission, state leave rules, FMLA and state eligibility, travel policy, HR triage and cases |
| `data/` | Demo data standing in for the HRIS, time-off tool and Dataverse tables: 7 employees in CA, NY, TX, WA, IL; company policy; state leave rules |
| `knowledge/` | Sample handbook, travel policy and benefits guide to upload as Copilot Studio knowledge |
| `tests/` | 40 tests covering every rule and the PRD's sample conversations |

## How it fits together

```
Employee in Teams / Microsoft 365 Copilot (Entra ID sign-in)
        |
Copilot Studio agent (new agent experience)
  instructions + skills: hr-question, leave-eligibility, apply-leave,
                         leave-status, travel-request, hr-handoff
        |                                   |
  Knowledge (SharePoint:              Tools API (this repo, imported via openapi.json)
  handbook, travel, benefits)         GetWorkerProfile, GetLeaveBalance, CheckLeaveRequest,
                                      SubmitLeave, LookupStateRule, CheckLeaveEligibility,
                                      CheckTravelRequest, SubmitTravelRequest,
                                      ClassifyHRTopic, CreateHRCase, ...
```

The model does the conversation. Every hard rule runs in the API, where it can be tested: working-day math, holidays, overlaps, balances net of pending requests, the state-vs-company sick leave comparison, FMLA criteria, travel exceptions and approval chains. Submits are refused unless `confirmed` is true, and every read is filtered to the signed-in employee.

## Run it locally

```bash
pip install -r requirements-dev.txt
pytest -q                                   # 40 tests
HR_TODAY=2026-10-07 uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs and pass `X-User-Email: maria.lopez@contoso.com` to try any tool as that employee.

Environment variables:

| Variable | Purpose |
| --- | --- |
| `HR_API_KEY` | If set, every tool call needs a matching `X-API-Key` header |
| `HR_TODAY` | Pins "today" (yyyy-MM-dd) so demos and tests behave the same every day |
| `HR_DATA_DIR` | Use a different data folder |

## Deploy

Railway: create a service from this repo (it builds the `Dockerfile`, health check `/health`), set `HR_API_KEY` as a variable, and generate a public domain. Any container host works the same way.

## Set up the agent in Copilot Studio

1. Create an agent in the **new agent experience**. Paste `copilot-studio/agent-instructions.md` into Instructions.
2. **Knowledge:** upload the files in `knowledge/` to a SharePoint library (one library per domain, current versions only) and add the library as knowledge. Turn off general knowledge.
3. **Tools:** add a REST API tool (or a custom connector) from `copilot-studio/openapi.json`, with the server URL set to your deployment. Use API key auth with header `X-API-Key`. Map the `X-User-Email` header to `System.User.Email` (in a custom connector, set it as a policy). Do not expose `DecideLeave` to the agent; it is the manager approval callback.
4. **Skills:** add each file in `copilot-studio/skills/` as a skill. The description in the front matter is what the orchestrator routes on.
5. **Settings:** authentication "Authenticate with Microsoft", content moderation High, Memory on (preview), Microsoft IQ off.
6. **Evaluate:** load `copilot-studio/evaluation-set.csv` into the Evaluate tab and run it. Sign in as the listed user for each row.
7. Publish to Teams.

## Before production

- **Identity:** the demo trusts the `X-User-Email` header behind an API key. In production, protect the API with Entra ID (OAuth 2.0 on the custom connector) and take the user from the token.
- **Data:** `app/store.py` is in-memory and resets on restart. Replace its methods with the HRIS (Workday, ADP, UKG, BambooHR), the time-off tool, Dataverse tables and the HR case system. The services only talk to that interface.
- **State law:** `data/state_leave_rules.json` is a simplified demo table for 5 states. HR compliance or counsel must review and own it. Rules older than 12 months are flagged automatically.
- **Approvals:** `DecideLeave` stands in for the Teams approval card. Wire it to a Power Automate Approvals flow.

## Tests

`pytest -q` runs on every push (GitHub Actions). Highlights:

- PRD sample 1: part-time California employee gets the 40-hour state minimum over company policy.
- PRD sample 2: "Friday and Monday" counts 2 working days, 8 hours on a 4-hour schedule; the same dates submitted twice are refused as an overlap.
- PRD sample 3: NY employee is FMLA and NY PFL eligible; a Texas new hire fails all three FMLA tests.
- PRD sample 4: a flight 6 days out needs a justification and Finance approval above $2,500.
- Privacy: employees cannot see, remind about or cancel each other's requests; only the assigned manager can decide.
- The committed `openapi.json`, skill files and evaluation set stay in sync with the API.

Based on the PRD "HR Policy & Leave Assistant (Microsoft Copilot Studio)" and the skills-first HR Leave Assistant pattern from [wrvishnu.com](https://www.wrvishnu.com/copilot-studio-new-agent-experience/).
