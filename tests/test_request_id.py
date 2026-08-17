from __future__ import annotations


def test_request_id_header_present(client):
    resp = client.get('/health', headers={'X-Request-ID': 'abc123'})
    assert resp.status_code == 200
    assert resp.headers['X-Request-ID'] == 'abc123'