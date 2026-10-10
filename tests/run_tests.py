#!/usr/bin/env python3
"""CI test entry point for huaweicloud-mcp monorepo.

This script is designed to be called from CI pipeline (.cloudbuild/buildtest.yml).
It runs pytest across all packages (core + services) with unified coverage collection,
and generates reports compatible with the company's codecov platform.

Usage:
    python tests/run_tests.py

Outputs:
    - test-report.xml: JUnit XML for test results
    - coverage.xml: Cobertura XML for codecov parsing
    - htmlcov/: HTML coverage report for humans
    - ut_cov_html/report.json: Test summary JSON (success count, runtime, etc.)
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory.

    Since this script lives in tests/, the parent is the project root.
    """
    return Path(__file__).resolve().parent.parent


def ensure_test_dependencies(root: Path) -> None:
    """Ensure pytest and pytest-cov are installed.

    In CI, requirements.txt is pre-installed by buildtest.yml.
    For local runs, auto-install missing packages.
    """
    import importlib

    required = ["pytest", "pytest_cov"]
    missing = []
    for pkg in required:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg.replace("_", "-"))

    if not missing:
        return

    print(f"Installing missing test dependencies: {', '.join(missing)}")
    req_file = root / "requirements.txt"
    if req_file.exists():
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file), "-q"],
            check=True,
        )
    else:
        subprocess.run(
            [sys.executable, "-m", "pip", "install"] + missing + ["-q"],
            check=True,
        )



def install_local_packages(root: Path) -> bool:
    """Install local packages in dependency order (core first, then services).

    Returns True if all installations succeed, False otherwise.
    """
    print("=" * 80)
    print("Installing local packages...")
    print("=" * 80)

    # Install core library first (other packages depend on it)
    core_pkg = root / "libs" / "huaweicloud_mcp_core"
    if not core_pkg.exists():
        print(f"ERROR: Core package not found at {core_pkg}")
        return False

    print(f"\n[1/2] Installing {core_pkg.name}...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", str(core_pkg)],
        cwd=str(root),
    )
    if result.returncode != 0:
        print(f"ERROR: Failed to install {core_pkg.name}")
        return False

    # Install service packages
    server_dir = root / "server"
    if not server_dir.exists():
        print(f"WARNING: Server directory not found at {server_dir}, skipping service packages")
        return True

    service_pkgs = sorted([d for d in server_dir.iterdir() if d.is_dir() and (d / "pyproject.toml").exists()])
    if not service_pkgs:
        print("WARNING: No service packages found in server/")
        return True

    for idx, pkg in enumerate(service_pkgs, start=2):
        print(f"\n[{idx}/{len(service_pkgs) + 1}] Installing {pkg.name}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", f"{pkg}[dev]"],
            cwd=str(root),
        )
        if result.returncode != 0:
            print(f"ERROR: Failed to install {pkg.name}")
            return False

    return True


def collect_coverage_paths(root: Path) -> list[str]:
    """Collect source paths for coverage measurement.

    Returns a list of paths relative to project root that should be included
    in coverage reporting.
    """
    cov_paths = []

    # Core library
    core_src = root / "libs" / "huaweicloud_mcp_core" / "src"
    if core_src.exists():
        cov_paths.append(str(core_src.relative_to(root)))

    # Service packages
    server_dir = root / "server"
    if server_dir.exists():
        for pkg_dir in sorted(server_dir.iterdir()):
            if pkg_dir.is_dir() and (pkg_dir / "pyproject.toml").exists():
                src_dir = pkg_dir / "src"
                if src_dir.exists():
                    cov_paths.append(str(src_dir.relative_to(root)))

    return cov_paths


def run_pytest(root: Path, cov_paths: list[str], report_dir: Path) -> int:
    """Run pytest with coverage collection.

    Args:
        root: Project root directory
        cov_paths: List of source paths to measure coverage for
        report_dir: Directory where reports will be written

    Returns:
        pytest exit code (0 = success, non-zero = failure)
    """
    print("\n" + "=" * 80)
    print("Running pytest with coverage...")
    print("=" * 80)

    # Build pytest command
    cmd = [sys.executable, "-m", "pytest"]

    # Add coverage flags for each source path
    for path in cov_paths:
        cmd.extend(["--cov", path])

    # Add report formats
    cmd.extend([
        "--cov-report=term-missing",           # Console output with missing lines
        f"--cov-report=html:{report_dir / 'htmlcov'}",  # HTML report
        f"--cov-report=xml:{report_dir / 'coverage.xml'}",  # XML for codecov
        "--junitxml=test-report.xml",          # JUnit XML for test results
        "-v",                                  # Verbose output
        "libs/",                               # Test directories
        "server/",
    ])

    print(f"\nCommand: {' '.join(cmd)}")
    print(f"\nWorking directory: {root}\n")

    result = subprocess.run(cmd, cwd=str(root))
    return result.returncode


