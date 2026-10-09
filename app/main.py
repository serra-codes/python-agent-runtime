import argparse
import json
import os
import subprocess
import sys

from openai import OpenAI

API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL",
                     default="https://openrouter.ai/api/v1")


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
    messages = [{"role": "user", "content": args.p}]

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
