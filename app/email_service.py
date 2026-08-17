from __future__ import annotations

from dataclasses import dataclass
from html import escape as html_escape
import json
from email.message import EmailMessage
import smtplib
from typing import Any, Callable

from jinja2 import Template
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .models import EmailDeliveryLog, EmailTemplate, Order, User
from .pdf_service import build_order_pdf
from .security import utcnow


@dataclass(slots=True)
class EmailSendResult:
    status: str
    provider_message_id: str | None = None
    error_message: str | None = None




def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))


def _email_shell(*, eyebrow: str, title: str, content: str, button_label: str, button_url: str) -> str:
    return f'''<!doctype html>
<html lang="pt"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f3f5f8;font-family:Arial,Helvetica,sans-serif;color:#253147">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f5f8;padding:28px 12px">
    <tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 12px 35px rgba(23,36,61,.10)">
        <tr><td style="background:#17243d;padding:26px 32px">
          <table role="presentation" width="100%"><tr>
            <td style="width:52px"><div style="width:44px;height:44px;line-height:44px;text-align:center;border-radius:12px;background:#c6a15b;color:#17243d;font-size:22px;font-weight:800">V</div></td>
            <td><div style="color:#ffffff;font-size:22px;font-weight:800;letter-spacing:.4px">VILLAS</div></td>
          </tr></table>
        </td></tr>
        <tr><td style="padding:34px 32px 12px"><div style="color:#b4893f;font-size:12px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase">{eyebrow}</div><h1 style="margin:8px 0 0;color:#17243d;font-size:28px;line-height:1.25">{title}</h1></td></tr>
        <tr><td style="padding:8px 32px 12px;font-size:15px;line-height:1.65">{content}</td></tr>
        <tr><td style="padding:16px 32px 36px"><a href="{button_url}" style="display:inline-block;background:#17243d;color:#ffffff;text-decoration:none;font-weight:700;padding:13px 22px;border-radius:10px">{button_label}</a></td></tr>
        <tr><td style="border-top:1px solid #e2e6ed;padding:20px 32px;color:#7a8392;font-size:12px;line-height:1.5">Mensagem automática da Villas.<br>Se tiver alguma questão, responda a este email.</td></tr>
      </table>
    </td></tr>
  </table>
</body></html>'''


