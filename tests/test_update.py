from chainq.update import parse_version


def test_parse_version():
    assert parse_version("1.2.3") == (1, 2, 3)
    assert parse_version("0.2.0") > parse_version("0.1.9")
    assert parse_version("1.0.0") > parse_version("0.9.9")
    assert parse_version("garbage") == (0,)


def test_prerelease_suffix_does_not_crash():
    assert parse_version("1.2.3rc1") == (0,)
