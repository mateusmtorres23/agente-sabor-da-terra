(function () {
  "use strict";

  const draftLabels = {
    pedido: "Rascunho de pedido",
    agendamento: "Rascunho de agendamento",
    resposta: "Rascunho de resposta",
    notificacao: "Rascunho de notificação"
  };

  const integratedChannels = ["E-mail", "WhatsApp", "Telegram"];
  const reviewLabels = {
    pedido: "Revisar pedido",
    agendamento: "Revisar agendamento",
    resposta: "Revisar resposta",
    notificacao: "Revisar notificação"
  };
  const calendarMonths = "janeiro fevereiro marco abril maio junho julho agosto setembro outubro novembro dezembro".split(" ");
  const uncertainResult = "Resultado incerto";
  const uncertainNotice = "O canal ainda não confirmou o envio. Reenviar pode duplicar a mensagem.";

  function dateInput(value) {
    const iso = /^\d{1,2}\/\d{1,2}\/\d{4}$/.test(value || "")
      ? value.split("/").map(part => part.padStart(2, "0")).reverse().join("-") : value;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso || "")) return "";
    const date = new Date(`${iso}T00:00:00Z`);
    return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === iso ? iso : "";
  }

  function normalize(text) {
    return String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  }

  function mentionedDeadline(text) {
    const wording = normalize(text);
    const compact = wording.match(/\b(\d{1,2})\s+(?:a|ate)\s+(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})\b/);
    if (compact) {
      const [, first, last, month, year] = compact;
      const monthNumber = calendarMonths.indexOf(month) + 1;
      return { due: dateInput(`${first}/${monthNumber}/${year}`), dueEnd: dateInput(`${last}/${monthNumber}/${year}`) };
    }
    const dates = [...wording.matchAll(/\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}\/\d{1,2}\/\d{4})\b/g)];
    if (!dates.length) return null;
    const [first, second] = dates;
    if (!second) return { due: dateInput(first[0]) };
    const separator = wording.slice(first.index + first[0].length, second.index).trim();
    return { due: dateInput(first[0]), dueEnd: /^(?:a|ate|e|[-–—])$/.test(separator) ? dateInput(second[0]) : "" };
  }

  function draftItems(value) {
    if (Array.isArray(value)) return value;
    return String(value || "").split("\n").filter(line => line.trim()).map(line => {
      const [name, qty, unit, condition = ""] = line.split(/[|•]/).map(part => part.trim());
      return { name, qty, unit, condition };
    });
  }

  window.createPrototypeChat = function (ctx) {
    const { state, esc, dateBR, render, save, toast, openSource, downloadPDF, navigate, uid } = ctx;
    const scrollPositions = new Map();
    const composerDrafts = new Map();
    let nextFocus = null;
    let scrollToEnd = true;

    function activeConversation() {
      return state.conversations.find((entry) => entry.id === state.activeChat);
    }

    function requestFor(conversation) {
      return conversation && state.triage.find((request) => request.id === conversation.requestId);
    }

    function message(role, text, extras) {
      return Object.assign({ role, text, id: uid("MSG") }, extras);
    }

    function showConversation(conversation) {
      state.activeChat = conversation.id;
      scrollToEnd = true;
      nextFocus = "composer-input";
      save();
      navigate("chat");
    }

    function newChat() {
      const conversation = { id: uid("CHAT"), title: "Novo chat", requestId: null, messages: [] };
      state.conversations.push(conversation);
      showConversation(conversation);
    }

    function openRequest(id) {
      const request = state.triage.find((entry) => entry.id === id);
      if (!request) return;
      ctx.startRequestAnalysis(request);
      let conversation = state.conversations.find((entry) => entry.requestId === id);
      if (!conversation) {
        const text = [request.analysis || request.summary, request.pending && request.state !== "Encerrada" && `Pendência: ${request.pending}`]
          .filter(Boolean).join("\n\n");
        conversation = {
          id,
          title: request.buyer,
          requestId: id,
          messages: [message("agent", text, {
            citation: request.analysisDocumentId ? ctx.citationId(request.analysisDocumentId) : undefined,
            actions: (request.drafts || []).map((kind) => ({ kind }))
          })]
        };
        state.conversations.push(conversation);
      }
      showConversation(conversation);
    }

    function history() {
      const conversations = state.conversations.filter((entry) => entry.messages.length || entry.id === state.activeChat);
      if (!conversations.length) return "";
      return `<div class="conversation-history"><h2>Conversas</h2><ul>${conversations.slice().reverse().map((entry) => `
        <li><button type="button" class="conversation-history-item" data-chat-action="switch" data-chat-id="${esc(entry.id)}"
          ${entry.id === state.activeChat && state.view === "chat" ? 'aria-current="page"' : ""}>${esc(entry.title)}</button></li>`).join("")}</ul></div>`;
    }

    function button(action, label, attrs = "", style = "") {
      return `<button type="button" class="chat-button ${style}" data-chat-action="${action}" ${attrs}>${label}</button>`;
    }

    function startScreen() {
      const suggestions = [
        ["Consultar um lote", "Qual a origem do lote LOT-2026-0094?"],
        ["Ver um resumo de vendas", "Gere um resumo por produtor para João da Serra"],
        ["Consultar um certificado", "Consulte a certificação orgânica de João da Serra"],
        ["Sugerir produtor de tomate", "Sugira um produtor para fornecer tomate"]
      ];
      return `<div class="chat-start"><h2>Como posso ajudar?</h2><div class="chat-suggestions">${suggestions.map(([label, text]) =>
        button("suggest", esc(label), `data-chat-text="${esc(text)}"`)).join("")}</div></div>`;
    }

    function renderChat() {
      const conversation = activeConversation();
      const request = requestFor(conversation);
      const hasMessages = Boolean(conversation?.messages.length);
      return `<section class="chat-workspace ${hasMessages ? "" : "chat-workspace-empty"}" aria-label="Conversa com o assistente">
        <header class="chat-topline">
          <div class="chat-topline-title"><h1>${esc(conversation?.title || "Novo chat")}</h1>
          ${request ? `<p>${esc(request.id)} · ${esc(request.channel)}${request.sample ? " · Amostra" : ""} · <span data-triage-state="${esc(request.id)}">${esc(request.state)}</span></p>` : ""}</div>
          ${request ? button("source", "Ver mensagem original", `data-chat-id="${esc(request.id)}"`) : ""}
        </header>
        <div class="chat-scroll" id="chat-scroll" role="log" aria-label="Histórico da conversa" aria-live="polite">
          <div class="chat-transcript">${hasMessages ? conversation.messages.map(renderMessage).join("") : startScreen()}</div>
        </div>
        <footer class="chat-compose-area"><form class="chat-compose" data-chat-form="composer">
          <label class="chat-sr-only" for="composer-input">Mensagem para o assistente</label>
          <textarea id="composer-input" name="prompt" rows="1" placeholder="Envie uma mensagem" required></textarea>
          <button class="chat-send" type="submit" aria-label="Enviar mensagem" title="Enviar mensagem">${ctx.icon("arrow-up")}</button>
        </form></footer>
      </section>`;
    }

    function renderMessage(entry, index) {
      const user = entry.role === "user";
      const document = state.documents.find((doc) => doc.id === entry.citation);
      const source = entry.citation ? button("source", esc(entry.citationLabel || document?.name || entry.citation), `data-chat-id="${esc(entry.citation)}"`) : "";
      const pdf = entry.downloadSummary ? button("pdf", "Baixar resumo em PDF", `data-chat-index="${index}"`) : "";
      const go = entry.orderId ? button("order", "Abrir pedido", `data-chat-id="${esc(entry.orderId)}"`) : "";
      const schedule = entry.scheduleId ? button("schedule", "Abrir agendamento", `data-chat-id="${esc(entry.scheduleId)}"`) : "";
      const actions = (entry.actions || []).map(({ kind, label }) => draftLabels[kind]
        ? button("draft", esc(label || reviewLabels[kind]), `data-chat-kind="${kind}"`, "chat-button-plain")
        : "").join("");
      const attachments = source + pdf + go + schedule + actions;
      return `<article class="conversation-message ${user ? "conversation-message-user" : "conversation-message-agent"}">
        <span class="chat-message-label">${user ? "Você" : "Assistente"}</span>
        <div class="chat-message-text">${esc(entry.text)}</div>
        ${attachments ? `<div class="chat-message-actions">${attachments}</div>` : ""}
        ${entry.draft ? renderDraft(entry.draft, index) : ""}
      </article>`;
    }

    function renderDraft(draft, index) {
      const title = draftLabels[draft.kind];
      if (!title) return "";
      if (draft.completed) {
        return `<section class="writing-block writing-block-complete"><h3>${title}</h3><p>${esc(draft.completed)}</p></section>`;
      }
      const isSchedule = draft.kind === "agendamento";
      const isSending = draft.kind === "resposta" || draft.kind === "notificacao";
      const fields = isSending ? renderSendFields(draft) : `<div class="writing-fields">
        <label${isSchedule ? "" : ' class="writing-full"'}>Comprador<input name="buyer" required value="${esc(draft.buyer)}"></label>
        <label>${isSchedule ? "Primeiro fornecimento" : "Data de entrega ou início do intervalo"}<input type="date" name="due" value="${esc(draft.due)}" required></label>
        ${isSchedule ? "" : `<label>Fim do intervalo (opcional)<input type="date" name="dueEnd" value="${esc(draft.dueEnd)}"></label>`}
        <fieldset class="writing-items writing-full"><legend>Itens</legend>
          <div data-writing-items>${(draftItems(draft.items).length ? draftItems(draft.items) : [{}]).map(renderDraftItem).join("")}</div>
          ${button("add-item", "Adicionar item")}
        </fieldset>
        ${isSchedule ? `<label>Antecedência em dias<input name="lead" type="number" min="0" value="${esc(draft.lead)}" required></label><label>Recorrência<input value="Semanal" readonly></label>` : ""}
        <label class="writing-full">Condições de atendimento<textarea name="conditions" rows="2">${esc(draft.conditions)}</textarea></label>
      </div>`;
      const submitLabel = isSchedule ? "Salvar agendamento" : "Cadastrar pedido";
      return `<form class="writing-block" id="chat-draft-${index}" data-chat-form="review" data-chat-index="${index}">
        <header><h3>${title}</h3><span>Em revisão</span></header>
        <div class="writing-body">${fields}<p class="writing-error" role="alert" hidden></p></div>
        <footer>${isSending
          ? `${button("copy", "Copiar resposta")}${draft.sendAllowed ? '<button class="chat-button chat-button-primary" type="submit">Enviar na demonstração</button>' : ""}`
          : `<button class="chat-button chat-button-primary" type="submit">${submitLabel}</button>`}</footer>
      </form>`;
    }

    function renderDraftItem(item) {
      return `<div class="writing-item">
        <label>Produto<input name="itemName" required value="${esc(item.name)}"></label>
        <label>Quantidade<input name="itemQty" type="number" step="any" min="0" required value="${esc(item.qty)}"></label>
        <label>Unidade<input name="itemUnit" required value="${esc(item.unit)}"></label>
        ${button("remove-item", ctx.icon("x"), 'aria-label="Remover item" title="Remover item"')}
        <label class="writing-item-condition">Condição do item<input name="itemCondition" value="${esc(item.condition)}"></label>
      </div>`;
    }

    function readDraftItems(form) {
      return [...form.querySelectorAll(".writing-item")].map(row => {
        const value = name => row.querySelector(`[name="${name}"]`).value.trim();
        return { name: value("itemName"), qty: value("itemQty"), unit: value("itemUnit"), condition: value("itemCondition") };
      });
    }

    function editDraftItems(element, add) {
      const form = element.closest("form");
      const container = form.querySelector("[data-writing-items]");
      if (add) {
        container.insertAdjacentHTML("beforeend", renderDraftItem({}));
      } else if (container.children.length > 1) {
        element.closest(".writing-item").remove();
      } else {
        return showError(form, "Mantenha pelo menos um item no rascunho.");
      }
      activeConversation().messages[Number(form.dataset.chatIndex)].draft.items = readDraftItems(form);
      form.querySelector(".writing-error").hidden = true;
      container.lastElementChild.querySelector("input").focus();
      save();
    }

    function renderSendFields(draft) {
      const isNotification = draft.kind === "notificacao";
      const destinations = isNotification ? `<label>Destinatário<select name="producerId" required>${testProducers().map((producer) => `
        <option value="${esc(producer.id)}" ${producer.id === draft.producerId ? "selected" : ""}>${esc(producer.name)} · ${esc(producer.contact)}</option>`).join("")}</select></label>`
        : `<label>Destinatário<input value="${esc(draft.to || "Sem destino de envio")}" readonly></label>`;
      const notice = draft.reason ? `<p class="writing-hint writing-full">${esc(draft.reason)}</p>` : "";
      return `<div class="writing-fields">${destinations}<label>Canal<input value="${esc(draft.channel || "—")}" readonly></label>
        ${notice}<label class="writing-full">${isNotification ? "Notificação" : "Resposta"}
        <textarea name="text" rows="4" required>${esc(draft.text)}</textarea></label></div>`;
    }

    function testProducers() {
      return state.producers.filter((producer) => typeof producer.contact === "string" && producer.contact.endsWith(".test"));
    }

    function requestDestination(request) {
      return request?.destination || request?.contact || request?.sender || (request?.id === "MSG-TESTE-01" ? "Ana Teste · contato de teste" : "");
    }

    function hasUncertainReply(conversation, destination, channel) {
      return state.sends.some(send => send.conversationId === conversation.id &&
        send.kind === "resposta" && send.to === destination && send.channel === channel && send.result === uncertainResult);
    }

    function requestItems(request) {
      if (Array.isArray(request?.items)) {
        return request.items.map(({ name, qty, unit, condition }) => [name, qty, unit, condition || ""].join(" | ")).join("\n");
      }
      const samples = {
        "PED-2026-003": "Tomate | 200 | kg",
        "PED-2026-004": "Mel orgânico | 15 | potes | Certificação orgânica vigente\nBanana | 30 | kg",
        "PED-2026-011": "Couve | 80 | maços\nMandioca | 40 | kg",
        "AG-2026-001": "Hortaliças variadas | 40 | kg"
      };
      return samples[request?.id] || "";
    }

    function createDraft(kind, request, conversation) {
      if (kind === "resposta") {
        const to = requestDestination(request);
        const canSend = Boolean(request && !request.sample && to && integratedChannels.includes(request.channel));
        const uncertain = canSend && hasUncertainReply(conversation, to, request.channel);
        return {
          kind, to, channel: request?.channel, sendAllowed: canSend && !uncertain,
          reason: uncertain ? uncertainNotice : request?.sample ? "Mensagem da amostra. Você pode copiar o texto revisado."
            : canSend ? "O envio será simulado para o contato de teste." : "Envio indisponível para esta conversa. Você pode copiar o texto revisado.",
          text: request?.type === "Consulta documental" && /0094/.test(request.original || "")
            ? "Olá! O lote LOT-2026-0094 registra 300 unidades de alface. Podemos esclarecer qualquer outra dúvida sobre a rastreabilidade."
            : "Olá! Recebemos sua solicitação e estamos conferindo as condições de atendimento. Retornaremos assim que tivermos uma atualização."
        };
      }
      if (kind === "notificacao") {
        const producer = testProducers()[0];
        return {
          kind, channel: "E-mail", producerId: producer?.id, sendAllowed: Boolean(producer),
          reason: producer ? "O envio será simulado para o contato de teste selecionado." : "Cadastre um endereço de teste para simular o envio.",
          text: "Olá! A Sabor da Terra gostaria de consultar sua disponibilidade para um novo fornecimento. Podemos confirmar com você os produtos, as quantidades e a data?"
        };
      }
      const storedDate = dateInput(request?.due);
      const supplied = storedDate ? { due: storedDate, dueEnd: dateInput(request.dueEnd) || undefined }
        : mentionedDeadline(request?.original);
      const hasValidDeadline = supplied?.due && supplied.dueEnd !== "" && (!supplied.dueEnd || supplied.dueEnd >= supplied.due);
      const revised = dateInput(conversation.confirmedDate);
      return {
        kind,
        buyer: request?.buyer || "",
        due: revised || (hasValidDeadline ? supplied.due : ""),
        dueEnd: kind === "pedido" ? (revised ? dateInput(conversation.confirmedDateEnd) : (hasValidDeadline && supplied.dueEnd) || "") : "",
        items: requestItems(request),
        conditions: request?.conditions || "",
        lead: 2
      };
    }

    function openDraft(kind) {
      const conversation = activeConversation();
      if (!conversation || !draftLabels[kind]) return;
      const openIndex = conversation.messages.findIndex(entry => entry.draft?.kind === kind && !entry.draft.completed);
      if (openIndex >= 0) {
        document.getElementById(`chat-draft-${openIndex}`)?.querySelector("input:not([readonly]), textarea, select")?.focus();
        return;
      }
      conversation.messages.push(message("agent", "", { draft: createDraft(kind, requestFor(conversation), conversation) }));
      nextFocus = `chat-draft-${conversation.messages.length - 1}`;
      scrollToEnd = true;
      save();
      render();
    }

    function replyTo(prompt, request, conversation) {
      const text = normalize(prompt);
      if (/resumo|vendas/.test(text)) return producerSummary(prompt);
      if (/notificac|notifiqu/.test(text)) return { draft: createDraft("notificacao", request, conversation) };
      if (/rascunho.*respost|respost|responda/.test(text)) return { draft: createDraft("resposta", request, conversation) };
      if (/agend|recorr/.test(text)) return { draft: createDraft("agendamento", request, conversation) };
      if (/rascunho.*pedido|cadastrar pedido|criar pedido/.test(text)) return { draft: createDraft("pedido", request, conversation) };
      if (/capacidade|produtor/.test(text) && /tomate/.test(`${text} ${normalize(request?.summary)}`)) {
        return capacitySuggestion();
      }
      const matchingDoc = state.documents.find((doc) => text.includes(normalize(doc.id)) || text.includes(normalize(doc.name)));
      if (matchingDoc) return documentAnswer(matchingDoc);
      if (/0094|origem do lote|rastreab.*alface/.test(text)) {
        const document = state.documents.find((doc) => doc.id === "DOC-2026-011");
        return document ? documentAnswer(document) : { text: "Não encontrei esse registro de rastreabilidade na base da demonstração." };
      }
      if (/certifica|certificad/.test(text) && !request) {
        const document = state.documents.find((doc) => doc.id === "DOC-2026-010");
        return document ? documentAnswer(document) : { text: "Não encontrei o certificado na base da demonstração." };
      }
      if (request && (request.drafts || []).includes("pedido")) {
        const deadline = mentionedDeadline(prompt);
        const actions = [{ kind: "pedido", label: "Revisar pedido" }];
        if (!deadline) {
          return { text: `Registrei seu esclarecimento sobre ${request.buyer}. Confira os dados no rascunho antes de cadastrar.`, actions };
        }
        const { due, dueEnd } = deadline;
        if (!due || dueEnd === "" || (dueEnd && dueEnd < due)) {
          return { text: "Informe uma data válida. Para um intervalo, o fim deve ser igual ou posterior ao início.", actions };
        }
        conversation.confirmedDate = due;
        conversation.confirmedDateEnd = dueEnd || "";
        for (const entry of conversation.messages) {
          if (entry.draft?.kind === "pedido" && !entry.draft.completed) {
            entry.draft.due = due;
            entry.draft.dueEnd = conversation.confirmedDateEnd;
          }
        }
        const reference = typeof ctx.today === "string" ? dateInput(ctx.today) : ctx.today.toISOString().slice(0, 10);
        if (request.state !== "Encerrada" && (request.pendingField === "due" || request.id === "PED-2026-003") && (dueEnd || due) >= reference) {
          request.pending = "";
          request.pendingField = "";
        }
        ctx.reviewRequest(request);
        return {
          text: `Registrei ${dueEnd ? `o intervalo de ${dateBR(due)} a ${dateBR(dueEnd)}` : `a data de ${dateBR(due)}`} no rascunho. Confira o prazo antes de cadastrar.`,
          actions
        };
      }
      return { text: "Na demonstração, posso consultar o lote LOT-2026-0094, conferir a certificação orgânica de João da Serra ou preparar seu resumo de vendas." };
    }

    function documentAnswer(document) {
      return {
        text: document.content || `Encontrei ${document.name}. Abra a fonte para consultar o original.`,
        citation: ctx.citationId(document.id) || document.id,
        citationLabel: document.name
      };
    }

    function capacitySuggestion() {
      const producer = state.producers.find((entry) => entry.id === "PR-001" && entry.status === "Ativo");
      const document = state.documents.find((entry) => entry.id === "DOC-DEMO-CAPACIDADE");
      if (!producer || !document) return { text: "Não encontrei uma estimativa de capacidade para os produtores ativos neste exemplo." };
      return {
        text: [`${producer.name} é um candidato para fornecer tomate.`, document.content,
          "Confirme com o produtor quanto ele pode entregar no prazo do pedido."].filter(Boolean).join("\n\n"),
        citation: ctx.citationId(document.id) || document.id,
        citationLabel: document.name
      };
    }

    function producerSummary(prompt) {
      const producer = state.producers.find((entry) => entry.id === "PR-001");
      if (!producer) return { text: "Não encontrei o produtor do exemplo na base da demonstração." };
      const start = "2026-09-01";
      const end = "2026-09-30";
      const reference = mentionedDeadline(prompt.match(/refer[eê]ncia(.+)/i)?.[1])?.due || "2026-11-11";
      const allocations = state.orders.filter((order) => {
        const due = dateInput(order.due);
        const dueEnd = dateInput(order.dueEnd) || due;
        return order.status !== "Cancelado" && due && due <= end && dueEnd >= start;
      })
        .flatMap((order) => order.allocations.filter((entry) => entry.producerId === producer.id || entry.producer === producer.name));
      let balance = "Sem pendência desse valor na data de referência.";
      if (reference >= "2026-10-01") balance = "Pagamento de R$ 940,00 registrado em 01/10/2026. O registro não comprova repasse bancário.";
      else if (reference >= "2026-09-02") balance = "R$ 940,00 a vencer em 02/10/2026.";
      const report = [
        `Resumo de demonstração de ${producer.name}`,
        `Período: ${dateBR(start)} a ${dateBR(end)} · Referência: ${dateBR(reference)}`,
        "Vendas: R$ 940,00, com transação registrada em setembro.",
        `Alocações: ${allocations.map((entry) => `${entry.qty} ${entry.unit} de ${entry.item}`).join(", ") || "nenhuma no período"}.`,
        `Pendência financeira: ${balance}`,
        "Fonte do exemplo: PED-2026-012."
      ].join("\n");
      return { text: report, downloadSummary: true };
    }

    function sendMessage(prompt) {
      const text = prompt.trim();
      if (!text) return;
      let conversation = activeConversation();
      if (!conversation) {
        conversation = { id: uid("CHAT"), title: "Novo chat", requestId: null, messages: [] };
        state.conversations.push(conversation);
        state.activeChat = conversation.id;
      }
      if (!conversation.messages.length && !conversation.requestId) conversation.title = text.length > 44 ? `${text.slice(0, 44)}…` : text;
      const response = replyTo(text, requestFor(conversation), conversation);
      conversation.messages.push(message("user", text), message("agent", "", response));
      composerDrafts.delete(conversation.id);
      scrollToEnd = true;
      nextFocus = "composer-input";
      save();
      render();
    }

    function showError(form, text) {
      const error = form.querySelector(".writing-error");
      error.hidden = false;
      error.textContent = text;
    }

    function confirmSend(form, draft, conversation, values) {
      const request = requestFor(conversation);
      const isNotification = draft.kind === "notificacao";
      const producer = isNotification && testProducers().find(({ id }) => id === values.get("producerId"));
      const destination = isNotification ? producer && `${producer.name} · ${producer.contact}` : requestDestination(request);
      if (!isNotification && hasUncertainReply(conversation, destination, draft.channel)) {
        return showError(form, uncertainNotice);
      }
      if (!draft.sendAllowed || !destination || (!isNotification && (!request || request.sample || !integratedChannels.includes(request.channel)))) {
        showError(form, "Envio indisponível. Use a opção de copiar o texto.");
        return;
      }
      const text = String(values.get("text") || "").trim();
      if (!text) return showError(form, "Escreva a mensagem antes de enviar.");
      const uncertain = !isNotification && request?.simulateUncertainSend;
      const result = uncertain ? uncertainResult : "Simulado com sucesso";
      state.sends.push({ id: uid("ENV"), kind: draft.kind, conversationId: conversation.id, text, to: destination, channel: draft.channel, result, at: new Date().toISOString() });
      draft.completed = uncertain ? uncertainResult : "Envio simulado confirmado";
      const notice = uncertain ? uncertainNotice : `Envio simulado registrado para ${destination} por ${draft.channel}.`;
      conversation.messages.push(message("agent", `${notice}\n\n${text}`));
      save();
      scrollToEnd = true;
      render();
    }

    function submitReview(form) {
      const conversation = activeConversation();
      const draft = conversation?.messages[Number(form.dataset.chatIndex)]?.draft;
      if (!draft || draft.completed) return;
      const values = new FormData(form);
      if (draft.kind === "resposta" || draft.kind === "notificacao") return confirmSend(form, draft, conversation, values);
      const items = readDraftItems(form);
      const buyer = String(values.get("buyer") || "").trim();
      const due = dateInput(values.get("due"));
      const isSchedule = draft.kind === "agendamento";
      const dueEnd = isSchedule ? "" : dateInput(values.get("dueEnd"));
      if (!items.length || !buyer || !due || items.some(item => !item.name || !item.unit || Number(item.qty) <= 0)) {
        return showError(form, "Informe comprador, prazo e itens com produto, quantidade positiva e unidade.");
      }
      if (!isSchedule && values.get("dueEnd") && (!dueEnd || dueEnd < due)) {
        return showError(form, "Informe um fim de intervalo igual ou posterior à data inicial.");
      }
      const request = requestFor(conversation);
      const details = { buyer, due, items, conditions: String(values.get("conditions") || "").trim(), source: request?.id || "—" };
      let result;
      try {
        result = isSchedule ? ctx.createSchedule({ ...details, firstDate: due, lead: Number(values.get("lead")) }) : ctx.createOrder({ ...details, dueEnd });
      } catch (error) {
        return showError(form, error.message);
      }
      if (!result || result.error) return showError(form, result?.error || "Não foi possível salvar o registro.");
      draft.completed = `${isSchedule ? "Agendamento salvo" : "Pedido cadastrado"} · ${result.id}`;
      conversation.messages.push(message("agent", `${isSchedule ? "Agendamento" : "Pedido"} ${result.id} confirmado.`,
        isSchedule ? { scheduleId: result.id } : { orderId: result.id }));
      save();
      scrollToEnd = true;
      render();
    }

    async function copyReview(form) {
      const field = form.elements.text;
      const text = field.value.trim();
      if (!text) return showError(form, "Escreva a mensagem antes de copiar.");
      try {
        await navigator.clipboard.writeText(text);
        toast("Resposta copiada.");
      } catch {
        field.focus();
        field.select();
        if (document.execCommand("copy")) toast("Resposta copiada.");
        else showError(form, "O texto está selecionado. Use Ctrl+C para copiar.");
      }
    }

    function click(element) {
      switch (element.dataset.chatAction) {
        case "switch": {
          const conversation = state.conversations.find((entry) => entry.id === element.dataset.chatId);
          if (conversation) showConversation(conversation);
          break;
        }
        case "source": openSource(element.dataset.chatId); break;
        case "suggest": sendMessage(element.dataset.chatText); break;
        case "draft": openDraft(element.dataset.chatKind); break;
        case "add-item": editDraftItems(element, true); break;
        case "remove-item": editDraftItems(element, false); break;
        case "pdf": downloadPDF(activeConversation()?.messages[Number(element.dataset.chatIndex)]?.text); break;
        case "order": navigate("orders", { mode: "detail", id: element.dataset.chatId }); break;
        case "schedule": navigate("schedules", { mode: "detail", id: element.dataset.chatId }); break;
        case "copy": copyReview(element.closest("form")); break;
        default: return false;
      }
      return true;
    }

    function submit(form) {
      if (form.dataset.chatForm === "composer") sendMessage(form.elements.prompt.value);
      else if (form.dataset.chatForm === "review") submitReview(form);
      else return false;
      return true;
    }

    function afterRender() {
      const scroller = document.getElementById("chat-scroll");
      if (!scroller) return;
      const conversation = activeConversation();
      const conversationId = conversation?.id || "new-chat";
      scroller.scrollTop = scrollToEnd ? scroller.scrollHeight : scrollPositions.get(conversationId) || 0;
      scroller.addEventListener("scroll", () => scrollPositions.set(conversationId, scroller.scrollTop));
      scrollToEnd = false;
      if (nextFocus) {
        const target = document.getElementById(nextFocus);
        if (target) (target.querySelector("input:not([readonly]), textarea, select") || target).focus();
        nextFocus = null;
      }
      const composer = document.getElementById("composer-input");
      function resizeComposer() {
        composer.style.height = "auto";
        composer.style.height = `${Math.min(composer.scrollHeight, 140)}px`;
      }
      composer.value = composerDrafts.get(conversationId) || "";
      resizeComposer();
      composer.addEventListener("input", () => {
        composerDrafts.set(conversationId, composer.value);
        resizeComposer();
      });
      composer.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
          event.preventDefault();
          composer.form.requestSubmit();
        }
      });
      scroller.querySelectorAll('[data-chat-form="review"]').forEach((form) => {
        const draft = conversation.messages[Number(form.dataset.chatIndex)].draft;
        form.addEventListener("input", ({ target }) => {
          if (target.closest(".writing-item")) draft.items = readDraftItems(form);
          else if (target.name) draft[target.name] = target.value;
        });
        form.addEventListener("change", save);
      });
    }

    return { render: renderChat, history, click, submit, openRequest, newChat, afterRender };
  };
})();
