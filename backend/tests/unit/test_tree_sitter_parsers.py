from app.services.parser.chunker import CodeChunker
from app.services.parser.languages import SupportedLanguage, language_registry


def test_language_detection():
    assert language_registry.detect_language("src/index.ts") == SupportedLanguage.TYPESCRIPT
    assert language_registry.detect_language("src/App.tsx") == SupportedLanguage.TSX
    assert language_registry.detect_language("backend/main.py") == SupportedLanguage.PYTHON
    assert language_registry.detect_language("docs/README.md") == SupportedLanguage.MARKDOWN
    assert language_registry.detect_language("package.json") == SupportedLanguage.JSON
    assert language_registry.detect_language("docker-compose.yml") == SupportedLanguage.YAML
    assert language_registry.detect_language("Makefile") == SupportedLanguage.UNKNOWN


def test_python_ast_parsing_and_chunking():
    py_code = """import os
from typing import Optional
from app.core import config

class AuthenticationService:
    def __init__(self, key: str):
        self.key = key

    async def validate_session(self, token: str) -> bool:
        if not token:
            return False
        return True

def top_level_helper(x: int) -> int:
    return x * 2
"""
    result = CodeChunker.parse_and_chunk_file("app/services/auth.py", py_code)

    assert result.language == "python"
    assert len(result.chunks) >= 3

    # Verify dependencies extracted
    dep_paths = [d.imported_path for d in result.dependencies]
    assert "os" in dep_paths
    assert "typing" in dep_paths
    assert "app.core" in dep_paths

    # Verify symbol chunks
    symbols = [c.symbol_name for c in result.chunks if c.symbol_name]
    assert "AuthenticationService" in symbols
    assert "validate_session" in symbols
    assert "top_level_helper" in symbols

    # Verify context header
    auth_chunk = next(c for c in result.chunks if c.symbol_name == "validate_session")
    assert (
        "# File: app/services/auth.py | Scope: AuthenticationService | Method: validate_session"
        in auth_chunk.context_header
    )


def test_typescript_ast_parsing_and_chunking():
    ts_code = """import { useState, useEffect } from 'react';
import axios from 'axios';

export interface UserProfile {
    id: string;
    username: string;
}

export class UserManager {
    private users: UserProfile[] = [];

    public async fetchUser(id: string): Promise<UserProfile | null> {
        return this.users.find(u => u.id === id) || null;
    }
}

export function formatName(name: string): string {
    return name.trim();
}
"""
    result = CodeChunker.parse_and_chunk_file("src/services/user.ts", ts_code)

    assert result.language == "typescript"
    assert len(result.chunks) >= 3

    # Check dependencies
    dep_paths = [d.imported_path for d in result.dependencies]
    assert "react" in dep_paths
    assert "axios" in dep_paths

    # Check interface and class symbols
    symbols = [c.symbol_name for c in result.chunks if c.symbol_name]
    assert "UserProfile" in symbols
    assert "UserManager" in symbols
    assert "fetchUser" in symbols
    assert "formatName" in symbols

    # Check context header
    ts_chunk = next(c for c in result.chunks if c.symbol_name == "fetchUser")
    assert (
        "// File: src/services/user.ts | Scope: UserManager | Method: fetchUser"
        in ts_chunk.context_header
    )


def test_markdown_ast_parsing_and_chunking():
    md_code = """# Forge AI Overview

Forge AI is an autonomous engineering platform.

## Architecture

We use PostgreSQL with pgvector and Next.js 15.

### Background Jobs

ARQ handles all queueing.
"""
    result = CodeChunker.parse_and_chunk_file("docs/overview.md", md_code)
    assert result.language == "markdown"
    assert len(result.chunks) >= 2


def test_json_and_yaml_parsing():
    json_code = '{\n  "name": "forgeai",\n  "version": "1.0.0"\n}'
    json_res = CodeChunker.parse_and_chunk_file("package.json", json_code)
    assert json_res.language == "json"
    assert len(json_res.chunks) >= 1

    yaml_code = "services:\n  api:\n    image: forgeai-api\n"
    yaml_res = CodeChunker.parse_and_chunk_file("docker-compose.yml", yaml_code)
    assert yaml_res.language == "yaml"
    assert len(yaml_res.chunks) >= 1
