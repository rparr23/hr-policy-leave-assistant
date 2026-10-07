---
name: travel-request
description: Starts a business travel approval and applies the travel policy. Activate on phrases like "I need to fly to Chicago Tuesday", "request travel approval", "book a client trip", "business trip to London next month".
---

# Travel request

## Tools
- tool: GetWorkerProfile
- tool: CheckTravelRequest
- tool: SubmitTravelRequest

## Collect
One missing item at a time: destination city, departure and return dates, business purpose, estimated total cost in USD, whether it is international, travel mode (flight, train, car), and for flights the cabin class and longest flight leg in hours.

## Check
1. Call CheckTravelRequest.
2. If problems are returned, explain and ask for corrections.
3. If policy_exceptions are returned (short_notice, cabin_class), explain the rule in one sentence and ask for a short justification for the approver.
4. Tell the user who will approve, in order (approval_chain), and the per diem total.

## Confirm, then submit
1. Read back destination, dates, cost, approvers and any justification.
2. Only after an explicit yes, call SubmitTravelRequest with confirmed = true and the justification.
3. Reply with the reference id exactly as returned.

## Constraints
- Do not book flights or hotels; this is the approval step only.
- Never submit without a yes in the same turn.