def generate_test_summary(pytest_exit_code: int, report_dir: Path) -> None:
    """Generate a JSON summary of test results.

    This mimics the structure expected by the codecov dashboard (report.json).
    """
    print("\n" + "=" * 80)
    print("Generating test summary...")
    print("=" * 80)

    # Parse JUnit XML if it exists
    junit_xml = report_dir / "test-report.xml"
    test_info = {
        "success": 0,
        "error": 0,
        "fail": 0,
        "skip": 0,
        "all": 0,
        "runtime": 0.0,
    }

    if junit_xml.exists():
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(junit_xml)
            root_elem = tree.getroot()

            # JUnit XML structure: <testsuites> or <testsuite>
            if root_elem.tag == "testsuites":
                testsuites = list(root_elem)
            else:
                testsuites = [root_elem]

            for ts in testsuites:
                if ts.tag == "testsuite":
                    tests = int(ts.get("tests", 0))
                    failures = int(ts.get("failures", 0))
                    errors = int(ts.get("errors", 0))
                    skipped = int(ts.get("skipped", 0))
                    time_str = ts.get("time", "0")

                    test_info["all"] += tests
                    test_info["fail"] += failures
                    test_info["error"] += errors
                    test_info["skip"] += skipped
                    test_info["runtime"] += float(time_str)

            test_info["success"] = test_info["all"] - test_info["fail"] - test_info["error"] - test_info["skip"]

        except Exception as e:
            print(f"WARNING: Failed to parse JUnit XML: {e}")
            # Fallback: assume all tests passed if pytest succeeded
            if pytest_exit_code == 0:
                test_info["success"] = 1
                test_info["all"] = 1

    # Write summary JSON
    summary = {
        "success": test_info["success"],
        "errors": test_info["error"],
        "failures": test_info["fail"],
        "skipped": test_info["skip"],
        "run_time": round(test_info["runtime"], 2),
        "all_case": test_info["all"],
        "cases": [],
        "timestamp": datetime.now().isoformat(),
    }

    summary_file = report_dir / "report.json"
    summary_file.parent.mkdir(parents=True, exist_ok=True)

    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\nTest summary written to: {summary_file}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def main():
    """Main entry point."""
    start_time = datetime.now()

    print("=" * 80)
    print(f"huaweicloud-mcp CI Test Runner")
    print(f"Started at: {start_time.isoformat()}")
    print("=" * 80)

    # Determine project root
    root = get_project_root()
    print(f"\nProject root: {root}")

    # Output directory for reports
    report_dir = root / "ut_cov_html"
    report_dir.mkdir(exist_ok=True)

    # Step 0: Ensure test dependencies (pytest, pytest-cov) are available
    ensure_test_dependencies(root)

    # Step 1: Install local packages
    if not install_local_packages(root):
        print("\nERROR: Package installation failed")
        sys.exit(1)

    # Step 2: Collect coverage paths
    cov_paths = collect_coverage_paths(root)
    if not cov_paths:
        print("\nERROR: No source paths found for coverage measurement")
        sys.exit(1)

    print(f"\nCoverage paths: {', '.join(cov_paths)}")

    # Step 3: Run pytest with coverage
    pytest_exit_code = run_pytest(root, cov_paths, report_dir)

    # Step 4: Generate test summary
    generate_test_summary(pytest_exit_code, report_dir)

    # Step 5: Report final status
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("\n" + "=" * 80)
    print(f"Test run completed at: {end_time.isoformat()}")
    print(f"Duration: {duration:.2f}s")
    print(f"Exit code: {pytest_exit_code}")
    print("=" * 80)

    if pytest_exit_code == 0:
        print("\n✓ All tests passed!")
    else:
        print(f"\n✗ Tests failed with exit code {pytest_exit_code}")

    # Copy coverage.xml to report_dir for codecov compatibility
    coverage_xml = root / "coverage.xml"
    if coverage_xml.exists():
        import shutil
        shutil.copy(coverage_xml, report_dir / "coverage.xml")
        print(f"\nCoverage XML copied to: {report_dir / 'coverage.xml'}")

    sys.exit(pytest_exit_code)


if __name__ == "__main__":
    main()
