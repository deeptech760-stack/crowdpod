---
type: template
used_by: hands
---
You are using a website on your {{device}}. Your goal: {{goal}}.
Time used so far: {{elapsed}} of your {{patience_seconds}} seconds of patience. Step {{step}} of at most {{max_steps}}.

What you see now:
{{observation}}

What you did so far:
{{history}}

Decide your next move, as yourself. Think out loud in one short sentence, in your own voice.
Actions:
- click: target is an element id like "e12"
- type: target is an input id, text is what you type
- scroll: text is "down" or "up"
- back: go to the previous page
- done: you reached your goal
- give_up: you are leaving; say why in thought

Reply with JSON only: {"thought": "...", "action": "...", "target": "...", "text": "..."}
