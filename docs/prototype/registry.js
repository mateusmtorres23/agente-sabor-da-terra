(function () {
  "use strict";

  const groups = {
    Produtores: { key: "producers", singular: "produtor", label: "Produtores", icon: "registry", prefix: "PR" },
    Produtos: { key: "products", singular: "produto", label: "Produtos", icon: "registry", prefix: "PROD" },
    Documentos: { key: "documents", singular: "documento", label: "Documentos", icon: "file", prefix: "DOC" }
  };

  window.createPrototypeRegistry = function (ctx) {
    const { state, esc, badge, save, toast, openSource, navigate, icon, uid, confirm } = ctx;

    function group() {
      return groups[state.registryTab] || groups.Produtores;
    }

    function records() {
      return state[group().key];
    }

    function byId(id) {
      return records().find((record) => record.id === id);
    }

    function citationId(id) {
      const doc = state.documents.find((record) => record.id === id);
      return doc ? `${doc.id}:v${doc.version || 1}` : id;
    }

    function resolveDocument(id) {
      for (const doc of state.documents) {
        if (doc.id === id || citationId(doc.id) === id) return doc;
        const archived = (doc.versions || []).find((version) => version.id === id);
        if (archived) return archived;
      }
      return null;
    }

    function producerMatches(allocation, record) {
      return allocation.producerId ? allocation.producerId === record.id : allocation.producer === record.name;
    }

    function productMatches(item, record) {
      return item.productId ? item.productId === record.id : item.name === record.name;
    }

    function productItems(entry, record) {
      if (Array.isArray(entry.items)) return entry.items.filter((item) => productMatches(item, record));
      return [];
    }

    function legacyScheduleHasProduct(schedule, record) {
      return typeof schedule.items === "string" && schedule.items.split("\n").some((line) => line.split("•")[0].trim() === record.name);
    }

    function documentLinks(record) {
      const ids = [record.id, citationId(record.id), ...(record.versions || []).map((version) => version.id)];
      return state.conversations.filter((conversation) => conversation.messages.some((message) => ids.includes(message.citation)))
        .map((conversation) => `Citação em “${conversation.title}”`);
    }

    function linksFor(record) {
      const key = group().key;
      let links = [];
      if (key === "documents") links = documentLinks(record);
      if (key === "producers") {
        links = state.orders.filter((order) => order.allocations.some((allocation) => producerMatches(allocation, record)))
          .map((order) => `Alocação no pedido ${order.id}`);
      }
      if (key === "products") {
        const inOrders = state.orders.filter((order) => productItems(order, record).length);
        const inSchedules = state.schedules.filter((schedule) => productItems(schedule, record).length ||
          (typeof schedule.items === "string" && ((schedule.productIds || []).includes(record.id) || legacyScheduleHasProduct(schedule, record))));
        links = [...inOrders.map((order) => `Item do pedido ${order.id}`), ...inSchedules.map((schedule) => `Item do agendamento ${schedule.id}`)];
      }
      if (record.linked && !links.length) links.push("Vínculo registrado na base de demonstração");
      return links;
    }

    function actionButton(action, label, options = {}) {
      const { tone = "", glyph = "", id = "" } = options;
      return `<button type="button" class="btn ${tone}" data-reg-action="${action}"${id ? ` data-id="${esc(id)}"` : ""}>${glyph ? icon(glyph) : ""}${label}</button>`;
    }

    function tabList() {
      const current = group().label;
      return `<nav class="registry-tabs" aria-label="Categorias de cadastro">${Object.keys(groups).map((label) => `
        <button type="button" class="registry-tab" ${label === current ? 'aria-current="page"' : ""} data-reg-action="tab" data-tab="${label}">${label}</button>`).join("")}</nav>`;
    }

    function listPage() {
      const { key, singular, label } = group();
      const columns = {
        producers: ["Nome", "Município", "Situação"],
        products: ["Nome", "Unidade", "Sazonalidade"],
        documents: ["Documento", "Tipo", "Situação"]
      }[key];
      const rows = records().map((record) => {
        const detail = record.city || record.unit || record.kind;
        const status = key === "products" ? esc(record.season || "—") : badge(record.status || "Disponível");
        return `<tr>
          <td><strong>${esc(record.name)}</strong><span class="registry-id">${esc(record.id)}</span></td>
          <td>${esc(detail || "—")}</td><td>${status}</td>
          <td class="registry-table-action">${actionButton("detail", "Abrir", { id: record.id, tone: "small", glyph: "arrow-right" })}</td>
        </tr>`;
      }).join("");
      return `<div class="registry-page">
        <header class="page-heading"><h1>Cadastros</h1>${actionButton("new", `Cadastrar ${singular}`, { tone: "primary", glyph: "plus" })}</header>
        ${tabList()}
        ${rows ? `<div class="card table-wrap"><table class="data-table"><thead><tr>${columns.map((column) => `<th scope="col">${column}</th>`).join("")}<th scope="col"><span class="sr-only">Ações</span></th></tr></thead><tbody>${rows}</tbody></table></div>` : `<div class="card empty">Nenhum registro em ${label.toLowerCase()}.</div>`}
      </div>`;
    }

    function fieldsFor(record) {
      if (group().key === "producers") return [["Município", record.city], ["Contato", record.contact], ["Situação", record.status]];
      if (group().key === "products") return [["Unidade", record.unit], ["Sazonalidade", record.season]];
      return [["Tipo", record.kind], ["Situação", record.status], ["Arquivo", record.fileName || `${record.name}.txt`]];
    }

    function breadcrumbs(record, editing = false) {
      return `<nav class="registry-breadcrumb" aria-label="Localização em Cadastros">
        <button class="link-button" type="button" data-reg-action="list">${group().label}</button>
        <span aria-hidden="true">/</span>
        ${editing ? `<button class="link-button" type="button" data-reg-action="detail" data-id="${esc(record.id)}">${esc(record.name)}</button><span aria-hidden="true">/</span><span aria-current="page">Editar</span>` : `<span aria-current="page">${esc(record ? record.name : "Novo cadastro")}</span>`}
      </nav>`;
    }

    function documentVersions(record) {
      const archived = record.versions || [];
      return `<section class="card registry-section"><h2>Arquivo original</h2>
        <div class="registry-file"><div class="registry-file-icon" aria-hidden="true">${icon("file")}</div><div><strong>${esc(record.fileName || `${record.name}.txt`)}</strong><small>Versão ${record.version || 1}</small></div>${actionButton("open-document", "Ver arquivo", { id: record.id, glyph: "external" })}</div>
        ${archived.length ? `<details class="registry-versions"><summary>Versões anteriores (${archived.length})</summary><ul>${archived.slice().reverse().map((version) => `<li><span>Versão ${version.version} · ${esc(version.fileName || version.name)}</span>${actionButton("open-document", "Ver arquivo", { id: version.id, tone: "small" })}</li>`).join("")}</ul></details>` : ""}
      </section>`;
    }

    function detailPage(record) {
      const links = linksFor(record);
      const isDocument = group().key === "documents";
      return `<div class="registry-page">
        ${breadcrumbs(record)}
        <header class="page-heading"><div><h1>${esc(record.name)}</h1><p>${esc(record.id)}</p></div><div class="actions">${actionButton("edit", "Editar cadastro", { id: record.id, glyph: "edit", tone: "primary" })}</div></header>
        <div class="registry-detail-grid"><div class="registry-detail-main">
          <section class="card registry-section"><h2>Dados do cadastro</h2><dl class="registry-details">${fieldsFor(record).map(([label, value]) => `<div><dt>${label}</dt><dd>${esc(value || "—")}</dd></div>`).join("")}</dl></section>
          ${isDocument ? documentVersions(record) : ""}
        </div><aside class="card registry-section registry-links">
          <h2>Vínculos</h2>${links.length ? `<ul>${links.map((link) => `<li>${esc(link)}</li>`).join("")}</ul><p>Exclusão bloqueada pelos vínculos acima.</p>` : `<p>Este cadastro pode ser excluído.</p>${actionButton("delete", "Excluir cadastro", { id: record.id, tone: "danger" })}`}
        </aside></div>
      </div>`;
    }

    function input(name, label, value, required = false) {
      return `<div class="field"><label for="reg-${name}">${label}</label><input id="reg-${name}" name="${name}" value="${esc(value)}"${required ? " required" : ""}></div>`;
    }

    function formPage(record) {
      const editing = Boolean(record);
      const data = record || {};
      const { key, singular } = group();
      let fields;
      if (key === "producers") {
        const status = data.status || "Ativo";
        const statuses = [...new Set(["Ativo", "Inativo", status])];
        fields = `${input("city", "Município", data.city, true)}${input("contact", "Contato", data.contact)}
          <div class="field"><label for="reg-status">Situação</label><select id="reg-status" name="status">${statuses.map((option) => `<option${status === option ? " selected" : ""}>${esc(option)}</option>`).join("")}</select></div>`;
      } else if (key === "products") {
        fields = `${input("unit", "Unidade", data.unit, true)}${input("season", "Sazonalidade", data.season)}`;
      } else {
        fields = `${input("kind", "Tipo de documento", data.kind, true)}${input("status", "Situação", data.status || "Disponível")}
          <div class="field full"><label for="reg-file">${editing ? "Substituir arquivo original" : "Arquivo original"}</label><input type="file" id="reg-file" name="file" accept=".txt,.md,.csv,.json,.pdf">
            <p class="registry-help">${editing ? "Uma substituição preserva as versões citadas em conversas. " : ""}Formatos aceitos: PDF, TXT, Markdown, CSV e JSON.</p>
          </div>
          ${data.fileData ? "" : `<div class="field full"><label for="reg-content">Conteúdo em texto</label><textarea id="reg-content" name="content" rows="6">${esc(data.content)}</textarea><p class="registry-help">Você pode inserir o conteúdo diretamente. Nesse caso, o original fica disponível em formato TXT.</p></div>`}`;
      }
      const back = editing ? actionButton("detail", "Cancelar", { id: record.id }) : actionButton("list", "Cancelar");
      return `<div class="registry-page">
        ${breadcrumbs(record, editing)}
        <header class="page-heading"><h1>${editing ? `Editar ${singular}` : `Cadastrar ${singular}`}</h1></header>
        <form class="card registry-section registry-form" data-reg-form="save" data-id="${esc(data.id)}">
          <div class="form-grid">${input("name", "Nome", data.name, true)}${fields}</div>
          <p class="notice error" data-reg-error role="alert" hidden></p>
          <div class="form-actions">${back}<button class="btn primary" type="submit">${editing ? "Salvar alterações" : "Cadastrar"}</button></div>
        </form>
      </div>`;
    }

    function renderPage() {
      const detail = state.detail || {};
      if (detail.mode === "new") return formPage(null);
      const record = byId(detail.id);
      if (record && detail.mode === "detail") return detailPage(record);
      if (record && detail.mode === "edit") return formPage(record);
      return listPage();
    }

    function go(mode, id) {
      navigate("registry", mode ? { mode, id } : null);
    }

    function remove(record) {
      const existingLinks = linksFor(record);
      if (existingLinks.length) {
        toast(`Exclusão bloqueada. ${existingLinks[0]}.`);
        return;
      }
      confirm({
        title: "Excluir cadastro",
        message: `Excluir “${record.name}” dos cadastros?`,
        label: "Excluir cadastro",
        onConfirm() {
          if (linksFor(record).length) return toast("O cadastro ganhou um vínculo e a exclusão foi bloqueada.");
          const entries = records();
          const index = entries.indexOf(record);
          if (index < 0) return;
          entries.splice(index, 1);
          try {
            save();
          } catch (error) {
            entries.splice(index, 0, record);
            toast("Não foi possível salvar a exclusão neste navegador.");
            return;
          }
          go();
          toast("Cadastro excluído.");
        }
      });
    }

    function click(button) {
      const action = button.dataset.regAction;
      if (!action) return false;
      const { id, tab } = button.dataset;
      switch (action) {
        case "tab": state.registryTab = tab; save(); go(); break;
        case "list": go(); break;
        case "new": go("new"); break;
        case "detail": go("detail", id); break;
        case "edit": go("edit", id); break;
        case "open-document": openSource(id); break;
        case "delete": {
          const record = byId(id);
          if (record) remove(record);
          break;
        }
      }
      return true;
    }

    function archiveDocument(record) {
      const { versions, ...snapshot } = record;
      const id = citationId(record.id);
      return [...(versions || []), { ...snapshot, id, documentId: record.id, version: record.version || 1 }];
    }

    function stableReferences(record) {
      if (group().key === "producers") {
        return state.orders.flatMap((order) => order.allocations.filter((allocation) => !allocation.producerId && producerMatches(allocation, record)))
          .map((allocation) => [allocation, "producerId", record.id]);
      }
      if (group().key === "products") {
        const itemReferences = [...state.orders, ...state.schedules].flatMap((entry) => productItems(entry, record)).filter((item) => !item.productId)
          .map((item) => [item, "productId", record.id]);
        const legacyReferences = state.schedules.filter((schedule) => legacyScheduleHasProduct(schedule, record) && !(schedule.productIds || []).includes(record.id))
          .map((schedule) => [schedule, "productIds", [...(schedule.productIds || []), record.id]]);
        return [...itemReferences, ...legacyReferences];
      }
      return state.conversations.flatMap((conversation) => conversation.messages.filter((message) => message.citation === record.id))
        .map((message) => [message, "citation", citationId(record.id)]);
    }

    function fileDataUrl(file, mimeType) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.replace(/^data:[^;]*;/, `data:${mimeType};`));
        reader.onerror = () => reject(new Error("Não foi possível ler o arquivo selecionado."));
        reader.readAsDataURL(file);
      });
    }

    async function documentFields(formData, previous, name) {
      const kind = String(formData.get("kind")).trim();
      if (!kind) throw new Error("Informe o tipo de documento.");
      const status = String(formData.get("status")).trim() || "Disponível";
      const file = formData.get("file");
      if (file && file.name) {
        const typeByExtension = { pdf: "application/pdf", txt: "text/plain", md: "text/markdown", csv: "text/csv", json: "application/json" };
        const mimeType = typeByExtension[file.name.split(".").pop().toLowerCase()];
        if (!mimeType) throw new Error("Escolha um arquivo PDF, TXT, Markdown, CSV ou JSON.");
        if (!file.size) throw new Error("O arquivo selecionado está vazio.");
        const [fileData, content] = await Promise.all([fileDataUrl(file, mimeType), mimeType === "application/pdf" ? "" : file.text()]);
        return { name, kind, status, content, fileName: file.name, fileData, mimeType };
      }
      if (previous && previous.fileData) return { ...previous, name, kind, status };
      const content = String(formData.get("content"));
      if (!content.trim()) throw new Error("Selecione um arquivo ou informe o conteúdo do documento.");
      const fileName = (previous && (previous.fileName || `${previous.name}.txt`)) || `${name}.txt`;
      return { name, kind, status, content, fileName, mimeType: "text/plain" };
    }

    async function readForm(form, previous) {
      const formData = new FormData(form);
      const value = (field) => String(formData.get(field) || "").trim();
      const name = value("name");
      if (!name) throw new Error("Informe o nome do cadastro.");
      if (group().key === "documents") return documentFields(formData, previous, name);
      if (group().key === "producers") {
        const city = value("city");
        if (!city) throw new Error("Informe o município do produtor.");
        return { name, city, contact: value("contact"), status: value("status") };
      }
      const unit = value("unit");
      if (!unit) throw new Error("Informe a unidade do produto.");
      return { name, unit, season: value("season") };
    }

    async function saveForm(form) {
      const submitButton = form.querySelector('[type="submit"]');
      if (submitButton.disabled) return;
      submitButton.disabled = true;
      const feedback = form.querySelector("[data-reg-error]");
      feedback.hidden = true;
      const editing = Boolean(form.dataset.id);
      const entries = records();
      const previous = byId(form.dataset.id);
      const index = previous ? entries.indexOf(previous) : entries.length;
      try {
        if (editing && !previous) throw new Error("O registro não está mais disponível.");
        const fields = await readForm(form, previous);
        if (!form.isConnected) return;
        const id = previous ? previous.id : uid(group().prefix);
        const record = { linked: false, ...previous, ...fields, id };
        if (previous && Object.keys(fields).every((key) => fields[key] === previous[key])) {
          go("detail", id);
          return;
        }
        if (previous && group().key === "documents") {
          record.versions = archiveDocument(previous);
          record.version = (previous.version || 1) + 1;
        }
        const references = previous ? stableReferences(previous) : [];
        const originalValues = references.map(([entry, field]) => entry[field]);
        references.forEach(([entry, field, value]) => { entry[field] = value; });
        entries[index] = record;
        try {
          save();
        } catch (error) {
          if (previous) entries[index] = previous;
          else entries.pop();
          references.forEach(([entry, field], i) => {
            if (originalValues[i] === undefined) delete entry[field];
            else entry[field] = originalValues[i];
          });
          throw new Error("O navegador não conseguiu guardar o cadastro. Verifique o espaço disponível e o tamanho do arquivo.");
        }
        go("detail", id);
        toast(editing ? "Alterações salvas." : "Cadastro criado.");
      } catch (error) {
        feedback.textContent = error.message;
        feedback.hidden = false;
      } finally {
        submitButton.disabled = false;
      }
    }

    function submit(form) {
      if (form.dataset.regForm !== "save") return false;
      saveForm(form);
      return true;
    }

    return { render: renderPage, click, submit, resolveDocument, citationId };
  };
}());
