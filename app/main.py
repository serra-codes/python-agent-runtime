import argparse
import json
import os
import sys

from openai import OpenAI, chat

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

    chat = client.chat.completions.create(
        model="anthropic/claude-haiku-4.5",
        messages=[{"role": "user", "content": args.p}],
        tools=[{
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
        }]
    )

    if not chat.choices:
        raise RuntimeError("no choices in response")

    message = chat.choices[0].message

    if message.tool_calls:
        tool_call = message.tool_calls[0]
        if getattr(tool_call, "type", None) == "function":
            function = getattr(tool_call, "function", None)
            if function is not None and getattr(function, "name", None) == "Read":
                arguments = getattr(function, "arguments", {})
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                file_path = arguments["file_path"]
                try:
                    with open(file_path, "r") as f:
                        file_contents = f.read()
                    print(f"{file_contents}")
                except Exception as e:
                    print(
                        f"Error reading file {file_path}: {e}", file=sys.stderr)
            else:
                print("No valid tool call found in the response.", file=sys.stderr)
        else:
            print("No valid tool call found in the response.", file=sys.stderr)
    elif message.content is not None:
        sys.stdout.write(message.content)

    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!", file=sys.stderr)

    # message = chat.choices[0].message
    # [ChatCompletionMessageFunctionToolCall(id='toolu_bdrk_018E8SmwsTrHKnhH1U7VR9M6', function=Function(arguments='{"file_path": "blueberry.py"}', name='Read'), type='function', index=0)]

    # TODO: Uncomment the following line to pass the first stage
    # print(chat.choices[0].message.content)


if __name__ == "__main__":
    main()
