import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.main import (
    discover_skills,
    execute_tool,
    prepare_messages,
    substitute_skill_arguments,
)


def write_skill(
    skills_dir,
    name,
    description,
    body,
    context=None,
    directory=None,
):
    skill_dir = skills_dir / (directory or name)
    skill_dir.mkdir(parents=True)
    context_line = f"context: {context}\n" if context else ""
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n"
        f"{context_line}---\n{body}",
        encoding="utf-8",
    )


class SkillArgumentTests(unittest.TestCase):
    def test_substitutes_all_argument_placeholder_forms(self):
        result = substitute_skill_arguments(
            "$ARGUMENTS / $ARGUMENTS[1] / $0 / $2",
            ["staging", "eu-west"],
        )

        self.assertEqual(result, "staging eu-west / eu-west / staging / ")

    def test_missing_indexed_arguments_are_empty(self):
        self.assertEqual(
            substitute_skill_arguments("$ARGUMENTS[0] $0", []),
            " ",
        )


class SkillMessageTests(unittest.TestCase):
    def test_stacks_known_skills_and_passes_shared_arguments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_dir = Path(temp_dir)
            write_skill(skills_dir, "apple", "Apple task", "apple-$ARGUMENTS")
            write_skill(skills_dir, "grape", "Grape task", "grape-$ARGUMENTS")
            skills = discover_skills(skills_dir)

            messages = prepare_messages("/apple /grape 4127", skills)

        self.assertEqual(messages[1]["content"], "apple-4127")
        self.assertEqual(messages[2]["content"], "grape-4127")

    def test_unknown_skill_token_ends_the_stack(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_dir = Path(temp_dir)
            write_skill(skills_dir, "apple", "Apple task", "apple-$ARGUMENTS")
            skills = discover_skills(skills_dir)

            messages = prepare_messages("/apple /pear 4127", skills)

        self.assertEqual(messages[1]["content"], "apple-/pear 4127")

    def test_slash_commands_keep_using_the_skill_directory_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_dir = Path(temp_dir)
            write_skill(
                skills_dir,
                "apple",
                "Apple task",
                "Do apple task",
                directory="apple-folder",
            )
            skills = discover_skills(skills_dir)

            messages = prepare_messages("/apple-folder", skills)

        self.assertEqual(messages[1]["content"], "Do apple task")

    def test_catalog_is_in_system_prompt_for_plain_language_requests(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_dir = Path(temp_dir)
            write_skill(skills_dir, "apple", "Apple task", "Do apple task")
            skills = discover_skills(skills_dir)

            messages = prepare_messages("Please do the apple task", skills)

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("- apple: Apple task", messages[0]["content"])
        self.assertIn("call the Skill tool", messages[0]["content"])
        self.assertEqual(messages[1]["content"], "Please do the apple task")


class ForkedSkillTests(unittest.TestCase):
    def test_runs_forked_skill_with_only_its_body(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_dir = Path(temp_dir)
            write_skill(
                skills_dir,
                "apple",
                "Apple task",
                "Return $0",
                context="fork",
            )
            skills = discover_skills(skills_dir)

            captured = {}

            def create_completion(**kwargs):
                captured.update({
                    **kwargs,
                    "messages": [dict(message) for message in kwargs["messages"]],
                })
                message = SimpleNamespace(
                    tool_calls=None,
                    content="blueberry",
                    model_dump=lambda exclude_none: {
                        "role": "assistant",
                        "content": "blueberry",
                    },
                )
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=message)]
                )

            client = SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(create=create_completion)
                )
            )
            result = execute_tool(
                client,
                skills,
                "Skill",
                {"name": "apple", "args": "blueberry"},
            )

        self.assertEqual(captured["messages"], [
            {"role": "user", "content": "Return blueberry"}
        ])
        self.assertIn("returned: blueberry", result)


if __name__ == "__main__":
    unittest.main()
