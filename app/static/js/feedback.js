(function () {
  'use strict';
  var modal = document.querySelector('[data-feedback-modal]');
  var card = modal && modal.querySelector('.feedback-card');
  var titleNode = modal && modal.querySelector('[data-feedback-title]');
  var messageNode = modal && modal.querySelector('[data-feedback-message]');
  var iconNode = modal && modal.querySelector('[data-feedback-icon]');
  var confirmButton = modal && modal.querySelector('[data-feedback-confirm]');
  var toast = document.querySelector('[data-site-toast]');
  var resolver = null;
  var toastTimer = null;

  var messages = {
    username_exists: 'Já existe um utilizador com esse username.',
    username_required: 'Indica um username.',
    full_name_required: 'Indica o nome do utilizador.',
    password_required: 'Indica uma password.',
    password_too_short: 'A password deve ter pelo menos 8 caracteres.',
    csrf_missing: 'A sessão expirou. Atualiza a página e tenta novamente.',
    csrf_invalid: 'A sessão expirou. Atualiza a página e tenta novamente.',
    invalid_credentials: 'Utilizador ou password incorretos.',
    user_not_found: 'O utilizador já não existe.',
    Internal: 'Ocorreu um erro inesperado. Tenta novamente.'
  };

  function friendlyMessage(value) {
    if (!value) return messages.Internal;
    if (typeof value === 'string') return messages[value] || value.replace(/_/g, ' ');
    if (Array.isArray(value)) return value.map(function (item) { return item.msg || 'Dados inválidos'; }).join(' · ');
    return messages.Internal;
  }

  function close(result) {
    if (!modal) return;
    modal.hidden = true;
    document.body.classList.remove('has-feedback-modal');
    if (resolver) { var resolve = resolver; resolver = null; resolve(result); }
  }

  function open(message, title, mode) {
    if (!modal) return Promise.resolve(mode !== 'confirm');
    card.className = 'feedback-card ' + (mode === 'confirm' ? '' : 'is-alert') + (mode === 'success' ? ' is-success' : '');
    titleNode.textContent = title || (mode === 'confirm' ? 'Confirmar ação' : 'Atenção');
    messageNode.textContent = friendlyMessage(message);
    iconNode.textContent = mode === 'success' ? '✓' : mode === 'confirm' ? '?' : '!';
    confirmButton.textContent = mode === 'confirm' ? 'Confirmar' : 'Fechar';
    modal.hidden = false;
    document.body.classList.add('has-feedback-modal');
    confirmButton.focus();
    return new Promise(function (resolve) { resolver = resolve; });
  }

  function notify(message, error) {
    if (!toast) return;
    window.clearTimeout(toastTimer);
    toast.textContent = friendlyMessage(message);
    toast.classList.toggle('is-error', Boolean(error));
    toast.hidden = false;
    toastTimer = window.setTimeout(function () { toast.hidden = true; }, 3600);
  }

  window.VillasFeedback = {
    confirm: function (message, title) { return open(message, title, 'confirm'); },
    alert: function (message, title) { return open(message, title, 'error'); },
    success: function (message) { notify(message, false); },
    error: function (message) { notify(message, true); }
  };

  modal && modal.querySelectorAll('[data-feedback-cancel]').forEach(function (button) { button.addEventListener('click', function () { close(false); }); });
  confirmButton && confirmButton.addEventListener('click', function () { close(true); });
  document.addEventListener('keydown', function (event) { if (event.key === 'Escape' && modal && !modal.hidden) close(false); });

  document.addEventListener('submit', async function (event) {
    if (event.defaultPrevented) return;
    var form = event.target;
    if (!(form instanceof HTMLFormElement) || form.method.toLowerCase() !== 'post') return;
    event.preventDefault();
    var confirmation = form.getAttribute('data-confirm');
    if (confirmation) {
      var accepted = await window.VillasFeedback.confirm(confirmation, form.getAttribute('data-confirm-title'));
      if (!accepted) return;
    }
    var submit = form.querySelector('[type="submit"]');
    if (submit) submit.disabled = true;
    try {
      var response = await fetch(form.action, {
        method: 'POST', credentials: 'same-origin', body: new FormData(form),
        headers: { 'X-Requested-With': 'fetch', 'Accept': 'application/json, text/html' }
      });
      if (!response.ok) {
        var detail = null;
        try { detail = (await response.json()).detail; } catch (ignore) {}
        await window.VillasFeedback.alert(detail || 'Ocorreu um erro inesperado.', 'Não foi possível concluir');
        return;
      }
      window.location.href = response.url || window.location.href;
    } catch (error) {
      await window.VillasFeedback.alert('Não foi possível comunicar com o servidor. Tenta novamente.', 'Erro de ligação');
    } finally {
      if (submit) submit.disabled = false;
    }
  });

  var params = new URLSearchParams(window.location.search);
  var successMessages = {
    created: 'Utilizador criado com sucesso.', updated: 'Alterações guardadas.', deleted: 'Utilizador eliminado.',
    password_updated: 'Password atualizada.', bulk_updated: 'Estado dos clientes atualizado.'
  };
  Object.keys(successMessages).some(function (key) {
    if (params.get(key) === '1') { notify(successMessages[key], false); params.delete(key); return true; }
    return false;
  });
  if (window.history.replaceState) {
    var clean = window.location.pathname + (params.toString() ? '?' + params.toString() : '') + window.location.hash;
    window.history.replaceState({}, '', clean);
  }
})();
