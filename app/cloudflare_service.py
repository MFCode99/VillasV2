from __future__ import annotations

import ipaddress
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


API_BASE = 'https://api.cloudflare.com/client/v4'
DNS_TYPES = {'A', 'AAAA', 'CNAME', 'MX', 'TXT'}
PROXY_TYPES = {'A', 'AAAA', 'CNAME'}


class CloudflareServiceError(RuntimeError):
    def __init__(self, code: str, message: str = ''):
        super().__init__(message or code)
        self.code = code


class CloudflareService:
    def __init__(self, *, zone_name: str, token_file: Path):
        self.zone_name = zone_name.strip().casefold().rstrip('.')
        self.token_file = token_file

    @property
    def token_configured(self) -> bool:
        return bool(self._token())

    def _token(self) -> str:
        try:
            file_token = self.token_file.read_text(encoding='utf-8').strip()
            if file_token:
                return file_token
        except OSError:
            pass
        return os.getenv('CLOUDFLARE_API_TOKEN', '').strip()

    @staticmethod
    def _validated_id(value: str) -> str:
        cleaned = value.strip().casefold()
        if not re.fullmatch(r'[a-f0-9]{32}', cleaned):
            raise CloudflareServiceError('cloudflare_identifier_invalid')
        return cleaned

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None, *, token: str | None = None) -> Any:
        secret = (token or self._token()).strip()
        if not secret:
            raise CloudflareServiceError('cloudflare_not_configured')
        body = json.dumps(payload).encode('utf-8') if payload is not None else None
        request = urllib.request.Request(
            f'{API_BASE}/{path.lstrip("/")}',
            data=body,
            method=method,
            headers={'Authorization': f'Bearer {secret}', 'Content-Type': 'application/json'},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise CloudflareServiceError('cloudflare_permission_denied') from exc
            raise CloudflareServiceError('cloudflare_request_failed', f'HTTP {exc.code}') from exc
        except (OSError, ValueError) as exc:
            raise CloudflareServiceError('cloudflare_unavailable') from exc
        if not data.get('success'):
            raise CloudflareServiceError('cloudflare_request_failed')
        return data.get('result')

    def _zone(self, *, token: str | None = None) -> dict[str, Any]:
        zones = self._request('GET', f'zones?name={urllib.parse.quote(self.zone_name)}', token=token) or []
        zone = next((item for item in zones if str(item.get('name', '')).casefold() == self.zone_name), None)
        if not zone:
            raise CloudflareServiceError('cloudflare_zone_not_found')
        return zone

    def save_token(self, token: str) -> dict[str, Any]:
        cleaned = token.strip()
        if len(cleaned) < 20 or len(cleaned) > 512:
            raise CloudflareServiceError('cloudflare_token_invalid')
        zone = self._zone(token=cleaned)
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(prefix='.cloudflare-', dir=self.token_file.parent)
        try:
            with os.fdopen(handle, 'w', encoding='utf-8') as stream:
                stream.write(cleaned)
                stream.write('\n')
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.token_file)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return self._zone_json(zone)

    def _zone_json(self, zone: dict[str, Any]) -> dict[str, Any]:
        return {
            'id': zone.get('id'),
            'name': zone.get('name'),
            'status': zone.get('status'),
            'paused': bool(zone.get('paused')),
            'plan': (zone.get('plan') or {}).get('name') or '',
            'nameServers': zone.get('name_servers') or [],
        }

    def dashboard(self) -> dict[str, Any]:
        if not self.token_configured:
            return {'connected': False, 'tokenConfigured': False, 'zoneName': self.zone_name, 'records': [], 'email': None}
        zone = self._zone()
        zone_id = zone['id']
        records = self._request('GET', f'zones/{zone_id}/dns_records?per_page=500') or []
        email: dict[str, Any]
        try:
            settings = self._request('GET', f'zones/{zone_id}/email/routing') or {}
            rules = self._request('GET', f'zones/{zone_id}/email/routing/rules?per_page=200') or []
            account_id = (zone.get('account') or {}).get('id')
            destinations = self._request('GET', f'accounts/{account_id}/email/routing/addresses?per_page=200') if account_id else []
            email = {
                'available': True,
                'enabled': bool(settings.get('enabled')),
                'status': settings.get('status') or 'unknown',
                'rules': [self._rule_json(rule) for rule in rules],
                'destinations': [
                    {'id': item.get('id'), 'email': item.get('email'), 'verified': bool(item.get('verified'))}
                    for item in (destinations or [])
                ],
            }
        except CloudflareServiceError as exc:
            email = {'available': False, 'error': exc.code, 'rules': [], 'destinations': []}
        return {
            'connected': True,
            'tokenConfigured': True,
            'zoneName': self.zone_name,
            'zone': self._zone_json(zone),
            'records': [self._record_json(item) for item in records if item.get('type') in DNS_TYPES],
            'email': email,
        }

    @staticmethod
    def _record_json(record: dict[str, Any]) -> dict[str, Any]:
        return {
            'id': record.get('id'), 'type': record.get('type'), 'name': record.get('name'),
            'content': record.get('content'), 'ttl': record.get('ttl'), 'proxied': bool(record.get('proxied')),
            'proxiable': bool(record.get('proxiable')), 'priority': record.get('priority'),
            'modifiedAt': record.get('modified_on'),
        }

    @staticmethod
    def _rule_json(rule: dict[str, Any]) -> dict[str, Any]:
        matchers = rule.get('matchers') or []
        actions = rule.get('actions') or []
        source = next((item.get('value') for item in matchers if item.get('type') == 'literal'), '*')
        destination = next((value for item in actions if item.get('type') == 'forward' for value in (item.get('value') or [])), '')
        return {'id': rule.get('id'), 'name': rule.get('name') or '', 'source': source, 'destination': destination, 'enabled': bool(rule.get('enabled')), 'sourceType': rule.get('source') or 'api'}

    def _validated_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        record_type = str(payload.get('type') or '').upper()
        name = str(payload.get('name') or '').strip().casefold().rstrip('.')
        content = str(payload.get('content') or '').strip()
        ttl = int(payload.get('ttl') or 1)
        if record_type not in DNS_TYPES or not name or not content or len(content) > 4096:
            raise CloudflareServiceError('cloudflare_record_invalid')
        if name != self.zone_name and not name.endswith(f'.{self.zone_name}'):
            raise CloudflareServiceError('cloudflare_record_outside_zone')
        if ttl != 1 and not 60 <= ttl <= 86400:
            raise CloudflareServiceError('cloudflare_record_invalid')
        if record_type == 'A':
            try: ipaddress.IPv4Address(content)
            except ValueError as exc: raise CloudflareServiceError('cloudflare_record_invalid') from exc
        if record_type == 'AAAA':
            try: ipaddress.IPv6Address(content)
            except ValueError as exc: raise CloudflareServiceError('cloudflare_record_invalid') from exc
        if record_type in {'CNAME', 'MX'} and not re.fullmatch(r'[A-Za-z0-9._-]+', content):
            raise CloudflareServiceError('cloudflare_record_invalid')
        result: dict[str, Any] = {'type': record_type, 'name': name, 'content': content, 'ttl': ttl}
        if record_type in PROXY_TYPES:
            result['proxied'] = bool(payload.get('proxied'))
        if record_type == 'MX':
            result['priority'] = max(0, min(65535, int(payload.get('priority') or 10)))
        return result

    def save_record(self, payload: dict[str, Any], *, record_id: str | None = None) -> dict[str, Any]:
        zone = self._zone()
        cleaned = self._validated_record(payload)
        if record_id:
            result = self._request('PATCH', f'zones/{zone["id"]}/dns_records/{self._validated_id(record_id)}', cleaned)
        else:
            result = self._request('POST', f'zones/{zone["id"]}/dns_records', cleaned)
        return self._record_json(result)

    def delete_record(self, record_id: str) -> None:
        zone = self._zone()
        self._request('DELETE', f'zones/{zone["id"]}/dns_records/{self._validated_id(record_id)}')

    def create_destination(self, email: str) -> dict[str, Any]:
        zone = self._zone()
        account_id = (zone.get('account') or {}).get('id')
        if not account_id:
            raise CloudflareServiceError('cloudflare_email_unavailable')
        result = self._request('POST', f'accounts/{account_id}/email/routing/addresses', {'email': email.strip().casefold()})
        return {'id': result.get('id'), 'email': result.get('email'), 'verified': bool(result.get('verified'))}

    def save_rule(self, *, source: str, destination: str, rule_id: str | None = None, enabled: bool = True) -> dict[str, Any]:
        zone = self._zone()
        source_value = source.strip().casefold()
        destination_value = destination.strip().casefold()
        if not source_value.endswith(f'@{self.zone_name}') or '@' not in destination_value:
            raise CloudflareServiceError('cloudflare_email_rule_invalid')
        payload = {
            'name': f'Encaminhar {source_value}', 'enabled': bool(enabled),
            'matchers': [{'type': 'literal', 'field': 'to', 'value': source_value}],
            'actions': [{'type': 'forward', 'value': [destination_value]}],
        }
        method = 'PUT' if rule_id else 'POST'
        path = f'zones/{zone["id"]}/email/routing/rules/{self._validated_id(rule_id)}' if rule_id else f'zones/{zone["id"]}/email/routing/rules'
        return self._rule_json(self._request(method, path, payload))

    def delete_rule(self, rule_id: str) -> None:
        zone = self._zone()
        self._request('DELETE', f'zones/{zone["id"]}/email/routing/rules/{self._validated_id(rule_id)}')
