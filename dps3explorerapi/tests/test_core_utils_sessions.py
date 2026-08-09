import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core import utils


class _DummyRow:
    def __init__(self, bucket_name):
        self.bucket_name = bucket_name


class _DummyQuery:
    def __init__(self, all_result=None, first_result=None):
        self._all_result = all_result if all_result is not None else []
        self._first_result = first_result

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self._all_result

    def first(self):
        return self._first_result


class _DummySession:
    def __init__(self, query):
        self._query = query
        self.closed = False

    def query(self, model):
        return self._query

    def close(self):
        self.closed = True


@pytest.mark.skip(reason="legacy UAM/s3_explorer path removed")
def test_get_all_folders_from_user_id_closes_session():
    pass


def test_get_bucket_name_from_base_path_closes_session(monkeypatch):
    query = _DummyQuery(first_result=_DummyRow("test-bucket"))
    fake_session = _DummySession(query)
    monkeypatch.setattr(utils, "Session", lambda: fake_session)

    result = utils.get_bucket_name_from_base_path("test-bucket")

    assert result == "test-bucket"
    assert fake_session.closed is True


def test_get_bucket_name_from_base_path_returns_none_when_missing(monkeypatch):
    query = _DummyQuery(first_result=None)
    fake_session = _DummySession(query)
    monkeypatch.setattr(utils, "Session", lambda: fake_session)

    result = utils.get_bucket_name_from_base_path("Missing/")

    assert result is None
    assert fake_session.closed is True