class EmailService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport_factory: Callable[[Settings], smtplib.SMTP] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.transport_factory = transport_factory or self._default_transport_factory

    def _default_transport_factory(self, settings: Settings) -> smtplib.SMTP:
        if settings.smtp_port == 465:
            client: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20)
        else:
            client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
            client.ehlo()
            if settings.smtp_port in {587, 25}:
                client.starttls()
                client.ehlo()
        if settings.smtp_user or settings.smtp_password:
            client.login(settings.smtp_user, settings.smtp_password)
        return client

    def health_check(self) -> bool:
        """Verify that the configured SMTP account can be reached and authenticated."""
        if not all((self.settings.smtp_host, self.settings.smtp_user, self.settings.smtp_password, self.settings.smtp_from)):
            return False
        client = None
        try:
            client = self.transport_factory(self.settings)
            return True
        except Exception:
            return False
        finally:
            try:
                if client is not None:
                    client.quit()
            except Exception:
                pass

    def _default_recipients(self, order: dict[str, Any]) -> list[str]:
        recipients: list[str] = []
        for value in [
            order.get('customerEmail') or order.get('customer_email'),
            self.settings.smtp_from,
            self.settings.smtp_user,
        ]:
            text = str(value or '').strip()
            if text and text not in recipients:
                recipients.append(text)
        return recipients

    def _render_template(self, db: Session, event: str, order: dict[str, Any]) -> tuple[str, str, str]:
        template = db.scalar(select(EmailTemplate).where(EmailTemplate.name == event, EmailTemplate.active.is_(True)))
        context = {
            'order': order,
            'public_number': order.get('publicNumber') or order.get('public_number'),
            'customer_name': order.get('customerName') or order.get('customer_name') or '',
            'total': order.get('total'),
            'status_label': order.get('orderStatusLabel') or order.get('order_status') or '',
        }
        if template is not None:
            subject = Template(template.subject).render(**context)
            body_html = Template(template.body_html).render(**context)
            body_text = Template(template.body_text or template.body_html).render(**context)
            return subject, body_html, body_text

        public_number = str(context['public_number'] or '')
        customer_name = html_escape(str(context['customer_name'] or 'Cliente'))
        status_label = html_escape(str(context['status_label'] or 'Pendente'))
        total = html_escape(str(context['total'] or '0.00'))
        event_copy = {
            'order_received': ('Recebemos a sua encomenda', 'A sua encomenda foi recebida e será analisada pela nossa equipa.'),
            'order_confirmed': ('Encomenda confirmada', 'A sua encomenda foi confirmada.'),
            'order_shipped': ('Encomenda enviada', 'A sua encomenda foi expedida.'),
        }
        headline, description = event_copy.get(event, ('Encomenda atualizada', 'O estado da sua encomenda foi atualizado.'))
        subject = f'{headline} — {public_number}'
        body_text = (
            f"Olá {context['customer_name'] or 'Cliente'},\n\n{description}\n\n"
            f"Encomenda: {public_number}\nEstado: {context['status_label']}\nTotal: {context['total']} €\n\n"
            'Em anexo seguem o documento com preços e a guia sem preços.\n'
        )
        portal_url = f"{self.settings.public_url.rstrip('/')}/encomendas/{public_number}"
        body_html = _email_shell(
            eyebrow='Atualização de encomenda',
            title=html_escape(headline),
            content=(
                f'<p style="margin:0 0 18px">Olá <b>{customer_name}</b>,</p><p>{html_escape(description)}</p>'
                f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:22px 0;background:#f5f7fa;border:1px solid #e1e6ee;border-radius:12px">'
                f'<tr><td style="padding:14px 18px;color:#6f7888">Encomenda</td><td style="padding:14px 18px;text-align:right;font-weight:700">{html_escape(public_number)}</td></tr>'
                f'<tr><td style="padding:14px 18px;border-top:1px solid #e1e6ee;color:#6f7888">Estado</td><td style="padding:14px 18px;border-top:1px solid #e1e6ee;text-align:right;font-weight:700">{status_label}</td></tr>'
                f'<tr><td style="padding:14px 18px;border-top:1px solid #e1e6ee;color:#6f7888">Total</td><td style="padding:14px 18px;border-top:1px solid #e1e6ee;text-align:right;font-size:18px;font-weight:800">{total} €</td></tr></table>'
                '<p style="color:#6f7888;font-size:13px">Em anexo seguem o documento com preços e a guia de preparação sem preços.</p>'
            ),
            button_label='Ver encomenda',
            button_url=html_escape(portal_url, quote=True),
        )
        return subject, body_html, body_text

    def _build_message(
        self,
        *,
        sender: str,
        recipients: list[str],
        subject: str,
        body_html: str,
        body_text: str,
        order: dict[str, Any],
        hide_prices: bool = False,
    ) -> EmailMessage:
        message = EmailMessage()
        message['From'] = sender
        message['To'] = ', '.join(recipients)
        message['Subject'] = subject
        message.set_content(body_text)
        message.add_alternative(body_html, subtype='html')
        attachments = [
            (f"{order.get('publicNumber') or order.get('public_number')}.pdf", build_order_pdf(order, hide_prices=hide_prices)),
            (f"{order.get('publicNumber') or order.get('public_number')}_sem_precos.pdf", build_order_pdf(order, hide_prices=True)),
        ]
        for filename, pdf_bytes in attachments:
            message.add_attachment(pdf_bytes, maintype='application', subtype='pdf', filename=filename)
        return message

    def send_order_event(
        self,
        db: Session,
        *,
        order: dict[str, Any],
        event: str,
        request_id: str | None,
        related_user_id: int | None = None,
        attempt: int = 1,
    ) -> EmailSendResult:
        recipients = self._default_recipients(order)
        sender = self.settings.smtp_from or self.settings.smtp_user or 'noreply@example.test'
        subject, body_html, body_text = self._render_template(db, event, order)
        log = EmailDeliveryLog(
            related_order_id=order.get('id'),
            related_user_id=related_user_id or order.get('userId'),
            template_name=event,
            request_id=request_id,
            attempt=attempt,
            recipient=', '.join(recipients) if recipients else '',
            subject=subject,
            status='pending',
            payload_json=_json_safe({'event': event, 'order': order, 'request_id': request_id}),
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        if not recipients or not self.settings.smtp_host:
            log.status = 'failed'
            log.error_message = 'smtp_not_configured'
            order_row = db.get(Order, order.get('id'))
            if order_row is not None:
                order_row.email_status = 'failed'
                order_row.email_error = 'smtp_not_configured'
                order_row.email_sent_at = None
            db.commit()
            return EmailSendResult(status='failed', error_message='smtp_not_configured')

        message = self._build_message(
            sender=sender,
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            order=order,
        )

        client = None
        try:
            client = self.transport_factory(self.settings)
            result = client.send_message(message)
            provider_message_id = None
            if hasattr(client, 'sock') and getattr(client, 'sock', None) is not None:
                provider_message_id = getattr(client.sock, 'getsockname', lambda: None)() or None
            log.status = 'sent'
            log.provider_message_id = str(provider_message_id or result or '')
            log.error_message = None
            order_row = db.get(Order, order.get('id'))
            if order_row is not None:
                order_row.email_status = 'sent'
                order_row.email_error = None
                order_row.email_sent_at = utcnow()
            db.commit()
            return EmailSendResult(status='sent', provider_message_id=log.provider_message_id)
        except Exception as exc:
            log.status = 'failed'
            log.error_message = str(exc)
            order_row = db.get(Order, order.get('id'))
            if order_row is not None:
                order_row.email_status = 'failed'
                order_row.email_error = str(exc)
                order_row.email_sent_at = None
            db.commit()
            return EmailSendResult(status='failed', error_message=str(exc))
        finally:
            try:
                if client is not None:
                    client.quit()
            except Exception:
                pass

    def send_order_pdf(
        self,
        db: Session,
        *,
        order: dict[str, Any],
        recipient: str,
        hide_prices: bool,
        request_id: str | None,
        related_user_id: int | None = None,
    ) -> EmailSendResult:
        """Send one selected version of an order PDF to the customer's email."""
        recipient = recipient.strip()
        public_number = str(order.get('publicNumber') or order.get('public_number') or '')
        sender = self.settings.smtp_from or self.settings.smtp_user or 'noreply@example.test'
        document_name = 'guia de preparação sem preços' if hide_prices else 'nota de encomenda com preços'
        subject = f'{document_name.capitalize()} — {public_number}'
        portal_url = f"{self.settings.public_url.rstrip('/')}/encomendas/{public_number}"
        body_text = f'Olá {order.get("customerName") or "Cliente"},\n\nEm anexo segue a sua {document_name} ({public_number}).\n'
        body_html = _email_shell(
            eyebrow='Documento de encomenda',
            title=document_name.capitalize(),
            content=(
                f'<p>Olá <b>{html_escape(str(order.get("customerName") or "Cliente"))}</b>,</p>'
                f'<p>Em anexo segue a sua {html_escape(document_name)} da encomenda <b>{html_escape(public_number)}</b>.</p>'
            ),
            button_label='Ver encomenda',
            button_url=html_escape(portal_url, quote=True),
        )
        log = EmailDeliveryLog(
            related_order_id=order.get('id'), related_user_id=related_user_id or order.get('userId'),
            template_name='order_pdf_unpriced' if hide_prices else 'order_pdf_priced', request_id=request_id,
            attempt=1, recipient=recipient, subject=subject, status='pending',
            payload_json=_json_safe({'event': 'order_pdf', 'hide_prices': hide_prices, 'order_id': order.get('id')}),
        )
        db.add(log); db.commit(); db.refresh(log)
        if not recipient or not self.settings.smtp_host:
            log.status = 'failed'; log.error_message = 'smtp_not_configured' if not self.settings.smtp_host else 'user_email_missing'; db.commit()
            return EmailSendResult(status='failed', error_message=log.error_message)
        message = EmailMessage()
        message['From'] = sender; message['To'] = recipient; message['Subject'] = subject
        message.set_content(body_text); message.add_alternative(body_html, subtype='html')
        filename = f'{public_number}_sem_precos.pdf' if hide_prices else f'{public_number}.pdf'
        message.add_attachment(build_order_pdf(order, hide_prices=hide_prices), maintype='application', subtype='pdf', filename=filename)
        client = None
        try:
            client = self.transport_factory(self.settings)
            result = client.send_message(message)
            log.status = 'sent'; log.provider_message_id = str(result or ''); log.error_message = None
            db.commit()
            return EmailSendResult(status='sent', provider_message_id=log.provider_message_id)
        except Exception as exc:
            log.status = 'failed'; log.error_message = str(exc); db.commit()
            return EmailSendResult(status='failed', error_message=str(exc))
        finally:
            try:
                if client is not None:
                    client.quit()
            except Exception:
                pass

    def send_user_created(self, db: Session, *, user: User, password: str, request_id: str | None) -> EmailSendResult:
        recipient = str(user.email or '').strip()
        sender = self.settings.smtp_from or self.settings.smtp_user or 'noreply@example.test'
        subject = 'Bem-vindo à Villas'
        body_text = (
            f'Olá {user.full_name},\n\nA sua conta na Villas foi criada.\n\n'
            f'Utilizador: {user.username}\nPassword: {password}\n\n'
            f'Aceda ao portal em: {self.settings.public_url}\n'
        )
        body_html = _email_shell(
            eyebrow='Conta criada',
            title='Bem-vindo à Villas',
            content=(
                f'<p style="margin:0 0 18px">Olá <b>{html_escape(user.full_name)}</b>,</p>'
                '<p>A sua conta foi criada. Utilize os dados abaixo para entrar:</p>'
                '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:22px 0;background:#f5f7fa;border:1px solid #e1e6ee;border-radius:12px">'
                f'<tr><td style="padding:14px 18px;color:#6f7888">Utilizador</td><td style="padding:14px 18px;text-align:right;font-weight:700">{html_escape(user.username)}</td></tr>'
                f'<tr><td style="padding:14px 18px;border-top:1px solid #e1e6ee;color:#6f7888">Password</td><td style="padding:14px 18px;border-top:1px solid #e1e6ee;text-align:right;font-weight:700">{html_escape(password)}</td></tr></table>'
                '<p style="color:#6f7888;font-size:13px">Guarde estas credenciais para aceder ao catálogo e efetuar encomendas.</p>'
            ),
            button_label='Entrar no portal',
            button_url=html_escape(self.settings.public_url, quote=True),
        )
        log = EmailDeliveryLog(
            related_user_id=user.id,
            template_name='user_created',
            request_id=request_id,
            attempt=1,
            recipient=recipient,
            subject=subject,
            status='pending',
            payload_json=_json_safe({'event': 'user_created', 'user_id': user.id, 'request_id': request_id}),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        if not recipient or not self.settings.smtp_host:
            log.status = 'failed'
            log.error_message = 'smtp_not_configured' if not self.settings.smtp_host else 'user_email_missing'
            db.commit()
            return EmailSendResult(status='failed', error_message=log.error_message)
        message = EmailMessage()
        message['From'] = sender
        message['To'] = recipient
        message['Subject'] = subject
        message.set_content(body_text)
        message.add_alternative(body_html, subtype='html')
        client = None
        try:
            client = self.transport_factory(self.settings)
            result = client.send_message(message)
            log.status = 'sent'
            log.provider_message_id = str(result or '')
            log.error_message = None
            db.commit()
            return EmailSendResult(status='sent', provider_message_id=log.provider_message_id)
        except Exception as exc:
            log.status = 'failed'
            log.error_message = str(exc)
            db.commit()
            return EmailSendResult(status='failed', error_message=str(exc))
        finally:
            try:
                if client is not None:
                    client.quit()
            except Exception:
                pass
