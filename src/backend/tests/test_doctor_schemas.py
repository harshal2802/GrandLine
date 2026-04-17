"""Tests for Doctor Agent Pydantic schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.doctor import (
    DoctorOutputSpec,
    HealthCheckSpec,
    ValidateCodeRequest,
)


class TestHealthCheckSpec:
    def test_accepts_valid_pytest(self) -> None:
        spec = HealthCheckSpec(
            phase_number=1,
            file_path="tests/test_auth.py",
            content="def test_login(): assert False",
            framework="pytest",
        )
        assert spec.framework == "pytest"

    def test_accepts_valid_vitest(self) -> None:
        spec = HealthCheckSpec(
            phase_number=1,
            file_path="src/auth.test.ts",
            content="test('login', () => { expect(true).toBe(false) })",
            framework="vitest",
        )
        assert spec.framework == "vitest"

    def test_rejects_phase_number_below_one(self) -> None:
        with pytest.raises(ValidationError):
            HealthCheckSpec(
                phase_number=0,
                file_path="tests/x.py",
                content="pass",
            )

    def test_rejects_empty_file_path(self) -> None:
        with pytest.raises(ValidationError):
            HealthCheckSpec(
                phase_number=1,
                file_path="",
                content="pass",
            )

    def test_rejects_empty_content(self) -> None:
        with pytest.raises(ValidationError):
            HealthCheckSpec(
                phase_number=1,
                file_path="tests/x.py",
                content="",
            )

    def test_rejects_invalid_framework(self) -> None:
        with pytest.raises(ValidationError):
            HealthCheckSpec(
                phase_number=1,
                file_path="tests/x.py",
                content="pass",
                framework="mocha",  # type: ignore[arg-type]
            )

    def test_defaults_framework_to_pytest(self) -> None:
        spec = HealthCheckSpec(
            phase_number=1,
            file_path="tests/x.py",
            content="pass",
        )
        assert spec.framework == "pytest"

    def test_rejects_absolute_file_path(self) -> None:
        with pytest.raises(ValidationError, match="relative"):
            HealthCheckSpec(
                phase_number=1,
                file_path="/etc/passwd",
                content="pass",
            )

    def test_rejects_path_traversal(self) -> None:
        with pytest.raises(ValidationError, match="traversal"):
            HealthCheckSpec(
                phase_number=1,
                file_path="../../etc/passwd",
                content="pass",
            )

    def test_rejects_nested_path_traversal(self) -> None:
        with pytest.raises(ValidationError, match="traversal"):
            HealthCheckSpec(
                phase_number=1,
                file_path="tests/../../etc/passwd",
                content="pass",
            )

    def test_accepts_nested_relative_path(self) -> None:
        spec = HealthCheckSpec(
            phase_number=1,
            file_path="tests/unit/test_auth.py",
            content="pass",
        )
        assert spec.file_path == "tests/unit/test_auth.py"


class TestDoctorOutputSpec:
    def test_rejects_empty_health_checks(self) -> None:
        with pytest.raises(ValidationError):
            DoctorOutputSpec(health_checks=[])

    def test_rejects_duplicate_file_paths(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate file_path"):
            DoctorOutputSpec(
                health_checks=[
                    HealthCheckSpec(phase_number=1, file_path="tests/x.py", content="a"),
                    HealthCheckSpec(phase_number=2, file_path="tests/x.py", content="b"),
                ]
            )

    def test_accepts_multi_phase_output(self) -> None:
        spec = DoctorOutputSpec(
            health_checks=[
                HealthCheckSpec(phase_number=1, file_path="tests/a.py", content="a"),
                HealthCheckSpec(phase_number=2, file_path="tests/b.py", content="b"),
            ]
        )
        assert len(spec.health_checks) == 2


class TestValidateCodeRequest:
    def test_rejects_empty_files(self) -> None:
        with pytest.raises(ValidationError):
            ValidateCodeRequest(files={})

    def test_accepts_files_dict(self) -> None:
        req = ValidateCodeRequest(files={"src/main.py": "print('hi')"})
        assert "src/main.py" in req.files

    def test_rejects_absolute_path_in_files(self) -> None:
        with pytest.raises(ValidationError, match="relative"):
            ValidateCodeRequest(files={"/etc/passwd": "bad"})

    def test_rejects_path_traversal_in_files(self) -> None:
        with pytest.raises(ValidationError, match="traversal"):
            ValidateCodeRequest(files={"../../etc/passwd": "bad"})
