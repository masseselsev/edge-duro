from core.apt_diagnostics import is_diagnostic_line, parse_diagnostics


def test_recognises_apt_error_lines():
    assert is_diagnostic_line("E: Unable to locate package edge-mvs")
    assert is_diagnostic_line("Package 'foo' has no installation candidate")
    assert is_diagnostic_line(" nginx-full : Depends: libnginx-mod-x but it is not installable")
    assert is_diagnostic_line("The following packages have unmet dependencies:")
    assert not is_diagnostic_line("Installing packages...")
    assert not is_diagnostic_line("50%")


def test_parses_unlocatable_package():
    found = parse_diagnostics(["E: Unable to locate package edge-mvs"])
    assert found == [{
        "name": "edge-mvs",
        "source": "edge",
        "reason": "dependency",
        "detail": "E: Unable to locate package edge-mvs",
    }]


def test_parses_unmet_dependency_and_blames_the_dependency():
    found = parse_diagnostics(
        [" nginx-full : Depends: libnginx-mod-x but it is not installable"]
    )
    assert len(found) == 1
    assert found[0]["name"] == "libnginx-mod-x"
    assert found[0]["source"] == "apt"
    assert found[0]["reason"] == "dependency"
    assert "nginx-full" in found[0]["detail"]


def test_parses_pre_depends():
    found = parse_diagnostics(
        [" edge-base : Pre-Depends: libedge0 but it is not installable"]
    )
    assert found[0]["name"] == "libedge0"


def test_parses_no_installation_candidate():
    found = parse_diagnostics(["Package 'htop' has no installation candidate"])
    assert found[0]["name"] == "htop"


def test_deduplicates_by_name_keeping_first_detail():
    found = parse_diagnostics([
        "E: Unable to locate package htop",
        "E: Unable to locate package htop",
    ])
    assert len(found) == 1


def test_ignores_unrelated_lines():
    assert parse_diagnostics([
        "Building image...",
        "The following packages have unmet dependencies:",
    ]) == []
