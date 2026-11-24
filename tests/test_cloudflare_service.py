from pathlib import Path

import pytest

from app.cloudflare_service import CloudflareService, CloudflareServiceError


def test_cloudflare_token_is_validated_and_saved_privately(tmp_path, monkeypatch):
    token_file = tmp_path / 'cloudflare-token'
    service = CloudflareService(zone_name='vitorgouveia.com', token_file=token_file)
    zone = {'id': 'a' * 32, 'name': 'vitorgouveia.com', 'status': 'active', 'paused': False, 'plan': {'name': 'Free'}, 'name_servers': []}
    monkeypatch.setattr(service, '_zone', lambda token=None: zone)

    result = service.save_token('t' * 40)

    assert result['name'] == 'vitorgouveia.com'
    assert token_file.read_text(encoding='utf-8').strip() == 't' * 40
    assert service.token_configured is True


def test_cloudflare_dns_records_are_scoped_to_configured_zone(tmp_path, monkeypatch):
    service = CloudflareService(zone_name='vitorgouveia.com', token_file=Path(tmp_path / 'token'))
    monkeypatch.setattr(service, '_zone', lambda token=None: {'id': 'a' * 32, 'name': 'vitorgouveia.com'})
    calls = []

    def request(method, path, payload=None, token=None):
        calls.append((method, path, payload))
        return {'id': 'b' * 32, **payload, 'proxiable': True, 'modified_on': '2026-11-13T00:00:00Z'}

    monkeypatch.setattr(service, '_request', request)
    record = service.save_record({'type': 'A', 'name': 'www.vitorgouveia.com', 'content': '192.0.2.10', 'ttl': 1, 'proxied': True})
    assert record['name'] == 'www.vitorgouveia.com'
    assert calls[0][0] == 'POST'

    with pytest.raises(CloudflareServiceError) as error:
        service.save_record({'type': 'A', 'name': 'example.com', 'content': '192.0.2.10', 'ttl': 1})
    assert error.value.code == 'cloudflare_record_outside_zone'


def test_cloudflare_rejects_invalid_record_identifier(tmp_path, monkeypatch):
    service = CloudflareService(zone_name='vitorgouveia.com', token_file=Path(tmp_path / 'token'))
    monkeypatch.setattr(service, '_zone', lambda token=None: {'id': 'a' * 32, 'name': 'vitorgouveia.com'})
    with pytest.raises(CloudflareServiceError) as error:
        service.delete_record('../outside')
    assert error.value.code == 'cloudflare_identifier_invalid'
