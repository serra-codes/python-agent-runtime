import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from openai import OpenAI

API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL",
                     default="https://openrouter.ai/api/v1")


def parse_skill_metadata(frontmatter, path):
    metadata = {}
    for line in frontmatter.splitlines():
        key, delimiter, value = line.partition(":")
        if delimiter and key.strip() in {"name", "description"}:
            metadata[key.strip()] = value.strip().strip("'\"")

    if not metadata.get("name") or not metadata.get("description"):
        raise ValueError(f"Skill file must define name and description: {path}")

    return metadata


def read_skill_metadata(path):
    with path.open(encoding="utf-8") as skill_file:
        if skill_file.readline().strip() != "---":
            raise ValueError(f"Skill file is missing YAML frontmatter: {path}")

        frontmatter = []
        for line in skill_file:
            if line.strip() == "---":
                return parse_skill_metadata("".join(frontmatter), path)
            frontmatter.append(line)

    raise ValueError(f"Skill file has unterminated YAML frontmatter: {path}")


def read_skill_body(path):
    with path.open(encoding="utf-8") as skill_file:
        if skill_file.readline().strip() != "---":
            raise ValueError(f"Skill file is missing YAML frontmatter: {path}")

        for line in skill_file:
            if line.strip() == "---":
                return skill_file.read().strip()

    raise ValueError(f"Skill file has unterminated YAML frontmatter: {path}")


def prepare_messages(prompt):
    stripped_prompt = prompt.strip()
    skills_dir = Path.cwd() / ".claude" / "skills"
    skill_files = sorted(skills_dir.glob("*/SKILL.md"))
    skills = []
    for skill_file in skill_files:
        metadata = read_skill_metadata(skill_file)
        skills.append((skill_file, metadata))

    skill_list = "\n".join(
        f"- {metadata['name']}: {metadata['description']}"
        for _, metadata in skills
    )
    messages = []
    if skills:
        messages.append({
            "role": "system",
            "content": f"You have access to the following skills:\n\n{skill_list}",
        })

    if not stripped_prompt.startswith("/"):
        messages.append({"role": "user", "content": prompt})
        return messages

    command_parts = stripped_prompt[1:].split(maxsplit=1)
    if not command_parts:
        raise ValueError("A skill name is required after '/'")
    command = command_parts[0]
    selected = next(
        (item for item in skills if item[0].parent.name == command),
        None,
    )
    if selected is None:
        raise FileNotFoundError(
            f"Skill {command!r} not found in {skills_dir}")

    skill_file, _ = selected
    skill_body = read_skill_body(skill_file)
    messages.append({"role": "user", "content": skill_body})
    return messages


def main():
    p = argparse.ArgumentParser()
    p.add_argument("-p", required=True)
    args = p.parse_args()

    if not API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    tools = [{
        "type": "function",
        "function": {
            "name": "Read",
            "description": "Read and return the contents of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The path to the file to read"
                    }
                },
                "required": ["file_path"]
            }
        }
    }, {
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
                        "description": "The path of the file to write to"
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write to the file"
                    }
                }
            }
        }
    }, {
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
                        "description": "The shell command to execute"
                    }
                }
            }
        }
    }]
    messages = prepare_messages(args.p)

    while True:
        response = client.chat.completions.create(
            model="anthropic/claude-haiku-4.5",
            messages=messages,
            tools=tools,
        )

        if not response.choices:
            raise RuntimeError("no choices in response")

        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            if message.content is not None:
                sys.stdout.write(message.content)
            return

        for tool_call in message.tool_calls:
            if tool_call.type != "function":
                result = f"Error: unsupported tool call type {tool_call.type!r}"
            else:
                function = tool_call.function
                arguments = json.loads(function.arguments)
                if function.name == "Read":
                    file_path = arguments["file_path"]
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            result = f.read()
                    except OSError as e:
                        result = f"Error reading file {file_path}: {e}"
                elif function.name == "Write":
                    file_path = arguments["file_path"]
                    try:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(arguments["content"])
                        result = f"Successfully wrote to {file_path}"
                    except OSError as e:
                        result = f"Error writing file {file_path}: {e}"
                elif function.name == "Bash":
                    try:
                        command_result = subprocess.run(
                            arguments["command"],
                            shell=True,
                            capture_output=True,
                            text=True,
                        )
                        output = []
                        if command_result.stdout:
                            output.append(f"stdout:\n{command_result.stdout}")
                        if command_result.stderr:
                            output.append(f"stderr:\n{command_result.stderr}")
                        if command_result.returncode != 0:
                            output.append(
                                f"Command exited with status "
                                f"{command_result.returncode}")
                        result = "\n".join(output) or "Command completed with no output."
                    except OSError as e:
                        result = f"Error executing command: {e}"
                else:
                    result = f"Error: unsupported tool {function.name!r}"

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })


if __name__ == "__main__":
    main()
