import os
import pytest
from unittest.mock import patch

from resolume_mcp.config import ResolumeConfig, load_config, _parse_port, _parse_bool, _parse_allowed_hosts


def test_parse_port_valid():
    assert _parse_port("TEST_PORT", "8080") == 8080


def test_parse_port_rejects_non_integer():
    with patch.dict(os.environ, {"TEST_PORT": "abc"}):
        with pytest.raises(ValueError, match="not a valid integer"):
            _parse_port("TEST_PORT", "8080")


def test_parse_port_rejects_out_of_range():
    with patch.dict(os.environ, {"TEST_PORT": "99999"}):
        with pytest.raises(ValueError, match="outside valid port range"):
            _parse_port("TEST_PORT", "8080")


def test_parse_port_rejects_zero():
    with patch.dict(os.environ, {"TEST_PORT": "0"}):
        with pytest.raises(ValueError, match="outside valid port range"):
            _parse_port("TEST_PORT", "8080")


def test_parse_bool_accepts_true_variants():
    for val in ("1", "true", "True", "TRUE", "yes", "YES"):
        with patch.dict(os.environ, {"TEST_BOOL": val}):
            assert _parse_bool("TEST_BOOL", "0") is True


def test_parse_bool_rejects_false_variants():
    for val in ("0", "false", "no", ""):
        with patch.dict(os.environ, {"TEST_BOOL": val}):
            assert _parse_bool("TEST_BOOL", "0") is False


def test_parse_allowed_hosts_accepts_csv():
    hosts = _parse_allowed_hosts("127.0.0.1, localhost ,10.0.0.5")
    assert hosts == frozenset({"127.0.0.1", "localhost", "10.0.0.5"})


def test_parse_allowed_hosts_rejects_empty():
    with pytest.raises(ValueError, match="RESOLUME_ALLOWED_HOSTS"):
        _parse_allowed_hosts(" , ")


def test_load_config_uses_defaults():
    config = load_config()
    assert config.host == "127.0.0.1"
    assert config.http_port == 8080
    assert config.osc_port == 7000
    assert config.allowed_hosts == frozenset({"127.0.0.1", "localhost", "::1"})
    assert config.use_https is False


def test_load_config_reads_env_vars():
    with patch.dict(
        os.environ,
        {
            "RESOLUME_HOST": "10.0.0.1",
            "RESOLUME_HTTP_PORT": "9090",
            "RESOLUME_USE_HTTPS": "true",
            "RESOLUME_ALLOWED_HOSTS": "127.0.0.1,10.0.0.1",
        },
    ):
        config = load_config()
    assert config.host == "10.0.0.1"
    assert config.http_port == 9090
    assert config.allowed_hosts == frozenset({"127.0.0.1", "10.0.0.1"})
    assert config.use_https is True


def test_load_config_rejects_host_outside_allowlist():
    with patch.dict(os.environ, {"RESOLUME_HOST": "10.0.0.1", "RESOLUME_ALLOWED_HOSTS": "127.0.0.1"}):
        with pytest.raises(ValueError, match="RESOLUME_ALLOWED_HOSTS"):
            load_config()
