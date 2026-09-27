from enum import StrEnum

import tree_sitter_javascript
import tree_sitter_json
import tree_sitter_markdown
import tree_sitter_python
import tree_sitter_typescript
import tree_sitter_yaml
from tree_sitter import Language, Parser


class SupportedLanguage(StrEnum):
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    TSX = "tsx"
    JAVASCRIPT = "javascript"
    HTML = "html"
    CSS = "css"
    MARKDOWN = "markdown"
    JSON = "json"
    YAML = "yaml"
    SQL = "sql"
    SHELL = "shell"
    TOML = "toml"
    UNKNOWN = "unknown"


EXTENSION_TO_LANGUAGE: dict[str, SupportedLanguage] = {
    ".py": SupportedLanguage.PYTHON,
    ".ts": SupportedLanguage.TYPESCRIPT,
    ".tsx": SupportedLanguage.TSX,
    ".js": SupportedLanguage.JAVASCRIPT,
    ".jsx": SupportedLanguage.JAVASCRIPT,
    ".mjs": SupportedLanguage.JAVASCRIPT,
    ".cjs": SupportedLanguage.JAVASCRIPT,
    ".html": SupportedLanguage.HTML,
    ".htm": SupportedLanguage.HTML,
    ".css": SupportedLanguage.CSS,
    ".scss": SupportedLanguage.CSS,
    ".sass": SupportedLanguage.CSS,
    ".less": SupportedLanguage.CSS,
    ".md": SupportedLanguage.MARKDOWN,
    ".mdx": SupportedLanguage.MARKDOWN,
    ".json": SupportedLanguage.JSON,
    ".yaml": SupportedLanguage.YAML,
    ".yml": SupportedLanguage.YAML,
    ".sql": SupportedLanguage.SQL,
    ".sh": SupportedLanguage.SHELL,
    ".bash": SupportedLanguage.SHELL,
    ".zsh": SupportedLanguage.SHELL,
    ".toml": SupportedLanguage.TOML,
}


class LanguageRegistry:
    """Registry maintaining initialized Tree-sitter Language and Parser instances."""

    def __init__(self) -> None:
        self._parsers: dict[SupportedLanguage, Parser] = {}
        self._init_parsers()

    def _init_parsers(self) -> None:
        self._parsers[SupportedLanguage.PYTHON] = Parser(Language(tree_sitter_python.language()))
        self._parsers[SupportedLanguage.TYPESCRIPT] = Parser(
            Language(tree_sitter_typescript.language_typescript())
        )
        self._parsers[SupportedLanguage.TSX] = Parser(
            Language(tree_sitter_typescript.language_tsx())
        )
        self._parsers[SupportedLanguage.JAVASCRIPT] = Parser(
            Language(tree_sitter_javascript.language())
        )
        self._parsers[SupportedLanguage.MARKDOWN] = Parser(
            Language(tree_sitter_markdown.language())
        )
        self._parsers[SupportedLanguage.JSON] = Parser(Language(tree_sitter_json.language()))
        self._parsers[SupportedLanguage.YAML] = Parser(Language(tree_sitter_yaml.language()))

    def detect_language(self, file_path: str) -> SupportedLanguage:
        """Detects supported language from file path extension."""
        import os

        _, ext = os.path.splitext(file_path.lower())
        return EXTENSION_TO_LANGUAGE.get(ext, SupportedLanguage.UNKNOWN)

    def get_parser(self, language: SupportedLanguage) -> Parser | None:
        """Returns the initialized Tree-sitter Parser for a given language."""
        return self._parsers.get(language)


language_registry = LanguageRegistry()
