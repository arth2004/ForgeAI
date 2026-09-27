from dataclasses import dataclass

from app.models.codebase import ChunkType
from app.services.parser.languages import language_registry
from app.services.parser.symbols import ExtractedDependency, ExtractedSymbol, SymbolExtractor


@dataclass
class ParsedChunk:
    chunk_index: int
    chunk_type: ChunkType
    symbol_name: str | None
    start_line: int
    end_line: int
    content: str
    context_header: str
    token_count: int


@dataclass
class FileParseResult:
    file_path: str
    language: str
    chunks: list[ParsedChunk]
    dependencies: list[ExtractedDependency]
    total_tokens: int


class CodeChunker:
    """AST-bounded semantic code chunker with context header injection."""

    MAX_CHUNK_TOKENS: int = 800
    SLIDING_WINDOW_TOKENS: int = 600
    SLIDING_WINDOW_OVERLAP: int = 100

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """Heuristic token count estimation (~4 characters per token)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    @classmethod
    def format_context_header(
        cls,
        file_path: str,
        symbol: ExtractedSymbol | None = None,
        part_suffix: str = "",
    ) -> str:
        """Formats the context header prepended to the chunk text."""
        parts = [f"File: {file_path}"]
        if symbol:
            if symbol.parent_scope:
                parts.append(f"Scope: {symbol.parent_scope}")
            if symbol.name:
                sym_label = symbol.symbol_type.value.capitalize()
                parts.append(f"{sym_label}: {symbol.name}")

        header_str = " | ".join(parts)
        if part_suffix:
            header_str += f" {part_suffix}"

        # Choose comment syntax based on file extension
        if file_path.endswith((".py", ".yaml", ".yml", ".sh", ".bash", ".zsh", ".toml")):
            return f"# {header_str}\n"
        elif file_path.endswith((".md", ".mdx", ".html", ".htm")):
            return f"<!-- {header_str} -->\n"
        elif file_path.endswith((".css", ".scss", ".sass", ".less", ".sql")):
            return f"/* {header_str} */\n"
        else:
            return f"// {header_str}\n"

    @classmethod
    def parse_and_chunk_file(
        cls,
        file_path: str,
        content: str,
    ) -> FileParseResult:
        """Parses a file with Tree-sitter (or fallback) and generates semantic chunks."""
        language_enum = language_registry.detect_language(file_path)
        parser = language_registry.get_parser(language_enum)

        lines = content.splitlines(keepends=True)
        len(lines)

        chunks: list[ParsedChunk] = []
        dependencies: list[ExtractedDependency] = []

        if parser and content.strip():
            try:
                tree = parser.parse(content.encode("utf-8"))
                symbols, dependencies = SymbolExtractor.extract_symbols_and_dependencies(
                    tree.root_node, content, language_enum
                )
                chunks = cls._chunk_with_ast_symbols(file_path, content, lines, symbols)
            except Exception:
                # If AST parsing fails unexpectedly, fallback to sliding line chunker
                chunks = cls._chunk_by_sliding_lines(file_path, lines)
        else:
            # Fallback for plain text / unknown extensions
            chunks = cls._chunk_by_sliding_lines(file_path, lines)

        total_tokens = sum(c.token_count for c in chunks)

        return FileParseResult(
            file_path=file_path,
            language=language_enum.value,
            chunks=chunks,
            dependencies=dependencies,
            total_tokens=total_tokens,
        )

    @classmethod
    def _chunk_with_ast_symbols(
        cls,
        file_path: str,
        content: str,
        lines: list[str],
        symbols: list[ExtractedSymbol],
    ) -> list[ParsedChunk]:
        chunks: list[ParsedChunk] = []
        covered_lines: set[int] = set()

        # Sort symbols by start line
        symbols = sorted(symbols, key=lambda s: (s.start_line, s.end_line))

        for symbol in symbols:
            # Check for overlapping sub-methods if class already processed
            sym_lines = lines[symbol.start_line - 1 : symbol.end_line]
            sym_content = "".join(sym_lines)
            sym_tokens = cls.estimate_tokens(sym_content)

            header = cls.format_context_header(file_path, symbol)
            header_tokens = cls.estimate_tokens(header)

            if sym_tokens + header_tokens <= cls.MAX_CHUNK_TOKENS:
                chunks.append(
                    ParsedChunk(
                        chunk_index=len(chunks),
                        chunk_type=symbol.symbol_type,
                        symbol_name=symbol.name,
                        start_line=symbol.start_line,
                        end_line=symbol.end_line,
                        content=sym_content,
                        context_header=header.strip(),
                        token_count=sym_tokens + header_tokens,
                    )
                )
                covered_lines.update(range(symbol.start_line, symbol.end_line + 1))
            else:
                # Oversized symbol: split into sliding sub-chunks
                sub_chunks = cls._split_oversized_symbol(file_path, symbol, sym_lines, len(chunks))
                chunks.extend(sub_chunks)
                covered_lines.update(range(symbol.start_line, symbol.end_line + 1))

        # Check for uncovered top-level blocks (e.g. imports, global constants, module statements)
        uncovered_ranges: list[tuple[int, int]] = []
        current_start: int | None = None

        for line_num in range(1, len(lines) + 1):
            if line_num not in covered_lines:
                if current_start is None:
                    current_start = line_num
            else:
                if current_start is not None:
                    uncovered_ranges.append((current_start, line_num - 1))
                    current_start = None

        if current_start is not None:
            uncovered_ranges.append((current_start, len(lines)))

        for u_start, u_end in uncovered_ranges:
            u_lines = lines[u_start - 1 : u_end]
            u_content = "".join(u_lines)
            if u_content.strip():
                header = cls.format_context_header(file_path, None)
                h_tokens = cls.estimate_tokens(header)
                u_tokens = cls.estimate_tokens(u_content)

                if u_tokens + h_tokens <= cls.MAX_CHUNK_TOKENS:
                    chunks.append(
                        ParsedChunk(
                            chunk_index=len(chunks),
                            chunk_type=ChunkType.MODULE if u_start == 1 else ChunkType.BLOCK,
                            symbol_name=None,
                            start_line=u_start,
                            end_line=u_end,
                            content=u_content,
                            context_header=header.strip(),
                            token_count=u_tokens + h_tokens,
                        )
                    )
                else:
                    # Split oversized uncovered blocks
                    sub_chunks = cls._split_oversized_lines(
                        file_path, u_lines, u_start, len(chunks)
                    )
                    chunks.extend(sub_chunks)

        # Re-sort chunks strictly by start line and re-index
        chunks = sorted(chunks, key=lambda c: (c.start_line, c.end_line))
        for idx, chunk in enumerate(chunks):
            chunk.chunk_index = idx

        return chunks

    @classmethod
    def _split_oversized_symbol(
        cls,
        file_path: str,
        symbol: ExtractedSymbol,
        lines: list[str],
        start_index: int,
    ) -> list[ParsedChunk]:
        chunks: list[ParsedChunk] = []
        total_lines = len(lines)
        window_line_size = max(10, total_lines // max(2, (len(lines) // 40)))
        step = max(5, window_line_size - 10)

        current_line_offset = 0
        part = 1

        while current_line_offset < total_lines:
            end_offset = min(total_lines, current_line_offset + window_line_size)
            chunk_lines = lines[current_line_offset:end_offset]
            chunk_content = "".join(chunk_lines)

            suffix = f"[Part {part}]"
            header = cls.format_context_header(file_path, symbol, part_suffix=suffix)
            token_count = cls.estimate_tokens(chunk_content) + cls.estimate_tokens(header)

            chunks.append(
                ParsedChunk(
                    chunk_index=start_index + len(chunks),
                    chunk_type=symbol.symbol_type,
                    symbol_name=symbol.name,
                    start_line=symbol.start_line + current_line_offset,
                    end_line=symbol.start_line + end_offset - 1,
                    content=chunk_content,
                    context_header=header.strip(),
                    token_count=token_count,
                )
            )

            if end_offset >= total_lines:
                break

            current_line_offset += step
            part += 1

        return chunks

    @classmethod
    def _split_oversized_lines(
        cls,
        file_path: str,
        lines: list[str],
        base_line_num: int,
        start_index: int,
    ) -> list[ParsedChunk]:
        chunks: list[ParsedChunk] = []
        total_lines = len(lines)
        window_size = 50
        step = 40

        curr = 0
        part = 1
        while curr < total_lines:
            end = min(total_lines, curr + window_size)
            chunk_lines = lines[curr:end]
            chunk_content = "".join(chunk_lines)

            suffix = f"[Part {part}]" if total_lines > window_size else ""
            header = cls.format_context_header(file_path, None, part_suffix=suffix)
            token_count = cls.estimate_tokens(chunk_content) + cls.estimate_tokens(header)

            chunks.append(
                ParsedChunk(
                    chunk_index=start_index + len(chunks),
                    chunk_type=ChunkType.BLOCK,
                    symbol_name=None,
                    start_line=base_line_num + curr,
                    end_line=base_line_num + end - 1,
                    content=chunk_content,
                    context_header=header.strip(),
                    token_count=token_count,
                )
            )

            if end >= total_lines:
                break
            curr += step
            part += 1

        return chunks

    @classmethod
    def _chunk_by_sliding_lines(
        cls,
        file_path: str,
        lines: list[str],
    ) -> list[ParsedChunk]:
        """Fallback line-based sliding chunker for non-AST files."""
        chunks: list[ParsedChunk] = []
        total_lines = len(lines)
        if total_lines == 0:
            return chunks

        window_size = 60
        step = 45
        curr = 0
        part = 1

        while curr < total_lines:
            end = min(total_lines, curr + window_size)
            chunk_lines = lines[curr:end]
            chunk_content = "".join(chunk_lines)

            suffix = f"[Part {part}]" if total_lines > window_size else ""
            header = cls.format_context_header(file_path, None, part_suffix=suffix)
            token_count = cls.estimate_tokens(chunk_content) + cls.estimate_tokens(header)

            chunks.append(
                ParsedChunk(
                    chunk_index=len(chunks),
                    chunk_type=ChunkType.BLOCK,
                    symbol_name=None,
                    start_line=curr + 1,
                    end_line=end,
                    content=chunk_content,
                    context_header=header.strip(),
                    token_count=token_count,
                )
            )

            if end >= total_lines:
                break
            curr += step
            part += 1

        return chunks
