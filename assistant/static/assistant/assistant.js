// The ResolveHub assistant: a help panel on every admin page. It sends the
// question with the page it was asked on (a form, a list or the desk in
// general), the field last focused on a form, and the last few exchanges so
// follow-up questions make sense. Answers are shown as plain text.
(function () {
  "use strict";

  const root = document.getElementById("rh-assistant");
  if (!root) return;

  const HISTORY_TURNS = 3;
  const toggle = root.querySelector(".rh-assistant-toggle");
  const panel = root.querySelector(".rh-assistant-panel");
  const closeButton = root.querySelector(".rh-assistant-close");
  const form = root.querySelector(".rh-assistant-form");
  const textarea = form.querySelector("textarea");
  const submit = form.querySelector("button[type=submit]");
  const fieldNote = root.querySelector(".rh-assistant-field");
  const log = root.querySelector(".rh-assistant-log");
  const suggestions = root.querySelector(".rh-assistant-suggestions");
  const history = [];
  let currentField = "";

  function setOpen(open) {
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    if (open) textarea.focus();
  }

  toggle.addEventListener("click", () => setOpen(panel.hidden));
  closeButton.addEventListener("click", () => setOpen(false));
  document.querySelectorAll("[data-rh-open-assistant]").forEach((button) => {
    button.addEventListener("click", () => setOpen(true));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) setOpen(false);
  });

  // On forms, remember which field the user was on, so "what goes here?"
  // works. Inline fields are named like "comments-2-0-body"; the model field
  // is the last part.
  const adminForm = root.dataset.page === "form" ? document.querySelector("#content-main form") : null;
  if (adminForm) {
    adminForm.addEventListener("focusin", (event) => {
      let input = event.target;
      // Searchable dropdowns (Select2) take focus on their own element; the
      // field is the original <select> just before it.
      const select2 = input.closest && input.closest(".select2-container");
      if (select2 && select2.previousElementSibling) input = select2.previousElementSibling;
      if (!input.name || input.type === "hidden") return;
      currentField = input.name.replace(/^.+-\d+-/, "");
      const label = input.id && document.querySelector(`label[for="${CSS.escape(input.id)}"]`);
      const labelText = label ? label.textContent.replace(/:\s*$/, "").trim() : currentField;
      fieldNote.textContent = `About the field: ${labelText}`;
      fieldNote.hidden = false;
    });
  }

  function csrfToken() {
    const input = document.querySelector("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function addMessage(kind, text) {
    const item = document.createElement("p");
    item.className = `rh-assistant-msg rh-assistant-${kind}`;
    item.textContent = text;
    log.appendChild(item);
    log.scrollTop = log.scrollHeight;
    return item;
  }

  async function ask(question) {
    if (suggestions) suggestions.hidden = true;
    addMessage("question", question);
    const pending = addMessage("pending", "Thinking…");
    submit.disabled = true;
    textarea.value = "";

    try {
      const response = await fetch(root.dataset.endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify({
          page: root.dataset.page,
          model: root.dataset.model,
          object_id: root.dataset.objectId,
          field: currentField,
          question: question,
          history: history.slice(-HISTORY_TURNS),
        }),
      });
      let data = {};
      try {
        data = await response.json();
      } catch (_) {
        // Non-JSON response, e.g. a proxy error page.
      }
      pending.remove();
      if (response.ok && data.answer) {
        addMessage("answer", data.answer);
        history.push({ question: question, answer: data.answer });
      } else {
        addMessage("error", data.error || "The assistant is unavailable right now.");
      }
    } catch (_) {
      pending.remove();
      addMessage("error", "Couldn't reach the server. Check your connection and try again.");
    } finally {
      submit.disabled = false;
      textarea.focus();
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = textarea.value.trim();
    if (question.length >= 3 && !submit.disabled) ask(question);
  });

  // Enter sends; Shift+Enter starts a new line.
  textarea.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  if (suggestions) {
    suggestions.addEventListener("click", (event) => {
      const chip = event.target.closest("button[data-question]");
      if (chip && !submit.disabled) ask(chip.dataset.question);
    });
  }
})();
