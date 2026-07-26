import ast
import unittest
from pathlib import Path


class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        self.source = self.root / "src" / "context_auditor"

    def test_domain_does_not_import_infrastructure(self):
        forbidden = ("context_auditor.adapters", "context_auditor.application")
        for path in (self.source / "domain").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = imported_modules(tree)
            self.assertFalse(
                any(item.startswith(forbidden) for item in imports),
                f"Forbidden dependency in {path}",
            )

    def test_application_does_not_import_concrete_adapters(self):
        for path in (self.source / "application").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("context_auditor.adapters.providers", text)
            self.assertNotIn("context_auditor.adapters.frameworks", text)

    def test_no_python_business_code_at_project_root(self):
        self.assertEqual(list(self.root.glob("*.py")), [])

    def test_root_contains_no_word_or_pdf(self):
        self.assertEqual(list(self.root.glob("*.docx")), [])
        self.assertEqual(list(self.root.glob("*.pdf")), [])


def imported_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


if __name__ == "__main__":
    unittest.main()
