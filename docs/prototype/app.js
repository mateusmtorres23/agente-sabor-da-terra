(function () {
  "use strict";

  const STORAGE = "sabor-da-terra-prototype-v1";
  const today = new Date("2026-11-11T12:00:00-03:00");
  const app = document.getElementById("app");
  const state = load();
  const filters = { search: "", status: "", urgency: "", type: "", channel: "" };
  const triageStates = ["Recebida", "Em análise", "Aguardando informações", "Pronta para decisão", "Encerrada"];
  const requestsInAnalysis = new Set();
  let searchOpen = false;
  let triageScroll = 0;
  let dialog = null;
  let dialogReturnFocus = "";
  let toastTimer;
  let idSequence = 0;

  function load() {
    try {
      return { ...window.prototypeSeed, ...JSON.parse(localStorage.getItem(STORAGE) || "{}") };
    } catch {
      return { ...window.prototypeSeed };
    }
  }

  function save() {
    localStorage.setItem(STORAGE, JSON.stringify(state));
  }

  function uid(prefix) {
    return prefix + "-" + Date.now().toString(36).toUpperCase() + "-" + (++idSequence);
  }

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, character =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  }

  function dateBR(value) {
    return /^\d{4}-\d{2}-\d{2}$/.test(value || "") ? value.split("-").reverse().join("/") : value || "—";
  }

  function isoDate(value) {
    return /^\d{2}\/\d{2}\/\d{4}$/.test(value || "") ? value.split("/").reverse().join("-") :
      /^\d{4}-\d{2}-\d{2}$/.test(value || "") ? value : "";
  }

  function badge(value, tone) {
    const text = String(value ?? "");
    const color = tone || (/Vencid|Alta|bloque|inativ|Cancelad/i.test(text) ? "red" :
      /Aguard|pendênc|Atenç/i.test(text) ? "amber" :
      /Amostra|Interno|Registrad|Recebida|Em análise/i.test(text) ? "gray" : "green");
    return '<span class="badge ' + esc(color) + '">' + esc(text) + '</span>';
  }

  function icon(name) {
    const paths = {
      plus: '<path d="M12 5v14M5 12h14"/>',
      menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
      panel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
      search: '<circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/>',
      x: '<path d="m6 6 12 12M18 6 6 18"/>',
      "arrow-up": '<path d="M12 19V5m-6 6 6-6 6 6"/>',
      "arrow-right": '<path d="M5 12h14m-6-6 6 6-6 6"/>',
      "arrow-left": '<path d="M19 12H5m6-6-6 6 6 6"/>',
      check: '<path d="m5 12 4 4L19 6"/>',
      chat: '<path d="M5 19v-3a3 3 0 0 1-2-3V7a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3H9z"/>',
      file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5"/>',
      download: '<path d="M12 3v12m-4-4 4 4 4-4M4 16v4h16v-4"/>',
      copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
      edit: '<path d="m15 5 4 4M4 20l4-.9L20 7a1.4 1.4 0 0 0 0-2l-1-1a1.4 1.4 0 0 0-2 0L5 16z"/>',
      dots: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
      chevron: '<path d="m9 6 6 6-6 6"/>',
      inbox: '<path d="M4 4h16l2 10v5a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-5z"/><path d="M2 14h6l2 3h4l2-3h6"/>',
      orders: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 9h6m-6 4h6m-6 4h4"/>',
      calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/>',
      registry: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 3v18m4-13h4m-4 4h4"/>',
      logout: '<path d="M10 4H4v16h6m-1-8h12m-5-5 5 5-5 5"/>',
      filter: '<path d="M4 6h16M7 12h10m-7 6h4"/>',
      external: '<path d="M13 5h6v6m0-6-8 8m-2-8H5v14h14v-4"/>'
    };
    return '<svg class="icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (paths[name] || paths.file) + '</svg>';
  }

  function toast(text) {
    const node = document.getElementById("toast");
    node.textContent = text;
    node.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => node.classList.remove("show"), 3200);
  }

  const ctx = {
    state, today, esc, badge, icon, dateBR, toast, uid, save, render, navigate, openSource, downloadPDF, confirm,
    startRequestAnalysis, reviewRequest
  };
  const operations = window.createPrototypeOperations(ctx);
  const registry = window.createPrototypeRegistry(ctx);
  ctx.createOrder = (...args) => operations.createOrder(...args);
  ctx.createSchedule = (...args) => operations.createSchedule(...args);
  ctx.citationId = id => registry.citationId(id);
  const chat = window.createPrototypeChat(ctx);
  const modules = [chat, operations, registry];

  function navigate(view, detail = null) {
    if (state.view === "triage" && view !== "triage") triageScroll = window.scrollY;
    state.view = view;
    state.detail = detail;
    dialog = null;
    save();
    render();
    window.scrollTo(0, view === "triage" ? triageScroll : 0);
  }

  function navButton(view, label, glyph) {
    const selected = state.view === view;
    return `<button class="nav-item${selected ? " active" : ""}" data-view="${view}" aria-label="${label}" title="${label}"${selected ? ' aria-current="page"' : ""}>${icon(glyph)}<span>${label}</span></button>`;
  }

  function sidebar() {
    const collapsed = Boolean(state.sidebarCollapsed);
    return `<aside id="app-sidebar" class="sidebar">
      <div class="sidebar-top">
        <button class="brand" data-view="triage" title="Sabor da Terra · Triagem"><span class="brand-mark" aria-hidden="true"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20v-7m0 1C6 14 4 10 4 6c5 0 8 3 8 7m0 1c0-5 3-8 8-9 0 5-3 9-8 9"/></svg></span><span class="brand-label">Sabor da Terra</span></button>
        <button class="icon-button sidebar-toggle" data-ui="sidebar" aria-controls="app-sidebar" aria-expanded="${!collapsed}" aria-label="${collapsed ? "Expandir barra lateral" : "Recolher barra lateral"}" title="${collapsed ? "Expandir barra lateral" : "Recolher barra lateral"}">${icon("panel")}</button>
      </div>
      <button class="new-chat" data-ui="new-chat" aria-label="Novo chat" title="Novo chat">${icon("plus")}<span>Novo chat</span></button>
      <nav class="nav" aria-label="Navegação principal">
        ${navButton("triage", "Triagem", "inbox")}
        ${navButton("orders", "Pedidos", "orders")}
        ${navButton("schedules", "Agendamentos", "calendar")}
        ${navButton("registry", "Cadastros", "registry")}
      </nav>
      ${state.view === "chat" && !collapsed ? '<div class="sidebar-history">' + chat.history() + '</div>' : ""}
      <div class="sidebar-footer">
        <span class="avatar" aria-hidden="true">MC</span><span class="user-name">Marina Costa</span>
        <button class="icon-button" data-ui="logout" aria-label="Sair da demonstração" title="Sair da demonstração">${icon("logout")}</button>
      </div>
    </aside>`;
  }

  function login() {
    return `<main class="login"><section class="login-card">
      <span class="login-brand">Sabor da Terra</span>
      <h1>Acesso à cooperativa</h1>
      <form data-ui-form="login">
        <div class="field"><label for="login-name">Funcionário</label><input id="login-name" value="Marina Costa" readonly></div>
        <div class="field"><label for="login-password">Senha de demonstração</label><input id="login-password" type="password" value="demo" required autocomplete="off"></div>
        <button class="btn primary">Entrar ${icon("arrow-right")}</button>
      </form>
    </section></main>`;
  }

  function render() {
    if (!state.authenticated) {
      app.innerHTML = login();
      return;
    }
    state.triage.forEach(startRequestAnalysis);
    const chatting = state.view === "chat";
    const content = chatting ? chat.render() : state.view === "triage" ? triagePage() :
      state.view === "registry" ? registry.render() : operations.render();
    app.innerHTML = `<div class="shell${state.sidebarCollapsed ? " sidebar-collapsed" : ""}${chatting ? " shell-chat" : ""}">
      ${sidebar()}
      <main class="main${chatting ? " main-chat" : ""}">${chatting ? content : '<div class="content">' + content + '</div>'}</main>
    </div>${dialog ? renderDialog() : ""}`;
    if (dialog) {
      const element = app.querySelector("dialog");
      element.showModal();
      element.addEventListener("cancel", event => {
        event.preventDefault();
        closeDialog();
      });
    }
    chat.afterRender?.();
  }

  function triagePage() {
    const count = matchingRequests().length;
    const types = [...new Set(state.triage.map(request => request.type))];
    const channels = [...new Set(state.triage.map(request => request.channel))];
    return `<header class="page-heading triage-heading">
      <div><h1>Triagem</h1><p id="triage-count" aria-live="polite">${requestCount(count)}</p></div>
      <div class="triage-controls">
        <div class="triage-search${searchOpen || filters.search ? " expanded" : ""}">
          <button class="icon-button" type="button" data-ui="search" aria-label="Buscar solicitações" title="Buscar solicitações" aria-controls="triage-search" aria-expanded="${Boolean(searchOpen || filters.search)}">${icon("search")}</button>
          <input type="search" id="triage-search" aria-label="Buscar solicitações" placeholder="Buscar solicitações" value="${esc(filters.search)}"${searchOpen || filters.search ? "" : " hidden"}>
        </div>
        <details class="triage-filters">
          <summary class="icon-button" aria-label="Filtros da triagem" title="Filtros da triagem">${filterIcon()}</summary>
          <div class="filter-popover">
            <div class="field"><label for="triage-status">Estado</label><select id="triage-status"><option value="">Todos</option>${options(triageStates, filters.status)}</select></div>
            <div class="field"><label for="triage-urgency">Urgência</label><select id="triage-urgency"><option value="">Todas</option>${options(["Alta", "Normal", "Indeterminada", "Vencida"], filters.urgency)}</select></div>
            <div class="field"><label for="triage-type">Tipo</label><select id="triage-type"><option value="">Todos</option>${options(types, filters.type)}</select></div>
            <div class="field"><label for="triage-channel">Canal</label><select id="triage-channel"><option value="">Todos</option>${options(channels, filters.channel)}</select></div>
          </div>
        </details>
        <button class="btn primary" data-ui="register">${icon("plus")} Registrar mensagem</button>
      </div>
    </header>
    <div id="triage-results" class="request-grid">${triageCards()}</div>`;
  }

  function options(values, selected) {
    return values.map(value => `<option${value === selected ? " selected" : ""}>${esc(value)}</option>`).join("");
  }

  function normalize(text) {
    return String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  }

  function requestCount(count) {
    return count + (count === 1 ? " solicitação" : " solicitações");
  }

  function filterIcon() {
    return icon("filter") + (filters.status || filters.urgency || filters.type || filters.channel ? '<span class="filter-dot"></span>' : "");
  }

  function matchingRequests() {
    const query = normalize(filters.search.trim());
    return state.triage.filter(request =>
      (!filters.status || request.state === filters.status) &&
      (!filters.urgency || (filters.urgency === "Vencida" ? isOverdue(request) : request.urgent === filters.urgency)) &&
      (!filters.type || request.type === filters.type) &&
      (!filters.channel || request.channel === filters.channel) &&
      normalize([request.buyer, request.id, request.summary, request.type, request.channel].join(" ")).includes(query)
    );
  }

  function isOverdue(request) {
    const lastDay = isoDate(request.dueEnd || request.due);
    return lastDay ? lastDay < today.toISOString().slice(0, 10) : request.urgent === "Vencida";
  }

  function triageCards(records = matchingRequests()) {
    if (!records.length) return '<div class="empty request-empty">Nenhuma solicitação encontrada.</div>';
    return records.map(request => {
      const urgency = request.urgent === "Alta" ? badge("Urgente", "red") : "";
      const overdue = isOverdue(request) ? badge("Prazo vencido", "red") : "";
      const deadline = request.due && request.due !== "—" ? dateBR(request.due) : "";
      const deadlineEnd = isoDate(request.dueEnd) ? dateBR(request.dueEnd) : "";
      return `<article class="request-card">
        <div class="request-top"><span>${esc(request.type)}</span>${urgency && request.urgencyReason ? `<span title="${esc(request.urgencyReason)}" aria-label="${esc(request.urgencyReason)}">${urgency}</span>` : urgency || overdue || badge(request.state, request.state === "Aguardando informações" ? "amber" : "gray")}</div>
        <h2>${esc(request.buyer)}</h2>
        <p class="request-summary">${esc(request.summary)}</p>
        ${request.result ? `<p class="request-result">${esc(request.result)}</p>` : ""}
        ${request.pending ? `<p class="request-pending"><span aria-hidden="true"></span>${esc(request.pending)}</p>` : ""}
        <div class="request-bottom">
          <div class="request-meta">${esc(request.id)} · ${esc(request.channel)}${request.sample ? " · Amostra" : ""}${deadline ? `<span>Prazo ${esc(deadline)}${deadlineEnd && deadlineEnd !== deadline ? " a " + esc(deadlineEnd) : ""}</span>` : ""}${urgency || overdue ? '<span>' + esc(request.state) + '</span>' : ""}${urgency && overdue ? overdue : ""}</div>
          <div class="request-actions">
            <button class="request-link" data-ui="request" data-id="${esc(request.id)}">${request.origin === "pedido" ? "Abrir chat sobre esse pedido" : "Abrir chat"} ${icon("arrow-right")}</button>
            ${request.state === "Encerrada" ? "" : `<button class="btn small" data-ui="close-request" data-id="${esc(request.id)}">Encerrar</button>`}
          </div>
        </div>
      </article>`;
    }).join("");
  }

  function refreshTriage() {
    const results = document.getElementById("triage-results");
    if (!results) return;
    const focused = document.activeElement;
    const action = results.contains(focused) ? focused.dataset.ui : null;
    const requestId = action ? focused.dataset.id : null;
    const records = matchingRequests();
    results.innerHTML = triageCards(records);
    if (action && requestId) results.querySelector(`[data-ui="${CSS.escape(action)}"][data-id="${CSS.escape(requestId)}"]`)?.focus({ preventScroll: true });
    const count = document.getElementById("triage-count");
    if (count) count.textContent = requestCount(records.length);
    const filterButton = app.querySelector(".triage-filters summary");
    if (filterButton) filterButton.innerHTML = filterIcon();
  }

  function showRequestState(request) {
    if (!dialog) refreshTriage();
    const indicator = app.querySelector(`[data-triage-state="${CSS.escape(request.id)}"]`);
    if (indicator) indicator.textContent = request.state;
  }

  function reviewRequest(request) {
    if (request.state === "Encerrada") return;
    request.state = request.pending && request.pendingBlocksDecision !== false ?
      "Aguardando informações" : "Pronta para decisão";
    save();
    showRequestState(request);
  }

  function startRequestAnalysis(request) {
    if (requestsInAnalysis.has(request.id) || !["Recebida", "Em análise"].includes(request.state)) return;
    requestsInAnalysis.add(request.id);
    setTimeout(() => {
      if (request.state === "Recebida") {
        request.state = "Em análise";
        save();
        showRequestState(request);
      }
      setTimeout(() => {
        requestsInAnalysis.delete(request.id);
        if (request.state === "Em análise") reviewRequest(request);
      }, 450);
    }, 250);
  }

  function showDialog(next) {
    const active = document.activeElement;
    dialogReturnFocus = active?.id ? "#" + CSS.escape(active.id) : "";
    if (!dialogReturnFocus && active instanceof HTMLElement) {
      active.dataset.returnFocus = "yes";
      dialogReturnFocus = '[data-return-focus="yes"]';
    }
    dialog = next;
    mountDialog();
  }

  function mountDialog() {
    app.querySelector("dialog")?.remove();
    app.insertAdjacentHTML("beforeend", renderDialog());
    const element = app.querySelector("dialog");
    element.showModal();
    element.addEventListener("cancel", event => {
      event.preventDefault();
      closeDialog();
    });
  }

  function closeDialog() {
    dialog = null;
    app.querySelector("dialog")?.remove();
    if (dialogReturnFocus) {
      const previous = app.querySelector(dialogReturnFocus);
      previous?.focus();
      previous?.removeAttribute("data-return-focus");
    }
    dialogReturnFocus = "";
    refreshTriage();
  }

  function confirm(details) {
    showDialog({ kind: "confirm", ...details });
  }

  function openSource(id) {
    showDialog({ kind: "source", id });
  }

  function closeRequest(request) {
    if (!request || request.state === "Encerrada") return;
    showDialog({ kind: "close-request", id: request.id });
  }

  function submitRequestClosure(form) {
    const request = state.triage.find(entry => entry.id === dialog?.id);
    if (!request || request.state === "Encerrada") return;
    const result = form.elements.result.value.trim();
    if (!result) return showFormError(form, "Informe o resultado da triagem.", form.elements.result);
    request.result = result;
    request.closedAt = new Date().toISOString();
    request.state = "Encerrada";
    save();
    closeDialog();
    if (state.view === "chat") render();
    if (state.view === "triage") app.querySelector(`[data-ui="request"][data-id="${CSS.escape(request.id)}"]`)?.focus();
    toast("Solicitação encerrada.");
  }

  function renderDialog() {
    let title;
    let body;
    if (dialog.kind === "confirm") {
      title = dialog.title;
      body = `<p class="dialog-message">${esc(dialog.message)}</p>
        <div class="form-actions"><button class="btn" data-ui="close-dialog">Voltar</button><button class="btn danger" data-ui="confirm-dialog">${esc(dialog.label || "Confirmar")}</button></div>`;
    } else if (dialog.kind === "source") {
      const documentRecord = registry.resolveDocument(dialog.id);
      const request = state.triage.find(record => record.id === dialog.id);
      title = documentRecord?.name || (request ? "Mensagem original" : "Fonte indisponível");
      body = `<p class="source-meta">${esc(documentRecord?.fileName || documentRecord?.id || (request ? request.channel + " · " + request.id : ""))}</p>
        ${documentRecord?.fileData && /^data:application\/pdf[;,]/i.test(documentRecord.fileData)
          ? `<object class="source-file" data="${esc(documentRecord.fileData)}" type="application/pdf"></object>`
          : `<div class="source-copy">${esc(documentRecord?.content || request?.original || "O conteúdo desta fonte está indisponível.")}</div>`}
        ${documentRecord ? `<div class="form-actions"><button class="btn" data-ui="download-source" data-id="${esc(dialog.id)}">${icon("download")} Baixar original</button></div>` : ""}`;
    } else if (dialog.kind === "close-request") {
      const request = state.triage.find(entry => entry.id === dialog.id);
      title = "Encerrar solicitação";
      body = `<form data-ui-form="close-request" class="form-grid">
        <p class="dialog-message full">${esc(request.id)} · ${esc(request.buyer)}</p>
        <div class="field full"><label for="request-result">Resultado da triagem</label><textarea id="request-result" name="result" rows="3" required autofocus></textarea></div>
        ${request.pending ? `<div class="full"><span class="field-label">Pendência registrada</span><p class="dialog-message">${esc(request.pending)}</p></div>` : ""}
        <p class="notice error full" role="alert" hidden></p>
        <div class="form-actions full"><button class="btn" type="button" data-ui="close-dialog">Voltar</button><button class="btn primary" type="submit">Encerrar solicitação</button></div>
      </form>`;
    } else {
      title = "Registrar mensagem";
      body = `<form data-ui-form="register" class="form-grid">
        <div class="field"><label for="request-buyer">Remetente</label><input id="request-buyer" name="buyer" required autofocus></div>
        <div class="field"><label for="request-channel">Canal</label><select id="request-channel" name="channel">${options(["E-mail", "WhatsApp", "Telegram", "Interno"])}</select></div>
        <div class="field full"><label for="request-contact">Contato de teste</label><input id="request-contact" name="contact"></div>
        <div class="field full"><label for="request-type">Tipo</label><select id="request-type" name="type">${options(["Pedido de compra", "Cotação", "Consulta documental", "Consulta financeira", "Oferta de produtor", "Comunicação administrativa", "Não identificado"])}</select></div>
        <div class="field"><label for="request-due">Data de entrega ou início do prazo</label><input id="request-due" name="due" type="date"></div>
        <div class="field"><label for="request-due-end">Fim do prazo (opcional)</label><input id="request-due-end" name="dueEnd" type="date"></div>
        <div class="field full"><label for="request-message">Mensagem</label><textarea id="request-message" name="message" rows="4" required></textarea></div>
        <p class="notice error full" role="alert" hidden></p>
        <div class="form-actions full"><button class="btn" type="button" data-ui="close-dialog">Voltar</button><button class="btn primary">Registrar mensagem</button></div>
      </form>`;
    }
    return `<dialog class="app-dialog${dialog.kind === "source" ? " source-dialog" : ""}" aria-labelledby="dialog-title">
      <header><h2 id="dialog-title">${esc(title)}</h2><button class="icon-button" data-ui="close-dialog" title="Fechar" aria-label="Fechar">${icon("x")}</button></header>
      <div class="dialog-body">${body}</div>
    </dialog>`;
  }

  function showFormError(form, message, input) {
    const error = form.querySelector('[role="alert"]');
    error.hidden = false;
    error.textContent = message;
    input.focus();
  }

  function registerRequest(form) {
    const data = new FormData(form);
    const buyer = String(data.get("buyer")).trim();
    const original = String(data.get("message")).trim();
    if (!buyer || !original) return showFormError(form, "Informe o remetente e a mensagem.", buyer ? form.elements.message : form.elements.buyer);
    const due = data.get("due");
    const dueEnd = data.get("dueEnd");
    if (dueEnd && !due) return showFormError(form, "Informe o início do prazo.", form.elements.due);
    if (dueEnd && dueEnd < due) return showFormError(form, "O fim do prazo deve ser na mesma data ou depois do início.", form.elements.dueEnd);
    const id = uid("MSG");
    const type = data.get("type");
    const purchase = type === "Pedido de compra";
    const receivedDay = today.toISOString().slice(0, 10);
    const followingDay = new Date(today.getTime() + 86400000).toISOString().slice(0, 10);
    const declaredUrgent = /\b(?:urgente(?:mente)?|urg[eê]ncia)\b/i.test(original);
    const urgencyReason = declaredUrgent ? "Urgência informada na mensagem." :
      due === receivedDay ? "Entrega prevista para o dia do recebimento." :
      due === followingDay ? "Entrega prevista para o dia seguinte ao recebimento." : "";
    const urgent = urgencyReason ? "Alta" : due > followingDay ? "Normal" : "Indeterminada";
    const needsDeadline = purchase && (!due || (dueEnd || due) < receivedDay);
    const pending = needsDeadline ? (due ? "Confirme uma nova data de entrega." : "Informe o prazo de entrega.") :
      type === "Não identificado" ? "Esclareça a intenção do remetente." : "";
    const request = {
      id, buyer, type, original, source: id, state: "Recebida", urgent, urgencyReason,
      channel: data.get("channel"), contact: String(data.get("contact")).trim(),
      receivedAt: today.toISOString(), due, dueEnd, sample: false,
      origin: purchase ? "pedido" : "consulta",
      summary: original.length > 170 ? original.slice(0, 167) + "…" : original,
      pending, pendingField: needsDeadline ? "due" : "",
      analysis: "Mensagem de " + buyer + " classificada como " + type.toLowerCase() + ". Confira os dados na mensagem original.",
      drafts: purchase ? ["pedido", "resposta"] : ["resposta"]
    };
    state.triage.unshift(request);
    closeDialog();
    save();
    startRequestAnalysis(request);
    toast("Mensagem registrada na triagem.");
  }

  function saveFile(name, payload) {
    const url = typeof payload === "string" ? payload : URL.createObjectURL(payload);
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.append(link);
    link.click();
    link.remove();
    if (typeof payload !== "string") setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function downloadSource(id) {
    const record = registry.resolveDocument(id);
    if (!record) return;
    const fileName = record.fileName || record.name.replace(/[\\/:*?"<>|]/g, "-") + ".txt";
    const payload = /^data:/i.test(record.fileData || "") ? record.fileData :
      new Blob([record.content || ""], { type: "text/plain;charset=utf-8" });
    saveFile(fileName, payload);
  }

  function downloadPDF(text, fileName = "resumo-do-produtor.pdf") {
    const lines = ("Sabor da Terra\n\n" + String(text || "")).split(/\r?\n/).flatMap(line => {
      const wrapped = [];
      while (line.length > 82) {
        const space = line.lastIndexOf(" ", 82);
        const end = space > 0 ? space : 82;
        wrapped.push(line.slice(0, end));
        line = line.slice(end).trimStart();
      }
      return [...wrapped, line];
    });
    const encode = line => Array.from(line.replace(/—|–/g, "-").replace(/…/g, "...")).map(character => {
      const code = character.charCodeAt(0);
      return (code <= 255 ? code : 63).toString(16).padStart(2, "0");
    }).join("");
    const pageIds = [];
    const objects = ["<< /Type /Catalog /Pages 2 0 R >>", "", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"];
    for (let start = 0; start < lines.length; start += 45) {
      const pageId = objects.length + 1;
      pageIds.push(pageId + " 0 R");
      const stream = "BT /F1 11 Tf 16 TL 52 752 Td " + lines.slice(start, start + 45).map(line => "<" + encode(line) + "> Tj").join(" T* ") + " ET";
      objects.push("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents " + (pageId + 1) + " 0 R >>",
        "<< /Length " + stream.length + " >>\nstream\n" + stream + "\nendstream");
    }
    objects[1] = "<< /Type /Pages /Count " + pageIds.length + " /Kids [" + pageIds.join(" ") + "] >>";
    let pdf = "%PDF-1.4\n";
    const offsets = [];
    objects.forEach((object, index) => {
      offsets.push(pdf.length);
      pdf += (index + 1) + " 0 obj\n" + object + "\nendobj\n";
    });
    const xref = pdf.length;
    pdf += "xref\n0 " + (objects.length + 1) + "\n0000000000 65535 f \n" +
      offsets.map(offset => String(offset).padStart(10, "0") + " 00000 n \n").join("") +
      "trailer\n<< /Size " + (objects.length + 1) + " /Root 1 0 R >>\nstartxref\n" + xref + "\n%%EOF\n";
    saveFile(fileName, new Blob([pdf], { type: "application/pdf" }));
  }

  app.addEventListener("click", event => {
    const button = event.target.closest("button");
    if (!button) return;
    if (modules.some(module => module.click(button))) {
      event.preventDefault();
      return;
    }
    if (button.dataset.view) return navigate(button.dataset.view);
    if (button.dataset.openChat) return chat.openRequest(button.dataset.openChat);
    switch (button.dataset.ui) {
      case "sidebar":
        state.sidebarCollapsed = !state.sidebarCollapsed;
        save();
        render();
        app.querySelector('[data-ui="sidebar"]')?.focus();
        break;
      case "new-chat":
      case "request":
        if (state.view === "triage") triageScroll = window.scrollY;
        if (button.dataset.ui === "new-chat") chat.newChat();
        else chat.openRequest(button.dataset.id);
        break;
      case "search": {
        searchOpen = !searchOpen;
        const input = document.getElementById("triage-search");
        if (!searchOpen) filters.search = input.value = "";
        input.hidden = !searchOpen;
        button.parentElement.classList.toggle("expanded", searchOpen);
        button.setAttribute("aria-expanded", String(searchOpen));
        if (searchOpen) input.focus();
        refreshTriage();
        break;
      }
      case "register": showDialog({ kind: "register" }); break;
      case "close-request": closeRequest(state.triage.find(request => request.id === button.dataset.id)); break;
      case "close-dialog": closeDialog(); break;
      case "download-source": downloadSource(button.dataset.id); break;
      case "confirm-dialog": {
        const callback = dialog.onConfirm;
        closeDialog();
        callback?.();
        break;
      }
      case "logout":
        state.authenticated = false;
        navigate("triage");
        break;
    }
  });

  app.addEventListener("submit", event => {
    const form = event.target;
    event.preventDefault();
    if (form.dataset.uiForm === "login") {
      if (document.getElementById("login-password").value !== "demo") return toast("Use a senha demo para entrar.");
      state.authenticated = true;
      navigate("triage");
    } else if (form.dataset.uiForm === "register") {
      registerRequest(form);
    } else if (form.dataset.uiForm === "close-request") {
      submitRequestClosure(form);
    } else {
      modules.some(module => module.submit(form));
    }
  });

  app.addEventListener("input", event => {
    if (event.target.id === "triage-search") {
      filters.search = event.target.value;
      refreshTriage();
    } else {
      modules.some(module => module.input?.(event.target, event));
    }
  });

  app.addEventListener("change", event => {
    const filter = event.target.id.replace("triage-", "");
    if (event.target.matches("select[id^='triage-']") && Object.hasOwn(filters, filter)) {
      filters[filter] = event.target.value;
      refreshTriage();
    } else {
      modules.some(module => module.change?.(event.target, event));
    }
  });

  operations.syncSchedules?.();
  render();
})();
