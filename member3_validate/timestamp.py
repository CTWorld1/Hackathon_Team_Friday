from member3_validate.timestamp import parse_hdfs_timestamp


def test_parse_hdfs_timestamp():
    parsed_time, fallback_used = parse_hdfs_timestamp("081109 203615")

    assert parsed_time.isoformat() == "2008-11-09T20:36:15"
    assert fallback_used is False


def test_bad_timestamp_uses_fallback():
    parsed_time, fallback_used = parse_hdfs_timestamp("bad timestamp")

    assert parsed_time is not None
    assert fallback_used is True