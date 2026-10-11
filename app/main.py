import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MODEL = "anthropic/claude-haiku-4.5"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "Read",
            "description": "Read and return the contents of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The path to the file to read",
                    }
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Write",
            "description": "Write content to a file",
            "parameters": {
                "type": "object",
                "required": ["file_path", "content"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The path of the file to write to",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write to the file",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Bash",
            "description": "Execute a shell command",
            "parameters": {
                "type": "object",
                "required": ["command"],
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Skill",
            "description": "Load a skill's instructions into the conversation",
            "parameters": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the skill to use",
                    },
                    "args": {
                        "type": "string",
                        "description": "Optional arguments for the skill",
                    },
                },
            },
        },
    },
]


@dataclass(frozen=True)
class Skill:
    name: str
    directory_name: str
    description: str
    body: str
    context: str | None = None


def parse_skill_metadata(frontmatter, path):
    metadata = {}
    for line in frontmatter.splitlines():
        key, delimiter, value = line.partition(":")
        if delimiter and key.strip() in {"name", "description", "context"}:
            metadata[key.strip()] = value.strip().strip("'\"")

    if not metadata.get("name") or not metadata.get("description"):
        raise ValueError(f"Skill file must define name and description: {path}")

    return metadata


def read_skill(path):
    with path.open(encoding="utf-8") as skill_file:
        if skill_file.readline().strip() != "---":
            raise ValueError(f"Skill file is missing YAML frontmatter: {path}")

        frontmatter = []
        for line in skill_file:
            if line.strip() == "---":
                metadata = parse_skill_metadata("".join(frontmatter), path)
                return Skill(
                    name=metadata["name"],
                    directory_name=path.parent.name,
                    description=metadata["description"],
                    body=skill_file.read().strip(),
                    context=metadata.get("context"),
                )
            frontmatter.append(line)

    raise ValueError(f"Skill file has unterminated YAML frontmatter: {path}")


def substitute_skill_arguments(skill_body, arguments):
    all_arguments = " ".join(arguments)

    def replace_placeholder(match):
        if match.group(1) is not None:
            index = int(match.group(1))
            return arguments[index] if index < len(arguments) else ""
        if match.group(2) is not None:
            index = int(match.group(2))
            return arguments[index] if index < len(arguments) else ""
        return all_arguments

    return re.sub(
        r"\$ARGUMENTS(?:\[(\d+)\])?|\$(\d+)",
        replace_placeholder,
        skill_body,
    )


def discover_skills(skills_dir):
    skill_files = sorted(skills_dir.glob("*/SKILL.md"))
    skills = {}
    for skill_file in skill_files:
        skill = read_skill(skill_file)
        if skill.name in skills:
            raise ValueError(f"Duplicate skill name {skill.name!r}: {skill_file}")
        skills[skill.name] = skill
    return skills


def prepare_messages(prompt, skills=None):
    stripped_prompt = prompt.strip()
    skills_dir = Path.cwd() / ".claude" / "skills"
    if skills is None:
        skills = discover_skills(skills_dir)

    skill_list = "\n".join(
        f"- {skill.name}: {skill.description}"
        for skill in skills.values()
    )
    skills_by_directory = {
        skill.directory_name: skill for skill in skills.values()
    }
    messages = []
    if skills:
        messages.append({
            "role": "system",
            "content": (
                f"You have access to the following skills:\n\n{skill_list}\n\n"
                "If a skill matches the user's request, call the Skill tool "
                "with its name and follow the instructions it returns."
            ),
        })

    if not stripped_prompt.startswith("/"):
        messages.append({"role": "user", "content": prompt})
        return messages

    prompt_tokens = stripped_prompt.split()
    expanded_skills = []
    argument_start = 0
    for index, token in enumerate(prompt_tokens):
        if not token.startswith("/"):
            break
        command = token[1:]
        selected = skills_by_directory.get(command)
        if selected is None:
            if not expanded_skills:
                if not command:
                    raise ValueError("A skill name is required after '/'")
                raise FileNotFoundError(
                    f"Skill {command!r} not found in {skills_dir}")
            break
        expanded_skills.append(selected)
        argument_start = index + 1

    arguments = prompt_tokens[argument_start:]
    for skill in expanded_skills:
        skill_body = substitute_skill_arguments(skill.body, arguments)
        messages.append({"role": "user", "content": skill_body})
    return messages


def execute_tool(client, skills, tool_name, arguments):
    if tool_name == "Read":
        file_path = arguments["file_path"]
        try:
            return Path(file_path).read_text(encoding="utf-8")
        except OSError as error:
            return f"Error reading file {file_path}: {error}"

    if tool_name == "Write":
        file_path = arguments["file_path"]
        try:
            Path(file_path).write_text(arguments["content"], encoding="utf-8")
            return f"Successfully wrote to {file_path}"
        except OSError as error:
            return f"Error writing file {file_path}: {error}"

    if tool_name == "Bash":
        try:
            command_result = subprocess.run(
                arguments["command"],
                shell=True,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            return f"Error executing command: {error}"

        output = []
        if command_result.stdout:
            output.append(f"stdout:\n{command_result.stdout}")
        if command_result.stderr:
            output.append(f"stderr:\n{command_result.stderr}")
        if command_result.returncode != 0:
            output.append(f"Command exited with status {command_result.returncode}")
        return "\n".join(output) or "Command completed with no output."

    if tool_name == "Skill":
        skill_name = arguments["name"]
        skill = skills.get(skill_name)
        if skill is None:
            return f"Error: skill {skill_name!r} not found"

        skill_body = substitute_skill_arguments(
            skill.body,
            arguments.get("args", "").split(),
        )
        if skill.context != "fork":
            return skill_body

        subagent_answer = run_agent(
            client,
            skills,
            [{"role": "user", "content": skill_body}],
        )
        return (
            f"Skill {skill_name} ran in a separate context "
            f"and returned: {subagent_answer}"
        )

    return f"Error: unsupported tool {tool_name!r}"


def run_agent(client, skills, messages):
    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
        )

        if not response.choices:
            raise RuntimeError("no choices in response")

        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            return message.content or ""

        for tool_call in message.tool_calls:
            if tool_call.type != "function":
                result = f"Error: unsupported tool call type {tool_call.type!r}"
            else:
                function = tool_call.function
                result = execute_tool(
                    client,
                    skills,
                    function.name,
                    json.loads(function.arguments),
                )

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })


def main():
    p = argparse.ArgumentParser()
    p.add_argument("-p", required=True)
    args = p.parse_args()

    if not API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    skills = discover_skills(Path.cwd() / ".claude" / "skills")
    messages = prepare_messages(args.p, skills)
    answer = run_agent(client, skills, messages)
    sys.stdout.write(answer)


if __name__ == "__main__":
    main()
