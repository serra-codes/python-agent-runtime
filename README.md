HTTP RESTful APIs, OpenAI-compatible tool
calling, agent loop, and how to integrate multiple tools into an AI assistant.

The entry point for implementation is in `app/main.py`.

# Local runtime requirements

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

For plain-language prompts, the model can also load a matching skill by calling
the `Skill` tool. The tool returns that skill's body with any supplied arguments
substituted into its placeholders.

Skills with `context: fork` in their frontmatter run in a separate agent
conversation that starts with only the skill body. The subagent's final answer
is returned to the main conversation as the result of the `Skill` tool.
