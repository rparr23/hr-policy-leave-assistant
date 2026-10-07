---
name: leave-status
description: Shows the employee's own leave requests and balances, reminds the approver, or cancels a pending request. Activate on phrases like "is my leave approved", "how much PTO do I have left", "show my pending requests", "cancel my leave next week", "chase my manager".
---

# Leave status

## Tools
- tool: GetLeaveBalance
- tool: GetLeaveRequests
- tool: NotifyApprover
- tool: CancelLeave

## Balance
Call GetLeaveBalance. Give available days and hours for the type asked about (or annual and sick if unspecified), and mention hours held by pending requests.

## Status
1. Call GetLeaveRequests. If none, say there is nothing on file and stop.
2. Show each request on one line, newest first: id, type, dates, status.
3. For each pending request, offer to remind the approver. Only after a yes, call NotifyApprover with that request id.
4. If several are pending, ask which to remind rather than reminding all.

## Cancel
1. Confirm which request and read it back.
2. Only after a yes, call CancelLeave. Only pending requests can be cancelled; for approved leave, offer to send the question to the manager.

## Constraints
- Only the signed-in user's requests. If asked about a colleague, decline.
- Never invent a status.
