"""Tests for Shipwright Agent Pydantic schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.shipwright import (
    BuildArtifactSpec,
    BuildResultResponse,
    ShipwrightOutputSpec,
)


class TestBuildArtifactSpec:
    def test_accepts_valid_python(self) -> None:
        spec = BuildArtifactSpec(
            file_path="app/auth.py",
            content="def login(): ...",
            language="python",
        )
        assert spec.language == "python"

    def test_accepts_valid_typescript(self) -> None:
        spec = BuildArtifactSpec(
            file_path="src/auth.ts",
            content="export function login() {}",
            language="typescript",
        )
        assert spec.language == "typescript"

    def test_rejects_empty_file_path(self) -> None:
        with pytest.raises(ValidationError):
            BuildArtifactSpec(file_path="", content="x")

    def test_rejects_empty_content(self) -> None:
        with pytest.raises(ValidationError):
            BuildArtifactSpec(file_path="a.py", content="")

    def test_rejects_invalid_language(self) -> None:
        with pytest.raises(ValidationError):
            BuildArtifactSpec(
                file_path="a.py",
                content="x",
                language="rust",  # type: ignore[arg-type]
            )

    def test_defaults_language_to_python(self) -> None:
        spec = BuildArtifactSpec(file_path="a.py", content="x")
        assert spec.language == "python"

    def test_rejects_absolute_file_path(self) -> None:
        with pytest.raises(ValidationError, match="relative"):
            BuildArtifactSpec(file_path="/etc/passwd", content="x")

    def test_rejects_path_traversal(self) -> None:
        with pytest.raises(ValidationError, match="traversal"):
            BuildArtifactSpec(file_path="../../etc/passwd", content="x")

    def test_rejects_nested_path_traversal(self) -> None:
        with pytest.raises(ValidationError, match="traversal"):
            BuildArtifactSpec(file_path="app/../../etc/passwd", content="x")

    def test_accepts_nested_relative_path(self) -> None:
        spec = BuildArtifactSpec(file_path="app/auth/handlers.py", content="x")
        assert spec.file_path == "app/auth/handlers.py"

    def test_rejects_drive_scheme_prefix(self) -> None:
        with pytest.raises(ValidationError, match="drive/scheme"):
            BuildArtifactSpec(file_path="C:/windows/system.ini", content="x")


class TestShipwrightOutputSpec:
    def test_rejects_empty_files(self) -> None:
        with pytest.raises(ValidationError):
            ShipwrightOutputSpec(files=[])

    def test_rejects_duplicate_file_paths(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate file_path"):
            ShipwrightOutputSpec(
                files=[
                    BuildArtifactSpec(file_path="a.py", content="x"),
                    BuildArtifactSpec(file_path="a.py", content="y"),
                ]
            )

    def test_accepts_multi_file_output(self) -> None:
        spec = ShipwrightOutputSpec(
            files=[
                BuildArtifactSpec(file_path="a.py", content="x"),
                BuildArtifactSpec(file_path="b.py", content="y"),
            ]
        )
        assert len(spec.files) == 2


class TestBuildResultResponse:
    def test_rejects_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            BuildResultResponse(
                voyage_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
                phase_number=1,
                shipwright_run_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
                status="weird",  # type: ignore[arg-type]
                iteration_count=1,
                passed_count=0,
                failed_count=0,
                total_count=0,
                file_count=0,
                summary="",
            )
