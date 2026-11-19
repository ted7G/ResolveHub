// Form help widget for the admin change form. Sends the question, the form
// being edited and the field last focused; renders the answer as plain text.
(function () {
  "use strict";

  const root = document.getElementById("rh-assistant");
  if (!root) return;

  const toggle = root.querySelector(".rh-assistant-toggle");
  const panel = root.querySelector(".rh-assistant-panel");
  const closeButton = root.querySelector(".rh-assistant-close");
  const form = root.querySelector(".rh-assistant-form");
  const textarea = form.querySelector("textarea");
  const submit = form.querySelector("button[type=submit]");
  const fieldNote = root.querySelector(".rh-assistant-field");
  const log = root.querySelector(".rh-assistant-log");
  let currentField = "";

  function setOpen(open) {
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    if (open) textarea.focus();
  }

  toggle.addEventListener("click", () => setOpen(panel.hidden));
  closeButton.addEventListener("click", () => setOpen(false));

  // Remember which admin field the user was on, so "what goes here?" works.
  // Inline fields are named like "comments-2-0-body"; the model field is the last part.
  const adminForm = document.querySelector("#content-main form");
  if (adminForm) {
    adminForm.addEventListener("focusin", (event) => {
      const input = event.target;
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

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = textarea.value.trim();
    if (question.length < 3) return;

    addMessage("question", question);
    const pending = addMessage("pending", "Thinking...");
    submit.disabled = true;
    textarea.value = "";

    try {
      const response = await fetch(root.dataset.endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify({
          model: root.dataset.model,
          object_id: root.dataset.objectId,
          field: currentField,
          question: question,
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
  });
})();
