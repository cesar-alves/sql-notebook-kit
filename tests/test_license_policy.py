from scripts.check_license_report import findings


def test_unknown_license_requires_a_reviewed_override():
    report = {"Unknown": [{"name": "mystery", "versions": ["1.0"]}]}
    assert findings(report, ecosystem="npm", overrides={}) == [
        "mystery has unreviewed license metadata: Unknown"
    ]
    assert findings(report, ecosystem="npm", overrides={"mystery": "MIT"}) == []


def test_python_empty_license_is_rejected():
    report = [{"Name": "mystery", "Version": "1.0", "License": ""}]
    assert findings(report, ecosystem="pypi", overrides={})
