(function () {
  'use strict';
  var page = document.querySelector('[data-users-page]');
  if (!page) return;

  var filters = page.querySelector('[data-user-filters]');
  var modal = page.querySelector('[data-user-modal]');
  var loading = page.querySelector('[data-user-loading]');
  var searchTimer = null;
  var requestSequence = 0;

  function setModal(open) {
    if (!modal) return;
    modal.hidden = !open;
    document.body.classList.toggle('has-user-modal', open);
    if (open) window.setTimeout(function () {
      var input = modal.querySelector('input[name="username"]');
      if (input) input.focus();
    }, 30);
  }

  function buildUrl() {
    var params = new URLSearchParams(new FormData(filters));
    var entries = Array.from(params.entries());
    entries.forEach(function (entry) {
      if (!entry[1] || (entry[0] === 'status' && entry[1] === 'all')) params.delete(entry[0]);
    });
    var query = params.toString();
    return window.location.pathname + (query ? '?' + query : '');
  }

  async function refreshUsers() {
    var sequence = ++requestSequence;
    var url = buildUrl();
    if (loading) loading.classList.add('is-loading');
    try {
      var response = await fetch(url, {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'fetch', 'Accept': 'text/html' }
      });
      if (!response.ok || response.redirected && response.url.indexOf('/entrar') !== -1) {
        window.location.href = url;
        return;
      }
      var html = await response.text();
      if (sequence !== requestSequence) return;
      var parsed = new DOMParser().parseFromString(html, 'text/html');
      var next = parsed.querySelector('[data-user-results]');
      var current = page.querySelector('[data-user-results]');
      if (!next || !current) {
        window.location.href = url;
        return;
      }
      current.replaceWith(next);
      var nextStats = parsed.querySelector('[data-user-stats]');
      var currentStats = page.querySelector('[data-user-stats]');
      if (nextStats && currentStats) currentStats.replaceWith(nextStats);
      window.history.replaceState({}, '', url);
      var role = filters.elements.namedItem('role').value;
      page.querySelectorAll('[data-user-role]').forEach(function (item) {
        item.classList.toggle('is-active', item.getAttribute('data-user-role') === role);
      });
    } catch (error) {
      window.location.href = url;
    } finally {
      if (sequence === requestSequence && loading) loading.classList.remove('is-loading');
    }
  }

  filters.addEventListener('submit', function (event) {
    event.preventDefault();
    refreshUsers();
  });
  var search = filters.querySelector('[data-user-search]');
  if (search) search.addEventListener('input', function () {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(refreshUsers, 250);
  });
  filters.querySelectorAll('[data-user-filter]').forEach(function (select) {
    select.addEventListener('change', refreshUsers);
  });

  page.addEventListener('click', function (event) {
    var roleLink = event.target.closest('[data-user-role]');
    if (roleLink) {
      event.preventDefault();
      filters.elements.namedItem('role').value = roleLink.getAttribute('data-user-role') || '';
      refreshUsers();
      return;
    }
    if (event.target.closest('[data-user-modal-open]')) setModal(true);
    if (event.target.closest('[data-user-modal-close]')) setModal(false);
  });

  page.addEventListener('submit', async function (event) {
    var toggleForm = event.target.closest('[data-user-toggle]');
    if (!toggleForm) return;
    event.preventDefault();
    var button = toggleForm.querySelector('.toggle-switch');
    var label = toggleForm.querySelector('span');
    var row = toggleForm.closest('[data-user-row]');
    button.disabled = true;
    try {
      var response = await fetch(toggleForm.action, { method: 'POST', credentials: 'same-origin', body: new FormData(toggleForm) });
      if (!response.ok || response.redirected && response.url.indexOf('/entrar') !== -1) throw new Error('toggle_failed');
      var active = !button.classList.contains('is-on');
      button.classList.toggle('is-on', active);
      button.setAttribute('aria-checked', String(active));
      label.textContent = active ? 'Ativo' : 'Inativo';
      row.classList.toggle('is-inactive', !active);
    } catch (error) {
      window.location.reload();
    } finally {
      button.disabled = false;
    }
  });

  var createForm = page.querySelector('[data-user-create]');
  if (createForm) createForm.addEventListener('submit', async function (event) {
    event.preventDefault();
    var submit = createForm.querySelector('[data-user-create-submit]');
    var feedback = createForm.querySelector('[data-user-create-feedback]');
    submit.disabled = true;
    feedback.textContent = '';
    try {
      var response = await fetch(createForm.action, { method: 'POST', credentials: 'same-origin', body: new FormData(createForm) });
      if (!response.ok || response.redirected && response.url.indexOf('/entrar') !== -1) throw new Error('create_failed');
      createForm.reset();
      setModal(false);
      await refreshUsers();
    } catch (error) {
      feedback.textContent = 'Não foi possível criar o utilizador. Confirma o username e os dados.';
    } finally {
      submit.disabled = false;
    }
  });

  var bulkForm = page.querySelector('[data-bulk-client-toggle]');
  if (bulkForm) bulkForm.addEventListener('submit', async function (event) {
    event.preventDefault();
    var activeInput = bulkForm.querySelector('input[name="active"]');
    var activating = activeInput.value === 'true';
    if (!activating) {
      var confirmed = window.VillasFeedback
        ? await window.VillasFeedback.confirm('Desativar todas as contas de cliente?', 'Desativar clientes')
        : window.confirm('Desativar todas as contas de cliente?');
      if (!confirmed) return;
    }
    var button = bulkForm.querySelector('.toggle-switch');
    button.disabled = true;
    try {
      var response = await fetch(bulkForm.action, { method: 'POST', credentials: 'same-origin', body: new FormData(bulkForm) });
      if (!response.ok || response.redirected && response.url.indexOf('/entrar') !== -1) throw new Error('bulk_toggle_failed');
      activeInput.value = activating ? 'false' : 'true';
      button.classList.toggle('is-on', activating);
      button.setAttribute('aria-checked', String(activating));
      await refreshUsers();
    } catch (error) {
      window.location.reload();
    } finally {
      button.disabled = false;
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && modal && !modal.hidden) setModal(false);
  });
})();
