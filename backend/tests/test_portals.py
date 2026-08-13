import yaml

from app.models import Profile
from app.sources.portals import write_portals_yml


def test_write_portals_yml_escapes_regex_special_roles(tmp_path):
    # Roles like "C++" or "Node.js (backend)" contain regex-special characters.
    # Before the fix these were spliced unescaped into a `|`-joined regex and
    # a hand-written quoted YAML string, either of which could corrupt the
    # file or produce a broken regex. Confirm the written file both parses as
    # valid YAML and preserves the roles as literal (escaped) alternatives.
    profile = Profile(target_roles=["C++", "Node.js (backend)"], location='Berlin, "DE"')
    dest = tmp_path / "portals.yml"

    write_portals_yml(profile, dest)

    data = yaml.safe_load(dest.read_text())
    assert data["companies"] == []
    assert data["location_filter"] == 'Berlin, "DE"'
    assert "C\\+\\+" in data["title_filter"]
    assert "Node\\.js" in data["title_filter"]


def test_write_portals_yml_defaults_to_match_all_with_no_roles(tmp_path):
    profile = Profile(target_roles=[])
    dest = tmp_path / "portals.yml"

    write_portals_yml(profile, dest)

    data = yaml.safe_load(dest.read_text())
    assert data["title_filter"] == ".*"
