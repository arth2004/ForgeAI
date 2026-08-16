from dataclasses import dataclass

from tree_sitter import Node

from app.models.codebase import ChunkType, DependencyType
from app.services.parser.languages import SupportedLanguage


@dataclass
class ExtractedSymbol:
    name: str
    symbol_type: ChunkType
    start_line: int
    end_line: int
    parent_scope: str | None = None
    node: Node | None = None


@dataclass
class ExtractedDependency:
    imported_path: str
    source_symbol: str | None = None
    target_symbol: str | None = None
    dependency_type: DependencyType = DependencyType.IMPORT


class SymbolExtractor:
    """Extracts symbols, definitions, and dependencies from Tree-sitter AST nodes."""

    @classmethod
    def extract_symbols_and_dependencies(
        cls,
        root_node: Node,
        source_code: str,
        language: SupportedLanguage,
    ) -> tuple[list[ExtractedSymbol], list[ExtractedDependency]]:
        symbols: list[ExtractedSymbol] = []
        dependencies: list[ExtractedDependency] = []
        source_bytes = source_code.encode("utf-8")

        if language == SupportedLanguage.PYTHON:
            cls._extract_python(root_node, source_bytes, symbols, dependencies)
        elif language in (
            SupportedLanguage.TYPESCRIPT,
            SupportedLanguage.TSX,
            SupportedLanguage.JAVASCRIPT,
        ):
            cls._extract_typescript_javascript(root_node, source_bytes, symbols, dependencies)
        elif language == SupportedLanguage.MARKDOWN:
            cls._extract_markdown(root_node, source_bytes, symbols)
        elif language in (SupportedLanguage.JSON, SupportedLanguage.YAML):
            cls._extract_data_structures(root_node, source_bytes, symbols, language)

        return symbols, dependencies

    @classmethod
    def _get_node_text(cls, node: Node, source_bytes: bytes) -> str:
        return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    @classmethod
    def _extract_python(
        cls,
        root_node: Node,
        source_bytes: bytes,
        symbols: list[ExtractedSymbol],
        dependencies: list[ExtractedDependency],
        current_scope: str | None = None,
    ) -> None:
        for child in root_node.children:
            node_type = child.type

            # Imports: `import foo`
            if node_type == "import_statement":
                for alias in child.children:
                    if alias.type in ("dotted_name", "aliased_import"):
                        mod_name = cls._get_node_text(alias, source_bytes)
                        dependencies.append(
                            ExtractedDependency(
                                imported_path=mod_name.split()[0],
                                dependency_type=DependencyType.IMPORT,
                            )
                        )
            # `from module import a, b`
            elif node_type == "import_from_statement":
                module_name = ""
                imported_symbols: list[str] = []
                is_after_import = False

                for sub in child.children:
                    if sub.type == "from":
                        continue
                    elif sub.type == "import":
                        is_after_import = True
                        continue

                    if not is_after_import:
                        if sub.type in ("dotted_name", "relative_import"):
                            module_name = cls._get_node_text(sub, source_bytes)
                    else:
                        if sub.type in ("dotted_name", "identifier"):
                            imported_symbols.append(cls._get_node_text(sub, source_bytes))
                        elif sub.type in ("import_specifier", "aliased_import"):
                            name_node = sub.child_by_field_name("name")
                            if name_node:
                                imported_symbols.append(cls._get_node_text(name_node, source_bytes))
                            else:
                                imported_symbols.append(
                                    cls._get_node_text(sub, source_bytes).split()[0]
                                )

                if module_name:
                    if imported_symbols:
                        for sym in imported_symbols:
                            dependencies.append(
                                ExtractedDependency(
                                    imported_path=module_name,
                                    target_symbol=sym,
                                    dependency_type=DependencyType.IMPORT,
                                )
                            )
                    else:
                        dependencies.append(
                            ExtractedDependency(
                                imported_path=module_name,
                                dependency_type=DependencyType.IMPORT,
                            )
                        )

            # Class definition
            elif node_type == "class_definition":
                name_node = child.child_by_field_name("name")
                class_name = (
                    cls._get_node_text(name_node, source_bytes) if name_node else "AnonymousClass"
                )
                symbols.append(
                    ExtractedSymbol(
                        name=class_name,
                        symbol_type=ChunkType.CLASS,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        parent_scope=current_scope,
                        node=child,
                    )
                )
                body_node = child.child_by_field_name("body")
                if body_node:
                    cls._extract_python(
                        body_node,
                        source_bytes,
                        symbols,
                        dependencies,
                        current_scope=class_name,
                    )

            # Function / Async Function definition
            elif node_type in ("function_definition", "async_function_definition"):
                name_node = child.child_by_field_name("name")
                fn_name = (
                    cls._get_node_text(name_node, source_bytes)
                    if name_node
                    else "anonymous_function"
                )
                sym_type = ChunkType.METHOD if current_scope else ChunkType.FUNCTION
                symbols.append(
                    ExtractedSymbol(
                        name=fn_name,
                        symbol_type=sym_type,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        parent_scope=current_scope,
                        node=child,
                    )
                )

    @classmethod
    def _extract_typescript_javascript(
        cls,
        root_node: Node,
        source_bytes: bytes,
        symbols: list[ExtractedSymbol],
        dependencies: list[ExtractedDependency],
        current_scope: str | None = None,
    ) -> None:
        for child in root_node.children:
            node_type = child.type

            # Imports: `import { x } from 'y'`, `import x from 'y'`
            if node_type == "import_statement":
                source_node = child.child_by_field_name("source")
                path = ""
                if source_node:
                    path = cls._get_node_text(source_node, source_bytes).strip("\"'")
                if path:
                    dependencies.append(
                        ExtractedDependency(
                            imported_path=path,
                            dependency_type=DependencyType.IMPORT,
                        )
                    )

            # Class Declaration
            elif node_type == "class_declaration":
                name_node = child.child_by_field_name("name")
                class_name = (
                    cls._get_node_text(name_node, source_bytes) if name_node else "AnonymousClass"
                )
                symbols.append(
                    ExtractedSymbol(
                        name=class_name,
                        symbol_type=ChunkType.CLASS,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        parent_scope=current_scope,
                        node=child,
                    )
                )
                body = child.child_by_field_name("body")
                if body:
                    cls._extract_typescript_javascript(
                        body, source_bytes, symbols, dependencies, current_scope=class_name
                    )

            # Interface Declaration
            elif node_type == "interface_declaration":
                name_node = child.child_by_field_name("name")
                if_name = (
                    cls._get_node_text(name_node, source_bytes)
                    if name_node
                    else "AnonymousInterface"
                )
                symbols.append(
                    ExtractedSymbol(
                        name=if_name,
                        symbol_type=ChunkType.INTERFACE,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        parent_scope=current_scope,
                        node=child,
                    )
                )

            # Type Alias Declaration
            elif node_type == "type_alias_declaration":
                name_node = child.child_by_field_name("name")
                type_name = (
                    cls._get_node_text(name_node, source_bytes) if name_node else "AnonymousType"
                )
                symbols.append(
                    ExtractedSymbol(
                        name=type_name,
                        symbol_type=ChunkType.TYPE_ALIAS,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        parent_scope=current_scope,
                        node=child,
                    )
                )

            # Function Declaration / Method Definition
            elif node_type in ("function_declaration", "method_definition"):
                name_node = child.child_by_field_name("name")
                fn_name = (
                    cls._get_node_text(name_node, source_bytes)
                    if name_node
                    else "anonymous_function"
                )
                sym_type = ChunkType.METHOD if current_scope else ChunkType.FUNCTION
                symbols.append(
                    ExtractedSymbol(
                        name=fn_name,
                        symbol_type=sym_type,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        parent_scope=current_scope,
                        node=child,
                    )
                )

            # Export Statement wrapping class/function
            elif node_type == "export_statement":
                cls._extract_typescript_javascript(
                    child, source_bytes, symbols, dependencies, current_scope=current_scope
                )

    @classmethod
    def _extract_markdown(
        cls,
        root_node: Node,
        source_bytes: bytes,
        symbols: list[ExtractedSymbol],
    ) -> None:
        for child in root_node.children:
            if child.type == "section":
                # Find heading inside section
                heading_text = "Section"
                for sub in child.children:
                    if sub.type in ("atx_heading", "setext_heading"):
                        heading_text = (
                            cls._get_node_text(sub, source_bytes).split("\n")[0].strip("# ")
                        )
                        break

                symbols.append(
                    ExtractedSymbol(
                        name=heading_text[:200],
                        symbol_type=ChunkType.MARKDOWN_SECTION,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        node=child,
                    )
                )
                # Recurse into nested sections
                cls._extract_markdown(child, source_bytes, symbols)
            elif child.type in ("atx_heading", "setext_heading"):
                heading_text = cls._get_node_text(child, source_bytes).split("\n")[0].strip("# ")
                symbols.append(
                    ExtractedSymbol(
                        name=heading_text[:200],
                        symbol_type=ChunkType.MARKDOWN_SECTION,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        node=child,
                    )
                )

    @classmethod
    def _extract_data_structures(
        cls,
        root_node: Node,
        source_bytes: bytes,
        symbols: list[ExtractedSymbol],
        language: SupportedLanguage,
    ) -> None:
        for child in root_node.children:
            if child.type in ("pair", "block_mapping_pair", "document", "block_node"):
                key_node = child.child_by_field_name("key")
                key_name = cls._get_node_text(key_node, source_bytes) if key_node else "data_block"
                symbols.append(
                    ExtractedSymbol(
                        name=key_name,
                        symbol_type=ChunkType.DATA_BLOCK,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        node=child,
                    )
                )
