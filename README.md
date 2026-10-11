[![progress-banner](https://backend.codecrafters.io/progress/claude-code/1285c67b-3f84-4e0d-98cc-467cf8df8a0c)](https://app.codecrafters.io/users/serra-codes?r=2qF)

This is a starting point for Python solutions to the
["Build Your own Claude Code" Challenge](https://codecrafters.io/challenges/claude-code).

Claude Code is an AI coding assistant that uses Large Language Models (LLMs) to
understand code and perform actions through tool calls. In this challenge,
you'll build your own Claude Code from scratch by implementing an LLM-powered
coding assistant.

Along the way you'll learn about HTTP RESTful APIs, OpenAI-compatible tool
calling, agent loop, and how to integrate multiple tools into an AI assistant.

**Note**: If you're viewing this repo on GitHub, head over to
[codecrafters.io](https://codecrafters.io) to try the challenge.

# Passing the first stage

The entry point for your `claude-code` implementation is in `app/main.py`. Study
and uncomment the relevant code, and submit to pass the first stage:

```sh
codecrafters submit
```

# Stage 2 & beyond

Note: This section is for stages 2 and beyond.

1. Ensure you have `uv` installed locally.
2. Run `./your_program.sh` to run your program, which is implemented in
   `app/main.py`.
3. Run `codecrafters submit` to submit your solution to CodeCrafters. Test
   output will be streamed to your terminal.

### Slash commands

Prompts beginning with a slash load a skill from
`.claude/skills/<name>/SKILL.md`. The skill name and description from each
skill's frontmatter are included in the system message, while only the invoked
skill's body is sent as the user message. Arguments after the skill name are
split on whitespace and substituted into `$ARGUMENTS`, `$ARGUMENTS[n]`, and
`$n` placeholders in the skill body, where `n` is a zero-based argument index.
Multiple skills can be stacked at the start of a prompt; the first token that
isn't a known skill ends the stack, and that token plus everything after it is
used as the arguments for each expanded skill.
