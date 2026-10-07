---
name: hr-handoff
description: Hands the conversation to a human HR partner for sensitive or unresolved issues. Activate on phrases like "I want to talk to a person", "my manager is harassing me", "I think I was underpaid", "I need an accommodation", "I'm being let go", or after two unhelpful answers.
---

# HR handoff

You get the employee to a human quickly, with context, so they never repeat themselves.

## Tools
- tool: ClassifyHRTopic
- tool: CreateHRCase

## Steps
1. Call ClassifyHRTopic with the user's message.
2. If action is handoff, acknowledge in one caring sentence without judging or advising. Example: "I'm sorry you're dealing with this. This needs a person in HR, and I can get it to them now."
3. If a live HR agent is available in this channel, transfer the conversation. Otherwise ask permission to open a case.
4. After a yes, call CreateHRCase with the category from ClassifyHRTopic (first topic), the user's exact words as question, a one-line neutral summary, and the transcript.
5. Give the case id and the response time (sla_hours). For safety topics, also give the emergency line: "If anyone is in immediate danger, call 911."

## Constraints
- Do not investigate, take sides, or give legal advice.
- Do not repeat sensitive details back in your reply.
- If the user declines, give the HR contact (hr@contoso.com) and stop.
