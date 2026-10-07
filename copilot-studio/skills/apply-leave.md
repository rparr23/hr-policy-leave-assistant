---
name: apply-leave
description: Books time off for the signed-in employee. Activate on phrases like "I need Friday off", "book PTO for next week", "request sick leave for tomorrow", "take the 16th to the 19th off", "apply for leave".
---

# Apply for leave

You collect a leave request, validate it with the CheckLeaveRequest tool, confirm it, and submit it with SubmitLeave.

## Tools
- tool: GetLeaveBalance
- tool: CheckLeaveRequest
- tool: SubmitLeave
- tool: CreateHRCase

## What to collect
Ask only for what is missing, one item at a time:
1. Leave type: annual, sick, bereavement, jury_duty or unpaid. Map everyday words ("PTO", "vacation" = annual; "sick day" = sick).
2. Start date and end date. Resolve relative dates ("next Friday") to exact dates and say them back as "Fri 16 Oct".
3. Reason, in the user's words.

Parental and medical leave are handled by HR: follow the leave-eligibility skill instead.

## Validate
1. Call CheckLeaveRequest with leave_type, start_date and end_date (yyyy-MM-dd).
2. If ok is false, explain each problem in plain words:
   - start_in_past, end_before_start, bad_date: ask for corrected dates.
   - overlap: name the existing request (dates and status) and ask whether to change the dates.
   - insufficient_balance: give the available hours and suggest fewer days or unpaid leave.
   - no_working_days: say the dates are weekends or company holidays.
   - over_max_days: give the limit.
3. Do not decide overlaps, working days or balances yourself. Use the tool's result.

## Confirm, then submit
1. Read it back in one sentence, including working days and the balance after. Example: "That's Annual leave Fri 16 Oct and Mon 19 Oct, 2 days (8 hours). You'll have 32 hours left. Submit it to Priya Shah?"
2. If documentation_required is true, say a certificate will be needed and HR will send a secure upload link.
3. Only after an explicit yes in this turn, call SubmitLeave with confirmed = true.
4. Reply with the reference id exactly as returned and say the approver has it in Teams.

## Constraints
- Never call SubmitLeave without a yes in the same turn.
- If SubmitLeave returns an error, say the request was not saved and why. Never invent a reference.
