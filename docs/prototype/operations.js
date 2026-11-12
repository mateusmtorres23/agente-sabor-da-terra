/* Pedidos, alocações e agendamentos do protótipo. */
window.createPrototypeOperations = function (ctx) {
  "use strict";

  const { state, esc, badge, dateBR, save, toast, navigate, uid } = ctx;

  function key(value) {
    return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim().toLowerCase();
  }

  function isoDate(value) {
    const input = String(value || "").trim();
    const parts = input.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    const date = parts ? `${parts[3]}-${parts[2]}-${parts[1]}` : input;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return "";
    const parsed = new Date(`${date}T12:00:00Z`);
    return Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== date ? "" : date;
  }

  function dateShift(date, days) {
    const shifted = new Date(`${date}T12:00:00Z`);
    shifted.setUTCDate(shifted.getUTCDate() + days);
    if (Number.isNaN(shifted.getTime())) return "";
    const result = shifted.toISOString();
    return result[10] === "T" ? result.slice(0, 10) : "";
  }

  function referenceDay() {
    return typeof ctx.today === "string" ? isoDate(ctx.today) : ctx.today.toISOString().slice(0, 10);
  }

  function itemsFrom(value) {
    if (Array.isArray(value)) return value;
    return String(value || "").split(/\r?\n/).filter(line => line.trim()).map(line => {
      const [name, qtyAndUnit, unit, condition] = line.split("•").map(part => part.trim());
      if (unit) return { name, qty: qtyAndUnit, unit, condition };
      const parts = (qtyAndUnit || "").match(/^(\d+(?:[.,]\d+)?)\s+(.+)$/);
      return { name, qty: parts?.[1], unit: parts?.[2], condition };
    });
  }

  function itemText(item) {
    return `${item.name} · ${item.qty} ${item.unit}`;
  }

  function quantity(value) {
    return Number(String(value || "").replace(",", "."));
  }

  function exceeds(amount, limit) {
    return amount > limit + Math.abs(limit) * Number.EPSILON * 8;
  }

  function normalizeItems(value) {
    const items = itemsFrom(value);
    if (!items.length) throw new Error("Adicione pelo menos um item.");
    return items.map((item, index) => {
      const name = String(item.name || "").trim();
      const unit = String(item.unit || "").trim();
      const qty = quantity(item.qty);
      if (!name || !unit || !Number.isFinite(qty) || qty <= 0) {
        throw new Error(`Preencha o produto, uma quantidade positiva e a unidade do item ${index + 1}.`);
      }
      const product = state.products.find(record => key(record.name) === key(name));
      return {
        id: item.id || uid("ITEM"),
        productId: product?.id || item.productId || null,
        name,
        qty,
        unit,
        condition: String(item.condition || "").trim()
      };
    });
  }

  function validateCommon(data) {
    const buyer = String(data.buyer || "").trim();
    if (!buyer) throw new Error("Informe o comprador.");
    return { buyer, conditions: String(data.conditions || "").trim(), items: normalizeItems(data.items) };
  }

  function createOrder(data) {
    const existing = data.operationId && state.orders.find(order => order.operationId === data.operationId);
    if (existing) return existing;
    const due = isoDate(data.due);
    if (!due) throw new Error("Informe um prazo de fornecimento válido.");
    const order = {
      ...validateCommon(data), id: uid("PED"), due, source: data.source || "—",
      status: "Ativo", allocations: [], operationId: data.operationId || null
    };
    state.orders.push(order);
    save();
    return order;
  }

  function validateSchedule(data) {
    const firstDate = isoDate(data.firstDate);
    const lead = Number(data.lead);
    if (!firstDate) throw new Error("Informe a primeira data de fornecimento.");
    if (data.lead === "" || data.lead == null || !Number.isSafeInteger(lead) || lead < 0) {
      throw new Error("Informe a antecedência em dias inteiros, a partir de zero.");
    }
    if (!dateShift(firstDate, -lead) || !dateShift(referenceDay(), lead)) {
      throw new Error("A antecedência gera uma data fora do intervalo disponível.");
    }
    return { ...validateCommon(data), firstDate, lead, recurrence: "Semanal" };
  }

  function createSchedule(data) {
    const existing = data.operationId && state.schedules.find(schedule => schedule.operationId === data.operationId);
    if (existing) return existing;
    const schedule = {
      ...validateSchedule(data), id: uid("AG"), source: data.source || "—",
      status: "Ativo", occurrences: [], operationId: data.operationId || null
    };
    state.schedules.push(schedule);
    syncSchedule(schedule);
    save();
    return schedule;
  }

  function recordOccurrence(schedule, date, status) {
    if (schedule.occurrences.some(entry => entry.date === date)) return false;
    const entry = { date, status, triageDate: dateShift(date, -Number(schedule.lead)) };
    if (status === "Gerada") {
      const existing = state.triage.find(request => request.source === schedule.id && isoDate(request.due) === date);
      entry.requestId = existing?.id || `${schedule.id}-${date}`;
      if (!existing) {
        const items = itemsFrom(schedule.items).map(item => ({ ...item }));
        const summary = items.map(itemText).join("; ");
        state.triage.push({
          id: entry.requestId, state: "Recebida", buyer: schedule.buyer, type: "Ocorrência agendada",
          channel: "Interno", urgent: date <= dateShift(referenceDay(), 1) ? "Alta" : "Normal",
          due: dateBR(date), summary, pending: "Confirmar disponibilidade para o fornecimento.",
          sample: false, source: schedule.id, origin: "agendamento", drafts: ["pedido"], items,
          conditions: schedule.conditions, analysis: `Fornecimento semanal em ${dateBR(date)}. ${summary}. ${schedule.conditions || ""}`.trim(),
          original: `Ocorrência de ${schedule.id} para ${dateBR(date)}. ${summary}. ${schedule.conditions || ""}`.trim()
        });
      }
    }
    schedule.occurrences.push(entry);
    return true;
  }

  function syncSchedule(schedule) {
    let changed = false;
    if (!schedule.occurrences) {
      schedule.occurrences = state.triage.filter(request => request.source === schedule.id && isoDate(request.due)).map(request => ({
        date: isoDate(request.due), triageDate: dateShift(isoDate(request.due), -Number(schedule.lead || 0)),
        status: "Gerada", requestId: request.id
      }));
      changed = true;
    }
    const firstDate = isoDate(schedule.firstDate);
    if (schedule.status === "Cancelado" || !firstDate) return changed;
    const day = referenceDay();
    const through = dateShift(day, Number(schedule.lead || 0));
    const recorded = new Set(schedule.occurrences.map(entry => entry.date));
    const cadence = schedule.recurrence === "Quinzenal" ? 14 : 7;
    for (let date = firstDate; date && date <= through; date = dateShift(date, cadence)) {
      if (!recorded.has(date)) changed = recordOccurrence(schedule, date, date < day ? "Perdida" : "Gerada") || changed;
    }
    return changed;
  }

  function syncSchedules() {
    let changed = false;
    for (const schedule of state.schedules) changed = syncSchedule(schedule) || changed;
    if (changed) save();
  }

  function sameItem(allocation, item, index) {
    return allocation.itemId ? allocation.itemId === (item.id || `legacy-${index}`) : key(allocation.item) === key(item.name);
  }

  function orderAllocations(order, item, index) {
    return order.allocations.filter(allocation => sameItem(allocation, item, index));
  }

  function currentProducer(allocation) {
    return state.producers.find(producer => producer.id === allocation.producerId || (!allocation.producerId && key(producer.name) === key(allocation.producer)));
  }

  function currentProduct(item) {
    return state.products.find(product => product.id === item.productId || (!item.productId && key(product.name) === key(item.name)));
  }

  function evidenceThrough(document) {
    const stated = `${document.status || ""}\n${document.content || ""}`;
    const dates = stated.match(/\d{2}\/\d{2}\/\d{4}|\d{4}-\d{2}-\d{2}/g) || [];
    return isoDate(document.validUntil) || isoDate(dates.at(-1));
  }

  function allocationBlock(order, item, producer) {
    if (!producer || producer.status !== "Ativo") return "Selecione um produtor ativo.";
    const itemScope = key(`${item.name} ${item.condition || ""}`);
    const scope = key(`${order.buyer} ${order.conditions || ""} ${itemScope}`);
    const deadline = isoDate(order.due);
    const docs = state.documents.filter(document => {
      const text = key(`${document.name} ${document.content || ""}`);
      return document.producerId ? document.producerId === producer.id : text.includes(key(producer.name));
    });
    const hasEvidence = pattern => docs.some(document => {
      const title = key(`${document.kind} ${document.name}`);
      return pattern.test(title) && evidenceThrough(document) >= deadline && !/vencid|suspens|inativ/.test(key(document.status));
    });
    if ((order.source === "PED-2026-004" || /\bpnae\b|\bdap\b|\bcaf\b/.test(scope)) && !hasEvidence(/\bdap\b|\bcaf\b/)) {
      return "Falta comprovação de vigência do DAP/CAF para a data de fornecimento.";
    }
    if (/organic/.test(itemScope)) {
      const productName = key(item.name).replace(/\s+organic[oa]s?\b/g, "");
      const organic = docs.some(document => {
        const title = key(`${document.kind} ${document.name}`);
        const products = key(document.content);
        return /organic/.test(title) && products.includes(productName) && evidenceThrough(document) >= deadline && !/vencid|suspens|inativ/.test(key(document.status));
      });
      if (!organic) return "Falta certificação orgânica vigente para o produto na data de fornecimento.";
    }
    if (/\bsie\b|\bsim\b|\bsisbi\b|laudo sanitario|registro sanitario/.test(scope) && !hasEvidence(/\bsie\b|\bsim\b|\bsisbi\b|sanitari/)) {
      return "Falta comprovação sanitária vigente para a data de fornecimento.";
    }
    return "";
  }

  function updateOrder(order, data) {
    const due = isoDate(data.due);
    if (!due) throw new Error("Informe um prazo de fornecimento válido.");
    const updated = { ...order, ...validateCommon(data), due };
    order.items.forEach((original, index) => {
      const allocations = orderAllocations(order, original, index);
      if (!allocations.length) return;
      const item = updated.items.find(candidate => candidate.id === (original.id || `legacy-${index}`));
      const total = allocations.reduce((sum, allocation) => sum + Number(allocation.qty), 0);
      if (!item || key(item.name) !== key(original.name) || key(item.unit) !== key(original.unit) || exceeds(total, item.qty)) {
        throw new Error(`Ajuste ou remova as alocações de ${original.name} antes de alterar o item.`);
      }
      if (due !== isoDate(order.due) || order.buyer !== updated.buyer || order.conditions !== updated.conditions || item.condition !== original.condition) {
        for (const allocation of allocations) {
          const reason = allocationBlock(updated, item, currentProducer(allocation));
          if (reason) throw new Error(`Ajuste a alocação de ${original.name}. ${reason}`);
        }
      }
      const affected = new Set(allocations.map(allocation => allocation.id));
      updated.allocations = updated.allocations.map(entry => affected.has(entry.id) ? { ...entry, itemId: item.id } : entry);
    });
    Object.assign(order, updated);
    save();
  }

  function orderStatus(order) {
    return order.status === "Cancelado" ? badge("Cancelado") : badge(order.status || "Ativo");
  }

  function heading(title, description, actions = "", parent = "") {
    return `<div class="page-heading ops-heading"><div>${parent}<h2>${esc(title)}</h2>${description ? `<p>${esc(description)}</p>` : ""}</div><div class="actions">${actions}</div></div>`;
  }

  function button(action, label, id = "", classes = "", extra = "") {
    return `<button type="button" class="btn ${classes}" data-ops-action="${action}" data-id="${esc(id)}" ${extra}>${esc(label)}</button>`;
  }

  function back(view, label) {
    return `<button type="button" class="ops-back" data-ops-action="${view}">← ${esc(label)}</button>`;
  }

  function table(heads, rows, empty) {
    if (!rows.length) return `<div class="card empty ops-empty">${esc(empty)}</div>`;
    return `<div class="card table-wrap ops-table"><table class="data-table"><thead><tr>${heads.map(head => `<th scope="col">${esc(head)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
  }

  function orderList() {
    const rows = state.orders.map(order => `<tr>
      <td><strong>${esc(order.buyer)}</strong><span class="ops-subline">${esc(order.id)}</span></td>
      <td>${order.items.map(item => esc(itemText(item))).join("<br>")}</td><td>${esc(dateBR(order.due))}</td>
      <td>${orderStatus(order)}</td><td class="ops-row-action">${button("order", "Abrir pedido", order.id, "small")}</td>
    </tr>`);
    return heading("Pedidos", "Acompanhe os pedidos e as alocações por item.", button("new-order", "Novo pedido", "", "primary")) +
      table(["Comprador", "Itens", "Fornecimento", "Estado", "Ações"], rows, "Nenhum pedido cadastrado.");
  }

  function scheduleList() {
    const rows = state.schedules.map(schedule => `<tr>
      <td><strong>${esc(schedule.buyer)}</strong><span class="ops-subline">${esc(schedule.id)}</span></td>
      <td>${esc(dateBR(schedule.firstDate))}</td><td>${esc(schedule.recurrence)}</td><td>${esc(schedule.lead)} dias</td>
      <td>${badge(schedule.status)}</td><td class="ops-row-action">${button("schedule", "Ver agendamento", schedule.id, "small")}</td>
    </tr>`);
    return heading("Agendamentos", "Acompanhe os fornecimentos recorrentes e suas datas de triagem.", button("new-schedule", "Novo agendamento", "", "primary")) +
      table(["Comprador", "Primeiro fornecimento", "Recorrência", "Antecedência", "Estado", "Ações"], rows, "Nenhum agendamento cadastrado.");
  }

  function infoList(rows) {
    return `<dl class="ops-info">${rows.map(([label, value]) => `<div><dt>${esc(label)}</dt><dd>${value || "—"}</dd></div>`).join("")}</dl>`;
  }

  function section(title, content) {
    return `<section class="card ops-section"><div class="section-title"><h3>${esc(title)}</h3></div><div class="section-body">${content}</div></section>`;
  }

  function orderDetail(order) {
    const active = order.status !== "Cancelado";
    const actions = active ? button("edit-order", "Editar pedido", order.id, "primary") + button("cancel-order", "Cancelar pedido", order.id, "danger") : "";
    const source = state.triage.find(request => request.id === order.source);
    const items = order.items.map((item, index) => {
      const allocations = orderAllocations(order, item, index);
      const total = allocations.reduce((sum, allocation) => sum + Number(allocation.qty), 0);
      const amount = exceeds(item.qty, total) ? Number((item.qty - total).toPrecision(12)) : 0;
      const rows = allocations.map(allocation => `<li class="ops-allocation-row"><div><strong>${esc(currentProducer(allocation)?.name || allocation.producer)}</strong><span class="ops-subline">${allocation.confirmed ? "Disponibilidade confirmada" : "Disponibilidade pendente"}</span></div><span>${esc(allocation.qty)} ${esc(allocation.unit)}</span><div class="actions">
        ${button("edit-allocation", "Editar", order.id, "small", `data-item="${index}" data-allocation="${esc(allocation.id)}"`)}
        ${button("remove-allocation", "Remover", order.id, "small", `data-allocation="${esc(allocation.id)}"`)}</div></li>`);
      const add = active && amount > 0 ? button("add-allocation", "Registrar alocação", order.id, "small", `data-item="${index}"`) : "";
      return `<article class="ops-item"><div class="ops-item-head"><div><h4>${esc(item.name)}</h4><p>${esc(item.qty)} ${esc(item.unit)} solicitados${item.condition ? ` · ${esc(item.condition)}` : ""}</p></div><span class="ops-balance">${esc(amount)} ${esc(item.unit)} a alocar</span></div>
        ${rows.length ? `<ul class="ops-allocations">${rows.join("")}</ul>` : '<p class="ops-inline-empty">Nenhuma alocação registrada.</p>'}${add}</article>`;
    }).join("");
    return heading(order.buyer, `Pedido ${order.id}`, actions, back("orders", "Pedidos")) + `<div class="ops-detail-grid">
      ${section("Itens e alocações", items)}
      ${section("Dados do pedido", infoList([["Estado", orderStatus(order)], ["Fornecimento", esc(dateBR(order.due))], ["Condições de atendimento", esc(order.conditions)], ["Solicitação de origem", source ? button("source", source.id, source.id, "small") : esc(order.source)]]))}
    </div>`;
  }

  function pendingOccurrences(schedule) {
    const firstDate = isoDate(schedule.firstDate);
    if (schedule.status === "Cancelado" || !firstDate) return [];
    const existing = new Set(schedule.occurrences.map(entry => entry.date));
    const pending = [];
    const today = referenceDay();
    const cadence = schedule.recurrence === "Quinzenal" ? 14 : 7;
    for (let date = firstDate; date && pending.length < 4; date = dateShift(date, cadence)) {
      if (!existing.has(date) && date >= today) {
        pending.push({ date, triageDate: dateShift(date, -Number(schedule.lead)), status: "Pendente" });
      }
    }
    return pending;
  }

  function scheduleDetail(schedule) {
    const active = schedule.status !== "Cancelado";
    const actions = active ? button("edit-schedule", "Editar agendamento", schedule.id, "primary") + button("cancel-schedule", "Cancelar agendamento", schedule.id, "danger") : "";
    const pending = pendingOccurrences(schedule);
    const history = [...schedule.occurrences].sort((a, b) => b.date.localeCompare(a.date));
    const occurrences = [...pending, ...history];
    const rows = occurrences.map(entry => {
      let action = "";
      if (entry.requestId) action = `<button type="button" class="btn small" data-open-chat="${esc(entry.requestId)}">Abrir chat</button>`;
      if (entry === pending[0]) action = button("simulate-occurrence", "Simular triagem", schedule.id, "small", `data-date="${esc(entry.date)}"`);
      return `<tr><td>${esc(dateBR(entry.date))}</td><td>${esc(dateBR(entry.triageDate))}</td><td>${badge(entry.status)}</td><td class="ops-row-action">${action}</td></tr>`;
    });
    const items = itemsFrom(schedule.items).map(item => `${esc(itemText(item))}${item.condition ? ` · ${esc(item.condition)}` : ""}`).join("<br>");
    return heading(schedule.buyer, `Agendamento ${schedule.id}`, actions, back("schedules", "Agendamentos")) + `<div class="ops-detail-grid">
      <section class="ops-occurrences"><h3>Ocorrências</h3>${table(["Fornecimento", "Entrada na triagem", "Estado", "Ações"], rows, "Nenhuma ocorrência registrada.")}</section>
      ${section("Dados do agendamento", infoList([["Estado", badge(schedule.status)], ["Recorrência", esc(schedule.recurrence)], ["Antecedência", `${esc(schedule.lead)} dias corridos`], ["Itens", items], ["Condições", esc(schedule.conditions)]]))}
    </div>`;
  }

  function input(label, name, value, attributes = "") {
    return `<label class="field ops-field"><span>${esc(label)}</span><input name="${name}" value="${esc(value)}" ${attributes}></label>`;
  }

  function itemRow(item = {}) {
    return `<fieldset class="ops-item-editor"><legend class="ops-visually-hidden">Item do pedido</legend>
      <input type="hidden" name="item-id" value="${esc(item.id)}"><input type="hidden" name="product-id" value="${esc(item.productId)}">
      ${input("Produto", "item-name", item.name, 'list="ops-products" required')}
      ${input("Quantidade", "item-qty", item.qty, 'type="number" step="any" min="0" required')}
      ${input("Unidade", "item-unit", item.unit, "required")}
      ${input("Condição do item", "item-condition", item.condition)}
      ${button("remove-item", "Remover", "", "small")}
    </fieldset>`;
  }

  function formActions(cancel, submitLabel) {
    return `<p class="notice error ops-form-error" role="alert" tabindex="-1" hidden></p><div class="form-actions">${cancel}<button class="btn primary" type="submit">${esc(submitLabel)}</button></div>`;
  }

  function orderScheduleForm(record, scheduled) {
    const view = scheduled ? "schedules" : "orders";
    const entity = scheduled ? "agendamento" : "pedido";
    const title = `${record ? "Editar" : "Novo"} ${entity}`;
    const rows = record ? itemsFrom(record.items).map((item, index) => ({ ...item, id: item.id || `legacy-${index}` })) : [{}];
    const productOptions = state.products.map(product => `<option value="${esc(product.name)}"></option>`).join("");
    const dates = scheduled ? `${input("Primeiro fornecimento", "firstDate", isoDate(record?.firstDate), 'type="date" required')}${input("Antecedência em dias corridos", "lead", record?.lead ?? 2, 'type="number" min="0" step="1" required')}` : input("Prazo de fornecimento", "due", isoDate(record?.due), 'type="date" required');
    return heading(title, scheduled ? "Fornecimento semanal" : "", "", back(view, scheduled ? "Agendamentos" : "Pedidos")) + `<form class="card ops-form" data-ops-form="${scheduled ? "schedule" : "order"}" data-id="${esc(record?.id)}">
      <div class="form-grid">${input("Comprador", "buyer", record?.buyer, "required")}${dates}</div>
      <div class="ops-form-section"><div class="ops-form-section-head"><h3>Itens</h3>${button("add-item", "Adicionar item", "", "small")}</div>
      <datalist id="ops-products">${productOptions}</datalist><div class="ops-item-fields">${rows.map(itemRow).join("")}</div></div>
      <label class="field ops-field"><span>Condições de atendimento</span><textarea name="conditions" rows="3">${esc(record?.conditions)}</textarea></label>
      ${formActions(button(record ? (scheduled ? "schedule" : "order") : view, "Voltar", record?.id), record ? "Salvar alterações" : scheduled ? "Salvar agendamento" : "Cadastrar pedido")}
    </form>`;
  }

  function allocationForm(order, detail) {
    const index = detail.itemIndex;
    const item = order.items[index];
    if (!item || order.status === "Cancelado") return orderDetail(order);
    const allocation = order.allocations.find(entry => entry.id === detail.allocationId);
    const selected = allocation && currentProducer(allocation)?.id;
    const total = orderAllocations(order, item, index).filter(entry => entry !== allocation).reduce((sum, entry) => sum + Number(entry.qty), 0);
    const balance = exceeds(item.qty, total) ? Number((item.qty - total).toPrecision(12)) : 0;
    const options = state.producers.map(producer => `<option value="${esc(producer.id)}" ${selected === producer.id ? "selected" : ""}>${esc(producer.name)}${producer.status !== "Ativo" ? " (inativo)" : ""}</option>`).join("");
    const title = allocation ? "Editar alocação" : "Registrar alocação";
    const hint = `${item.name} · ${balance} ${item.unit} disponíveis para esta alocação`;
    return heading(title, hint, "", `<button type="button" class="ops-back" data-ops-action="order" data-id="${esc(order.id)}">← Voltar ao pedido</button>`) + `<form class="card ops-form ops-form-narrow" data-ops-form="allocation" data-id="${esc(order.id)}" data-item="${index}" data-allocation="${esc(allocation?.id)}">
      <label class="field ops-field"><span>Produtor</span><select name="producerId" required><option value="">Selecione um produtor</option>${options}</select></label>
      <div class="form-grid">${input("Quantidade", "qty", allocation?.qty, 'type="number" step="any" min="0" required')}${input("Unidade", "unit", item.unit, "readonly")}</div>
      <label class="ops-check"><input type="checkbox" name="confirmed" ${allocation?.confirmed ? "checked" : ""} required> Confirmei a disponibilidade com o produtor.</label>
      ${formActions(button("order", "Voltar", order.id), "Salvar alocação")}
    </form>`;
  }

  function render() {
    const detail = state.detail || {};
    const scheduled = state.view === "schedules";
    const records = scheduled ? state.schedules : state.orders;
    const record = records.find(entry => entry.id === detail.id);
    if (detail.mode === "new") return orderScheduleForm(null, scheduled);
    if (record && detail.mode === "edit" && record.status !== "Cancelado") return orderScheduleForm(record, scheduled);
    if (record && !scheduled && detail.mode === "allocation") return allocationForm(record, detail);
    if (record) return scheduled ? scheduleDetail(record) : orderDetail(record);
    return scheduled ? scheduleList() : orderList();
  }

  function confirmCancel(record, scheduled) {
    ctx.confirm({
      title: scheduled ? "Cancelar agendamento?" : "Cancelar pedido?",
      message: scheduled ? "As ocorrências pendentes deixam de ser geradas. O histórico continua disponível." : "As alocações deste pedido serão removidas e o pedido continuará disponível para consulta.",
      label: scheduled ? "Cancelar agendamento" : "Cancelar pedido",
      onConfirm() {
        record.status = "Cancelado";
        if (!scheduled) record.allocations = [];
        save();
        ctx.render();
        toast(scheduled ? "Agendamento cancelado." : "Pedido cancelado.");
      }
    });
  }

  function navigateTo(view, mode, id, extra = {}) {
    navigate(view, { mode, id, ...extra });
  }

  function click(target) {
    const action = target.dataset.opsAction;
    if (!action) return false;
    const { id, allocation: allocationId } = target.dataset;
    const order = state.orders.find(entry => entry.id === id);
    const schedule = state.schedules.find(entry => entry.id === id);
    switch (action) {
      case "orders": case "schedules": navigate(action); break;
      case "order": case "edit-order": navigateTo("orders", action === "order" ? "detail" : "edit", id); break;
      case "schedule": case "edit-schedule": navigateTo("schedules", action === "schedule" ? "detail" : "edit", id); break;
      case "new-order": case "new-schedule": navigateTo(action === "new-order" ? "orders" : "schedules", "new"); break;
      case "cancel-order": if (order) confirmCancel(order, false); break;
      case "cancel-schedule": if (schedule) confirmCancel(schedule, true); break;
      case "source": ctx.openSource(id); break;
      case "add-allocation": case "edit-allocation":
        navigateTo("orders", "allocation", id, { itemIndex: Number(target.dataset.item), allocationId }); break;
      case "remove-allocation":
        if (!order || order.status === "Cancelado") break;
        ctx.confirm({ title: "Remover alocação?", message: "A quantidade volta a ficar disponível para alocação neste pedido.", label: "Remover alocação", onConfirm() {
          order.allocations = order.allocations.filter(entry => entry.id !== allocationId);
          save();
          ctx.render();
          toast("Alocação removida.");
        } });
        break;
      case "simulate-occurrence": {
        const date = target.dataset.date;
        if (!schedule || pendingOccurrences(schedule)[0]?.date !== date) break;
        if (recordOccurrence(schedule, date, "Gerada")) {
          save();
          ctx.render();
          toast("Ocorrência disponível na triagem.");
        }
        break;
      }
      case "add-item": {
        const fields = target.closest("form").querySelector(".ops-item-fields");
        fields.insertAdjacentHTML("beforeend", itemRow());
        fields.lastElementChild.querySelector('[name="item-name"]').focus();
        break;
      }
      case "remove-item": {
        const fieldset = target.closest("fieldset");
        const fields = fieldset.parentElement;
        if (fields.children.length > 1) {
          fieldset.remove();
          fields.lastElementChild.querySelector('[name="item-name"]').focus();
        } else {
          formError(target.closest("form"), "Mantenha pelo menos um item no formulário.");
        }
        break;
      }
      default: return false;
    }
    return true;
  }

  function formError(form, message) {
    const alert = form.querySelector(".ops-form-error");
    alert.textContent = message;
    alert.hidden = false;
    alert.focus();
  }

  function formItems(form) {
    return Array.from(form.querySelectorAll(".ops-item-editor"), row => {
      const value = name => row.querySelector(`[name="${name}"]`).value;
      return { id: value("item-id"), productId: value("product-id"), name: value("item-name"), qty: value("item-qty"), unit: value("item-unit"), condition: value("item-condition") };
    });
  }

  function saveAllocation(form, data) {
    const order = state.orders.find(entry => entry.id === form.dataset.id);
    const index = Number(form.dataset.item);
    const item = order?.items[index];
    if (!item || order.status === "Cancelado") throw new Error("Este item não está disponível para alocação.");
    const producer = state.producers.find(entry => entry.id === data.get("producerId"));
    const reason = allocationBlock(order, item, producer);
    if (reason) throw new Error(reason);
    if (!data.has("confirmed")) throw new Error("Confirme a disponibilidade com o produtor.");
    const qty = quantity(data.get("qty"));
    if (!Number.isFinite(qty) || qty <= 0) throw new Error("Informe uma quantidade maior que zero.");
    const id = form.dataset.allocation;
    const allocated = orderAllocations(order, item, index).filter(entry => entry.id !== id).reduce((sum, entry) => sum + Number(entry.qty), 0);
    if (exceeds(allocated + qty, item.qty)) throw new Error("A quantidade excede o saldo disponível para o item.");
    const allocation = { id: id || uid("AL"), itemId: item.id || `legacy-${index}`, item: item.name, producerId: producer.id, producer: producer.name, qty, unit: item.unit, confirmed: true };
    if (id) order.allocations = order.allocations.map(entry => entry.id === id ? allocation : entry);
    else order.allocations.push(allocation);
    save();
    navigateTo("orders", "detail", order.id);
    toast("Alocação salva.");
  }

  function submit(form) {
    const kind = form.dataset.opsForm;
    if (!kind) return false;
    const data = new FormData(form);
    try {
      if (kind === "allocation") saveAllocation(form, data);
      if (kind === "order") {
        const input = { buyer: data.get("buyer"), due: data.get("due"), conditions: data.get("conditions"), items: formItems(form) };
        const existing = state.orders.find(order => order.id === form.dataset.id);
        if (existing) updateOrder(existing, input);
        const order = existing || createOrder(input);
        navigateTo("orders", "detail", order.id);
        toast(existing ? "Pedido atualizado." : "Pedido cadastrado.");
      }
      if (kind === "schedule") {
        const input = { buyer: data.get("buyer"), firstDate: data.get("firstDate"), lead: data.get("lead"), conditions: data.get("conditions"), items: formItems(form) };
        const existing = state.schedules.find(schedule => schedule.id === form.dataset.id);
        if (existing) {
          Object.assign(existing, validateSchedule(input));
          syncSchedule(existing);
          save();
        }
        const schedule = existing || createSchedule(input);
        navigateTo("schedules", "detail", schedule.id);
        toast(existing ? "Agendamento atualizado." : "Agendamento cadastrado.");
      }
    } catch (error) {
      formError(form, error.message);
    }
    return true;
  }

  function change(target) {
    if (target.name !== "item-name" || !target.closest(".ops-item-editor")) return false;
    const row = target.closest(".ops-item-editor");
    const product = currentProduct({ name: target.value });
    row.querySelector('[name="product-id"]').value = product?.id || "";
    if (product) row.querySelector('[name="item-unit"]').value = product.unit;
    return true;
  }

  return { render, click, submit, change, createOrder, createSchedule, syncSchedules };
};
